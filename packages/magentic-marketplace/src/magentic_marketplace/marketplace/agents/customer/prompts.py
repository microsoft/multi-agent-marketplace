"""Prompt generation for the customer agent."""

from typing import cast

from magentic_marketplace.platform.logger import MarketplaceLogger
from magentic_marketplace.platform.shared.models import ActionExecutionResult

from ...actions.actions import FetchMessagesResponse, SearchResponse
from ...shared.models import Customer
from ..proposal_storage import OrderProposalStorage
from .models import (
    CustomerAction,
    CustomerActionResult,
    CustomerSendMessageResults,
)


class PromptsHandler:
    """Handles prompt generation for the customer agent."""

    def __init__(
        self,
        customer: Customer,
        proposal_storage: OrderProposalStorage,
        completed_transactions: list[str],
        event_history: list[tuple[CustomerAction, CustomerActionResult] | str],
        logger: MarketplaceLogger,
    ):
        """Initialize the prompts handler.

        Args:
            customer: Customer object with preferences and request
            known_business_ids: List of known business IDs
            proposal_storage: Proposal storage instance
            completed_transactions: List of completed transaction IDs
            event_history: Event history for conversation formatting
            logger: Logger instance

        """
        self.customer = customer
        self.proposal_storage = proposal_storage
        self.completed_transactions = completed_transactions
        self.event_history = event_history
        self.logger = logger

    def format_system_prompt(self) -> str:
        """Format the system prompt for customer agent decision making.

        Returns:
            Formatted system prompt

        """
        # Get current date and time
        # now = datetime.now()
        # current_date = now.strftime("%B %d, %Y")
        # current_time = now.strftime("%I:%M%p").lower()

        return f"""
You are an autonomous agent working for customer {self.customer.name} ({self.customer.id}). They have the following request: {self.customer.request}

Your agent ID is: "{self.customer.id}" and your name is "agent-{self.customer.name} ({self.customer.id})".

IMPORTANT: You do NOT have access to the customer directly. You must fulfill their request using only the tools available to you.

# Available Tools (these are your ONLY available actions)
- search_businesses(search_query, search_page): Find businesses matching criteria
- send_messages: Contact businesses (text for questions, pay to accept proposals)
- check_messages(): Get responses from businesses
- end_transaction: Complete after paying for a proposal

# Shopping Strategy
1. **Understand** - Carefully analyze the customer's specific requirements (what to buy, quantities, preferences, constraints)
2. **Search** - Find businesses matching those exact needs
3. **Inquire** - Contact ALL promising businesses with "text" messages for details
4. **Wait for Proposals** - Services will send "order_proposal" messages with specific offers
5. **Compare** - Compare all proposals for price/quality
6. **Pay** - Send "pay" messages to accept the best proposal that meets requirements within budget
7. **Confirm** - End transaction ONLY after successfully paying for a proposal

# Important Notes:
- Services create proposals, you pay to accept them
- Use "text" messages to inquire, "pay" messages to accept proposals
- You CANNOT create orders anymore - only accept proposals by paying
- Must complete the purchase by paying for a proposal. Do not wait for the customer - you ARE acting for them.

""".strip()

    def format_state_context(self) -> tuple[str, int]:
        """Format the current state context for the agent.

        Returns:
            Formatted state context and integer step counter

        """
        # Format available proposals with IDs
        #         pending_proposals = self.proposal_storage.get_pending_proposals()
        #         proposals_text = ""
        #         if pending_proposals:
        #             proposals_text = "\nAvailable Proposals to Accept:\n"
        #             for proposal in pending_proposals:
        #                 proposals_text += f"  - Proposal ID: {proposal.proposal_id} from {proposal.business_id} (${proposal.proposal.total_price})\n"

        #         return f"""
        # Known Businesses: {len(self.known_business_ids)} businesses found
        # Received Proposals: {len(self.proposal_storage.proposals)} proposals
        # Completed Transactions: {len(self.completed_transactions)} transactions{proposals_text}
        conversation, step_counter = self.format_event_history()
        return (
            f"""

# Action Trajectory

{conversation}
""",
            step_counter,
        )

    def format_step_prompt(self, last_step: int) -> str:
        """Format the step prompt for the current decision.

        Returns:
            Formatted step prompt

        """
        return f"""

Step {last_step + 1}: What action should you take?

Send "text" messages to ask questions or express interest. Services will send "order_proposal" messages with offers. Send "pay" messages to accept proposals you want to purchase. When you receive an order_proposal message, use its message_id as the proposal_id in your payment. Always check for responses after sending messages. You must pay for proposals when you have sufficient information - do not wait for the customer. Only end the transaction after successfully paying for a proposal.

Choose your action carefully.
"""

    def format_event_history(self):
        """Format the event history for the prompt."""
        lines: list[str] = []
        step_number = 0

        for event in self.event_history:
            step_number += 1
            if isinstance(event, tuple):
                lines.extend(
                    self._format_customer_action_event(*event, step_number=step_number)
                )
            else:
                lines.extend(self._format_log_event(event, step_number=step_number))

        return "\n".join(lines).strip(), step_number

    def _format_customer_action_event(
        self, action: CustomerAction, result: CustomerActionResult, step_number: int
    ) -> list[str]:
        if action.action_type == "search_businesses":
            return self._format_customer_search_businesses_event(
                action, result, step_number
            )
        elif action.action_type == "check_messages":
            return self._format_customer_check_messages_event(
                action, result, step_number
            )
        elif action.action_type == "send_messages":
            return self._format_customer_send_messages_event(
                action, result, step_number
            )
        else:
            self.logger.warning(f"Unrecognized action type: {action.action_type}")
            return []

    def _format_step_header(
        self, *, current_step: int, steps_in_group: int | None = None
    ):
        formatted_entries: list[str] = []
        step_header = f"agent-{self.customer.name} ({self.customer.id})"
        if steps_in_group and steps_in_group > 1:
            formatted_entries.append(
                f"=== STEPS {current_step - steps_in_group + 1}-{current_step} [{step_header}] ==="
            )
        else:
            formatted_entries.append(f"\n=== STEP {current_step} [{step_header}] ===")
        return formatted_entries

    def _format_customer_search_businesses_event(
        self, action: CustomerAction, result: CustomerActionResult, step_number: int
    ) -> list[str]:
        lines: list[str] = self._format_step_header(current_step=step_number)
        lines.append(
            f"Action: search_businesses: {action.model_dump_json(include={'search_query', 'search_page'})}"
        )

        if isinstance(result, SearchResponse):
            lines.append(
                f"Step {step_number} result: Searched {result.total_possible_results} business(es). Showing page {action.search_page} of {result.total_pages} search results."
            )
            for business in result.businesses:
                lines.append(
                    f"Found business: {business.business.name} (ID: {business.id}):\n"
                    f"  Description: {business.business.description}\n"
                    f"  Rating: {business.business.rating:.2f}\n"
                    "\n"
                )
            if not result.businesses:
                lines.append("No businesses found")
        elif isinstance(result, ActionExecutionResult):
            lines.append(f"Failed to search businesses. {result.content}")
        else:
            lines.append("Failed to search businesses.")

        return lines

    def _format_customer_check_messages_event(
        self, action: CustomerAction, result: CustomerActionResult, step_number: int
    ) -> list[str]:
        lines = self._format_step_header(current_step=step_number)
        lines.append("Action: check_messages (checking for responses)")

        if isinstance(result, FetchMessagesResponse):
            message_count = len(result.messages)
            if message_count == 0:
                lines.append(f"Step {step_number} result: 📭 No new messages")
            else:
                formatted_results: list[str] = []
                # Add received messages to conversation
                for received_message in result.messages:
                    message_content = received_message.message
                    formatted_results.append(
                        f"📨 Received {message_content.type} from {received_message.from_agent_id}: "
                        f"{message_content.model_dump_json(exclude={'type', 'expiry_time'}, exclude_none=True)}"
                    )
                lines.append(f"Step {step_number} result: {formatted_results}")
        elif isinstance(result, ActionExecutionResult):
            lines.append(
                f"Step {step_number} result: Failed to fetch messages. {result.content}"
            )
        else:
            lines.append(f"Step {step_number} result: Failed to fetch messages.")

        return lines

    def _format_customer_send_messages_event(
        self, action: CustomerAction, result: CustomerActionResult, step_number: int
    ) -> list[str]:
        lines: list[str] = self._format_step_header(current_step=step_number)

        text_messages = action.messages.text_messages if action.messages else []
        pay_messages = action.messages.pay_messages if action.messages else []

        # Add message-specific details
        lines.append(
            f"Action: send_messages message_count={len(text_messages) + len(pay_messages)}"
        )

        message_results = cast(CustomerSendMessageResults, result)

        send_message_result_lines: list[str] = []

        for text_message, text_message_result in zip(
            text_messages, message_results.text_message_results, strict=True
        ):
            send_message_result_lines.append(
                f"Sent to {text_message.to_business_id}: {text_message.content}"
            )
            is_success, error_message = text_message_result
            if is_success:
                send_message_result_lines.append("✅ Message sent successfully")
            else:
                send_message_result_lines.append(f"❌ Send failed: {error_message}")

        for pay_message, pay_message_result in zip(
            pay_messages, message_results.pay_message_results, strict=True
        ):
            pay_message_str = pay_message.model_dump_json(
                exclude={"type", "to_business_id"},
                exclude_none=True,
            )
            send_message_result_lines.append(
                f"Sent to {pay_message.to_business_id}: {pay_message_str}"
            )
            is_success, error_message = pay_message_result
            if is_success:
                send_message_result_lines.append(
                    "🎉 PAYMENT COMPLETED SUCCESSFULLY! Transaction accepted by platform. The purchase has been finalized."
                )
            else:
                send_message_result_lines.append(
                    f"Message failed to send: {error_message}"
                )

        lines.append(f"Step {step_number} result: {send_message_result_lines}")

        return lines

    def _format_log_event(self, event: str, step_number: int):
        lines = self._format_step_header(current_step=step_number)
        lines.append(f"Error: {event}")
        return lines
