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

        self.record_event(f"❌ ERROR: {content}")

    def format_conversation_text(self) -> str:
        """Generate conversation text from event history.

        Returns:
            Formatted conversation history

        """
        formatted_entries: list[str] = []
        step_counter = 0

        for entry in self.event_history:
            if isinstance(entry, tuple) and len(entry) == 2:
                first, second = entry
                # Action-result pair: treat as a STEP
                step_counter += 1
                entries = self._format_action_entry(first, second, step_counter)
                formatted_entries.extend(entries)
            else:
                formatted_entries.append(f"\n=== LOG ===\n{entry}")

        return "\n".join(formatted_entries) if formatted_entries else ""

    def _format_action_entry(
        self, action: BaseAction, result: ActionExecutionResult, step_counter: int
    ) -> list[str]:
        """Format BaseAction and ActionExecutionResult pair.

        Returns:
            List of formatted strings

        """
        formatted_entries: list[str] = []
        formatted_entries.append(f"\n\n=== STEP {step_counter} ===")

        # Dispatch to specific action formatters
        if isinstance(action, Search):
            entries = self._format_search_action(action, result)
        elif isinstance(action, SendMessage):
            entries = self._format_send_message_action(action, result)
        elif isinstance(action, FetchMessages):
            entries = self._format_fetch_messages_action(action, result)
        else:
            # Unknown action type - should not happen with our current design
            self.logger.warning(f"Unknown action type: {type(action)}")
            entries = [
                f"Action: {action.__class__.__name__}",
                "❌ Unsupported action type",
            ]

        formatted_entries.extend(entries)
        return formatted_entries

    def _format_search_action(
        self, action: Search, result: ActionExecutionResult
    ) -> list[str]:
        """Format Search action and result.

        Args:
            action: Search action
            result: Action execution result

        Returns:
            List of formatted strings

        """
        formatted_entries: list[str] = []
        formatted_entries.append("Action: Search businesses")
        formatted_entries.append(f"Arguments: {action.model_dump_json()}")
        formatted_entries.append("\nResult:")
        if result.is_error:
            formatted_entries.append(f"❌ Action failed: {result.content}")
        else:
            try:
                search_response = SearchResponse.model_validate(result.content)
                formatted_entries.append(
                    f"Searched {search_response.total_possible_results} business(es). Showing page {action.page} of {search_response.total_pages}"
                )
                for business in search_response.businesses:
                    formatted_entries.append(
                        f"{business.business.name} (ID: {business.id}): {business.business.description}"
                    )
                if not search_response.businesses:
                    formatted_entries.append("✅ No businesses found")
            except Exception:
                formatted_entries.append(
                    f"❌ Error parsing search response: {result.content}"
                )

        return formatted_entries

    def _format_send_message_action(
        self, action: SendMessage, result: ActionExecutionResult
    ) -> list[str]:
        """Format SendMessage action and result.

        Args:
            action: SendMessage action
            result: Action execution result

        Returns:
            List of formatted strings

        """
        formatted_entries: list[str] = []
        # Add message-specific details
        message = action.message
        formatted_entries.append(
            f"Action: Send {message.type} message to {action.to_agent_id}: {message.model_dump_json()}"
        )

        formatted_entries.append("\nResult:")
        if result.is_error:
            formatted_entries.append(f"❌ Action failed: {result.content}")
        else:
            # Handle success based on message type
            if message.type == "payment":
                formatted_entries.append(
                    "🎉 PAYMENT COMPLETED SUCCESSFULLY! Transaction accepted by platform. The purchase has been finalized."
                )
            else:
                formatted_entries.append("✅ Message sent successfully")

        return formatted_entries

    def _format_fetch_messages_action(
        self, action: FetchMessages, result: ActionExecutionResult
    ) -> list[str]:
        """Format FetchMessages action and result.

        Args:
            action: FetchMessages action
            result: Action execution result

        Returns:
            List of formatted strings

        """
        formatted_entries: list[str] = []
        formatted_entries.append("Action: Fetch messages")
        formatted_entries.append("\nResult:")
        if result.is_error:
            formatted_entries.append(f" Action failed: {result.content}")
        else:
            try:
                content = FetchMessagesResponse.model_validate(result.content)
                message_count = len(content.messages)
                if message_count > 0:
                    formatted_entries.append(f"✅ Received {message_count} messages")
                else:
                    formatted_entries.append("✅ No new messages")
                # Add received messages to conversation
                for received_message in content.messages:
                    message_content = received_message.message
                    formatted_entries.append(
                        f"\n✉️ {message_content.type} message from {received_message.from_agent_id}:\n{message_content.model_dump_json()}"
                    )
            except Exception:
                formatted_entries.append(
                    f" Error parsing fetch response: {result.content}"
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

        formatted_entries.append(f"\n\n=== STEP {step_counter} ===")
        formatted_entries.append("Action: Unknown")
        formatted_entries.append(f"{str(entry)}")

        return formatted_entries
