"""Response generation functionality for the business agent."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from magentic_marketplace.platform.logger import MarketplaceLogger

from ...actions import SendOrderProposal, SendTextMessage
from ...shared.models import Business
from ..history_storage import HistoryStorage
from ..proposal_storage import OrderProposalStorage
from .models import BusinessAction
from .prompts import PromptsHandler


class ResponseHandler:
    """Handles LLM-powered response generation for the business agent."""

    def __init__(
        self,
        business: Business,
        agent_id: str,
        customer_histories: dict[str, HistoryStorage],
        proposal_storage: OrderProposalStorage,
        logger: MarketplaceLogger,
        generate_struct_fn: Callable[[str, type], Awaitable[tuple[Any, Any]]],
    ):
        """Initialize the response handler.

        Args:
            business: Business data
            agent_id: Business agent ID
            customer_histories: Per-customer history storage instances
            proposal_storage: Proposal storage instance
            logger: Logger instance
            generate_struct_fn: Function to generate structured responses with LLM

        """
        self.business = business
        self.agent_id = agent_id
        self.customer_histories = customer_histories
        self.proposal_storage = proposal_storage
        self.logger = logger
        self.generate_struct_fn = generate_struct_fn
        self.prompts = PromptsHandler(business, customer_histories, logger)

    async def generate_response_to_inquiry(
        self, customer_id: str, customer_message: str, context: str = ""
    ) -> SendOrderProposal | SendTextMessage:
        """Generate a contextual response using LLM.

        Args:
            customer_id: ID of the customer
            customer_message: The customer's message
            context: Additional context for the prompt

        Returns:
            Response message (text or order proposal) to be sent by caller

        """
        self.logger.info(
            f"Generating response to customer {customer_id} inquiry.",
            data={"customer_message": customer_message},
        )

        # Get prompt from prompts handler
        prompt = self.prompts.format_response_prompt(
            customer_id, customer_message, context
        )

        try:
            action, _ = await self.generate_struct_fn(prompt, BusinessAction)

            # Type assertion for proper type checking
            assert isinstance(action, BusinessAction)

            # Extract the response based on action type
            if action.action_type == "text":
                if action.message:
                    response = SendTextMessage(
                        created_at=datetime.now(UTC),
                        from_agent_id=self.agent_id,
                        to_agent_id=customer_id,
                        content=action.message,
                    )
                    self.logger.info(
                        f"Generated text response to customer {customer_id} inquiry",
                        data=response,
                    )
                    return response
                else:
                    raise ValueError("Text action must have string content")

            elif action.action_type == "order_proposal":
                if not action.order_proposal:
                    raise ValueError(
                        "Order proposal action must have OrderProposal content"
                    )

                # Generate deterministic proposal ID before returning
                proposal = action.order_proposal
                current_count = self.proposal_storage.customer_proposal_counts.get(
                    customer_id, 0
                )
                proposal_count = current_count + 1
                deterministic_id = f"{self.agent_id}_{customer_id}_{proposal_count}"

                # Create new proposal with deterministic ID
                proposal_with_id = SendOrderProposal(
                    created_at=datetime.now(UTC),
                    from_agent_id=self.agent_id,
                    to_agent_id=customer_id,
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
            return SendTextMessage(
                created_at=datetime.now(UTC),
                from_agent_id=self.agent_id,
                to_agent_id=customer_id,
                content="I'm sorry, I'm having trouble processing your request right now. Please try again.",
            )

    def generate_payment_confirmation(
        self, *, customer_id: str, proposal_id: str, total_price: float
    ) -> SendTextMessage:
        """Generate a payment confirmation message.

        Args:
            customer_id: The paying customer's id
            proposal_id: ID of the confirmed proposal
            total_price: Total price of the order

        Returns:
            Confirmation message

        """
        return SendTextMessage(
            created_at=datetime.now(UTC),
            from_agent_id=self.agent_id,
            to_agent_id=customer_id,
            content=f"Payment received! Your order for ${total_price} is confirmed. "
            f"Order ID: {proposal_id}. Thank you for your business!",
        )

    def generate_proposal_not_found_error(
        self, *, customer_id: str, proposal_id: str
    ) -> SendTextMessage:
        """Generate an error message for proposal not found.

        Args:
            customer_id: The customer attempting to pay for a proposal.
            proposal_id: ID of the proposal that wasn't found

        Returns:
            Error message

        """
        return SendTextMessage(
            created_at=datetime.now(UTC),
            from_agent_id=self.agent_id,
            to_agent_id=customer_id,
            content=f"Sorry, I couldn't find proposal {proposal_id}. "
            "Please check the proposal ID or request a new quote.",
        )
