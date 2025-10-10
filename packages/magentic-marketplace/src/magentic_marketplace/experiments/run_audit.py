#!/usr/bin/env python3
"""Audit marketplace simulation to verify customers received all proposals sent to them."""

import json
import sys
from collections import defaultdict
from pathlib import Path

from magentic_marketplace.marketplace.actions import ActionAdapter, SendMessage
from magentic_marketplace.marketplace.actions.actions import (
    FetchMessages,
    FetchMessagesResponse,
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
from magentic_marketplace.platform.database.base import (
    BaseDatabaseController,
    RangeQueryParams,
)
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
RESET_COLOR = "\033[0m" if sys.stdout.isatty() else ""


class MarketplaceAudit:
    """Audit engine to verify customers received all proposals in their LLM context."""

    def __init__(self, db_controller: BaseDatabaseController):
        """Initialize audit with database controller."""
        self.db = db_controller

        # Agent profiles
        self.customer_agents: dict[str, CustomerAgentProfile] = {}
        self.business_agents: dict[str, BusinessAgentProfile] = {}

        # Order and payment tracking
        self.order_proposals: list[OrderProposal] = []
        self.payments: list[Payment] = []

        # Map proposal_id -> (business_agent_id, customer_agent_id, timestamp)
        self.proposal_metadata: dict[str, tuple[str, str, str]] = {}

        # Map customer_agent_id -> list of proposals they received
        self.customer_proposals: dict[str, list[OrderProposal]] = defaultdict(list)

        # Track payments by customer
        self.customer_payments: dict[str, list[Payment]] = defaultdict(list)

        # Track all messages for context with timestamps
        self.customer_messages: dict[str, list[tuple[str, Message, str]]] = defaultdict(
            list
        )  # customer_id -> [(to_agent_id, message, timestamp)]
        self.business_messages: dict[str, list[tuple[str, Message, str]]] = defaultdict(
            list
        )  # business_id -> [(to_agent_id, message, timestamp)]

        # Track FetchMessages actions per customer (only non-zero results)
        self.customer_fetch_actions: dict[str, list[dict]] = defaultdict(
            list
        )  # customer_id -> [fetch_action_data]

        # Track all customer actions and business messages to customers with indices
        self.customer_actions: dict[str, list[tuple[int | None, dict]]] = defaultdict(
            list
        )  # customer_id -> [(index, action_data)]
        self.business_messages_to_customers: dict[
            str, list[tuple[int | None, dict]]
        ] = defaultdict(list)  # customer_id -> [(index, message_data)]

    async def load_data(self):
        """Load and parse actions data and agent profiles from database."""
        # Load agent profiles
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

        # Load actions
        actions = await self.db.actions.get_all()

        for action_row in actions:
            await self._process_action_row(action_row)

    async def _process_action_row(self, action_row: ActionRow):
        """Process a single action row to extract proposals and payments."""
        action_request: ActionExecutionRequest = action_row.data.request
        action_result: ActionExecutionResult = action_row.data.result
        agent_id = action_row.data.agent_id
        timestamp = action_row.created_at.isoformat()
        index = action_row.index  # type: ignore[attr-defined]

        action = ActionAdapter.validate_python(action_request.parameters)

        # Track all customer actions
        if "customer" in agent_id.lower():
            action_data = {
                "index": index,
                "timestamp": timestamp,
                "agent_id": agent_id,
                "action_type": action_request.name,
                "action": action.model_dump(mode="json"),
                "result": {
                    "is_error": action_result.is_error,
                    "content": action_result.content
                    if not action_result.is_error
                    else str(action_result.content),
                },
            }
            self.customer_actions[agent_id].append((index, action_data))

        # Process SendMessage actions
        if isinstance(action, SendMessage):
            await self._process_send_message(
                action, action_result, agent_id, timestamp, index
            )
        elif isinstance(action, FetchMessages):
            await self._process_fetch_messages(
                action, action_result, agent_id, timestamp
            )

    async def _process_send_message(
        self,
        action: SendMessage,
        result: ActionExecutionResult,
        agent_id: str,
        timestamp: str,
        index: int | None,
    ):
        """Process SendMessage actions and parse message content."""
        if result.is_error:
            return

        try:
            message = action.message

            # Track all messages by sender type with timestamps
            if "customer" in agent_id.lower():
                self.customer_messages[action.from_agent_id].append(
                    (action.to_agent_id, message, timestamp)
                )
            elif "business" in agent_id.lower():
                self.business_messages[action.from_agent_id].append(
                    (action.to_agent_id, message, timestamp)
                )

                # Track business messages to customers with index
                if "customer" in action.to_agent_id.lower():
                    message_data = {
                        "index": index,
                        "timestamp": timestamp,
                        "from_agent_id": action.from_agent_id,
                        "to_agent_id": action.to_agent_id,
                        "message": message.model_dump(mode="json"),
                    }
                    self.business_messages_to_customers[action.to_agent_id].append(
                        (index, message_data)
                    )

            # Process OrderProposal messages
            if isinstance(message, OrderProposal):
                self.order_proposals.append(message)

                # Store metadata: proposal_id -> (business_id, customer_id, timestamp)
                self.proposal_metadata[message.id] = (
                    action.from_agent_id,  # business
                    action.to_agent_id,  # customer
                    timestamp,
                )

                # Track proposals received by each customer
                self.customer_proposals[action.to_agent_id].append(message)

            elif isinstance(message, Payment):
                self.payments.append(message)
                # Link to customer if this is a payment from customer
                if "customer" in agent_id.lower():
                    self.customer_payments[action.from_agent_id].append(message)

        except Exception as e:
            print(f"Warning: Failed to parse message: {e}")

    async def _process_fetch_messages(
        self,
        action: FetchMessages,
        result: ActionExecutionResult,
        agent_id: str,
        timestamp: str,
    ):
        """Process FetchMessages actions and track non-zero results."""
        if result.is_error:
            return

        try:
            # Only track for customers
            if "customer" not in agent_id.lower():
                return

            # Parse the result as FetchMessagesResponse
            if result.content:
                fetch_response = FetchMessagesResponse.model_validate(result.content)

                # Only track if there are messages
                if fetch_response.messages:
                    # Serialize the fetch action data
                    fetch_data = {
                        "timestamp": timestamp,
                        "from_agent_id_filter": action.from_agent_id,
                        "limit": action.limit,
                        "offset": action.offset,
                        "after": action.after.isoformat() if action.after else None,
                        "after_index": getattr(action, "after_index", None),
                        "num_messages_fetched": len(fetch_response.messages),
                        "messages": [
                            {
                                "from_agent_id": msg.from_agent_id,
                                "to_agent_id": msg.to_agent_id,
                                "created_at": msg.created_at.isoformat(),
                                "message": msg.message.model_dump(mode="json"),
                                "index": getattr(msg, "index", None),
                            }
                            for msg in fetch_response.messages
                        ],
                    }
                    self.customer_fetch_actions[agent_id].append(fetch_data)

        except Exception as e:
            print(f"Warning: Failed to parse FetchMessages result: {e}")

    def get_customer_messages_to_business(
        self, customer_id: str, business_id: str
    ) -> list[tuple[Message, str]]:
        """Get all messages a customer sent to a specific business with timestamps.

        Args:
            customer_id: The customer agent ID
            business_id: The business agent ID

        Returns:
            List of (message, timestamp) tuples the customer sent to the business

        """
        messages = []
        for to_agent_id, message, timestamp in self.customer_messages.get(
            customer_id, []
        ):
            if to_agent_id == business_id:
                messages.append((message, timestamp))
        return messages

    def get_payment_for_proposal(self, proposal_id: str) -> Payment | None:
        """Get the payment message for a specific proposal.

        Args:
            proposal_id: The proposal ID

        Returns:
            Payment message if found, None otherwise

        """
        for payment in self.payments:
            if payment.proposal_message_id == proposal_id:
                return payment
        return None

    async def get_last_llm_log_for_customer(
        self, customer_id: str
    ) -> tuple[LLMCallLog, str] | None:
        """Get the last LLM log for a specific customer with timestamp.

        Args:
            customer_id: The customer agent ID

        Returns:
            Tuple of (LLMCallLog, timestamp) for the most recent log, or None if not found

        """
        # Query for all LLM logs for this customer
        query = llm_call.all()
        params = RangeQueryParams()
        logs = await self.db.logs.find(query, params)

        if not logs:
            return None

        # Filter logs by customer_id and find the most recent
        customer_logs = []
        for log_row in logs:
            log = log_row.data
            agent_id = (log.metadata or {}).get("agent_id", None)

            if agent_id == customer_id:
                try:
                    llm_call_log = LLMCallLog.model_validate(log.data)
                    timestamp = log_row.created_at.isoformat()
                    customer_logs.append((log_row.index, llm_call_log, timestamp))  # type: ignore[attr-defined]
                except Exception as e:
                    print(f"Warning: Could not parse LLM call log: {e}")
                    continue

        if not customer_logs:
            return None

        # Sort by index and return the most recent (log, timestamp)
        customer_logs.sort(key=lambda x: x[0])
        return (customer_logs[-1][1], customer_logs[-1][2])

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

    def calculate_customer_utility(
        self, customer_agent_id: str
    ) -> tuple[float, bool, float | None]:
        """Calculate customer utility and whether they achieved optimal utility.

        Args:
            customer_agent_id: ID of the customer

        Returns:
            Tuple of (utility, needs_met, optimal_utility) where needs_met indicates
            if customer got what they wanted, and optimal_utility is the best possible
            utility (None if no matching businesses exist)

        """
        if customer_agent_id not in self.customer_agents:
            return 0.0, False, None

        customer = self.customer_agents[customer_agent_id].customer
        payments = self.customer_payments.get(customer_agent_id, [])
        proposals_received = self.customer_proposals.get(customer_agent_id, [])

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

        # Calculate actual utility
        total_payments = 0.0
        needs_met = False

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
                total_payments += price_paid

                # Find which business sent this proposal to check amenities
                business_agent_id = self._find_business_for_proposal(proposal.id)

                # Check if this payment meets the customer's needs
                if proposal_items == requested_items:
                    # Items match - now check amenities
                    if business_agent_id and self.check_amenity_match(
                        customer_agent_id, business_agent_id
                    ):
                        # Items AND amenities match - needs are met!
                        needs_met = True

        # Calculate utility: match_score counted only ONCE if needs were met
        match_score = 0.0
        if needs_met:
            match_score = 2 * sum(customer.menu_features.values())

        utility = round(match_score - total_payments, 2)
        return utility, needs_met, optimal_utility

    def _find_business_for_proposal(self, proposal_id: str) -> str | None:
        """Find which business sent a specific proposal."""
        # First check in proposal_metadata which is more direct
        if proposal_id in self.proposal_metadata:
            business_id, _, _ = self.proposal_metadata[proposal_id]
            return business_id

        # Fallback to searching through messages
        for business_agent_id, messages in self.business_messages.items():
            for _, msg, _ in messages:
                if isinstance(msg, OrderProposal) and msg.id == proposal_id:
                    return business_agent_id
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
        }

        print(f"{CYAN_COLOR}{'=' * 60}")
        print("MARKETPLACE PROPOSAL AUDIT")
        print(f"{'=' * 60}{RESET_COLOR}\n")

        print(f"Total proposals to audit: {results['total_proposals']}\n")

        # Check each proposal
        for proposal in self.order_proposals:
            proposal_id = proposal.id

            # Get metadata about this proposal
            if proposal_id not in self.proposal_metadata:
                print(
                    f"{YELLOW_COLOR}Warning: No metadata found for proposal {proposal_id}{RESET_COLOR}"
                )
                continue

            business_id, customer_id, proposal_timestamp = self.proposal_metadata[
                proposal_id
            ]

            # Track unique customers and businesses
            results["unique_customers"].add(customer_id)
            results["unique_businesses"].add(business_id)
            results["customer_stats"][customer_id]["received"] += 1

            # Get the last LLM log for this customer
            llm_log_result = await self.get_last_llm_log_for_customer(customer_id)

            if llm_log_result is None:
                print(
                    f"{YELLOW_COLOR}Customer {customer_id} has no LLM logs{RESET_COLOR}"
                )
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
                print(
                    f"{GREEN_COLOR}Found:{RESET_COLOR} Proposal {proposal_id} in {customer_id}'s last LLM log"
                )
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

                # Get the customer messages to this business
                customer_msgs_with_timestamps = self.get_customer_messages_to_business(
                    customer_id, business_id
                )

                # Serialize customer messages with timestamps (use mode='json' to handle datetime)
                customer_messages_serialized = [
                    {"message": msg.model_dump(mode="json"), "timestamp": ts}
                    for msg, ts in customer_msgs_with_timestamps
                ]

                # Get the payment message for this proposal
                payment_msg = self.get_payment_for_proposal(proposal_id)
                payment_serialized = (
                    payment_msg.model_dump(mode="json") if payment_msg else None
                )

                # Get all FetchMessages actions for this customer
                fetch_actions = self.customer_fetch_actions.get(customer_id, [])

                # Build combined timeline of customer actions and business messages
                timeline_items = []

                # Add customer actions
                for idx, action_data in self.customer_actions.get(customer_id, []):
                    timeline_items.append(
                        {
                            "type": "customer_action",
                            "index": idx,
                            "data": action_data,
                        }
                    )

                # Add business messages to this customer
                for idx, message_data in self.business_messages_to_customers.get(
                    customer_id, []
                ):
                    timeline_items.append(
                        {
                            "type": "business_message",
                            "index": idx,
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
                        "fetch_messages_actions": fetch_actions,
                        "customer_timeline": timeline_items,
                    }
                )
                print(
                    f"{RED_COLOR}Missing:{RESET_COLOR} Proposal {proposal_id} NOT in {customer_id}'s last LLM log (from {business_id})"
                )

        # Calculate utility statistics for all customers
        for customer_id in self.customer_agents.keys():
            payments = self.customer_payments.get(customer_id, [])

            if payments:
                results["customers_who_made_purchases"] += 1

            utility, needs_met, optimal_utility = self.calculate_customer_utility(
                customer_id
            )

            if needs_met:
                results["customers_with_needs_met"] += 1

            # Check if customer achieved suboptimal utility
            if optimal_utility is not None and payments:
                if utility < optimal_utility:
                    customer_name = self.customer_agents[customer_id].customer.name

                    # Construct customer trace path
                    customer_trace_path = (
                        f"{db_name}-agent-llm-traces/customers/{customer_id}-0.md"
                    )

                    # Find which business(es) the customer transacted with
                    proposals_received = self.customer_proposals.get(customer_id, [])
                    businesses_transacted = []
                    for payment in payments:
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
                    llm_log_result = await self.get_last_llm_log_for_customer(
                        customer_id
                    )
                    if llm_log_result is not None:
                        llm_log, _ = llm_log_result
                        # Check each proposal received to see if it's in the log
                        for proposal in proposals_received:
                            if self.check_proposal_in_log(proposal.id, llm_log):
                                proposals_in_final_log += 1

                    results["customers_with_suboptimal_utility"].append(
                        {
                            "customer_id": customer_id,
                            "customer_name": customer_name,
                            "actual_utility": utility,
                            "optimal_utility": optimal_utility,
                            "utility_gap": round(optimal_utility - utility, 2),
                            "needs_met": needs_met,
                            "businesses_transacted": businesses_transacted,
                            "proposals_received_total": len(proposals_received),
                            "proposals_in_final_llm_log": proposals_in_final_log,
                            "trace_path": customer_trace_path,
                        }
                    )

        # Sort suboptimal utility customers by utility gap (largest gap first)
        results["customers_with_suboptimal_utility"].sort(
            key=lambda x: x["utility_gap"], reverse=True
        )

        return results

    async def generate_report(
        self, save_to_json: bool = True, db_name: str = "unknown"
    ):
        """Generate comprehensive audit report."""
        await self.load_data()

        print(
            f"Loaded {len(self.order_proposals)} proposals and {len(self.payments)} payments\n"
        )

        # Run the audit
        results = await self.audit_proposals(db_name=db_name)

        # Print summary
        print(f"\n{CYAN_COLOR}{'=' * 60}")
        print("AUDIT SUMMARY")
        print(f"{'=' * 60}{RESET_COLOR}\n")

        # Overall statistics
        print(f"{CYAN_COLOR}OVERALL STATISTICS:{RESET_COLOR}")
        print(f"Total proposals sent: {results['total_proposals']}")
        print(
            f"{GREEN_COLOR}Proposals found in customer logs: {results['proposals_found']}{RESET_COLOR}"
        )
        print(
            f"{RED_COLOR}Proposals missing from customer logs: {results['proposals_missing']}{RESET_COLOR}"
        )

        if results["total_proposals"] > 0:
            success_rate = (
                results["proposals_found"] / results["total_proposals"]
            ) * 100
            print(f"Success rate: {success_rate:.1f}%")

        # Customer and business statistics
        print(f"\n{CYAN_COLOR}CUSTOMER & BUSINESS STATISTICS:{RESET_COLOR}")
        print(
            f"Unique customers who received proposals: {len(results['unique_customers'])}"
        )
        print(
            f"Unique businesses who sent proposals: {len(results['unique_businesses'])}"
        )

        if results["unique_customers"]:
            avg_proposals_per_customer = results["total_proposals"] / len(
                results["unique_customers"]
            )
            print(f"Average proposals per customer: {avg_proposals_per_customer:.1f}")

        # FetchMessages statistics
        print(f"\n{CYAN_COLOR}FETCHMESSAGES STATISTICS:{RESET_COLOR}")
        total_fetch_actions = sum(
            len(fetches) for fetches in self.customer_fetch_actions.values()
        )
        customers_with_fetches = len(self.customer_fetch_actions)
        print(
            f"Total FetchMessages actions with non-zero results: {total_fetch_actions}"
        )
        print(f"Customers who fetched messages: {customers_with_fetches}")
        if customers_with_fetches > 0:
            avg_fetches_per_customer = total_fetch_actions / customers_with_fetches
            print(
                f"Average fetches per active customer: {avg_fetches_per_customer:.1f}"
            )

        # Customer delivery status
        customers_with_all = sum(
            1
            for stats in results["customer_stats"].values()
            if stats["missing"] == 0 and stats["received"] > 0
        )
        customers_with_partial = sum(
            1
            for stats in results["customer_stats"].values()
            if 0 < stats["missing"] < stats["received"]
        )
        customers_with_none = sum(
            1
            for stats in results["customer_stats"].values()
            if stats["found"] == 0 and stats["received"] > 0
        )

        print(f"\n{CYAN_COLOR}CUSTOMER DELIVERY STATUS:{RESET_COLOR}")
        print(
            f"{GREEN_COLOR}Customers who received all proposals in LLM logs: {customers_with_all}{RESET_COLOR}"
        )
        print(
            f"{YELLOW_COLOR}Customers who received some proposals in LLM logs: {customers_with_partial}{RESET_COLOR}"
        )
        print(
            f"{RED_COLOR}Customers who received no proposals in LLM logs: {customers_with_none}{RESET_COLOR}"
        )

        # Missing reasons breakdown
        if results["missing_reasons"]:
            print(f"\n{CYAN_COLOR}MISSING PROPOSAL REASONS:{RESET_COLOR}")
            for reason, count in sorted(
                results["missing_reasons"].items(), key=lambda x: x[1], reverse=True
            ):
                print(f"  {reason}: {count}")

        print(
            f"\n{YELLOW_COLOR}Unique customers without LLM logs: {len(results['customers_without_logs'])}{RESET_COLOR}"
        )

        # Utility analysis summary
        print(f"\n{CYAN_COLOR}UTILITY ANALYSIS:{RESET_COLOR}")
        print(
            f"Customers who made purchases: {results['customers_who_made_purchases']}/{len(self.customer_agents)}"
        )
        print(
            f"Customers with needs met: {results['customers_with_needs_met']}/{results['customers_who_made_purchases'] if results['customers_who_made_purchases'] > 0 else len(self.customer_agents)}"
        )

        if results["customers_with_suboptimal_utility"]:
            print(
                f"\n{YELLOW_COLOR}Customers with less than optimal utility: {len(results['customers_with_suboptimal_utility'])}{RESET_COLOR}"
            )
            for customer_data in results["customers_with_suboptimal_utility"]:
                print(
                    f"  - {customer_data['customer_name']} (ID: {customer_data['customer_id']})"
                )
                print(
                    f"    Actual utility: {customer_data['actual_utility']:.2f}, "
                    f"Optimal utility: {customer_data['optimal_utility']:.2f}, "
                    f"Gap: {customer_data['utility_gap']:.2f}"
                )
                print(f"    Needs met: {customer_data['needs_met']}")
                print(
                    f"    Proposals in final LLM log: {customer_data.get('proposals_in_final_llm_log', 0)}/{customer_data.get('proposals_received_total', 0)}"
                )
                if customer_data.get("trace_path"):
                    print(f"    Customer trace: {customer_data['trace_path']}")
                if customer_data.get("businesses_transacted"):
                    print("    Transacted with:")
                    for biz in customer_data["businesses_transacted"]:
                        print(
                            f"      - {biz['business_name']} (ID: {biz['business_id']}) - "
                            f"Paid: ${biz['price_paid']:.2f}"
                        )
                        if biz.get("trace_path"):
                            print(f"        Business trace: {biz['trace_path']}")
        else:
            print(
                f"\n{GREEN_COLOR}All customers who made purchases achieved optimal utility!{RESET_COLOR}"
            )

        # Print details of missing proposals
        if results["missing_details"]:
            print(f"\n{RED_COLOR}MISSING PROPOSAL DETAILS:{RESET_COLOR}")
            for detail in results["missing_details"]:
                print(f"  Proposal: {detail['proposal_id']}")
                print(f"    Business: {detail['business_id']}")
                print(f"    Customer: {detail['customer_id']}")
                print(f"    Reason: {detail['reason']}")

                # Print customer messages to business
                if detail.get("customer_messages_to_business"):
                    print(
                        f"    Customer Messages to Business: {len(detail['customer_messages_to_business'])}"
                    )
                    for i, msg_data in enumerate(
                        detail["customer_messages_to_business"], 1
                    ):
                        msg = msg_data.get("message", {})
                        timestamp = msg_data.get("timestamp", "unknown")
                        msg_type = msg.get("type", "unknown")
                        print(
                            f"      Message {i} (type: {msg_type}, timestamp: {timestamp}):"
                        )
                        msg_str = json.dumps(msg, indent=8)
                        if len(msg_str) > 300:
                            print(f"        {msg_str[:300]}...")
                        else:
                            print(f"        {msg_str}")

                # Print proposal details
                if detail.get("proposal"):
                    proposal_timestamp = detail.get("proposal_timestamp", "unknown")
                    print(f"    Proposal Details (timestamp: {proposal_timestamp}):")
                    proposal_str = json.dumps(detail["proposal"], indent=6)
                    if len(proposal_str) > 500:
                        print(f"      {proposal_str[:500]}...")
                    else:
                        print(f"      {proposal_str}")

                # Print payment details
                if detail.get("payment"):
                    print("    Payment Message:")
                    payment_str = json.dumps(detail["payment"], indent=6)
                    if len(payment_str) > 300:
                        print(f"      {payment_str[:300]}...")
                    else:
                        print(f"      {payment_str}")
                else:
                    print(
                        "    Payment Message: None (customer did not pay for this proposal)"
                    )

                # Print FetchMessages actions
                if detail.get("fetch_messages_actions"):
                    fetch_actions = detail["fetch_messages_actions"]
                    print(
                        f"    FetchMessages Actions: {len(fetch_actions)} calls with non-zero results"
                    )
                    for i, fetch in enumerate(fetch_actions, 1):
                        num_msgs = fetch.get("num_messages_fetched", 0)
                        timestamp = fetch.get("timestamp", "unknown")
                        from_filter = fetch.get("from_agent_id_filter", "None")
                        print(f"      Fetch {i} (timestamp: {timestamp}):")
                        print(
                            f"        Fetched {num_msgs} messages (from_agent_id_filter: {from_filter})"
                        )
                        # Show proposal IDs in fetched messages
                        proposal_ids_in_fetch = []
                        for msg_data in fetch.get("messages", []):
                            msg = msg_data.get("message", {})
                            if msg.get("type") == "order_proposal":
                                proposal_ids_in_fetch.append(msg.get("id", "unknown"))
                        if proposal_ids_in_fetch:
                            print(
                                f"        Proposal IDs in fetch: {', '.join(proposal_ids_in_fetch)}"
                            )

                # Print customer timeline summary
                if detail.get("customer_timeline"):
                    timeline = detail["customer_timeline"]
                    print(
                        f"    Customer Timeline: {len(timeline)} events (actions + messages received)"
                    )
                    print("      (Full timeline available in JSON output)")
                    # Show first few and last few for context
                    num_to_show = min(3, len(timeline))
                    if num_to_show > 0:
                        print(f"      First {num_to_show} events:")
                        for item in timeline[:num_to_show]:
                            event_type = item.get("type")
                            event_data = item.get("data", {})
                            idx = item.get("index")
                            ts = event_data.get("timestamp", "unknown")
                            if event_type == "customer_action":
                                action_type = event_data.get("action_type", "unknown")
                                print(
                                    f"        [{idx}] {ts}: Customer action: {action_type}"
                                )
                            else:
                                from_agent = event_data.get("from_agent_id", "unknown")
                                msg_type = event_data.get("message", {}).get(
                                    "type", "unknown"
                                )
                                print(
                                    f"        [{idx}] {ts}: Received {msg_type} from {from_agent}"
                                )
                    if len(timeline) > num_to_show * 2:
                        print(
                            f"      ... ({len(timeline) - num_to_show * 2} more events)"
                        )
                        print(f"      Last {num_to_show} events:")
                        for item in timeline[-num_to_show:]:
                            event_type = item.get("type")
                            event_data = item.get("data", {})
                            idx = item.get("index")
                            ts = event_data.get("timestamp", "unknown")
                            if event_type == "customer_action":
                                action_type = event_data.get("action_type", "unknown")
                                print(
                                    f"        [{idx}] {ts}: Customer action: {action_type}"
                                )
                            else:
                                from_agent = event_data.get("from_agent_id", "unknown")
                                msg_type = event_data.get("message", {}).get(
                                    "type", "unknown"
                                )
                                print(
                                    f"        [{idx}] {ts}: Received {msg_type} from {from_agent}"
                                )

                # Print LLM prompt if available
                if detail.get("llm_prompt"):
                    llm_timestamp = detail.get("llm_timestamp", "unknown")
                    llm_model = detail.get("llm_model", "unknown")
                    llm_provider = detail.get("llm_provider", "unknown")
                    print(
                        f"    LLM Prompt (model: {llm_model}, provider: {llm_provider}, timestamp: {llm_timestamp}, truncated to 1000 chars):"
                    )

                    if isinstance(detail["llm_prompt"], str):
                        prompt_text = detail["llm_prompt"]
                    else:
                        # For message sequences, format nicely
                        prompt_text = json.dumps(detail["llm_prompt"], indent=6)

                    if len(prompt_text) > 1000:
                        print(f"      {prompt_text[:1000]}...")
                    else:
                        print(f"      {prompt_text}")

                # Print LLM response if available
                if detail.get("llm_response"):
                    print("    LLM Response (truncated to 500 chars):")
                    response_text = (
                        json.dumps(detail["llm_response"], indent=6)
                        if isinstance(detail["llm_response"], dict)
                        else str(detail["llm_response"])
                    )
                    if len(response_text) > 500:
                        print(f"      {response_text[:500]}...")
                    else:
                        print(f"      {response_text}")
                print()

        # Save to JSON if requested
        if save_to_json:
            output_path = f"audit_results_{db_name}.json"

            # Calculate FetchMessages statistics
            total_fetch_actions = sum(
                len(fetches) for fetches in self.customer_fetch_actions.values()
            )
            customers_with_fetches = len(self.customer_fetch_actions)
            avg_fetches_per_customer = (
                total_fetch_actions / customers_with_fetches
                if customers_with_fetches > 0
                else 0
            )

            # Convert sets to lists for JSON serialization
            json_results = {
                **results,
                "unique_customers": sorted(results["unique_customers"]),
                "unique_businesses": sorted(results["unique_businesses"]),
                "customers_without_logs": sorted(results["customers_without_logs"]),
                "customer_stats": dict(results["customer_stats"]),
                "missing_reasons": dict(results["missing_reasons"]),
                "customers_with_suboptimal_utility": results[
                    "customers_with_suboptimal_utility"
                ],
                "customers_with_suboptimal_utility_count": len(
                    results["customers_with_suboptimal_utility"]
                ),
                "customers_who_made_purchases": results["customers_who_made_purchases"],
                "customers_with_needs_met": results["customers_with_needs_met"],
                "fetch_messages_stats": {
                    "total_fetch_actions": total_fetch_actions,
                    "customers_with_fetches": customers_with_fetches,
                    "avg_fetches_per_customer": avg_fetches_per_customer,
                },
            }
            with open(output_path, "w") as f:
                json.dump(json_results, f, indent=2)
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
