"""Prompt generation for the customer agent."""

from datetime import datetime

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
        now = datetime.now()
        current_date = now.strftime("%B %d, %Y")
        current_time = now.strftime("%I:%M%p").lower()

        return f"""Current Date: {current_date}
Current Time: {current_time}

You are an autonomous agent working for customer {self.customer.name}.
They have the following request: {self.customer.request}

Customer preferences:
- Interested menu items: {", ".join(f"{item} (${price})" for item, price in self.customer.menu_features.items())}
- Required amenities: {", ".join(self.customer.amenity_features)}

IMPORTANT: You must fulfill their request using only the available actions.

Available Actions:
- search_businesses: Find businesses matching criteria (use when you need to find businesses)
- send_messages: Contact businesses with text messages (use to ask questions or express interest)
- check_messages: Check for responses from businesses (use to get proposals and replies)
- end_transaction: Complete after successfully paying for a proposal

Shopping Strategy:
1. Search for relevant businesses if you haven't found any yet
2. Send inquiry messages to promising businesses
3. Check for responses and proposals
4. Pay for the best proposal that meets requirements
5. End transaction after successful payment

You MUST complete the purchase by paying for a proposal. Do not wait for the customer - you ARE acting for them.
"""

    def format_state_context(self) -> str:
        """Format the current state context for the agent.

        Returns:
            Formatted state context

        """
        # Format available proposals with IDs
        pending_proposals = self.proposal_storage.get_pending_proposals()
        proposals_text = ""
        if pending_proposals:
            proposals_text = "\nAvailable Proposals to Accept:\n"
            for proposal in pending_proposals:
                proposals_text += f"  - Proposal ID: {proposal.proposal_id} from {proposal.business_id} (${proposal.proposal.total_price})\n"

        return f"""
Known Businesses: {len(self.known_business_ids)} businesses found
Received Proposals: {len(self.proposal_storage.proposals)} proposals
Completed Transactions: {len(self.completed_transactions)} transactions{proposals_text}

Recent conversation history:
{self.history_storage.format_conversation_text()}
"""

    def format_step_prompt(self) -> str:
        """Format the step prompt for the current decision.

        Returns:
            Formatted step prompt

        """
        return """
---

What action should you take next?

Choose your action carefully based on the current state and your goal to fulfill the customer's request.
"""
