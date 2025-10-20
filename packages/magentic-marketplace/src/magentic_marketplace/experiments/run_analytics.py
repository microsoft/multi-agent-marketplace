#!/usr/bin/env python3
"""Analyze marketplace simulation data to compute utility metrics using typed models."""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from magentic_marketplace.experiments.models import (
    AnalyticsResults,
    BusinessSummary,
    CustomerSummary,
    TransactionSummary,
)
from magentic_marketplace.marketplace.actions import (
    ActionAdapter,
    Search,
    SearchResponse,
    SendMessage,
)
from magentic_marketplace.marketplace.actions.messaging import (
    Message,
    OrderProposal,
    Payment,
)
from magentic_marketplace.marketplace.database.queries.logs import llm_call
from magentic_marketplace.marketplace.llm.base import LLMCallLog
from magentic_marketplace.marketplace.shared.models import (
    BusinessAgentProfile,
    CustomerAgentProfile,
    MarketplaceAgentProfileAdapter,
)
from magentic_marketplace.platform.database import (
    connect_to_postgresql_database,
)
from magentic_marketplace.platform.database.base import BaseDatabaseController
from magentic_marketplace.platform.database.models import ActionRow, LogRow
from magentic_marketplace.platform.database.sqlite.sqlite import (
    SQLiteDatabaseController,
)
from magentic_marketplace.platform.shared.models import (
    ActionExecutionRequest,
    ActionExecutionResult,
)

from .models.analytics import (
    InvalidBusiness,
    InvalidCustomer,
    InvalidMenuItem,
    InvalidMenuItemPrice,
    InvalidTotalPrice,
    OrderProposalError,
)

# Terminal colors for output formatting
RED_COLOR = "\033[91m" if sys.stdout.isatty() else ""
YELLOW_COLOR = "\033[93m" if sys.stdout.isatty() else ""
GREEN_COLOR = "\033[92m" if sys.stdout.isatty() else ""
CYAN_COLOR = "\033[96m" if sys.stdout.isatty() else ""
BLUE_COLOR = "\033[94m" if sys.stdout.isatty() else ""
MAGENTA_COLOR = "\033[95m" if sys.stdout.isatty() else ""
RESET_COLOR = "\033[0m" if sys.stdout.isatty() else ""


def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


class MarketplaceAnalytics:
    """Advanced analytics engine for marketplace simulation data using typed models."""

    def __init__(
        self, db_controller: BaseDatabaseController, fuzzy_match_distance: int = 0
    ):
        """Initialize analytics with database controller."""
        self.db = db_controller
        self.fuzzy_match_distance = fuzzy_match_distance
        self.customer_agents: dict[str, CustomerAgentProfile] = {}
        self.business_agents: dict[str, BusinessAgentProfile] = {}

        # Typed action and message tracking
        self.action_stats: Counter[str] = Counter()
        self.message_stats: Counter[str] = Counter()
        self.customer_messages: dict[str, list[Message]] = defaultdict(list)
        self.business_messages: dict[str, list[Message]] = defaultdict(list)

        # Order and payment tracking
        self.order_proposals: list[OrderProposal] = []
        self.payments: list[Payment] = []
        self.customer_orders: dict[str, list[OrderProposal]] = defaultdict(list)
        self.customer_payments: dict[str, list[Payment]] = defaultdict(list)
        self.purchased_proposal_ids: set[str] = set()

        # Search tracking
        self.customer_searches: dict[str, list[tuple[Search, SearchResponse]]] = (
            defaultdict(list)
        )

        # Track all llm logs keyed by agent
        self.agent_llm_logs: dict[str, list[tuple[LogRow, LLMCallLog]]] = defaultdict(
            list
        )

        # Track all failed LLM calls
        self.failed_llm_logs: list[tuple[LogRow, LLMCallLog, str]] = []

        # Track LLM providers and models
        self.llm_providers: set[str] = set()
        self.llm_models: set[str] = set()

        # Track invalid purchased proposals with error details
        self.invalid_proposals: dict[str, list[OrderProposalError]] = defaultdict(list)

        # Track fuzzy matching for purchased proposals
        # proposal_id -> (distance, proposed item, matched item on menu)
        self.purchased_proposal_fuzzy_matches: dict[
            str, list[tuple[int, str, str]]
        ] = {}

    async def load_data(self):
        """Load and parse agents data from database."""
        agents = await self.db.agents.get_all()

        for agent_row in agents:
            agent_data = agent_row.data
            agent = MarketplaceAgentProfileAdapter.validate_python(
                agent_data.model_dump()
            )

            if isinstance(agent, CustomerAgentProfile):
                self.customer_agents[agent.id] = agent
            elif isinstance(agent, BusinessAgentProfile):  # pyright: ignore[reportUnnecessaryIsInstance] # Makes code more readable
                self.business_agents[agent.id] = agent
            else:
                raise TypeError(f"Unrecognized agent type: {agent}")

        await self.load_llm_logs()

    async def load_llm_logs(self):
        """Load all LLM call logs from database and cache them organized by agent."""
        query = llm_call.all()
        logs = await self.db.logs.find(query)

        for log_row in logs:
            log = log_row.data
            try:
                llm_call_log = LLMCallLog.model_validate(log.data)
                agent_id = (log.metadata or {}).get("agent_id", "unknown")

                self.agent_llm_logs[agent_id].append((log_row, llm_call_log))

                # Also track failures separately for quick access
                if not llm_call_log.success:
                    self.failed_llm_logs.append((log_row, llm_call_log, agent_id))

                # Track models and providers
                if llm_call_log.provider:
                    self.llm_providers.add(llm_call_log.provider)
                if llm_call_log.model:
                    self.llm_models.add(llm_call_log.model)
            except Exception as e:
                print(f"Warning: Could not parse LLM call log: {e}")

    async def analyze_actions(self):
        """Analyze all actions using typed models."""
        actions = await self.db.actions.get_all()

        for action_row in actions:
            await self._process_action_row(action_row)

    async def _process_action_row(self, action_row: ActionRow):
        """Process a single action row with proper typing."""
        action_request: ActionExecutionRequest = action_row.data.request
        action_result: ActionExecutionResult = action_row.data.result
        agent_id = action_row.data.agent_id

        # Count action types
        action_name = action_request.name
        self.action_stats[action_name] += 1

        # Parse agent type
        agent_type = self._get_agent_type(agent_id)

        action = ActionAdapter.validate_python(action_request.parameters)

        # Process based on action type
        if isinstance(action, SendMessage):
            await self._process_send_message(action, action_result, agent_type)

        if isinstance(action, Search):
            if not action_result.is_error:
                search_response = SearchResponse.model_validate(action_result.content)
                self.customer_searches[agent_id].append((action, search_response))

        # Note: FetchMessages and Search are only counted, not processed for message content

    def _get_agent_type(self, agent_id: str) -> str:
        """Determine if agent is customer or business."""
        if agent_id in self.customer_agents:
            return "customer"
        elif agent_id in self.business_agents:
            return "business"
        return "unknown"

    async def _process_send_message(
        self,
        action: SendMessage,
        result: ActionExecutionResult,
        agent_type: str,
    ):
        """Process SendMessage actions and parse message content."""
        if result.is_error:
            return

        try:
            message = action.message
            # Count message types
            self.message_stats[message.type] += 1

            # Store messages by agent type
            if agent_type == "customer":
                self.customer_messages[action.from_agent_id].append(message)
            elif agent_type == "business":
                self.business_messages[action.from_agent_id].append(message)

            # Process specific message types
            if isinstance(message, OrderProposal):
                self.order_proposals.append(message)
                errors = self.check_proposal_errors(
                    message, action.from_agent_id, action.to_agent_id
                )
                if errors:
                    self.invalid_proposals[message.id] = errors

                # Link to customer if this came from a business
                if agent_type == "business":
                    if action.to_agent_id in self.customer_agents:
                        self.customer_orders[action.to_agent_id].append(message)
                    else:
                        print("WARNING: order proposal to non-existing customer")

            elif isinstance(message, Payment):
                self.payments.append(message)
                self.purchased_proposal_ids.add(message.proposal_message_id)
                # Link to customer if this is a payment from customer
                if agent_type == "customer":
                    self.customer_payments[action.from_agent_id].append(message)

        except Exception as e:
            print(f"Warning: Failed to parse message: {e}")

    def calculate_menu_matches(self, customer_agent_id: str) -> list[tuple[str, float]]:
        """Calculate which businesses can fulfill customer's menu requirements."""
        if customer_agent_id not in self.customer_agents:
            return []

        customer_agent = self.customer_agents[customer_agent_id]
        customer = customer_agent.customer
        requested_items = customer.menu_features
        matches: list[tuple[str, float]] = []

        for business_agent_id, business_agent in self.business_agents.items():
            business = business_agent.business

            total_price = 0.0
            can_fulfill = True

            for item_name in requested_items:
                if item_name in business.menu_features:
                    total_price += business.menu_features[item_name]
                else:
                    can_fulfill = False
                    break

            if can_fulfill:
                matches.append((business_agent_id, round(total_price, 2)))

        matches.sort(key=lambda x: x[1])
        return matches

    def check_amenity_match(
        self, customer_agent_id: str, business_agent_id: str
    ) -> bool:
        """Check if business provides all required amenities for customer."""
        if (
            customer_agent_id not in self.customer_agents
            or business_agent_id not in self.business_agents
        ):
            return False

        customer = self.customer_agents[customer_agent_id].customer
        business = self.business_agents[business_agent_id].business

        required_amenities = set(customer.amenity_features)
        available_amenities = {
            amenity
            for amenity, available in business.amenity_features.items()
            if available
        }

        return required_amenities.issubset(available_amenities)

    def get_optimal_business_for_customer(self, customer_agent_id: str):
        """Get the business that has the optimal (menu-match + amenity match for lowest total price) for the customer, irrespective of any real proposals or not.

        Args:
            customer_agent_id: The customer's id

        Returns:
            str: The business id or None

        """
        # (business_id, total_price), sorted ascending by total_price
        menu_matches = self.calculate_menu_matches(customer_agent_id)
        for business_agent_id, _ in menu_matches:
            if self.check_amenity_match(customer_agent_id, business_agent_id):
                # Return the first because they are sorted by total_price
                # i.e. the first match is the cheapest
                return business_agent_id

        return None

    def filter_valid_proposal_items(
        self, business_agent_id: str, proposal: OrderProposal
    ):
        """Return only the proposed items that actually match real menu items (up to self.fuzzy_match_distance)."""
        business_agent = self.business_agents[business_agent_id]
        menu_items = set(business_agent.business.menu_features.keys())
        proposal_items = {item.item_name for item in proposal.items}

        # Start with exact matches
        matched_items: set[str] = proposal_items.intersection(menu_items)

        fuzzy_matches: list[tuple[int, str, str]] = []
        if self.fuzzy_match_distance > 0:
            # Remove exact matches
            menu_items.difference_update(matched_items)
            proposal_items.difference_update(matched_items)

            # Calculate all pairwise distances of remaining items
            fuzzy_distances: list[tuple[int, str, str]] = []
            for menu_item in menu_items:
                for proposal_item in proposal_items:
                    distance = levenshtein_distance(
                        menu_item.lower(), proposal_item.lower()
                    )
                    if distance <= self.fuzzy_match_distance:
                        fuzzy_distances.append(
                            (
                                distance,
                                menu_item,
                                proposal_item,
                            )
                        )

            # Greedily pick matches
            for distance, menu_item, proposal_item in sorted(fuzzy_distances):
                # Make sure these are still available
                if menu_item in menu_items and proposal_item in proposal_items:
                    # Add the menu_item to the match list (for exact match with customer requests)
                    matched_items.add(menu_item)
                    # Track fuzzy matches for reporting
                    fuzzy_matches.append((distance, proposal_item, menu_item))
                    # Remove so we don't double count
                    menu_items.remove(menu_item)
                    proposal_items.remove(proposal_item)

        return matched_items, fuzzy_matches

    def calculate_customer_utility(self, customer_agent_id: str) -> tuple[float, bool]:
        """Calculate customer utility where  match_score is only counted once if ANY payment meets the customer's needs.

        Args:
            customer_agent_id: ID of the customer

        Returns:
            Tuple of (utility, needs_met) where needs_met indicates if customer got what they wanted

        """
        if customer_agent_id not in self.customer_agents:
            return 0.0, False

        customer = self.customer_agents[customer_agent_id].customer
        payments = self.customer_payments.get(customer_agent_id, [])
        proposals_received = self.customer_orders.get(customer_agent_id, [])

        total_payments = 0.0
        needs_met = False

        for payment in payments:
            # Find the corresponding proposal
            proposal = next(
                (p for p in proposals_received if p.id == payment.proposal_message_id),
                None,
            )
            if proposal:
                # Get proposal items that are actually part of the businesses menu (up to fuzzy distance)
                business_agent_id = self._find_business_for_proposal(proposal.id)
                if business_agent_id:
                    proposal_items, proposal_item_fuzzy_matches = (
                        self.filter_valid_proposal_items(business_agent_id, proposal)
                    )

                    requested_items = set(customer.menu_features.keys())
                    price_paid = proposal.total_price
                    total_payments += price_paid

                    if requested_items.issubset(proposal_items):
                        # Record fuzzy matches
                        if proposal_item_fuzzy_matches:
                            self.purchased_proposal_fuzzy_matches[proposal.id] = (
                                proposal_item_fuzzy_matches
                            )

                        # Items match (exactly or fuzzily) - now check amenities
                        if self.check_amenity_match(
                            customer_agent_id, business_agent_id
                        ):
                            # Items AND amenities match - needs are met!
                            needs_met = True

        # Calculate utility: match_score counted only ONCE if needs were met
        match_score = 0.0
        if needs_met:
            match_score = 2 * sum(customer.menu_features.values())

        utility = match_score - total_payments
        return round(utility, 2), needs_met

    def _find_business_for_proposal(self, proposal_id: str) -> str | None:
        """Find which business sent a specific proposal."""
        for business_agent_id, messages in self.business_messages.items():
            for msg in messages:
                if isinstance(msg, OrderProposal) and msg.id == proposal_id:
                    return business_agent_id
        return None

    def check_proposal_errors(
        self, proposal: OrderProposal, business_agent_id: str, customer_agent_id: str
    ) -> list[OrderProposalError]:
        """Check if proposal items and prices are valid against business menu."""
        errors: list[OrderProposalError] = []
        business_agent = self.business_agents.get(business_agent_id, None)
        customer_agent = self.customer_agents.get(customer_agent_id, None)
        if not business_agent:
            errors.append(
                InvalidBusiness(
                    proposal_id=proposal.id,
                    business_agent_id=business_agent_id,
                    customer_agent_id=customer_agent_id,
                )
            )

        if not customer_agent:
            errors.append(
                InvalidCustomer(
                    proposal_id=proposal.id,
                    business_agent_id=business_agent_id,
                    customer_agent_id=customer_agent_id,
                )
            )
        if business_agent:
            business_menu = business_agent.business.menu_features
            proposed_total = 0
            for item in proposal.items:
                proposed_total += item.unit_price * item.quantity
                if item.item_name not in business_menu:
                    # Find closest menu item to calculate distance and track the pair
                    item_distances = [
                        (
                            levenshtein_distance(
                                item.item_name.lower(), menu_item.lower()
                            ),
                            menu_item,
                        )
                        for menu_item in business_menu.keys()
                    ]
                    closest_distance, closest_menu_item = sorted(item_distances)[0]
                    errors.append(
                        InvalidMenuItem(
                            proposal_id=proposal.id,
                            business_agent_id=business_agent_id,
                            customer_agent_id=customer_agent_id,
                            proposed_menu_item=item.item_name,
                            closest_menu_item=closest_menu_item,
                            closest_menu_item_distance=closest_distance,
                        )
                    )

                elif abs(item.unit_price - business_menu[item.item_name]) >= 0.01:
                    errors.append(
                        InvalidMenuItemPrice(
                            proposal_id=proposal.id,
                            business_agent_id=business_agent_id,
                            customer_agent_id=customer_agent_id,
                            menu_item=item.item_name,
                            proposed_price=item.unit_price,
                            actual_price=business_menu[item.item_name],
                        )
                    )
            if abs(proposal.total_price - proposed_total) >= 0.01:
                errors.append(
                    InvalidTotalPrice(
                        proposal_id=proposal.id,
                        business_agent_id=business_agent_id,
                        customer_agent_id=customer_agent_id,
                        proposed_total_price=proposal.total_price,
                        calculated_total_price=proposed_total,
                    )
                )

        return errors

    def calculate_conversation_utility(
        self, customer_agent_id: str, business_agent_id: str
    ) -> float:
        """Calculate utility for a specific customer-business conversation.

        This calculates utility based on payments made by the customer to this specific
        business. Unlike total customer utility, the match score is counted for each
        payment in this conversation that meets the customer's needs.

        Args:
            customer_agent_id: ID of the customer
            business_agent_id: ID of the business

        Returns:
            Utility for this specific conversation (can be positive or negative)

        """
        if customer_agent_id not in self.customer_agents:
            return 0.0

        customer = self.customer_agents[customer_agent_id].customer
        all_payments = self.customer_payments.get(customer_agent_id, [])
        all_proposals = self.customer_orders.get(customer_agent_id, [])

        # Filter payments that went to this specific business
        total_payments_to_business = 0.0
        match_score = 0.0

        for payment in all_payments:
            # Find the corresponding proposal
            proposal = next(
                (p for p in all_proposals if p.id == payment.proposal_message_id),
                None,
            )
            if proposal:
                # Check if this proposal is from the target business
                proposal_business_id = self._find_business_for_proposal(proposal.id)
                if proposal_business_id == business_agent_id:
                    # This payment is to the target business
                    total_payments_to_business += proposal.total_price

                    # Check if this payment meets customer's needs
                    proposal_items = {item.item_name for item in proposal.items}
                    requested_items = set(customer.menu_features.keys())

                    if proposal_items == requested_items:
                        # Items match - now check amenities
                        if self.check_amenity_match(
                            customer_agent_id, business_agent_id
                        ):
                            # Items AND amenities match - add match score
                            match_score = 2 * sum(customer.menu_features.values())

        utility = match_score - total_payments_to_business
        return round(utility, 2)

    def _calculate_business_utilities(self) -> dict[str, float]:
        """Calculate utility (revenue) for each business based on payments received."""
        business_utilities: defaultdict[str, float] = defaultdict(float)

        # Go through all payments and find which businesses received them
        for customer_agent_id, payments in self.customer_payments.items():
            for payment in payments:
                # Find the corresponding proposal to get business info
                proposals_received = self.customer_orders.get(customer_agent_id, [])
                proposal = next(
                    (
                        p
                        for p in proposals_received
                        if p.id == payment.proposal_message_id
                    ),
                    None,
                )
                if proposal:
                    # Use the helper method to find the business
                    business_agent_id = self._find_business_for_proposal(proposal.id)
                    if business_agent_id:
                        business_utilities[business_agent_id] += proposal.total_price

        return dict(business_utilities)

    def collect_analytics_results(self) -> AnalyticsResults:
        """Collect all analytics results into a structured format."""
        business_utilities = self._calculate_business_utilities()

        # Calculate transaction summary
        avg_proposal_value = None
        if self.order_proposals:
            avg_proposal_value = sum(p.total_price for p in self.order_proposals) / len(
                self.order_proposals
            )

        avg_paid_order_value = None
        if self.payments:
            paid_order_values: list[float] = []
            for customer_id, payments in self.customer_payments.items():
                for payment in payments:
                    proposals_received = self.customer_orders.get(customer_id, [])
                    proposal = next(
                        (
                            p
                            for p in proposals_received
                            if p.id == payment.proposal_message_id
                        ),
                        None,
                    )
                    if proposal:
                        paid_order_values.append(proposal.total_price)

            if paid_order_values:
                avg_paid_order_value = sum(paid_order_values) / len(paid_order_values)

        transaction_summary = TransactionSummary(
            order_proposals_created=len(self.order_proposals),
            payments_made=len(self.payments),
            average_paid_order_value=avg_paid_order_value,
            average_proposal_value=avg_proposal_value,
            invalid_proposals_purchased=len(
                self.purchased_proposal_ids.intersection(self.invalid_proposals.keys())
            ),
            total_invalid_proposals=len(self.invalid_proposals),
        )

        # Collect customer summaries
        customer_summaries: list[CustomerSummary] = []
        total_utility = 0.0
        customers_who_purchased = 0
        customers_with_needs_met = 0

        for customer_agent_id in sorted(self.customer_agents.keys()):
            customer = self.customer_agents[customer_agent_id].customer
            messages_sent = len(self.customer_messages.get(customer_agent_id, []))
            orders_received = len(self.customer_orders.get(customer_agent_id, []))
            payments_made = len(self.customer_payments.get(customer_agent_id, []))
            searches_made = len(self.customer_searches.get(customer_agent_id, []))
            utility, needs_met = self.calculate_customer_utility(customer_agent_id)

            customer_summaries.append(
                CustomerSummary(
                    customer_id=customer_agent_id,
                    customer_name=customer.name,
                    messages_sent=messages_sent,
                    searches_made=searches_made,
                    proposals_received=orders_received,
                    payments_made=payments_made,
                    utility=utility,
                    needs_met=needs_met,
                )
            )

            total_utility += utility
            if payments_made > 0:
                customers_who_purchased += 1
            if needs_met:
                customers_with_needs_met += 1

        # Collect business summaries
        business_summaries: list[BusinessSummary] = []
        for business_agent_id in sorted(self.business_agents.keys()):
            business = self.business_agents[business_agent_id].business
            messages_sent = len(self.business_messages.get(business_agent_id, []))
            proposals_sent = sum(
                1
                for msg in self.business_messages.get(business_agent_id, [])
                if isinstance(msg, OrderProposal)
            )
            utility = business_utilities.get(business_agent_id, 0.0)

            business_summaries.append(
                BusinessSummary(
                    business_id=business_agent_id,
                    business_name=business.name,
                    messages_sent=messages_sent,
                    proposals_sent=proposals_sent,
                    utility=utility,
                )
            )

        # Calculate final summary metrics
        avg_utility_per_active_customer = None
        if customers_who_purchased > 0:
            avg_utility_per_active_customer = total_utility / customers_who_purchased

        completion_rate = (
            (customers_who_purchased / len(self.customer_agents)) * 100
            if self.customer_agents
            else 0
        )

        return AnalyticsResults(
            total_customers=len(self.customer_agents),
            total_businesses=len(self.business_agents),
            total_actions_executed=sum(self.action_stats.values()),
            total_messages_sent=sum(self.message_stats.values()),
            action_breakdown=dict(self.action_stats),
            message_type_breakdown=dict(self.message_stats),
            transaction_summary=transaction_summary,
            customer_summaries=customer_summaries,
            business_summaries=business_summaries,
            customers_who_made_purchases=customers_who_purchased,
            customers_with_needs_met=customers_with_needs_met,
            total_marketplace_customer_utility=total_utility,
            average_utility_per_active_customer=avg_utility_per_active_customer,
            purchase_completion_rate=completion_rate,
            llm_providers=list(self.llm_providers),
            llm_models=list(self.llm_models),
            total_llm_calls=sum(map(len, self.agent_llm_logs.values())),
            failed_llm_calls=len(self.failed_llm_logs),
        )

    async def generate_report(
        self,
        db_name: str = "unknown",
        save_to_json: bool = True,
        print_results: bool = True,
    ) -> AnalyticsResults:
        """Generate comprehensive analytics report."""
        await self.load_data()
        await self.analyze_actions()

        # Collect analytics results once
        analytics_results = self.collect_analytics_results()

        # Save to JSON if requested
        if save_to_json:
            output_path = f"analytics_results_{db_name}.json"
            with open(output_path, "w") as f:
                json.dump(analytics_results.model_dump(), f, indent=2)
            print(f"Analytics results saved to: {output_path}")

        # Print report using the collected results
        if print_results:
            self._print_report(analytics_results)

        return analytics_results

    def _print_report(self, results: AnalyticsResults):
        """Print the analytics report using collected results."""
        print(f"{CYAN_COLOR}{'=' * 60}")
        print("MARKETPLACE SIMULATION ANALYTICS REPORT")
        print(f"{'=' * 60}{RESET_COLOR}\n")

        # Basic statistics
        print(f"{BLUE_COLOR}SIMULATION OVERVIEW:{RESET_COLOR}")
        print(
            f"Found {results.total_customers} customers and {results.total_businesses} businesses"
        )
        print(f"Total actions executed: {results.total_actions_executed}")
        print(f"Total messages sent: {results.total_messages_sent}")
        print()

        # Action breakdown
        print(f"{YELLOW_COLOR}ACTION BREAKDOWN:{RESET_COLOR}")
        # Sort by count descending
        sorted_actions = sorted(
            results.action_breakdown.items(), key=lambda x: x[1], reverse=True
        )
        for action_type, count in sorted_actions:
            print(f"  {action_type}: {count}")
        print()

        # Message breakdown
        print(f"{YELLOW_COLOR}MESSAGE TYPE BREAKDOWN:{RESET_COLOR}")
        # Sort by count descending
        sorted_messages = sorted(
            results.message_type_breakdown.items(), key=lambda x: x[1], reverse=True
        )
        for message_type, count in sorted_messages:
            print(f"  {message_type}: {count}")
        print()

        # Customer summary
        print(f"{CYAN_COLOR}CUSTOMER SUMMARY:{RESET_COLOR}")
        print("=" * 40)

        for customer in results.customer_summaries:
            print(
                f"{customer.customer_name}:\t{customer.messages_sent} messages, "
                f"{customer.proposals_received} proposals, {customer.payments_made} payments,\t"
                f"utility: {customer.utility:.2f}"
            )
        print()

        # Business summary
        print(f"{CYAN_COLOR}BUSINESS SUMMARY:{RESET_COLOR}")
        print("=" * 40)
        for business in results.business_summaries:
            print(
                f"{business.business_name}:\t{business.messages_sent} messages, "
                f"{business.proposals_sent} proposals sent,\tutility: {business.utility:.2f}"
            )
        print()

        # Detailed customer analysis
        print(f"{CYAN_COLOR}DETAILED CUSTOMER ANALYSIS:{RESET_COLOR}")
        print("=" * 40)

        for customer in results.customer_summaries:
            customer_agent_id = customer.customer_id
            customer_data = self.customer_agents[customer_agent_id].customer

            # Customer header
            print(
                f"\n{YELLOW_COLOR}{customer_data.name} (ID: {customer_data.id}){RESET_COLOR}"
            )
            print(
                f"Request: {customer_data.request[:100]}{'...' if len(customer_data.request) > 100 else ''}"
            )
            print(f"Desired items: {list(customer_data.menu_features.keys())}")
            print(f"Required amenities: {customer_data.amenity_features}")

            # Business matches
            menu_matches = self.calculate_menu_matches(customer_agent_id)
            if menu_matches:
                print(
                    f"\n{len(menu_matches)} businesses can fulfill menu requirements:"
                )
                optimal_price = menu_matches[0][1]

                for i, (business_agent_id, price) in enumerate(
                    menu_matches[:3]
                ):  # Show top 3
                    business = (
                        self.business_agents[business_agent_id].business
                        if business_agent_id in self.business_agents
                        else None
                    )
                    business_name = business.name if business else "Unknown"
                    amenity_match = self.check_amenity_match(
                        customer_agent_id, business_agent_id
                    )

                    status = ""
                    if amenity_match and price == optimal_price:
                        status = " (OPTIMAL)"
                    elif amenity_match:
                        status = " (GOOD FIT)"

                    amenity_status = "Yes" if amenity_match else "No"
                    print(
                        f"  {i + 1}. {business_name} - ${price} - Amenities: {amenity_status}{status}"
                    )

            # Customer activity (from collected results)
            print(
                f"\nActivity: {customer.messages_sent} messages sent, "
                f"{customer.proposals_received} proposals received, {customer.payments_made} payments made."
            )

            # Search activity
            print("\nSearch Activity:")
            searches = self.customer_searches.get(customer_agent_id, [])
            if searches:
                unique_queries = {search.query for search, _ in searches}
                print("  Queries: ")
                for search, response in searches:
                    print(f"   - Query: '{search.query}'")
                    print(f"     Page: {search.page}")
                    print(f".    Algorithm: {search.search_algorithm}")
                    print(
                        f"     Businesses: {','.join([b.business.name for b in response.businesses])}"
                    )

                print(f"  Total searches made: {len(searches)}")
                print(f"  Unique queries tried: {len(unique_queries)}")

            # Payment and order details with welfare analysis
            payments = self.customer_payments.get(customer_agent_id, [])
            proposals_received = self.customer_orders.get(customer_agent_id, [])

            # Get optimal price for comparison
            menu_matches = self.calculate_menu_matches(customer_agent_id)
            optimal_price = menu_matches[0][1] if menu_matches else None

            if payments:
                print(f"\n{GREEN_COLOR}{len(payments)} payment(s) made:{RESET_COLOR}")
                for payment in payments:
                    # Find the corresponding proposal
                    proposal = next(
                        (
                            p
                            for p in proposals_received
                            if p.id == payment.proposal_message_id
                        ),
                        None,
                    )
                    if proposal:
                        # Find which business sent this proposal
                        business_agent_id = self._find_business_for_proposal(
                            proposal.id
                        )
                        business_name = "Unknown"
                        if (
                            business_agent_id
                            and business_agent_id in self.business_agents
                        ):
                            business_name = self.business_agents[
                                business_agent_id
                            ].business.name

                        price_paid = proposal.total_price
                        print(
                            f"  - Paid ${price_paid:.2f} to {business_name}, ", end=""
                        )

                        # Check item matching
                        proposal_items = {item.item_name for item in proposal.items}
                        requested_items = set(customer_data.menu_features.keys())

                        if proposal_items != requested_items:
                            print("which does NOT match the requested menu items.")
                            print(
                                f"    (Ordered items: {', '.join(sorted(proposal_items))})"
                            )
                        elif business_agent_id and self.check_amenity_match(
                            customer_agent_id, business_agent_id
                        ):
                            print("which matches all requested amenities, ", end="")
                            if optimal_price is not None:
                                if price_paid < optimal_price:
                                    print(
                                        f"and is BETTER than the optimal posted price by ${round(optimal_price - price_paid, 2)}."
                                    )
                                elif price_paid == optimal_price:
                                    print(
                                        f"and is the optimal price of ${optimal_price:.2f}."
                                    )
                                else:
                                    print(
                                        f"but is NOT the optimal price of ${optimal_price:.2f}."
                                    )
                            else:
                                print("")
                        else:
                            print("which does NOT match all requested amenities.")

                        # Show order details
                        print("    Order items:")
                        for item in proposal.items:
                            print(
                                f"      - {item.item_name}: ${item.unit_price:.2f} x {item.quantity}"
                            )
                    else:
                        print("  - Payment (no matching proposal found)")

            # Utility calculations
            print(
                f"\nCustomer utility: {customer.utility:.2f} (needs met: {customer.needs_met})"
            )

        # Search aggregate
        total_searches = sum([len(s) for s in self.customer_searches.values()])
        searches_per_customer = total_searches / len(self.customer_searches.keys())

        total_queries = []
        total_pages = []
        for search_queries in self.customer_searches.values():
            # Map queries to pages
            queries_to_pages: dict[str, list] = defaultdict(list)
            for search, _ in search_queries:
                queries_to_pages[search.query].append(search.page)

            total_queries.append(len(queries_to_pages.keys()))
            total_pages.append(sum([len(s) for s in queries_to_pages.values()]))

        pages_per_query = sum(total_pages) / sum(total_queries)

        # Transaction summary
        print(f"\n{GREEN_COLOR}TRANSACTION SUMMARY:{RESET_COLOR}")
        print("=" * 40)
        ts = results.transaction_summary
        print(f"Order proposals created: {ts.order_proposals_created}")
        print(f"Payments made: {ts.payments_made}")
        print(f"Average proposal value: ${ts.average_proposal_value:.2f}")
        print(f"Average paid order value: ${ts.average_paid_order_value:.2f}")
        print(f"Total invalid proposals: {ts.total_invalid_proposals}")
        print(f"Invalid proposals purchased: {ts.invalid_proposals_purchased}")

        # Aggregate error types across all invalid proposals
        errors_by_type: dict[str, list[OrderProposalError]] = defaultdict(list)
        for errors in self.invalid_proposals.values():
            for error in errors:
                errors_by_type[error.type].append(error)

        print()

        print("Error types:")
        if errors_by_type:
            # Iterate over error types, most common first
            for error_type, errors in sorted(
                errors_by_type.items(), key=lambda item: len(item[1]), reverse=True
            ):
                print(f"  - {error_type}: {len(errors)}")
                # Build a header to explain the following rows
                header = ""
                indent = " " * 6
                if error_type == "invalid_menu_item_price":
                    header = "Item | Proposed | Actual"
                elif error_type == "invalid_total_price":
                    header = "Proposed | Calculated | Delta"
                elif error_type == "invalid_business":
                    header = "Business"
                elif error_type == "invalid_customer":
                    header = "Customer"

                if header:
                    divider = "-" * len(header)
                    print(indent + header)
                    print(indent + divider)

                # Iterate over each error, with "largest" by sort_key first (e.g. largest levenshtein distance)
                for error in sorted(errors, key=lambda e: e.sort_key, reverse=True):
                    if error.type == "invalid_menu_item":
                        # json.dumps to make the character differences easier to see
                        print(f"{indent}Distance: {error.closest_menu_item_distance}")
                        print(
                            f"{indent}  Proposed: {json.dumps(error.proposed_menu_item)}"
                        )
                        print(
                            f"{indent}  Matched:  {json.dumps(error.closest_menu_item)}"
                        )
                        print()
                    elif error.type == "invalid_menu_item_price":
                        print(
                            f"      {error.menu_item} | ${error.proposed_price:.2f} | ${error.actual_price:.2f}"
                        )
                    elif error.type == "invalid_total_price":
                        print(
                            f"      ${error.proposed_total_price:.2f} | ${error.calculated_total_price:.2f} | ${abs(error.calculated_total_price - error.proposed_total_price):.2f}"
                        )
                    elif error.type == "invalid_business":
                        print(f"      {error.business_agent_id}")
                    elif error.type == "invalid_customer":
                        print(f"      {error.customer_agent_id}")
        else:
            print("  - No errors")

        # Fuzzy matched proposals summary
        print()
        print(
            f"{len(self.purchased_proposal_fuzzy_matches)} purchased proposals contained invalid menu items that fuzzy-matched an actual menu item with distance <= {self.fuzzy_match_distance}"
        )
        for proposal_id, matches in list(self.purchased_proposal_fuzzy_matches.items()):
            print(f"  Proposal: {proposal_id}")
            indent = " " * 6
            for distance, proposed_item, menu_item in matches:
                print(f"{indent}Distance: {distance}")
                print(f"{indent}  Proposed: {json.dumps(proposed_item)}")
                print(f"{indent}  Matched:  {json.dumps(menu_item)}")
                print()

        # LLM Call summary
        print(f"\n{BLUE_COLOR}LLM CALL SUMMARY:{RESET_COLOR}")
        print("=" * 40)
        print(f"LLM providers: {results.llm_providers}")
        print(f"LLM models: {results.llm_models}")
        print(f"Total LLM calls: {results.total_llm_calls}")
        print(f"Failed LLM calls: {results.failed_llm_calls}")

        # Final summary
        print(f"\n{MAGENTA_COLOR}SEARCH SUMMARY:{RESET_COLOR}")
        print("=" * 40)
        print(f"Searches per customer: {searches_per_customer:.2f}")
        print(f"Pages per query: {pages_per_query:.2f}")
        print(f"Total searches: {total_searches}")

        # Final summary
        print(f"\n{CYAN_COLOR}FINAL SUMMARY:{RESET_COLOR}")
        print("=" * 40)
        print(
            f"Customers who made purchases: {results.customers_who_made_purchases}/{results.total_customers}"
        )
        print(
            f"Customers with needs met: {results.customers_with_needs_met}/{results.total_customers}"
        )

        print(f"\nPurchase completion rate: {results.purchase_completion_rate:.1f}%")

        print(
            f"Total marketplace customer utility: {results.total_marketplace_customer_utility:.2f}"
        )

        if results.average_utility_per_active_customer is not None:
            print(
                f"Average utility per active customer: {results.average_utility_per_active_customer:.2f}"
            )


async def run_analytics(
    db_path_or_schema: str,
    db_type: str,
    save_to_json: bool = True,
    print_results: bool = True,
    fuzzy_match_distance: int = 0,
) -> AnalyticsResults:
    """Run comprehensive analytics on the database.

    Args:
        db_path_or_schema (str): Path to SQLite database file or Postgres schema name.
        db_type (str): Type of database ("sqlite" or "postgres").
        save_to_json (bool): Whether to save results to JSON file.
        print_results (bool): Whether to print results to console.
        fuzzy_match_distance (int): Max fuzzy distance to consider a requested item and a proposal item a "match".

    """
    if db_type == "sqlite":
        if not Path(db_path_or_schema).exists():
            raise FileNotFoundError(
                f"SQLite database file {db_path_or_schema} not found"
            )

        db_name = Path(db_path_or_schema).stem

        db_controller = SQLiteDatabaseController(db_path_or_schema)
        await db_controller.initialize()

        analytics = MarketplaceAnalytics(
            db_controller, fuzzy_match_distance=fuzzy_match_distance
        )
        results = await analytics.generate_report(
            db_name=db_name, save_to_json=save_to_json, print_results=print_results
        )
        return results
    elif db_type == "postgres":
        async with connect_to_postgresql_database(
            schema=db_path_or_schema,
            host="localhost",
            port=5432,
            password="postgres",
            mode="existing",
        ) as db_controller:
            analytics = MarketplaceAnalytics(
                db_controller, fuzzy_match_distance=fuzzy_match_distance
            )
            results = await analytics.generate_report(
                db_name=db_path_or_schema,
                save_to_json=save_to_json,
                print_results=print_results,
            )
            return results
    else:
        raise ValueError(
            f"Unsupported database type: {db_type}. Must be 'sqlite' or 'postgres'."
        )
