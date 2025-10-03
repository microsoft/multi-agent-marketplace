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
from magentic_marketplace.marketplace.actions import ActionAdapter, SendMessage
from magentic_marketplace.marketplace.actions.messaging import (
    Message,
    OrderProposal,
    Payment,
)
from magentic_marketplace.marketplace.shared.models import (
    BusinessAgentProfile,
    CustomerAgentProfile,
    MarketplaceAgentProfileAdapter,
)
from magentic_marketplace.platform.database import (
    create_postgresql_database,
)
from magentic_marketplace.platform.database.base import BaseDatabaseController
from magentic_marketplace.platform.database.models import ActionRow
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
BLUE_COLOR = "\033[94m" if sys.stdout.isatty() else ""
RESET_COLOR = "\033[0m" if sys.stdout.isatty() else ""


class MarketplaceAnalytics:
    """Advanced analytics engine for marketplace simulation data using typed models."""

    def __init__(self, db_controller: BaseDatabaseController):
        """Initialize analytics with database controller."""
        self.db = db_controller
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
                # Link to customer if this came from a business
                if agent_type == "business":
                    if action.to_agent_id in self.customer_agents:
                        self.customer_orders[action.to_agent_id].append(message)
                    else:
                        print("WARNING: order proposal to non-existing customer")

            elif isinstance(message, Payment):
                self.payments.append(message)
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

    def calculate_customer_utility(self, customer_agent_id: str) -> float:
        """Calculate utility for a customer based on their payments and received proposals."""
        if customer_agent_id not in self.customer_agents:
            return 0.0

        customer = self.customer_agents[customer_agent_id].customer
        total_utility = 0.0

        # Calculate utility from payments made
        payments = self.customer_payments.get(customer_agent_id, [])
        proposals_received = self.customer_orders.get(customer_agent_id, [])

        for payment in payments:
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

                # Find which business sent this proposal to check amenities
                business_agent_id = self._find_business_for_proposal(proposal.id)

                if proposal_items != requested_items:
                    # Does NOT match requested menu items - negative utility
                    total_utility -= price_paid
                elif business_agent_id and self.check_amenity_match(
                    customer_agent_id, business_agent_id
                ):
                    # Matches menu items AND amenities - positive utility
                    item_values_sum = sum(customer.menu_features.values())
                    utility = 2 * item_values_sum - price_paid
                    total_utility += utility
                else:
                    # Matches menu items but does NOT match amenities - negative utility
                    total_utility -= price_paid
            else:
                print(
                    f"WARNING: Payment found for customer {customer_agent_id} without matching proposal so ignoring. Here is the payment: {payment}"
                )

        return round(total_utility, 2)

    def _find_business_for_proposal(self, proposal_id: str) -> str | None:
        """Find which business sent a specific proposal."""
        for business_agent_id, messages in self.business_messages.items():
            for msg in messages:
                if isinstance(msg, OrderProposal) and msg.id == proposal_id:
                    return business_agent_id
        return None

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
            average_proposal_value=avg_proposal_value,
            average_paid_order_value=avg_paid_order_value,
        )

        # Collect customer summaries
        customer_summaries: list[CustomerSummary] = []
        total_utility = 0.0
        successful_customers = 0

        for customer_agent_id in sorted(self.customer_agents.keys()):
            customer = self.customer_agents[customer_agent_id].customer
            messages_sent = len(self.customer_messages.get(customer_agent_id, []))
            orders_received = len(self.customer_orders.get(customer_agent_id, []))
            payments_made = len(self.customer_payments.get(customer_agent_id, []))
            utility = self.calculate_customer_utility(customer_agent_id)

            customer_summaries.append(
                CustomerSummary(
                    customer_id=customer_agent_id,
                    customer_name=customer.name,
                    messages_sent=messages_sent,
                    proposals_received=orders_received,
                    payments_made=payments_made,
                    utility=utility,
                )
            )

            total_utility += utility
            if payments_made > 0:
                successful_customers += 1

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
        if successful_customers > 0:
            avg_utility_per_active_customer = total_utility / successful_customers

        completion_rate = (
            (successful_customers / len(self.customer_agents)) * 100
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
            customers_who_made_purchases=successful_customers,
            total_marketplace_customer_utility=total_utility,
            average_utility_per_active_customer=avg_utility_per_active_customer,
            purchase_completion_rate=completion_rate,
        )

    async def generate_report(
        self, save_to_json: bool = True, db_name: str = "unknown"
    ):
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
        self._print_report(analytics_results)

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

        # Transaction summary
        print(f"{GREEN_COLOR}TRANSACTION SUMMARY:{RESET_COLOR}")
        ts = results.transaction_summary
        print(f"Order proposals created: {ts.order_proposals_created}")
        print(f"Payments made: {ts.payments_made}")

        if ts.average_proposal_value is not None:
            print(f"Average proposal value: ${ts.average_proposal_value:.2f}")

        if ts.average_paid_order_value is not None:
            print(f"Average paid order value: ${ts.average_paid_order_value:.2f}")
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
                f"{customer.proposals_received} proposals received, {customer.payments_made} payments made"
            )

            # Utility calculation
            print(f"Customer utility: {customer.utility:.2f}")

        # Final summary
        print(f"\n{CYAN_COLOR}FINAL SUMMARY:{RESET_COLOR}")
        print("=" * 40)
        print(
            f"Customers who made purchases: {results.customers_who_made_purchases}/{results.total_customers}"
        )
        print(
            f"Total marketplace customer utility: {results.total_marketplace_customer_utility:.2f}"
        )

        if results.average_utility_per_active_customer is not None:
            print(
                f"Average utility per active customer: {results.average_utility_per_active_customer:.2f}"
            )

        print(f"Purchase completion rate: {results.purchase_completion_rate:.1f}%")


async def run_analytics(
    db_path_or_schema: str, db_type: str, save_to_json: bool = True
):
    """Run comprehensive analytics on the database.

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

        analytics = MarketplaceAnalytics(db_controller)
        await analytics.generate_report(save_to_json=save_to_json, db_name=db_name)
    elif db_type == "postgres":
        async with create_postgresql_database(
            schema=db_path_or_schema,
            host="localhost",
            port=5432,
            password="postgres",
        ) as db_controller:
            analytics = MarketplaceAnalytics(db_controller)
            await analytics.generate_report(
                save_to_json=save_to_json, db_name=db_path_or_schema
            )
    else:
        raise ValueError(
            f"Unsupported database type: {db_type}. Must be 'sqlite' or 'postgres'."
        )
