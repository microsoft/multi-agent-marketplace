"""Main customer agent implementation."""

import asyncio
import traceback

from magentic_marketplace.platform.shared.models import (
    BaseAction,
)

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
from ..proposal_storage import OrderProposalStorage
from .models import (
    CustomerAction,
    CustomerActionResult,
    CustomerSendMessageResults,
    CustomerSummary,
)
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
        self.proposal_storage = OrderProposalStorage()
        self.completed_transactions: list[str] = []
        self.conversation_step: int = 0

        self._event_history: list[
            tuple[CustomerAction, CustomerActionResult] | str
        ] = []
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

        # 3. Decide what to do next
        action = await self._generate_customer_action()

        new_messages = False
        if action:
            # 4. Execute the action (handles messaging internally)
            new_messages = await self._execute_customer_action(action)

        # # 5a. Check if transaction completed
        # if len(self.completed_transactions) > 0:
        #     self.logger.info("Completed a transaction, shutting down!")
        #     self.shutdown()
        #     return

        # 5b. Early-stopping if max steps exceeded
        if self._max_steps is not None and self.conversation_step >= self._max_steps:
            await self.logger.warning("Max steps exceeded, shutting down early!")
            self.shutdown()
            return

        if not new_messages:
            # 6. Wait before next decision
            await asyncio.sleep(self._polling_interval)
        else:
            # Go straight into next decision if received new messages
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
            proposal_storage=self.proposal_storage,
            completed_transactions=self.completed_transactions,
            event_history=self._event_history,
            logger=self.logger,
        )

    async def _generate_customer_action(self) -> CustomerAction | None:
        """Use LLM to decide the next action to take.

        Returns:
            The action to take next

        """
        # Build prompt using prompts handler
        prompts = self._get_prompts_handler()
        system_prompt = prompts.format_system_prompt().strip()
        state_context, step_counter = prompts.format_state_context()
        state_context = state_context.strip()
        step_prompt = prompts.format_step_prompt(step_counter).strip()

        full_prompt = f"{system_prompt}\n\n\n\n{state_context}\n\n{step_prompt}"

        # Use LLM to decide next action
        try:
            action, _ = await self.generate_struct(
                prompt=full_prompt,
                response_format=CustomerAction,
            )

            self.logger.info(
                f"[Step {self.conversation_step}/{self._max_steps or 'inf'}] Action: {action.action_type}. Reason: {action.reason}"
            )

            return action

        except Exception:
            self.logger.exception(
                f"[Step {self.conversation_step}/{self._max_steps or 'inf'}] LLM decision failed"
            )
            # Record the event so the LLM can recover next time (hopefully)
            self._event_history.append(f"LLM decision failed: {traceback.format_exc()}")
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
                limit=self._search_bandwidth,
                page=action.search_page,
            )
            search_result = await self.execute_action(search_action)

            if not search_result.is_error:
                search_response = SearchResponse.model_validate(search_result.content)
                business_names = [ba.business.name for ba in search_response.businesses]
                business_names_str = ",".join(business_names)

                self.logger.info(
                    f'Search: "{search_action.query}", {search_action.search_algorithm}, resulting in {len(search_response.businesses)} business(es) found out of {search_response.total_possible_results} total business(es). Showing page {action.search_page} of {search_response.total_pages}.'
                )
                self.logger.info(f"Search Result: {business_names_str}")
                self._event_history.append((action, search_response))
            else:
                self._event_history.append((action, search_result))
        # Check for new messages
        elif action.action_type == "check_messages":
            fetch_response = await self.fetch_messages()
            self._event_history.append((action, fetch_response))
            messages = fetch_response.messages
            await self._process_new_messages(messages)
            return len(messages) > 0
        elif action.action_type == "send_messages":
            # Send messages directly with proper error handling
            if action.messages is None:
                raise ValueError(
                    "messages cannot be empty when action_type is send_messages"
                )

            # The CustomerAction creates two lists: one for text messages and one for payment messages
            # Each message is sent independently to the Marketplace, and can each have an independent error
            # This class is used to keep the results of sending each individual message in an identical format to CustomerAction,
            # so that it is easier to format them for prompting later.
            send_message_results = CustomerSendMessageResults()

            for text_message in action.messages.text_messages:
                business_id = text_message.to_business_id
                message = TextMessage(content=text_message.content)
                try:
                    result = await self.send_message(business_id, message)
                    if result.is_error:
                        self.logger.error(
                            f"Failed to send message to {business_id}: {result.content}"
                        )
                        send_message_results.text_message_results.append(
                            (False, str(result.content))
                        )
                    else:
                        send_message_results.text_message_results.append(
                            (True, "Success!")
                        )
                except Exception:
                    self.logger.exception(f"Failed to send message to {business_id}")
                    send_message_results.text_message_results.append(
                        (
                            False,
                            f"Failed to send message to {business_id}. {traceback.format_exc()}",
                        )
                    )

            for pay_message in action.messages.pay_messages:
                business_id = pay_message.to_business_id
                proposal_to_accept = pay_message.proposal_message_id
                stored_proposal = self.proposal_storage.get_proposal(proposal_to_accept)

                if stored_proposal:
                    payment = Payment(
                        proposal_message_id=proposal_to_accept,
                        payment_method=pay_message.payment_method or "credit_card",
                        payment_message=pay_message.payment_message
                        or f"Accepting your proposal for {len(stored_proposal.proposal.items)} items",
                    )

                    self.logger.info(
                        f"Sending ${stored_proposal.proposal.total_price} payment to {stored_proposal.business_id} for proposal id {proposal_to_accept}",
                    )

                    try:
                        result = await self.send_message(
                            stored_proposal.business_id, payment
                        )
                        if not result.is_error:
                            # Mark proposal as accepted
                            success = self.proposal_storage.update_proposal_status(
                                proposal_to_accept, "accepted"
                            )
                            if success:
                                send_message_results.pay_message_results.append(
                                    (True, "Payment accepted!")
                                )
                                self.completed_transactions.append(proposal_to_accept)
                            else:
                                send_message_results.pay_message_results.append(
                                    (False, "Failed to update order proposal status.")
                                )
                        else:
                            self.logger.error(
                                f"Failed to send payment: {result.content}"
                            )
                            send_message_results.pay_message_results.append(
                                (False, f"Failed to send payment: {result.content}")
                            )
                    except Exception:
                        self.logger.exception(
                            f"Failed to send payment for proposal {stored_proposal.proposal_id}"
                        )
                        send_message_results.pay_message_results.append(
                            (
                                False,
                                f"Failed to send payment for proposal {stored_proposal.proposal_id}: {traceback.format_exc()}",
                            )
                        )

                else:
                    self.logger.warning(
                        f"Error: proposal_to_accept '{proposal_to_accept}' does not match any known proposals."
                    )
                    send_message_results.pay_message_results.append(
                        (
                            False,
                            f"Error: proposal_to_accept '{proposal_to_accept}' does not match any known proposals.",
                        )
                    )

            self._event_history.append((action, send_message_results))

        elif action.action_type == "end_transaction":
            # Accept the proposal specified by the LLM
            self.shutdown()

        # No new messages
        return False

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
