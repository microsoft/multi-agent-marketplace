"""Main business agent implementation."""

import asyncio
from collections import defaultdict

from magentic_marketplace.marketplace.protocol.protocol import ActionExecutionResult
from magentic_marketplace.platform.shared.models import (
    BaseAction,
)

from ...actions import (
    FetchMessages,
    FetchMessagesResponse,
    Message,
    OrderProposal,
    Payment,
    ReceivedMessage,
    SendMessage,
    TextMessage,
)
from ...llm.config import BaseLLMConfig
from ...shared.models import Business, BusinessAgentProfile
from ..base import BaseSimpleMarketplaceAgent
from ..history_storage import HistoryStorage
from ..proposal_storage import OrderProposalStorage
from .models import BusinessSummary
from .responses import ResponseHandler


class BusinessAgent(BaseSimpleMarketplaceAgent[BusinessAgentProfile]):
    """Business agent that responds to customer inquiries and creates proposals."""

    def __init__(
        self,
        business: Business,
        base_url: str,
        llm_config: BaseLLMConfig | None = None,
        polling_interval: float = 2,
    ):
        """Initialize the business agent.

        Args:
            business: Business object with menu and capabilities
            base_url: The marketplace server URL
            llm_config: LLM configuration for the agent
            polling_interval: Number of seconds to wait after fetching 0 messages.

        """
        profile = BusinessAgentProfile.from_business(business)
        super().__init__(profile, base_url, llm_config)

        # Initialize state from BaseBusinessAgent
        self.customer_histories: dict[str, HistoryStorage] = defaultdict(
            lambda: HistoryStorage(self.logger)
        )
        self.proposal_storage = OrderProposalStorage()
        self.confirmed_orders: list[str] = []
        self._polling_interval = polling_interval

        # Initialize handler resources
        self._responses = ResponseHandler(
            business=self.business,
            agent_id=self.id,
            customer_histories=self.customer_histories,
            proposal_storage=self.proposal_storage,
            logger=self.logger,
            generate_struct_fn=self.generate_struct,
        )

    @property
    def business(self) -> Business:
        """Access business data from profile with full type safety."""
        return self.profile.business

    def get_customer_history(self, customer_id: str) -> HistoryStorage:
        """Get or create HistoryStorage for a specific customer.

        Args:
            customer_id: ID of the customer

        Returns:
            HistoryStorage instance for this customer

        """
        if customer_id not in self.customer_histories:
            self.customer_histories[customer_id] = HistoryStorage(self.logger)
        return self.customer_histories[customer_id]

    async def execute_action(self, action: BaseAction):
        """Execute an action and record it in event history.

        Args:
            action: The action to execute

        Returns:
            Result of the action execution

        """
        # Execute the action through the parent class
        result = await super().execute_action(action)

        if isinstance(action, SendMessage):
            self.logger.info(
                f"Sending {action.message.type} message to customer {action.to_agent_id}"
            )
            self.customer_histories[action.to_agent_id].record_event(action, result)
        elif isinstance(action, FetchMessages):
            if result.is_error:
                # Everyone gets the error
                for customer_history in self.customer_histories.values():
                    customer_history.record_event(action, result)
            else:
                content = FetchMessagesResponse.model_validate(result.content)

                # Don't love this at all, we do this same work after returning.
                # But we need to group up all the received messages
                # and rebuild a ActionExecutionResult per customer
                new_messages_by_customer: dict[str, list[ReceivedMessage]] = (
                    defaultdict(list)
                )
                for message in content.messages:
                    new_messages_by_customer[message.from_agent_id].append(message)

                for customer_id, messages in new_messages_by_customer.items():
                    self.customer_histories[customer_id].record_event(
                        action,
                        ActionExecutionResult(
                            content=FetchMessagesResponse(
                                messages=messages, has_more=False
                            )
                        ),
                    )

        return result

    async def _handle_new_customer_messages(
        self, customer_id: str, new_messages: list[ReceivedMessage]
    ):
        messages_to_send: list[tuple[str, Message]] = []

        # First, handle all payments to update proposal statuses
        for received_message in new_messages:
            if isinstance(received_message.message, Payment):
                response = await self._handle_payment(
                    customer_id, received_message.message
                )
                messages_to_send.append((customer_id, response))

        # Find the most recent TextMessage if it exists
        last_text_message: TextMessage | None = None
        for message in new_messages:
            if isinstance(message.message, TextMessage):
                last_text_message = message.message

        # Generate a text response if there are any text messages
        if last_text_message is not None:
            response_message = await self._responses.generate_response_to_inquiry(
                customer_id, last_text_message.content
            )
            messages_to_send.append((customer_id, response_message))

        # Send all generated responses
        for customer_id, message in messages_to_send:
            # If this is a proposal, store it in proposal storage
            if isinstance(message, OrderProposal):
                self.proposal_storage.add_proposal(message, self.id, customer_id)

            # Note: Messages are now recorded as action-result pairs via send_message
            try:
                result = await self.send_message(customer_id, message)
                if result.is_error:
                    self.logger.error(
                        f"Failed to send message to {customer_id}: {result.content}"
                    )
            except Exception as e:
                self.logger.exception(f"Failed to send message to {customer_id}")
                customer_history = self.get_customer_history(customer_id)
                customer_history.record_error(
                    f"Failed to send message to {customer_id}", e
                )

    async def step(self):
        """One step of business agent logic - check for and handle customer messages."""
        # Check for new messages
        messages = await self.fetch_messages()

        # self.logger.info(
        #     f"handling business step. Num messages: {len(messages.messages)}"
        # )

        # Group new messages by customer
        new_messages_by_customer: dict[str, list[ReceivedMessage]] = defaultdict(list)
        for received_message in messages.messages:
            # Note: ReceivedMessages are now captured in the FetchMessages ActionExecutionResult
            new_messages_by_customer[received_message.from_agent_id].append(
                received_message
            )

        # Handle each customer conversation individually
        # Handle all customer conversations concurrently
        if new_messages_by_customer:
            await asyncio.gather(
                *[
                    self._handle_new_customer_messages(customer_id, new_messages)
                    for customer_id, new_messages in new_messages_by_customer.items()
                ]
            )

        if len(new_messages_by_customer) == 0:
            # Wait before next check
            await asyncio.sleep(self._polling_interval)
        else:
            await asyncio.sleep(0)

    async def on_started(self):
        """Handle when the business agent starts."""
        self.logger.info("Ready for customers")

    async def _handle_payment(self, customer_id: str, payment: Payment) -> Message:
        """Handle a payment from a customer.

        Args:
            customer_id: ID of the customer
            payment: The payment message

        Returns:
            Message to send back to customer

        """
        proposal_id = payment.proposal_message_id
        self.logger.info(
            f"Processing payment for proposal {proposal_id} from customer {customer_id}"
        )

        stored_proposal = self.proposal_storage.get_proposal(proposal_id)
        if stored_proposal and stored_proposal.status == "pending":
            # Accept the payment
            self.proposal_storage.update_proposal_status(proposal_id, "accepted")
            self.confirmed_orders.append(proposal_id)

            # Generate confirmation using ResponseHandler
            confirmation = self._responses.generate_payment_confirmation(
                proposal_id, stored_proposal.proposal.total_price
            )
            self.logger.info(
                f"Confirmed payment for proposal {proposal_id} from customer {customer_id}"
            )
            return confirmation
        else:
            self.logger.error(
                f"Failed to process payment for proposal {proposal_id} from customer {customer_id}. Proposal is missing or not pending."
            )
            # Generate error message using ResponseHandler
            error_message = self._responses.generate_proposal_not_found_error(
                proposal_id
            )
            return error_message

    def get_business_summary(self) -> BusinessSummary:
        """Get a summary of business operations.

        Returns:
            Summary of business state and transactions

        """
        return BusinessSummary(
            business_id=self.business.id,
            business_name=self.business.name,
            description=self.business.description,
            rating=self.business.rating,
            menu_items=len(self.business.menu_features),
            amenities=len(self.business.amenity_features),
            pending_proposals=self.proposal_storage.count_pending_proposals(),
            confirmed_orders=len(self.confirmed_orders),
            delivery_available=self.business.amenity_features.get("delivery", False),
        )
