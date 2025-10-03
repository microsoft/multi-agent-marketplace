"""Main customer agent implementation."""

import asyncio

from magentic_marketplace.platform.shared.models import BaseAction

from ...actions import (
    OrderProposal,
    Payment,
    ReceivedMessage,
    Search,
    SearchAlgorithm,
    SearchResponse,
    TextMessage,
)
from ...llm.config import BaseLLMConfig
from ...shared.models import Customer, CustomerAgentProfile
from ..base import BaseSimpleMarketplaceAgent
from ..history_storage import HistoryStorage
from ..proposal_storage import OrderProposalStorage
from .models import CustomerAction, CustomerSummary
from .prompts import PromptsHandler


class CustomerAgent(BaseSimpleMarketplaceAgent[CustomerAgentProfile]):
    """Customer agent that autonomously shops in the marketplace."""

    def __init__(
        self,
        customer: Customer,
        base_url: str,
        llm_config: BaseLLMConfig | None = None,
        search_algorithm: str = "simple",
        search_bandwidth: int = 10,
        polling_interval: float = 2,
        max_steps: int | None = None,
    ):
        """Initialize the customer agent.

        Args:
            customer: Customer object with request and preferences
            base_url: The marketplace server URL
            llm_config: LLM configuration for the agent
            search_algorithm: Search algorithm to use (e.g., "simple", "filtered", "rnr")
            search_bandwidth: The maximum number of search results to return.
            polling_interval: Number of seconds to wait after receiving no messages.
            max_steps: Maximum number of steps to take before stopping.

        """
        profile = CustomerAgentProfile.from_customer(customer)
        super().__init__(profile, base_url, llm_config)

        # Initialize customer agent state
        self.history = HistoryStorage(self.logger)
        self.proposal_storage = OrderProposalStorage()
        self.completed_transactions: list[str] = []
        self.known_business_ids: list[str] = []
        self.conversation_step: int = 0

        self._search_algorithm = SearchAlgorithm(search_algorithm)
        self._search_bandwidth = search_bandwidth

        self._polling_interval = polling_interval
        self._max_steps = max_steps

    @property
    def customer(self) -> Customer:
        """Access customer data from profile with full type safety."""
        return self.profile.customer

    async def execute_action(self, action: BaseAction):
        """Execute an action and record it in event history.

        Args:
            action: The action to execute

        Returns:
            Result of the action execution

        """
        # Execute the action through the parent class
        result = await super().execute_action(action)

        # Record the action-result pair in event history
        self.history.record_event(action, result)

        return result

    async def step(self):
        """One step of autonomous shopping agent logic.

        This method performs one iteration of the customer's shopping journey:
        1. Check for new messages from businesses
        2. Decide next action using LLM
        3. Execute the action (search, prepare messages, or end transaction)
        4. Check if transaction completed (triggers shutdown)
        """
        self.conversation_step += 1

        # 1. Check for new messages from businesses
        fetch_result = await self.fetch_messages()

        # 2. Process received messages: store events and proposals
        await self._process_new_messages(fetch_result.messages)

        # 3. Decide what to do next
        action = await self._generate_customer_action()

        if action:
            # 4. Execute the action (handles messaging internally)
            await self._execute_customer_action(action)

        # 5a. Check if transaction completed
        if len(self.completed_transactions) > 0:
            await self.logger.info("Completed a transaction, shutting down!")
            self.shutdown()
            return

        # 5b. Early-stopping if max steps exceeded
        if self._max_steps is not None and self.conversation_step >= self._max_steps:
            self.logger.warning("Max steps exceeded, shutting down early!")
            self.shutdown()
            return

        if len(fetch_result.messages) == 0:
            # 6. Wait before next decision
            await asyncio.sleep(self._polling_interval)
        else:
            await asyncio.sleep(0)

    async def on_started(self):
        """Handle when the customer agent starts."""
        self.logger.info("Starting autonomous shopping agent")

    async def _process_new_messages(self, messages: list[ReceivedMessage]):
        for message in messages:
            # Note: ReceivedMessages are now captured in the FetchMessages ActionExecutionResult
            # Store order proposals
            if isinstance(message.message, OrderProposal):
                self.proposal_storage.add_proposal(
                    message.message,
                    message.from_agent_id,
                    self.id,
                )
                self.logger.debug(
                    f"Received and stored order proposal {message.message.id} from {message.from_agent_id}",
                    data=message,
                )

    def _get_prompts_handler(self) -> PromptsHandler:
        """Get a fresh PromptsHandler with current state."""
        return PromptsHandler(
            customer=self.customer,
            known_business_ids=self.known_business_ids,
            proposal_storage=self.proposal_storage,
            completed_transactions=self.completed_transactions,
            event_history=self.history.event_history,
            logger=self.logger,
        )

    async def _generate_customer_action(self) -> CustomerAction | None:
        """Use LLM to decide the next action to take.

        Returns:
            The action to take next

        """
        # Build prompt using prompts handler
        prompts = self._get_prompts_handler()
        system_prompt = prompts.format_system_prompt()
        state_context = prompts.format_state_context()
        step_prompt = prompts.format_step_prompt()

        full_prompt = system_prompt + state_context + step_prompt

        # Use LLM to decide next action
        try:
            action, _ = await self.generate_struct(
                prompt=full_prompt,
                response_format=CustomerAction,
            )

            self.logger.info(
                f"Next action: {action.action_type}. Reason: {action.reason}"
            )

            return action

        except Exception as e:
            self.logger.exception("LLM decision failed")
            # Record the event so the LLM can recover next time (hopefully)
            self.history.record_error("LLM decision failed", e)
            return None

    async def _execute_customer_action(self, action: CustomerAction):
        """Execute the action decided by the LLM.

        Args:
            action: The action to execute

        """
        # Execute search and update known businesses
        if action.action_type == "search_businesses":
            search_action = Search(
                query=action.search_query or self.customer.request,
                search_algorithm=self._search_algorithm,
                constraints=action.search_constraints,
                limit=self._search_bandwidth,
            )
            search_result = await self.execute_action(search_action)

            if not search_result.is_error:
                search_response = SearchResponse.model_validate(search_result.content)
                business_ids = [ba.id for ba in search_response.businesses]
                self.known_business_ids.extend(business_ids)
        elif action.action_type == "send_messages":
            # Send messages directly with proper error handling
            if action.target_business_ids and action.message_content:
                for business_id in action.target_business_ids:
                    message = TextMessage(content=action.message_content)

                    try:
                        result = await self.send_message(business_id, message)
                        if result.is_error:
                            self.logger.error(
                                f"Failed to send message to {business_id}: {result.content}"
                            )
                    except Exception as e:
                        self.logger.exception(
                            f"Failed to send message to {business_id}"
                        )
                        self.history.record_error(
                            f"Failed to send message to {business_id}", e
                        )
        elif action.action_type == "end_transaction":
            # Accept the proposal specified by the LLM
            if action.proposal_to_accept:
                stored_proposal = self.proposal_storage.get_proposal(
                    action.proposal_to_accept
                )

                if stored_proposal:
                    payment_message = Payment(
                        proposal_message_id=action.proposal_to_accept,
                        payment_method="credit_card",
                        payment_message=action.message_content
                        or f"Accepting your proposal for {len(stored_proposal.proposal.items)} items",
                    )

                    self.logger.info(
                        f"Sending ${stored_proposal.proposal.total_price} payment to {stored_proposal.business_id} for proposal id {action.proposal_to_accept}",
                    )

                    try:
                        result = await self.send_message(
                            stored_proposal.business_id, payment_message
                        )
                        if not result.is_error:
                            # Mark proposal as accepted
                            success = self.proposal_storage.update_proposal_status(
                                action.proposal_to_accept, "accepted"
                            )
                            if success:
                                self.completed_transactions.append(
                                    action.proposal_to_accept
                                )
                        else:
                            self.logger.error(
                                f"Failed to send payment: {result.content}"
                            )
                    except Exception as e:
                        self.logger.exception(
                            f"Failed to send payment for proposal {stored_proposal.proposal_id}"
                        )
                        self.history.record_error(
                            f"Failed to send payment for proposal {stored_proposal.proposal_id}",
                            e,
                        )

                else:
                    self.logger.warning(
                        f"Error: proposal_to_accept '{action.proposal_to_accept}' does not match any known proposals."
                    )
                    self.history.record_error(
                        f"Error: proposal_to_accept '{action.proposal_to_accept}' does not match any known proposals."
                    )
            else:
                self.logger.warning(
                    "Error: proposal_to_accept missing. proposal_to_accept is required when action_type is end_transaction."
                )
                self.history.record_error(
                    "Error: proposal_to_accept missing. proposal_to_accept is required when action_type is end_transaction."
                )

    def get_transaction_summary(self) -> CustomerSummary:
        """Get a summary of completed transactions.

        Returns:
            Summary of transactions and proposals

        """
        return CustomerSummary(
            customer_id=self.customer.id,
            customer_name=self.customer.name,
            request=self.customer.request,
            profile=self.customer.model_dump(),
            proposals_received=self.proposal_storage.count_proposals(),
            transactions_completed=len(self.completed_transactions),
            completed_proposal_ids=self.completed_transactions,
        )
