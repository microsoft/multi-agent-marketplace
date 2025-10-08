"""Prompt generation for the customer agent."""

from magentic_marketplace.platform.logger import MarketplaceLogger

from ...shared.models import Customer
from ..history_storage import HistoryEntry, HistoryStorage
from ..proposal_storage import OrderProposalStorage


class PromptsHandler:
    """Handles prompt generation for the customer agent."""

    def __init__(
        self,
        customer: Customer,
        known_business_ids: list[str],
        proposal_storage: OrderProposalStorage,
        completed_transactions: list[str],
        event_history: list[HistoryEntry],
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
        self.known_business_ids = known_business_ids
        self.proposal_storage = proposal_storage
        self.completed_transactions = completed_transactions
        # Create a HistoryStorage instance for formatting
        self.history_storage = HistoryStorage(logger)
        self.history_storage.event_history = event_history

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
You are an autonomous agent working for customer {self.customer.name}. They have the following request: {self.customer.request}

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
        conversation, step_counter = self.history_storage.format_conversation_text(
            step_header=f"agent-{self.customer.name} ({self.customer.id})"
        )
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
