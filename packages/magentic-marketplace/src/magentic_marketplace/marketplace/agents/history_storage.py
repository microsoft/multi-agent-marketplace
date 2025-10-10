"""Shared history storage and conversation formatting for agents."""

from typing import overload

from magentic_marketplace.platform.logger import MarketplaceLogger
from magentic_marketplace.platform.shared.models import (
    ActionExecutionResult,
    BaseAction,
)

from ..actions import (
    FetchMessages,
    FetchMessagesResponse,
    Search,
    SearchResponse,
    SendMessage,
)

# Generic history entry type that both customer and business agents can use
HistoryEntry = tuple[BaseAction, ActionExecutionResult] | str


class HistoryStorage:
    """Manages event history storage and conversation formatting for agents."""

    def __init__(self, logger: MarketplaceLogger):
        """Initialize the history storage.

        Args:
            logger: Logger instance for warnings and debug messages

        """
        self.event_history: list[HistoryEntry] = []
        self.logger = logger

    @overload
    def record_event(self, event: HistoryEntry, result: None = None) -> None: ...
    @overload
    def record_event(
        self, event: BaseAction, result: ActionExecutionResult
    ) -> None: ...
    def record_event(
        self,
        event: HistoryEntry | BaseAction,
        result: ActionExecutionResult | None = None,
    ) -> None:
        """Record an event in the history.

        Args:
            event: The event to record (either a HistoryEvent tuple, or a BaseAction and then result must be provided)
            result: The ActionExecutionResult if event is a BaseAction

        """
        if isinstance(event, BaseAction):
            if result is None:
                raise ValueError("result is required when event is BaseAction")
            self.event_history.append((event, result))
        else:
            self.event_history.append(event)

    def record_log(self, message: str):
        """Record a log message in the history.

        Args:
            message: The message to record

        """
        self.record_event(message)

    def record_error(self, message: str, exception: Exception | None = None):
        """Record an error message in the history.

        Args:
            message: The error message to record
            exception: Optional exception that caused the error

        """
        content = message
        if exception:
            # Recursively build error message with inner exceptions
            error_chain: list[str] = []
            current_exception = exception
            while current_exception is not None:
                error_chain.append(str(current_exception))
                current_exception = getattr(
                    current_exception, "__cause__", None
                ) or getattr(current_exception, "__context__", None)
            content = f"{message}: {' -> '.join(error_chain)}"

        self.record_event(f"ERROR: {content}")

    def format_conversation_text(self, step_header: str) -> tuple[str, int]:
        """Generate conversation text from event history.

        Args:
            step_header: string to include in each step header

        Returns:
            Formatted conversation history

        """
        formatted_entries: list[str] = []
        step_counter = 0

        consecutive_text_messages: list[tuple[SendMessage, ActionExecutionResult]] = []
        consecutive_empty_fetch_messages: list[
            tuple[FetchMessages, ActionExecutionResult]
        ] = []

        def flush_consecutive_send_messages():
            nonlocal step_counter
            if consecutive_text_messages:
                # Increment step counter first
                step_counter += 1
                formatted_entries.extend(
                    self._format_send_message_actions(
                        consecutive_text_messages,
                        step_header=step_header,
                        current_step=step_counter,
                        # Do not include step_count because all of these messages were sent in the same step
                    )
                )
                consecutive_text_messages.clear()

        def flush_consecutive_fetch_messages():
            nonlocal step_counter
            if consecutive_empty_fetch_messages:
                formatted_entries.extend(
                    self._format_fetch_messages_action(
                        *consecutive_empty_fetch_messages[-1],
                        step_header=step_header,
                        current_step=step_counter
                        + len(consecutive_empty_fetch_messages),
                        steps_in_group=len(consecutive_empty_fetch_messages),
                    )
                )
                # Increment step counter by the number of empty fetches
                step_counter += len(consecutive_empty_fetch_messages)
                consecutive_empty_fetch_messages.clear()

        def flush_consecutive_buffers():
            nonlocal step_counter
            # Flush both buffers (only one should have items at a time)
            flush_consecutive_fetch_messages()
            flush_consecutive_send_messages()

        for entry in self.event_history:
            if isinstance(entry, tuple) and len(entry) == 2:
                first, second = entry

                # First, group any consecutive messages, these if-elses contain continue statements
                if isinstance(first, FetchMessages):
                    try:
                        response = FetchMessagesResponse.model_validate(second.content)
                        if not response.messages:
                            # Flush text messages before starting fetch messages
                            flush_consecutive_send_messages()
                            consecutive_empty_fetch_messages.append((first, second))
                            continue
                    except Exception:
                        # Let the _format_action_entry below handle it
                        pass
                # Group consecutive SendMessage to better reflect how the CustomerAction is formatted (multiple messages per action)
                elif isinstance(first, SendMessage) and first.message.type == "text":
                    # Flush empty fetches before starting text messages
                    flush_consecutive_fetch_messages()
                    consecutive_text_messages.append((first, second))
                    continue

                # Handle the current/ungrouped entry, but first flush the groups
                flush_consecutive_buffers()

                step_counter += 1

                formatted_entries.extend(
                    self._format_action_entry(
                        first,
                        second,
                        step_header=step_header,
                        current_step=step_counter,
                    )
                )
            else:
                formatted_entries.append(f"\n=== LOG ===\n{entry}")

        # Flush any remaining empty_fetch_messages
        flush_consecutive_buffers()

        return (
            "\n".join(formatted_entries) if formatted_entries else ""
        ).strip(), step_counter

    def _format_step_header(
        self, *, step_header: str, current_step: int, steps_in_group: int | None = None
    ):
        formatted_entries: list[str] = []
        if steps_in_group and steps_in_group > 1:
            formatted_entries.append(
                f"=== STEPS {current_step - steps_in_group + 1}-{current_step} [{step_header}] ==="
            )
        else:
            formatted_entries.append(f"\n=== STEP {current_step} [{step_header}] ===")
        return formatted_entries

    def _format_action_entry(
        self,
        action: BaseAction,
        result: ActionExecutionResult,
        *,
        step_header: str,
        current_step: int,
        steps_in_group: int | None = None,
    ) -> list[str]:
        """Format BaseAction and ActionExecutionResult pair.

        Args:
            action: The action taken
            result: The result of taking the action
            step_header: string to include in every step header
            current_step: The action step number
            steps_in_group: The number of identical steps leading up to this step

        Returns:
            List of formatted strings

        """
        formatted_entries: list[str] = []

        # Dispatch to specific action formatters
        if isinstance(action, Search):
            formatted_entries.extend(
                self._format_search_action(
                    action, result, current_step=current_step, step_header=step_header
                )
            )
        elif isinstance(action, SendMessage):
            formatted_entries.extend(
                self._format_send_message_actions(
                    [(action, result)],
                    current_step=current_step,
                    step_header=step_header,
                )
            )
        elif isinstance(action, FetchMessages):
            formatted_entries.extend(
                self._format_fetch_messages_action(
                    action,
                    result,
                    current_step=current_step,
                    steps_in_group=steps_in_group,
                    step_header=step_header,
                )
            )

        return formatted_entries

    def _format_search_action(
        self,
        action: Search,
        result: ActionExecutionResult,
        *,
        current_step: int,
        step_header: str,
    ) -> list[str]:
        """Format Search action and result.

        Args:
            action: Search action
            result: Action execution result
            current_step: the action step count
            step_header: string to include in step header

        Returns:
            List of formatted strings

        """
        formatted_entries: list[str] = self._format_step_header(
            step_header=step_header, current_step=current_step
        )
        formatted_entries.append(
            f"Action: search_businesses: {action.model_dump_json()}"
        )
        if result.is_error:
            formatted_entries.append(f"Result: Action failed. {result.content}")
        else:
            try:
                search_response = SearchResponse.model_validate(result.content)
                formatted_entries.append(
                    f"Step {current_step} result: Searched {search_response.total_possible_results} business(es). Showing page {action.page} of {search_response.total_pages}"
                )
                for business in search_response.businesses:
                    formatted_entries.append(
                        f"Found business: {business.business.name} (ID: {business.id}):\n"
                        f"  Description: {business.business.description}\n"
                        f"  Rating: {business.business.rating:.2f}\n"
                        "\n"
                    )
                if not search_response.businesses:
                    formatted_entries.append("No businesses found")
            except Exception:
                formatted_entries.append(
                    f"Error parsing search response: {result.content}"
                )

        return formatted_entries

    def _format_send_message_actions(
        self,
        entries: list[tuple[SendMessage, ActionExecutionResult]],
        *,
        current_step: int,
        step_header: str,
    ) -> list[str]:
        """Format SendMessage action and result.

        Args:
            entries: list of SendMessage, ActionExecutionResult tuples
            current_step: The action step count
            step_header: string to include in step header

        Returns:
            List of formatted strings

        """
        formatted_entries: list[str] = self._format_step_header(
            step_header=step_header, current_step=current_step
        )
        # Add message-specific details
        formatted_entries.append(f"Action: send_messages message_count={len(entries)}")

        formatted_results: list[str] = []
        for action, result in entries:
            message = action.message
            formatted_results.append(message.model_dump_json())
            if result.is_error:
                formatted_results.append(f"Message send failed: {result.content}")
            else:
                # Handle success based on message type
                if message.type == "payment":
                    formatted_results.append(
                        "🎉 PAYMENT COMPLETED SUCCESSFULLY! Transaction accepted by platform. The purchase has been finalized."
                    )
                else:
                    formatted_results.append("✅ Message sent successfully")

        formatted_entries.append(f"Step {current_step} result: {formatted_results}")

        return formatted_entries

    def _format_fetch_messages_action(
        self,
        action: FetchMessages,
        result: ActionExecutionResult,
        *,
        current_step: int,
        step_header: str,
        steps_in_group: int | None = None,
    ) -> list[str]:
        """Format FetchMessages action and result.

        Args:
            action: FetchMessages action
            result: Action execution result
            current_step: The action step number
            step_header: string to include in the step header
            steps_in_group: The number of identical steps leading up to this step

        Returns:
            List of formatted strings

        """
        formatted_entries: list[str] = self._format_step_header(
            step_header=step_header,
            current_step=current_step,
            steps_in_group=steps_in_group,
        )
        # If end_step, then this is an empty FetchMessageResponse
        if steps_in_group:
            formatted_entries.append(f"Action: check_messages ({steps_in_group} times)")
            formatted_entries.append("📭 No new messages found in all checks")
        else:
            formatted_entries.append("Action: check_messages (checking for responses)")
        if result.is_error:
            formatted_entries.append(
                f"Step {current_step} result: Action failed. {result.content}"
            )
        else:
            try:
                content = FetchMessagesResponse.model_validate(result.content)
                message_count = len(content.messages)
                if message_count == 0:
                    formatted_entries.append(
                        f"Step {current_step} result: 📭 No new messages"
                    )
                else:
                    formatted_results: list[str] = []
                    # Add received messages to conversation
                    for received_message in content.messages:
                        message_content = received_message.message
                        formatted_results.append(
                            f"✉️ Received {message_content.type} from {received_message.from_agent_id}: {message_content.model_dump_json()}"
                        )
                    formatted_entries.append(
                        f"Step {current_step} result: {formatted_results}"
                    )
            except Exception:
                formatted_entries.append(
                    f"Error parsing fetch response: {result.content}"
                )

        return formatted_entries

    def _format_unknown_event(
        self, entry: HistoryEntry, step_counter: int
    ) -> list[str]:
        """Format unknown event with STEP header.

        Args:
            entry: The unknown event entry
            step_counter: Current step number

        Returns:
            List of formatted strings for the unknown event

        """
        formatted_entries: list[str] = []
        self.logger.warning(f"Unknown history event: {type(entry)}")

        formatted_entries.append(f"\n=== STEP {step_counter} ===")
        formatted_entries.append("Action: Unknown")
        formatted_entries.append(f"{str(entry)}")

        return formatted_entries
