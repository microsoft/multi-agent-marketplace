"""Response generation functionality for the business agent."""

from collections.abc import Awaitable, Callable
from typing import Any

from magentic_marketplace.platform.logger import MarketplaceLogger

from ...actions import OrderProposal, TextMessage
from ...shared.models import Business
from ..proposal_storage import OrderProposalStorage
from .models import BusinessAction
from .prompts import PromptsHandler


class ResponseHandler:
    """Handles LLM-powered response generation for the business agent."""

    def __init__(
        self,
        business: Business,
        agent_id: str,
        proposal_storage: OrderProposalStorage,
        logger: MarketplaceLogger,
        generate_struct_fn: Callable[[str, type], Awaitable[tuple[Any, Any]]],
    ):
        """Initialize the response handler.

        Args:
            business: Business data
            agent_id: Business agent ID
            proposal_storage: Proposal storage instance
            logger: Logger instance
            generate_struct_fn: Function to generate structured responses with LLM

        """
        self.business = business
        self.agent_id = agent_id
        self.proposal_storage = proposal_storage
        self.logger = logger
        self.generate_struct_fn = generate_struct_fn
        self.prompts = PromptsHandler(business, logger)

    async def generate_response_to_inquiry(
        self, customer_id: str, conversation_history: list[str]
    ) -> TextMessage | OrderProposal:
        """Generate a contextual response using LLM.

        Args:
            customer_id: ID of the customer
            conversation_history: history of convo
            context: Additional context for the prompt

        Returns:
            Response message (text or order proposal) to be sent by caller

        """
        self.logger.info(f"Generating response to customer {customer_id} inquiry.")

        # Get prompt from prompts handler
        prompt = self.prompts.format_response_prompt(conversation_history, customer_id)

        try:
            action, _ = await self.generate_struct_fn(prompt, BusinessAction)

            # Type assertion for proper type checking
            assert isinstance(action, BusinessAction)

            # Extract the response based on action type
            if action.action_type == "text":
                if action.text_message:
                    response = TextMessage(content=action.text_message.content)
                    self.logger.info(
                        f"Generated text response to customer {customer_id} inquiry",
                        data=response,
                    )
                    return response
                else:
                    raise ValueError("Text action must have string content")

            elif action.action_type == "order_proposal":
                if not action.order_proposal_message:
                    raise ValueError(
                        "Order proposal action must have OrderProposal content"
                    )

                # Generate deterministic proposal ID before returning
                proposal = action.order_proposal_message
                current_count = self.proposal_storage.customer_proposal_counts.get(
                    customer_id, 0
                )
                proposal_count = current_count + 1
                deterministic_id = f"{self.agent_id}_{customer_id}_{proposal_count}"

                # Create new proposal with deterministic ID
                proposal_with_id = OrderProposal(
                    id=deterministic_id,
                    items=proposal.items,
                    total_price=proposal.total_price,
                    special_instructions=proposal.special_instructions,
                    estimated_delivery=proposal.estimated_delivery,
                    expiry_time=proposal.expiry_time,
                )

                return proposal_with_id

            else:
                raise ValueError(f"Unknown action_type: {action.action_type}")

        except Exception:
            self.logger.exception("LLM response generation failed")
            # Fallback to simple text response
            return TextMessage(
                content="I'm sorry, I'm having trouble processing your request right now. Please try again."
            )

    def generate_payment_confirmation(
        self, proposal_id: str, total_price: float
    ) -> TextMessage:
        """Generate a payment confirmation message.

        Args:
            proposal_id: ID of the confirmed proposal
            total_price: Total price of the order

        Returns:
            Confirmation message

        """
        return TextMessage(
            content=f"Payment received! Your order for ${total_price} is confirmed. "
            f"Order ID: {proposal_id}. Thank you for your business!"
        )

    def generate_proposal_not_found_error(self, proposal_id: str) -> TextMessage:
        """Generate an error message for proposal not found.

        Args:
            proposal_id: ID of the proposal that wasn't found

        Returns:
            Error message

        """
        return TextMessage(
            content=f"Sorry, I couldn't find proposal {proposal_id}. "
            "Please check the proposal ID or request a new quote."
        )
