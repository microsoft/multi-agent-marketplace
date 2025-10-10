#!/usr/bin/env python3
"""Audit marketplace simulation to verify customers received all proposals sent to them."""

import json
import sys
from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel

from magentic_marketplace.marketplace.actions import (
    ActionAdapter,
    Search,
    SearchResponse,
    SendMessage,
)
from magentic_marketplace.marketplace.actions.actions import (
    FetchMessages,
    FetchMessagesResponse,
)
from magentic_marketplace.marketplace.actions.messaging import (
    OrderProposal,
    Payment,
    TextMessage,
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
from magentic_marketplace.platform.database.base import (
    BaseDatabaseController,
    RangeQueryParams,
)
from magentic_marketplace.platform.database.models import ActionRow, LogRow
from magentic_marketplace.platform.database.sqlite.sqlite import (
    SQLiteDatabaseController,
)
from magentic_marketplace.platform.shared.models import (
    ActionExecutionRequest,
    ActionExecutionResult,
)

# Terminal colors for output formatting
RED_COLOR = "\033[91m" if sys.stdout.isatty() else ""
YELLOW_COLOR = "\033[93m" if sys.stdout.isatty() else ""
GREEN_COLOR = "\033[92m" if sys.stdout.isatty() else ""
CYAN_COLOR = "\033[96m" if sys.stdout.isatty() else ""
RESET_COLOR = "\033[0m" if sys.stdout.isatty() else ""


class CustomerUtility(BaseModel):
    """Utility metrics for a customer."""

    customer_id: str
    actual_utility: float
    optimal_utility: float | None
    utility_gap: float
    needs_met: bool
    paid_businesses: dict[
        str, tuple[ActionRow, Payment]
    ] = {}  # business_id -> (action_row, payment)


class CustomerAudit(BaseModel):
    """Complete audit data for a customer."""

    customer: CustomerAgentProfile
    utility: CustomerUtility
    timeline: list[ActionRow | LogRow]  # All actions and logs combined
    timeline_length: int
    llm_calls: list[LogRow]  # LLM call logs
    llm_calls_length: int
    logs: list[LogRow]  # All logs
    logs_length: int
    sent_actions: list[ActionRow]
    received_actions: list[ActionRow]
    all_actions: list[ActionRow]
    proposals_received: list[ActionRow]
    proposals_received_length: int
    payments_made: list[ActionRow]
    payments_made_length: int
    searches_made: list[ActionRow]
    searches_made_length: int


class BusinessAudit(BaseModel):
    """Complete audit data for a business."""

    business: BusinessAgentProfile
    timeline: list[ActionRow | LogRow]  # All actions and logs combined
    timeline_length: int
    llm_calls: list[LogRow]
    llm_calls_length: int
    logs: list[LogRow]
    logs_length: int
    sent_actions: list[ActionRow]
    received_actions: list[ActionRow]
    all_actions: list[ActionRow]


class AuditResult(BaseModel):
    """Top-level audit results."""

    customers: dict[str, CustomerAudit]
    customers_length: int
    businesses: dict[str, BusinessAudit]
    businesses_length: int
    suboptimal_customers: dict[str, CustomerUtility]
    suboptimal_customers_length: int
    optimal_customers: dict[str, CustomerUtility]
    optimal_customers_length: int
    superoptimal_customers: dict[str, CustomerUtility]
    superoptimal_customers_length: int
    actual_customer_utility: float
    optimal_customer_utility: float
    customer_utility_gap: float

    # Utility gap breakdown by proposal visibility
    utility_gap_needs_not_met_had_all_proposals: float
    count_needs_not_met_had_all_proposals: int
    utility_gap_needs_not_met_missing_proposals: float
    count_needs_not_met_missing_proposals: int
    utility_gap_needs_met_had_all_proposals: float
    count_needs_met_had_all_proposals: int
    utility_gap_needs_met_missing_proposals: float
    count_needs_met_missing_proposals: int

    customers_made_no_payment: list[str]  # customer_ids
    customers_made_no_payment_length: int
    customers_with_no_optimal_business: list[
        str
    ]  # customer_ids where no business can optimally serve them
    customers_with_no_optimal_business_length: int
    customers_missing_optimal_proposal_in_llm: list[
        str
    ]  # customer_ids where optimal business exists but proposal not in final LLM log (either not sent or not in log)
    customers_missing_optimal_proposal_in_llm_length: int
    businesses_received_no_messages: list[str]  # business_ids
    businesses_received_no_messages_length: int
    businesses_sent_no_proposals: list[str]  # business_ids
    businesses_sent_no_proposals_length: int
    failed_llm_calls: list[
        tuple[LogRow, LLMCallLog, str]
    ]  # [(log_row, llm_call_log, agent_id)]
    failed_llm_calls_length: int


class MarketplaceAudit:
    """Audit engine to verify customers received all proposals in their LLM context."""

    def __init__(self, db_controller: BaseDatabaseController):
        """Initialize audit with database controller."""
        self.db = db_controller

        # Agent profiles
        self.customer_agents: dict[str, CustomerAgentProfile] = {}
        self.business_agents: dict[str, BusinessAgentProfile] = {}

        # Order and payment tracking - store ActionRow for full context
        self.order_proposals: dict[
            str, tuple[ActionRow, SendMessage, OrderProposal]
        ] = {}  # proposal_id -> (action_row, send_message, order_proposal)
        self.payments: list[tuple[ActionRow, SendMessage, Payment]] = []

        # Track customer utility metrics
        self.customer_utility: dict[
            str, CustomerUtility
        ] = {}  # customer_id -> utility metrics

        # Track all customer and business actions - store ActionRow for full context
        self.customer_actions: dict[str, list[ActionRow]] = defaultdict(
            list
        )  # customer_id -> [action_rows]
        self.business_actions: dict[str, list[ActionRow]] = defaultdict(
            list
        )  # business_id -> [action_rows]

        # Track messages sent by customers (by type)
        self.customer_sent_text_messages: dict[
            str, list[tuple[ActionRow, SendMessage, TextMessage]]
        ] = defaultdict(
            list
        )  # customer_id -> [(action_row, send_message, text_message)]
        self.customer_sent_payments: dict[
            str, list[tuple[ActionRow, SendMessage, Payment]]
        ] = defaultdict(list)  # customer_id -> [(action_row, send_message, payment)]

        # Track messages received by customers (by type)
        self.customer_received_text_messages: dict[
            str, list[tuple[ActionRow, SendMessage, TextMessage]]
        ] = defaultdict(
            list
        )  # customer_id -> [(action_row, send_message, text_message)]
        self.customer_received_order_proposals: dict[
            str, list[tuple[ActionRow, SendMessage, OrderProposal]]
        ] = defaultdict(
            list
        )  # customer_id -> [(action_row, send_message, order_proposal)]

        # Track messages sent by businesses (by type)
        self.business_sent_text_messages: dict[
            str, list[tuple[ActionRow, SendMessage, TextMessage]]
        ] = defaultdict(
            list
        )  # business_id -> [(action_row, send_message, text_message)]
        self.business_sent_order_proposals: dict[
            str, list[tuple[ActionRow, SendMessage, OrderProposal]]
        ] = defaultdict(
            list
        )  # business_id -> [(action_row, send_message, order_proposal)]

        # Track messages received by businesses (by type)
        self.business_received_text_messages: dict[
            str, list[tuple[ActionRow, SendMessage, TextMessage]]
        ] = defaultdict(
            list
        )  # business_id -> [(action_row, send_message, text_message)]
        self.business_received_payments: dict[
            str, list[tuple[ActionRow, SendMessage, Payment]]
        ] = defaultdict(list)  # business_id -> [(action_row, send_message, payment)]

        # Track FetchMessages actions per customer and business (only non-zero results)
        self.customer_fetch_actions: dict[
            str, list[tuple[ActionRow, FetchMessages, FetchMessagesResponse]]
        ] = defaultdict(
            list
        )  # customer_id -> [(action_row, fetch_action, fetch_response)]
        self.business_fetch_actions: dict[
            str, list[tuple[ActionRow, FetchMessages, FetchMessagesResponse]]
        ] = defaultdict(
            list
        )  # business_id -> [(action_row, fetch_action, fetch_response)]

        # Track Search actions per customer and business
        self.customer_searches: dict[
            str, list[tuple[ActionRow, Search, SearchResponse]]
        ] = defaultdict(
            list
        )  # customer_id -> [(action_row, search_action, search_response)]
        self.business_searches: dict[
            str, list[tuple[ActionRow, Search, SearchResponse]]
        ] = defaultdict(
            list
        )  # business_id -> [(action_row, search_action, search_response)]

        # Cache all LLM logs organized by agent to avoid multiple database queries
        self.agent_llm_logs: dict[str, list[tuple[LogRow, LLMCallLog]]] = defaultdict(
            list
        )  # agent_id -> [(log_row, parsed_log)]

        # Cache failed LLM logs separately for quick access
        self.failed_llm_logs: list[
            tuple[LogRow, LLMCallLog, str]
        ] = []  # [(log_row, parsed_log, agent_id)]

    async def load_data(self):
        """Load and parse actions data and agent profiles from database."""
        # Load agent profiles
        await self._load_agents()
        # Load all LLM logs once (cached for reuse)
        await self._load_llm_logs()
        # Load actions
        await self._load_actions()

    async def _load_actions(self):
        actions = await self.db.actions.get_all()

        for action_row in actions:
            await self._process_action_row(action_row)

    async def _load_agents(self):
        agents = await self.db.agents.get_all()
        for agent_row in agents:
            agent_data = agent_row.data
            agent = MarketplaceAgentProfileAdapter.validate_python(
                agent_data.model_dump()
            )

            if isinstance(agent, CustomerAgentProfile):
                self.customer_agents[agent.id] = agent
            elif isinstance(agent, BusinessAgentProfile):
                self.business_agents[agent.id] = agent

    async def _load_llm_logs(self):
        """Load all LLM call logs from database and cache them organized by agent."""
        query = llm_call.all()
        params = RangeQueryParams()
        logs = await self.db.logs.find(query, params)

        for log_row in logs:
            log = log_row.data
            try:
                llm_call_log = LLMCallLog.model_validate(log.data)
                agent_id = (log.metadata or {}).get("agent_id", "unknown")

                self.agent_llm_logs[agent_id].append((log_row, llm_call_log))

                # Also track failures separately for quick access
                if not llm_call_log.success:
                    self.failed_llm_logs.append((log_row, llm_call_log, agent_id))
            except Exception as e:
                print(f"Warning: Could not parse LLM call log: {e}")
                continue

    async def _process_action_row(self, action_row: ActionRow):
        """Process a single action row to extract proposals and payments."""
        action_request: ActionExecutionRequest = action_row.data.request
        action_result: ActionExecutionResult = action_row.data.result
        agent_id = action_row.data.agent_id

        action = ActionAdapter.validate_python(action_request.parameters)

        # Track ALL customer and business actions
        if "customer" in agent_id.lower():
            self.customer_actions[agent_id].append(action_row)
        elif "business" in agent_id.lower():
            self.business_actions[agent_id].append(action_row)

        # Process SendMessage actions
        if isinstance(action, SendMessage):
            await self._process_send_message(
                action, action_result, agent_id, action_row
            )
        elif isinstance(action, FetchMessages):
            await self._process_fetch_messages(
                action, action_result, agent_id, action_row
            )
        elif isinstance(action, Search):
            await self._process_search(action, action_result, agent_id, action_row)

    async def _process_send_message(
        self,
        action: SendMessage,
        result: ActionExecutionResult,
        agent_id: str,
        action_row: ActionRow,
    ):
        """Process SendMessage actions and parse message content."""
        if result.is_error:
            return

        try:
            message = action.message

            # Track customer sent messages by type
            if "customer" in agent_id.lower():
                if isinstance(message, TextMessage):
                    self.customer_sent_text_messages[action.from_agent_id].append(
                        (action_row, action, message)
                    )
                elif isinstance(message, Payment):
                    self.customer_sent_payments[action.from_agent_id].append(
                        (action_row, action, message)
                    )

            # Track customer received messages by type
            if "customer" in action.to_agent_id.lower():
                if isinstance(message, TextMessage):
                    self.customer_received_text_messages[action.to_agent_id].append(
                        (action_row, action, message)
                    )
                elif isinstance(message, OrderProposal):
                    self.customer_received_order_proposals[action.to_agent_id].append(
                        (action_row, action, message)
                    )

            # Track business sent messages by type
            if "business" in agent_id.lower():
                if isinstance(message, TextMessage):
                    self.business_sent_text_messages[action.from_agent_id].append(
                        (action_row, action, message)
                    )
                elif isinstance(message, OrderProposal):
                    self.business_sent_order_proposals[action.from_agent_id].append(
                        (action_row, action, message)
                    )

            # Track business received messages by type
            if "business" in action.to_agent_id.lower():
                if isinstance(message, TextMessage):
                    self.business_received_text_messages[action.to_agent_id].append(
                        (action_row, action, message)
                    )
                elif isinstance(message, Payment):
                    self.business_received_payments[action.to_agent_id].append(
                        (action_row, action, message)
                    )

            # Process OrderProposal messages
            if isinstance(message, OrderProposal):
                # Store full context keyed by proposal_id
                self.order_proposals[message.id] = (action_row, action, message)

            elif isinstance(message, Payment):
                self.payments.append((action_row, action, message))

        except Exception as e:
            print(f"Warning: Failed to parse message: {e}")

    async def _process_fetch_messages(
        self,
        action: FetchMessages,
        result: ActionExecutionResult,
        agent_id: str,
        action_row: ActionRow,
    ):
        """Process FetchMessages actions and track non-zero results."""
        if result.is_error:
            return

        try:
            # Parse the result as FetchMessagesResponse
            if result.content:
                fetch_response = FetchMessagesResponse.model_validate(result.content)

                # Only track if there are messages
                if fetch_response.messages:
                    # Store ActionRow, action, and response
                    if "customer" in agent_id.lower():
                        self.customer_fetch_actions[agent_id].append(
                            (action_row, action, fetch_response)
                        )
                    elif "business" in agent_id.lower():
                        self.business_fetch_actions[agent_id].append(
                            (action_row, action, fetch_response)
                        )

        except Exception as e:
            print(f"Warning: Failed to parse FetchMessages result: {e}")

    async def _process_search(
        self,
        action: Search,
        result: ActionExecutionResult,
        agent_id: str,
        action_row: ActionRow,
    ):
        """Process Search actions and track results."""
        if result.is_error:
            return

        try:
            # Parse the result as SearchResponse
            if result.content:
                search_response = SearchResponse.model_validate(result.content)
                # Store ActionRow, action, and response
                if "customer" in agent_id.lower():
                    self.customer_searches[agent_id].append(
                        (action_row, action, search_response)
                    )
                elif "business" in agent_id.lower():
                    self.business_searches[agent_id].append(
                        (action_row, action, search_response)
                    )

        except Exception as e:
            print(f"Warning: Failed to parse Search result: {e}")

    def get_payment_for_proposal(self, proposal_id: str) -> Payment | None:
        """Get the payment message for a specific proposal.

        Args:
            proposal_id: The proposal ID

        Returns:
            Payment message if found, None otherwise

        """
        for _, _, payment in self.payments:
            if payment.proposal_message_id == proposal_id:
                return payment
        return None

    def get_llm_failures(self) -> list[dict]:
        """Get all failed LLM calls from cached failed logs.

        Returns:
            List of dictionaries containing failure details

        """
        failures = []
        for log_row, llm_call_log, agent_id in self.failed_llm_logs:
            # Serialize the LLM prompt
            llm_prompt = None
            if isinstance(llm_call_log.prompt, str):
                llm_prompt = llm_call_log.prompt
            else:
                llm_prompt = llm_call_log.prompt

            # Serialize the LLM response
            llm_response = None
            if isinstance(llm_call_log.response, str):
                try:
                    llm_response = json.loads(llm_call_log.response)
                except json.JSONDecodeError:
                    llm_response = llm_call_log.response
            else:
                llm_response = llm_call_log.response

            failures.append(
                {
                    "agent_id": agent_id,
                    "llm_model": llm_call_log.model
                    if llm_call_log.model
                    else "unknown",
                    "llm_provider": llm_call_log.provider
                    if llm_call_log.provider
                    else "unknown",
                    "llm_prompt": llm_prompt,
                    "llm_response": llm_response,
                    "llm_timestamp": log_row.created_at.isoformat(),
                    "error_message": llm_call_log.error_message,
                    "duration_ms": llm_call_log.duration_ms,
                }
            )

        # Sort failures by timestamp (earliest first)
        failures.sort(key=lambda x: x["llm_timestamp"])

        return failures

    def get_last_llm_log_for_customer(
        self, customer_id: str
    ) -> tuple[LLMCallLog, str] | None:
        """Get the last LLM log for a specific customer with timestamp from cached logs.

        Args:
            customer_id: The customer agent ID

        Returns:
            Tuple of (LLMCallLog, timestamp) for the most recent log, or None if not found

        """
        # Get cached logs for this customer
        customer_logs = self.agent_llm_logs.get(customer_id, [])

        if not customer_logs:
            return None

        # Build list with indices for sorting
        indexed_logs = []
        for log_row, llm_call_log in customer_logs:
            index = log_row.index  # type: ignore[attr-defined]
            timestamp = log_row.created_at.isoformat()
            indexed_logs.append((index, llm_call_log, timestamp))

        # Sort by index and return the most recent (log, timestamp)
        indexed_logs.sort(key=lambda x: x[0])
        return (indexed_logs[-1][1], indexed_logs[-1][2])

    def calculate_menu_matches(self, customer_agent_id: str) -> list[tuple[str, float]]:
        """Calculate which businesses can fulfill customer's menu requirements.

        Args:
            customer_agent_id: The customer agent ID

        Returns:
            List of (business_agent_id, total_price) tuples, sorted by price

        """
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
        """Check if business provides all required amenities for customer.

        Args:
            customer_agent_id: The customer agent ID
            business_agent_id: The business agent ID

        Returns:
            True if business provides all required amenities

        """
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

    def calculate_customer_utility(self, customer_agent_id: str) -> CustomerUtility:
        """Calculate customer utility and whether they achieved optimal utility.

        Args:
            customer_agent_id: ID of the customer

        Returns:
            CustomerUtility object with all utility metrics

        """
        if customer_agent_id not in self.customer_agents:
            return CustomerUtility(
                customer_id=customer_agent_id,
                actual_utility=0.0,
                optimal_utility=None,
                utility_gap=0.0,
                needs_met=False,
                paid_businesses={},
            )

        customer = self.customer_agents[customer_agent_id].customer
        payment_tuples = self.customer_sent_payments.get(customer_agent_id, [])
        # Extract OrderProposal objects from typed tuples
        proposals_received = [
            proposal
            for _, _, proposal in self.customer_received_order_proposals.get(
                customer_agent_id, []
            )
        ]

        # Calculate optimal utility (best case scenario)
        menu_matches = self.calculate_menu_matches(customer_agent_id)
        optimal_utility = None
        if menu_matches:
            # Find the optimal match (cheapest with amenities)
            for business_agent_id, price in menu_matches:
                if self.check_amenity_match(customer_agent_id, business_agent_id):
                    match_score = 2 * sum(customer.menu_features.values())
                    optimal_utility = round(match_score - price, 2)
                    break

        # Calculate actual utility and build paid_businesses dict
        total_payments = 0.0
        needs_met = False
        paid_businesses: dict[str, tuple[ActionRow, Payment]] = {}

        for action_row, _send_message, payment in payment_tuples:
            # Find the corresponding proposal
            proposal = next(
                (p for p in proposals_received if p.id == payment.proposal_message_id),
                None,
            )
            if proposal:
                # Check if proposal matches customer's desired items
                proposal_items = {item.item_name for item in proposal.items}
                requested_items = set(customer.menu_features.keys())
                price_paid = proposal.total_price
                total_payments += price_paid

                # Find which business sent this proposal to check amenities
                business_agent_id = self._find_business_for_proposal(proposal.id)

                if business_agent_id:
                    # Track which business was paid
                    paid_businesses[business_agent_id] = (action_row, payment)

                    # Check if this payment meets the customer's needs
                    if proposal_items == requested_items:
                        # Items match - now check amenities
                        if self.check_amenity_match(
                            customer_agent_id, business_agent_id
                        ):
                            # Items AND amenities match - needs are met!
                            needs_met = True

        # Calculate utility: match_score counted only ONCE if needs were met
        match_score = 0.0
        if needs_met:
            match_score = 2 * sum(customer.menu_features.values())

        utility = round(match_score - total_payments, 2)
        utility_gap = 0.0
        if optimal_utility is not None:
            utility_gap = round(optimal_utility - utility, 2)

        return CustomerUtility(
            customer_id=customer_agent_id,
            actual_utility=utility,
            optimal_utility=optimal_utility,
            utility_gap=utility_gap,
            needs_met=needs_met,
            paid_businesses=paid_businesses,
        )

    def _find_business_for_proposal(self, proposal_id: str) -> str | None:
        """Find which business sent a specific proposal."""
        # Direct lookup in order_proposals dict
        if proposal_id in self.order_proposals:
            _, send_message, _ = self.order_proposals[proposal_id]
            return send_message.from_agent_id
        return None

    def check_proposal_in_log(self, proposal_id: str, llm_log: LLMCallLog) -> bool:
        """Check if a proposal ID appears in the LLM log.

        Args:
            proposal_id: The proposal ID to search for
            llm_log: The LLM call log to search in

        Returns:
            True if proposal_id is found in the log, False otherwise

        """
        # Search in prompt
        if isinstance(llm_log.prompt, str):
            if proposal_id in llm_log.prompt:
                return True
        else:
            # For message sequences, search in all content
            for message in llm_log.prompt:
                content = str(message.get("content", ""))
                if proposal_id in content:
                    return True

        # Search in response
        if isinstance(llm_log.response, str):
            if proposal_id in llm_log.response:
                return True
        else:
            # For structured response, convert to JSON string and search
            response_str = json.dumps(llm_log.response)
            if proposal_id in response_str:
                return True

        return False

    async def audit_proposals(self, db_name: str = "unknown") -> dict:
        """Audit all proposals to verify they appear in customer LLM logs.

        Returns:
            Dictionary with audit results

        """
        results = {
            "total_proposals": len(self.order_proposals),
            "proposals_found": 0,
            "proposals_missing": 0,
            "customers_without_logs": set(),
            "missing_details": [],
            "customer_stats": defaultdict(
                lambda: {"received": 0, "found": 0, "missing": 0}
            ),
            "unique_customers": set(),
            "unique_businesses": set(),
            "missing_reasons": defaultdict(int),
            "customers_with_suboptimal_utility": [],
            "customers_who_made_purchases": 0,
            "customers_with_needs_met": 0,
            "llm_failures": [],
        }

        # Get LLM failures from cached logs
        llm_failures = self.get_llm_failures()
        results["llm_failures"] = llm_failures

        # Check each proposal
        for proposal_id, (
            action_row,
            send_message,
            proposal,
        ) in self.order_proposals.items():
            # Extract metadata from the stored context
            business_id = send_message.from_agent_id
            customer_id = send_message.to_agent_id
            proposal_timestamp = action_row.created_at.isoformat()

            # Track unique customers and businesses
            results["unique_customers"].add(customer_id)
            results["unique_businesses"].add(business_id)
            results["customer_stats"][customer_id]["received"] += 1

            # Get the last LLM log for this customer
            llm_log_result = self.get_last_llm_log_for_customer(customer_id)

            if llm_log_result is None:
                results["customers_without_logs"].add(customer_id)
                results["proposals_missing"] += 1
                results["customer_stats"][customer_id]["missing"] += 1
                results["missing_reasons"]["No LLM logs found"] += 1
                results["missing_details"].append(
                    {
                        "proposal_id": proposal_id,
                        "business_id": business_id,
                        "customer_id": customer_id,
                        "reason": "No LLM logs found",
                    }
                )
                continue

            # Unpack LLM log and timestamp
            llm_log, llm_timestamp = llm_log_result

            # Check if proposal appears in the log
            if self.check_proposal_in_log(proposal_id, llm_log):
                results["proposals_found"] += 1
                results["customer_stats"][customer_id]["found"] += 1
            else:
                results["proposals_missing"] += 1
                results["customer_stats"][customer_id]["missing"] += 1
                results["missing_reasons"]["Proposal ID not found in last LLM log"] += 1

                # Serialize the LLM prompt for storage
                llm_prompt = None
                if isinstance(llm_log.prompt, str):
                    llm_prompt = llm_log.prompt
                else:
                    # For message sequences, keep as list
                    llm_prompt = llm_log.prompt

                # Serialize the LLM response for storage
                llm_response = None
                if isinstance(llm_log.response, str):
                    # Try to parse as JSON if it's a JSON string
                    try:
                        llm_response = json.loads(llm_log.response)
                    except json.JSONDecodeError:
                        llm_response = llm_log.response
                else:
                    # For BaseModel or dict responses, keep as dict
                    llm_response = llm_log.response

                # Get LLM model info
                llm_model = llm_log.model if llm_log.model else "unknown"
                llm_provider = llm_log.provider if llm_log.provider else "unknown"

                # Get the customer messages to this business and serialize
                customer_messages_serialized = []
                # Include text messages sent by customer to this business
                for action_row, send_message, _ in self.customer_sent_text_messages.get(
                    customer_id, []
                ):
                    if send_message.to_agent_id == business_id:
                        customer_messages_serialized.append(
                            action_row.model_dump(mode="json")
                        )
                # Include payments sent by customer to this business
                for action_row, send_message, _ in self.customer_sent_payments.get(
                    customer_id, []
                ):
                    if send_message.to_agent_id == business_id:
                        customer_messages_serialized.append(
                            action_row.model_dump(mode="json")
                        )

                # Get the payment message for this proposal
                payment_msg = self.get_payment_for_proposal(proposal_id)
                payment_serialized = (
                    payment_msg.model_dump(mode="json") if payment_msg else None
                )

                # Get all FetchMessages actions for this customer and serialize them
                fetch_actions_serialized = []
                for action_row, _, fetch_response in self.customer_fetch_actions.get(
                    customer_id, []
                ):
                    fetch_data = action_row.model_dump(mode="json")
                    fetch_data["num_messages_fetched"] = len(fetch_response.messages)
                    fetch_actions_serialized.append(fetch_data)

                # Build combined timeline of customer actions and business messages
                timeline_items = []

                # Add customer actions - serialize from ActionRow
                for action_row in self.customer_actions.get(customer_id, []):
                    index = action_row.index  # type: ignore[attr-defined]
                    action_data = action_row.model_dump(mode="json")

                    timeline_items.append(
                        {
                            "type": "customer_action",
                            "index": index,
                            "data": action_data,
                        }
                    )

                # Add business messages to this customer - serialize from typed tuples
                # Include text messages received by customer
                for action_row, _, _ in self.customer_received_text_messages.get(
                    customer_id, []
                ):
                    index = action_row.index  # type: ignore[attr-defined]
                    message_data = action_row.model_dump(mode="json")

                    timeline_items.append(
                        {
                            "type": "business_message",
                            "index": index,
                            "data": message_data,
                        }
                    )
                # Include order proposals received by customer
                for action_row, _, _ in self.customer_received_order_proposals.get(
                    customer_id, []
                ):
                    index = action_row.index  # type: ignore[attr-defined]
                    message_data = action_row.model_dump(mode="json")

                    timeline_items.append(
                        {
                            "type": "business_message",
                            "index": index,
                            "data": message_data,
                        }
                    )

                # Sort by index
                timeline_items.sort(key=lambda x: x["index"])

                results["missing_details"].append(
                    {
                        "proposal_id": proposal_id,
                        "business_id": business_id,
                        "customer_id": customer_id,
                        "reason": "Proposal ID not found in last LLM log",
                        "llm_model": llm_model,
                        "llm_provider": llm_provider,
                        "llm_prompt": llm_prompt,
                        "llm_response": llm_response,
                        "llm_timestamp": llm_timestamp,
                        "proposal": proposal.model_dump(mode="json"),
                        "proposal_timestamp": proposal_timestamp,
                        "customer_messages_to_business": customer_messages_serialized,
                        "payment": payment_serialized,
                        "fetch_messages_actions": fetch_actions_serialized,
                        "customer_timeline": timeline_items,
                    }
                )

        # Calculate utility statistics for all customers
        theoretical_optimal_total_utility = 0.0
        actual_total_utility = 0.0
        total_suboptimal_utility = 0.0
        total_optimal_utility = 0.0
        total_superoptimal_utility = 0.0
        utility_gap_from_non_purchasers = 0.0

        for customer_id in self.customer_agents.keys():
            payments = self.customer_sent_payments.get(customer_id, [])

            if payments:
                results["customers_who_made_purchases"] += 1

            # Calculate and store CustomerUtility object
            customer_util = self.calculate_customer_utility(customer_id)
            self.customer_utility[customer_id] = customer_util

            # Track total utilities
            actual_total_utility += customer_util.actual_utility
            if customer_util.optimal_utility is not None:
                theoretical_optimal_total_utility += customer_util.optimal_utility

                # Track utility gap from customers who didn't purchase
                if not payments:
                    # No purchase means actual_utility = 0, so gap = optimal_utility - 0
                    utility_gap_from_non_purchasers += customer_util.utility_gap

                # Categorize by whether customer achieved optimal or better (only for purchasers)
                if payments:
                    if customer_util.actual_utility < customer_util.optimal_utility:
                        total_suboptimal_utility += customer_util.actual_utility
                    elif customer_util.actual_utility == customer_util.optimal_utility:
                        total_optimal_utility += customer_util.actual_utility
                    else:  # utility > optimal_utility
                        total_superoptimal_utility += customer_util.actual_utility

            if customer_util.needs_met:
                results["customers_with_needs_met"] += 1

            # Check if customer achieved suboptimal utility
            if customer_util.optimal_utility is not None and payments:
                if customer_util.actual_utility < customer_util.optimal_utility:
                    customer_name = self.customer_agents[customer_id].customer.name

                    # Construct customer trace path
                    customer_trace_path = (
                        f"{db_name}-agent-llm-traces/customers/{customer_id}-0.md"
                    )

                    # Find which business(es) the customer transacted with
                    # Extract OrderProposal objects from typed tuples
                    proposals_received = [
                        proposal
                        for _, _, proposal in self.customer_received_order_proposals.get(
                            customer_id, []
                        )
                    ]
                    businesses_transacted = []
                    for _, _send_message, payment in payments:
                        proposal = next(
                            (
                                p
                                for p in proposals_received
                                if p.id == payment.proposal_message_id
                            ),
                            None,
                        )
                        if proposal:
                            business_id = self._find_business_for_proposal(proposal.id)
                            if business_id:
                                business_name = (
                                    self.business_agents[business_id].business.name
                                    if business_id in self.business_agents
                                    else "Unknown"
                                )
                                # Construct business-customer trace path
                                business_trace_path = f"{db_name}-agent-llm-traces/businesses/{business_id}-{customer_id}-0.md"

                                businesses_transacted.append(
                                    {
                                        "business_id": business_id,
                                        "business_name": business_name,
                                        "price_paid": proposal.total_price,
                                        "trace_path": business_trace_path,
                                    }
                                )

                    # Count proposals in final LLM log
                    proposals_in_final_log = 0
                    llm_log_result = self.get_last_llm_log_for_customer(customer_id)
                    if llm_log_result is not None:
                        llm_log, _ = llm_log_result
                        # Check each proposal received to see if it's in the log
                        for proposal in proposals_received:
                            if self.check_proposal_in_log(proposal.id, llm_log):
                                proposals_in_final_log += 1

                    # For customers with needs not met, check if optimal business proposal was in LLM log
                    optimal_business_proposal_status = "needs_met"
                    if not customer_util.needs_met:
                        # Find the optimal business
                        menu_matches = self.calculate_menu_matches(customer_id)
                        optimal_business_id = None

                        for business_id, _price in menu_matches:
                            if self.check_amenity_match(customer_id, business_id):
                                optimal_business_id = business_id
                                break

                        if not optimal_business_id:
                            # No business can optimally serve this customer
                            optimal_business_proposal_status = "no_optimal_business"
                        else:
                            # Check if optimal business sent a proposal
                            optimal_proposal_id = None
                            for proposal in proposals_received:
                                proposal_business_id = self._find_business_for_proposal(
                                    proposal.id
                                )
                                if proposal_business_id == optimal_business_id:
                                    optimal_proposal_id = proposal.id
                                    break

                            if not optimal_proposal_id:
                                # Optimal business exists but didn't send a proposal
                                optimal_business_proposal_status = (
                                    "no_proposal_from_optimal_business"
                                )
                            elif llm_log_result is None:
                                # Customer has no LLM logs
                                optimal_business_proposal_status = "no_llm_logs"
                            else:
                                # Check if the proposal is in the log
                                llm_log, _ = llm_log_result
                                if self.check_proposal_in_log(
                                    optimal_proposal_id, llm_log
                                ):
                                    optimal_business_proposal_status = "proposal_in_log"
                                else:
                                    optimal_business_proposal_status = (
                                        "proposal_not_in_log"
                                    )

                    results["customers_with_suboptimal_utility"].append(
                        {
                            **customer_util.model_dump(),
                            "customer_name": customer_name,
                            "businesses_transacted": businesses_transacted,
                            "proposals_received_total": len(proposals_received),
                            "proposals_in_final_llm_log": proposals_in_final_log,
                            "trace_path": customer_trace_path,
                            "optimal_business_proposal_status": optimal_business_proposal_status,
                        }
                    )

        # Sort suboptimal utility customers by utility gap (largest gap first)
        results["customers_with_suboptimal_utility"].sort(
            key=lambda x: x["utility_gap"], reverse=True
        )

        # Count optimal business proposal status values and sum utility gaps by status
        optimal_business_proposal_status_counts = defaultdict(int)
        optimal_business_proposal_status_utility_gaps = defaultdict(float)
        for customer_data in results["customers_with_suboptimal_utility"]:
            status = customer_data.get("optimal_business_proposal_status", "unknown")
            utility_gap = customer_data.get("utility_gap", 0.0)
            optimal_business_proposal_status_counts[status] += 1
            optimal_business_proposal_status_utility_gaps[status] += utility_gap

        results["optimal_business_proposal_status_counts"] = dict(
            optimal_business_proposal_status_counts
        )
        results["optimal_business_proposal_status_utility_gaps"] = {
            k: round(v, 2)
            for k, v in optimal_business_proposal_status_utility_gaps.items()
        }

        # Find businesses that received no messages from customers
        businesses_with_no_messages = []
        for business_id, business_profile in self.business_agents.items():
            # Check if business received any text messages or payments
            has_text_messages = business_id in self.business_received_text_messages
            has_payments = business_id in self.business_received_payments
            if not has_text_messages and not has_payments:
                businesses_with_no_messages.append(
                    {
                        "business_id": business_id,
                        "business_name": business_profile.business.name,
                    }
                )

        # Sort by business ID for consistency
        businesses_with_no_messages.sort(key=lambda x: x["business_id"])
        results["businesses_with_no_messages"] = businesses_with_no_messages

        # Add utility totals
        results["theoretical_optimal_total_utility"] = round(
            theoretical_optimal_total_utility, 2
        )
        results["actual_total_utility"] = round(actual_total_utility, 2)
        results["total_utility_gap"] = round(
            theoretical_optimal_total_utility - actual_total_utility, 2
        )
        results["total_suboptimal_utility"] = round(total_suboptimal_utility, 2)
        results["total_optimal_utility"] = round(total_optimal_utility, 2)
        results["total_superoptimal_utility"] = round(total_superoptimal_utility, 2)
        results["utility_gap_from_non_purchasers"] = round(
            utility_gap_from_non_purchasers, 2
        )

        return results

    def build_audit_result(self, db_name: str) -> AuditResult:
        """Build complete AuditResult from analyzed data.

        Args:
            db_name: Name of the database being audited

        Returns:
            AuditResult with all customer and business audit data

        """
        # Build CustomerAudit objects
        customers_audit = {}
        for customer_id, customer_profile in self.customer_agents.items():
            # Get all actions for this customer
            all_actions = self.customer_actions.get(customer_id, [])

            # Get sent actions (SendMessage actions where from_agent_id matches)
            sent_actions = [
                action_row
                for action_row in all_actions
                if action_row.data.request.parameters.get("from_agent_id")
                == customer_id
            ]

            # Get received actions (combine text messages and order proposals)
            received_actions = []
            for action_row, _, _ in self.customer_received_text_messages.get(
                customer_id, []
            ):
                received_actions.append(action_row)
            for action_row, _, _ in self.customer_received_order_proposals.get(
                customer_id, []
            ):
                received_actions.append(action_row)

            # Get LLM logs for this customer
            llm_logs_with_data = self.agent_llm_logs.get(customer_id, [])
            logs = [log_row for log_row, _ in llm_logs_with_data]

            # Filter for only LLM call logs (all in agent_llm_logs are LLM calls)
            llm_calls = logs.copy()

            # Build timeline: combine all_actions + logs, sorted by index
            timeline = []
            timeline.extend(all_actions)
            timeline.extend(logs)
            timeline.sort(key=lambda x: x.index)

            # Get utility for this customer
            utility = self.customer_utility.get(customer_id)
            if not utility:
                utility = CustomerUtility(
                    customer_id=customer_id,
                    actual_utility=0.0,
                    optimal_utility=None,
                    utility_gap=0.0,
                    needs_met=False,
                    paid_businesses={},
                )

            # Get proposals received
            proposals_received = [
                action_row
                for action_row, _, _ in self.customer_received_order_proposals.get(
                    customer_id, []
                )
            ]

            # Get payments made
            payments_made = [
                action_row
                for action_row, _, _ in self.customer_sent_payments.get(customer_id, [])
            ]

            # Get searches made
            searches_made = [
                action_row
                for action_row, _, _ in self.customer_searches.get(customer_id, [])
            ]

            customers_audit[customer_id] = CustomerAudit(
                customer=customer_profile,
                utility=utility,
                timeline=timeline,
                timeline_length=len(timeline),
                llm_calls=llm_calls,
                llm_calls_length=len(llm_calls),
                logs=logs,
                logs_length=len(logs),
                sent_actions=sent_actions,
                received_actions=received_actions,
                all_actions=all_actions,
                proposals_received=proposals_received,
                proposals_received_length=len(proposals_received),
                payments_made=payments_made,
                payments_made_length=len(payments_made),
                searches_made=searches_made,
                searches_made_length=len(searches_made),
            )

        # Build BusinessAudit objects
        businesses_audit = {}
        for business_id, business_profile in self.business_agents.items():
            # Get all actions for this business
            all_actions = self.business_actions.get(business_id, [])

            # Get sent actions (SendMessage actions where from_agent_id matches)
            sent_actions = [
                action_row
                for action_row in all_actions
                if action_row.data.request.parameters.get("from_agent_id")
                == business_id
            ]

            # Get received actions (combine text messages and payments)
            received_actions = []
            for action_row, _, _ in self.business_received_text_messages.get(
                business_id, []
            ):
                received_actions.append(action_row)
            for action_row, _, _ in self.business_received_payments.get(
                business_id, []
            ):
                received_actions.append(action_row)

            # Get LLM logs for this business
            llm_logs_with_data = self.agent_llm_logs.get(business_id, [])
            logs = [log_row for log_row, _ in llm_logs_with_data]

            # Filter for only LLM call logs (all in agent_llm_logs are LLM calls)
            llm_calls = logs.copy()

            # Build timeline: combine all_actions + logs, sorted by created_at
            timeline = []
            timeline.extend(all_actions)
            timeline.extend(logs)
            timeline.sort(key=lambda x: x.created_at)

            businesses_audit[business_id] = BusinessAudit(
                business=business_profile,
                timeline=timeline,
                timeline_length=len(timeline),
                llm_calls=llm_calls,
                llm_calls_length=len(llm_calls),
                logs=logs,
                logs_length=len(logs),
                sent_actions=sent_actions,
                received_actions=received_actions,
                all_actions=all_actions,
            )

        # Categorize customers by utility
        suboptimal_customers = {}
        optimal_customers = {}
        superoptimal_customers = {}

        for customer_id, utility in self.customer_utility.items():
            if utility.optimal_utility is not None:
                if utility.actual_utility < utility.optimal_utility:
                    suboptimal_customers[customer_id] = utility
                elif utility.actual_utility == utility.optimal_utility:
                    optimal_customers[customer_id] = utility
                else:  # utility.actual_utility > utility.optimal_utility
                    superoptimal_customers[customer_id] = utility

        # Calculate total utilities
        actual_customer_utility = sum(
            u.actual_utility for u in self.customer_utility.values()
        )
        optimal_customer_utility = sum(
            u.optimal_utility
            for u in self.customer_utility.values()
            if u.optimal_utility is not None
        )
        customer_utility_gap = optimal_customer_utility - actual_customer_utility

        # Find businesses that received no messages
        businesses_received_no_messages = []
        for business_id in self.business_agents.keys():
            has_text_messages = business_id in self.business_received_text_messages
            has_payments = business_id in self.business_received_payments
            if not has_text_messages and not has_payments:
                businesses_received_no_messages.append(business_id)

        # Find businesses that sent no proposals
        businesses_sent_no_proposals = [
            business_id
            for business_id in self.business_agents.keys()
            if business_id not in self.business_sent_order_proposals
        ]

        # Find customers that made no payment
        customers_made_no_payment = [
            customer_id
            for customer_id in self.customer_agents.keys()
            if customer_id not in self.customer_sent_payments
        ]

        # Find customers with no optimal business
        customers_with_no_optimal_business = []

        # Find customers missing optimal business proposal in their final LLM log
        customers_missing_optimal_proposal_in_llm = []

        for customer_id, utility in self.customer_utility.items():
            if utility.optimal_utility is None:
                customers_with_no_optimal_business.append(customer_id)
                continue

            # Find the optimal business
            menu_matches = self.calculate_menu_matches(customer_id)
            optimal_business_id = None
            for business_id, _ in menu_matches:
                if self.check_amenity_match(customer_id, business_id):
                    optimal_business_id = business_id
                    break

            if not optimal_business_id:
                customers_with_no_optimal_business.append(customer_id)
                continue

            # Check if optimal business sent a proposal to this customer
            optimal_proposal_id = None
            for proposal_id, (_, send_msg, _) in self.order_proposals.items():
                if (
                    send_msg.from_agent_id == optimal_business_id
                    and send_msg.to_agent_id == customer_id
                ):
                    optimal_proposal_id = proposal_id
                    break

            if not optimal_proposal_id:
                # Optimal business exists but never sent a proposal - this is a problem
                customers_missing_optimal_proposal_in_llm.append(customer_id)
                continue

            # Check if the proposal is in the customer's final LLM log
            llm_log_result = self.get_last_llm_log_for_customer(customer_id)
            if llm_log_result is not None:
                llm_log, _ = llm_log_result
                if not self.check_proposal_in_log(optimal_proposal_id, llm_log):
                    customers_missing_optimal_proposal_in_llm.append(customer_id)
            else:
                # Customer has no LLM logs - can't verify
                customers_missing_optimal_proposal_in_llm.append(customer_id)

        # Calculate utility gap breakdown by proposal visibility
        utility_gap_needs_not_met_had_all_proposals = 0.0
        utility_gap_needs_not_met_missing_proposals = 0.0
        utility_gap_needs_met_had_all_proposals = 0.0
        utility_gap_needs_met_missing_proposals = 0.0

        # Track counts for each category
        count_needs_not_met_had_all_proposals = 0
        count_needs_not_met_missing_proposals = 0
        count_needs_met_had_all_proposals = 0
        count_needs_met_missing_proposals = 0

        for customer_id, utility in self.customer_utility.items():
            if utility.optimal_utility is None:
                continue

            # Find all businesses this customer contacted
            contacted_businesses = set()
            for _, send_message, _ in self.customer_sent_text_messages.get(
                customer_id, []
            ):
                if "business" in send_message.to_agent_id.lower():
                    contacted_businesses.add(send_message.to_agent_id)
            for _, send_message, _ in self.customer_sent_payments.get(customer_id, []):
                if "business" in send_message.to_agent_id.lower():
                    contacted_businesses.add(send_message.to_agent_id)

            # Check if customer had all proposals from contacted businesses in last LLM log
            had_all_proposals = True
            if contacted_businesses:
                llm_log_result = self.get_last_llm_log_for_customer(customer_id)
                if llm_log_result is not None:
                    llm_log, _ = llm_log_result
                    # For each contacted business, check if they sent a proposal and if it's in the log
                    for business_id in contacted_businesses:
                        # Check if this business sent any proposals to this customer
                        business_sent_proposals = [
                            proposal_id
                            for proposal_id, (
                                _,
                                send_msg,
                                _,
                            ) in self.order_proposals.items()
                            if send_msg.from_agent_id == business_id
                            and send_msg.to_agent_id == customer_id
                        ]
                        # If business sent proposals, check if they're all in the log
                        for proposal_id in business_sent_proposals:
                            if not self.check_proposal_in_log(proposal_id, llm_log):
                                had_all_proposals = False
                                break
                        if not had_all_proposals:
                            break
                else:
                    had_all_proposals = False

            # Categorize based on needs_met and proposal visibility
            if not utility.needs_met:
                if had_all_proposals:
                    utility_gap_needs_not_met_had_all_proposals += utility.utility_gap
                    count_needs_not_met_had_all_proposals += 1
                else:
                    utility_gap_needs_not_met_missing_proposals += utility.utility_gap
                    count_needs_not_met_missing_proposals += 1
            else:
                if had_all_proposals:
                    utility_gap_needs_met_had_all_proposals += utility.utility_gap
                    count_needs_met_had_all_proposals += 1
                else:
                    utility_gap_needs_met_missing_proposals += utility.utility_gap
                    count_needs_met_missing_proposals += 1

        return AuditResult(
            customers=customers_audit,
            customers_length=len(customers_audit),
            businesses=businesses_audit,
            businesses_length=len(businesses_audit),
            suboptimal_customers=suboptimal_customers,
            suboptimal_customers_length=len(suboptimal_customers),
            optimal_customers=optimal_customers,
            optimal_customers_length=len(optimal_customers),
            superoptimal_customers=superoptimal_customers,
            superoptimal_customers_length=len(superoptimal_customers),
            actual_customer_utility=round(actual_customer_utility, 2),
            optimal_customer_utility=round(optimal_customer_utility, 2),
            customer_utility_gap=round(customer_utility_gap, 2),
            utility_gap_needs_not_met_had_all_proposals=round(
                utility_gap_needs_not_met_had_all_proposals, 2
            ),
            count_needs_not_met_had_all_proposals=count_needs_not_met_had_all_proposals,
            utility_gap_needs_not_met_missing_proposals=round(
                utility_gap_needs_not_met_missing_proposals, 2
            ),
            count_needs_not_met_missing_proposals=count_needs_not_met_missing_proposals,
            utility_gap_needs_met_had_all_proposals=round(
                utility_gap_needs_met_had_all_proposals, 2
            ),
            count_needs_met_had_all_proposals=count_needs_met_had_all_proposals,
            utility_gap_needs_met_missing_proposals=round(
                utility_gap_needs_met_missing_proposals, 2
            ),
            count_needs_met_missing_proposals=count_needs_met_missing_proposals,
            customers_made_no_payment=customers_made_no_payment,
            customers_made_no_payment_length=len(customers_made_no_payment),
            customers_with_no_optimal_business=customers_with_no_optimal_business,
            customers_with_no_optimal_business_length=len(
                customers_with_no_optimal_business
            ),
            customers_missing_optimal_proposal_in_llm=customers_missing_optimal_proposal_in_llm,
            customers_missing_optimal_proposal_in_llm_length=len(
                customers_missing_optimal_proposal_in_llm
            ),
            businesses_received_no_messages=businesses_received_no_messages,
            businesses_received_no_messages_length=len(businesses_received_no_messages),
            businesses_sent_no_proposals=businesses_sent_no_proposals,
            businesses_sent_no_proposals_length=len(businesses_sent_no_proposals),
            failed_llm_calls=self.failed_llm_logs,
            failed_llm_calls_length=len(self.failed_llm_logs),
        )

    async def generate_report(
        self, save_to_json: bool = True, db_name: str = "unknown"
    ):
        """Generate comprehensive audit report."""
        print("Running audit...")
        await self.load_data()

        # Run the audit to populate customer_utility
        await self.audit_proposals(db_name=db_name)

        # Build the complete audit result
        audit_result = self.build_audit_result(db_name)

        # Print summary statistics
        print(f"\n{CYAN_COLOR}=== AUDIT SUMMARY ==={RESET_COLOR}")
        print(f"Total customer utility: {audit_result.actual_customer_utility:.2f}")
        print(f"Optimal customer utility: {audit_result.optimal_customer_utility:.2f}")
        print(f"Customer utility gap: {audit_result.customer_utility_gap:.2f}")
        print(
            f"Marketplace efficiency: {(audit_result.actual_customer_utility / audit_result.optimal_customer_utility * 100):.1f}%"
            if audit_result.optimal_customer_utility > 0
            else "Marketplace efficiency: N/A"
        )

        # Print utility gap breakdown
        print("\nUtility gap breakdown:")
        print(
            f"  Needs NOT met + had all proposals ({audit_result.count_needs_not_met_had_all_proposals} customers): {audit_result.utility_gap_needs_not_met_had_all_proposals:.2f}"
        )
        print(
            f"  Needs NOT met + missing proposals ({audit_result.count_needs_not_met_missing_proposals} customers): {audit_result.utility_gap_needs_not_met_missing_proposals:.2f}"
        )
        print(
            f"  Needs met + had all proposals ({audit_result.count_needs_met_had_all_proposals} customers): {audit_result.utility_gap_needs_met_had_all_proposals:.2f}"
        )
        print(
            f"  Needs met + missing proposals ({audit_result.count_needs_met_missing_proposals} customers): {audit_result.utility_gap_needs_met_missing_proposals:.2f}"
        )

        # Print warnings
        print(f"\n{YELLOW_COLOR}=== AUDIT WARNINGS ==={RESET_COLOR}")

        # Warning 1: Customers that made no payment
        if audit_result.customers_made_no_payment:
            print(
                f"{YELLOW_COLOR}  {audit_result.customers_made_no_payment_length} customers made no payment{RESET_COLOR}"
            )
        else:
            print(
                f"{GREEN_COLOR}  All customers made at least one payment{RESET_COLOR}"
            )

        # Warning 2: Customers with no optimal business
        if audit_result.customers_with_no_optimal_business:
            print(
                f"{RED_COLOR}  {audit_result.customers_with_no_optimal_business_length} customers have no business that can optimally serve them{RESET_COLOR}"
            )
        else:
            print(
                f"{GREEN_COLOR}  All customers have at least one business that can optimally serve them{RESET_COLOR}"
            )

        # Warning 3: Customers missing optimal proposal in LLM log
        if audit_result.customers_missing_optimal_proposal_in_llm:
            print(
                f"{YELLOW_COLOR}  {audit_result.customers_missing_optimal_proposal_in_llm_length} customers did not have optimal business proposal in final LLM log{RESET_COLOR}"
            )
        else:
            print(
                f"{GREEN_COLOR}  All customers had optimal proposals in their LLM logs{RESET_COLOR}"
            )

        # Warning 4: Businesses that never sent order proposals
        if audit_result.businesses_sent_no_proposals:
            print(
                f"{YELLOW_COLOR}  {audit_result.businesses_sent_no_proposals_length} businesses never sent any order proposals{RESET_COLOR}"
            )
        else:
            print(
                f"{GREEN_COLOR}  All businesses sent at least one order proposal{RESET_COLOR}"
            )

        # Warning 5: Businesses that received no messages
        if audit_result.businesses_received_no_messages:
            print(
                f"{YELLOW_COLOR}  {audit_result.businesses_received_no_messages_length} businesses received no messages from customers{RESET_COLOR}"
            )
        else:
            print(
                f"{GREEN_COLOR}  All businesses received at least one message{RESET_COLOR}"
            )

        # Warning 6: Suboptimal customers
        if audit_result.suboptimal_customers:
            total_suboptimal_gap = sum(
                u.utility_gap for u in audit_result.suboptimal_customers.values()
            )
            print(
                f"{YELLOW_COLOR}  {audit_result.suboptimal_customers_length} customers achieved suboptimal utility (total gap: {total_suboptimal_gap:.2f}){RESET_COLOR}"
            )
        else:
            print(
                f"{GREEN_COLOR}  All customers achieved optimal or better utility{RESET_COLOR}"
            )

        # Warning 7: Failed LLM calls
        if audit_result.failed_llm_calls:
            print(
                f"{RED_COLOR}  {audit_result.failed_llm_calls_length} LLM calls failed{RESET_COLOR}"
            )
        else:
            print(f"{GREEN_COLOR}  No LLM call failures{RESET_COLOR}")

        print()

        # Save to JSON if requested
        if save_to_json:
            output_path = f"audit_results_{db_name}.json"
            with open(output_path, "w") as f:
                json.dump(audit_result.model_dump(mode="json"), f, indent=2)
            print(f"Audit results saved to: {output_path}")


async def run_audit(db_path_or_schema: str, db_type: str, save_to_json: bool = True):
    """Run proposal audit on the database.

    Args:
        db_path_or_schema (str): Path to SQLite database file or Postgres schema name.
        db_type (str): Type of database ("sqlite" or "postgres").
        save_to_json (bool): Whether to save results to JSON file.

    """
    if db_type == "sqlite":
        if not Path(db_path_or_schema).exists():
            raise FileNotFoundError(
                f"SQLite database file {db_path_or_schema} not found"
            )

        db_name = Path(db_path_or_schema).stem

        db_controller = SQLiteDatabaseController(db_path_or_schema)
        await db_controller.initialize()

        audit = MarketplaceAudit(db_controller)
        await audit.generate_report(save_to_json=save_to_json, db_name=db_name)
    elif db_type == "postgres":
        async with connect_to_postgresql_database(
            schema=db_path_or_schema,
            host="localhost",
            port=5432,
            password="postgres",
            mode="existing",
        ) as db_controller:
            audit = MarketplaceAudit(db_controller)
            await audit.generate_report(
                save_to_json=save_to_json, db_name=db_path_or_schema
            )
    else:
        raise ValueError(
            f"Unsupported database type: {db_type}. Must be 'sqlite' or 'postgres'."
        )
