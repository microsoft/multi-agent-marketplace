"""Tests for HistoryStorage."""

from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from magentic_marketplace.marketplace.actions import (
    FetchMessages,
    FetchMessagesResponse,
)
from magentic_marketplace.marketplace.agents.history_storage import HistoryStorage
from magentic_marketplace.platform.shared.models import ActionExecutionResult


@pytest.fixture
def logger():
    """Return a mock logger for testing."""
    mock_logger = Mock()
    mock_logger.warning = Mock()
    return mock_logger


@pytest.fixture
def history_storage(logger):
    """Return a HistoryStorage instance for testing."""
    return HistoryStorage(logger=logger)


def test_format_conversation_text_squashes_consecutive_empty_fetch_messages(
    history_storage: HistoryStorage,
):
    """Test that multiple consecutive empty fetch_messages are correctly squashed."""
    # Create multiple consecutive empty FetchMessages actions
    for i in range(5):
        action = FetchMessages(
            type="fetch_messages",
            from_agent_id=None,
            limit=None,
            offset=None,
            after=None,
            after_index=i if i > 0 else None,
        )
        result = ActionExecutionResult(
            is_error=False,
            content=FetchMessagesResponse(messages=[], has_more=False),
        )
        history_storage.record_event(action, result)

    # Format the conversation
    formatted_text, step_count = history_storage.format_conversation_text(
        step_header="TEST"
    )

    # Verify the consecutive empty fetch messages were squashed
    # Should only show one formatted entry for all 5 empty fetch messages
    assert "STEPS 1-5" in formatted_text  # Should show range of steps
    assert "check_messages (5 times)" in formatted_text  # Should show count
    assert "No new messages found in all checks" in formatted_text

    # Verify step count is correct (5 consecutive fetch messages = 5 steps)
    assert step_count == 5

    # Verify there's only one occurrence of the squashed message
    # (not 5 separate entries)
    assert formatted_text.count("check_messages") == 1


def test_format_conversation_text_multiple_groups_squashed(
    history_storage: HistoryStorage,
):
    """Test that multiple consecutive empty fetch_messages are squashed correctly with different counts."""
    # Add 3 empty fetch messages
    for _i in range(3):
        action = FetchMessages(type="fetch_messages")
        result = ActionExecutionResult(
            is_error=False,
            content=FetchMessagesResponse(messages=[], has_more=False),
        )
        history_storage.record_event(action, result)

    # Format the conversation
    formatted_text, step_count = history_storage.format_conversation_text(
        step_header="TEST"
    )

    # Verify the squashing worked
    assert "check_messages (3 times)" in formatted_text
    assert "No new messages found in all checks" in formatted_text
    assert step_count == 3
    # Should only have one occurrence of check_messages
    assert formatted_text.count("check_messages") == 1


def test_format_conversation_text_single_empty_fetch_still_squashed(
    history_storage: HistoryStorage,
):
    """Test that even a single empty fetch_message uses the squashing format."""
    action = FetchMessages(type="fetch_messages")
    result = ActionExecutionResult(
        is_error=False,
        content=FetchMessagesResponse(messages=[], has_more=False),
    )
    history_storage.record_event(action, result)

    # Format the conversation
    formatted_text, step_count = history_storage.format_conversation_text(
        step_header="TEST"
    )

    # Single empty fetch uses squashing format with count of 1
    assert "check_messages (1 times)" in formatted_text
    assert "No new messages found in all checks" in formatted_text

    # Verify step count
    assert step_count == 1


def test_format_conversation_text_consecutive_send_messages_grouped(
    history_storage: HistoryStorage,
):
    """Test that consecutive text SendMessage actions are grouped into a single step."""
    from magentic_marketplace.marketplace.actions import SendMessage
    from magentic_marketplace.marketplace.actions.messaging import TextMessage

    # Create multiple consecutive SendMessage actions with text messages
    for i in range(3):
        action = SendMessage(
            type="send_message",
            from_agent_id="customer-123",
            to_agent_id="business-456",
            created_at=datetime.now(UTC),
            message=TextMessage(type="text", content=f"Message {i + 1}"),
        )
        result = ActionExecutionResult(
            is_error=False,
            content={"status": "sent"},
        )
        history_storage.record_event(action, result)

    # Format the conversation
    formatted_text, step_count = history_storage.format_conversation_text(
        step_header="TEST"
    )

    # Verify the consecutive send messages were grouped into a single step
    assert "message_count=3" in formatted_text  # Should show all 3 messages
    assert "Message 1" in formatted_text
    assert "Message 2" in formatted_text
    assert "Message 3" in formatted_text

    # Should only be counted as 1 step (all messages sent together)
    assert step_count == 1

    # Should only have one STEP header
    assert formatted_text.count("STEP 1") == 1
    assert "STEP 2" not in formatted_text


def test_format_conversation_text_step_counter_after_send_message_group(
    history_storage: HistoryStorage,
):
    """Test that step counter increments correctly after a send_message group."""
    from magentic_marketplace.marketplace.actions import SendMessage
    from magentic_marketplace.marketplace.actions.messaging import TextMessage

    # Add a group of 2 consecutive send_messages (should be step 1)
    for i in range(2):
        action = SendMessage(
            type="send_message",
            from_agent_id="customer-123",
            to_agent_id="business-456",
            created_at=datetime.now(UTC),
            message=TextMessage(type="text", content=f"Message {i + 1}"),
        )
        result = ActionExecutionResult(
            is_error=False,
            content={"status": "sent"},
        )
        history_storage.record_event(action, result)

    # Add an empty fetch message (should be step 2)
    fetch_action = FetchMessages(type="fetch_messages")
    fetch_result = ActionExecutionResult(
        is_error=False,
        content=FetchMessagesResponse(messages=[], has_more=False),
    )
    history_storage.record_event(fetch_action, fetch_result)

    # Add another group of 2 send_messages (should be step 3)
    for i in range(2):
        action = SendMessage(
            type="send_message",
            from_agent_id="customer-123",
            to_agent_id="business-456",
            created_at=datetime.now(UTC),
            message=TextMessage(type="text", content=f"Message {i + 3}"),
        )
        result = ActionExecutionResult(
            is_error=False,
            content={"status": "sent"},
        )
        history_storage.record_event(action, result)

    # Format the conversation
    formatted_text, step_count = history_storage.format_conversation_text(
        step_header="TEST"
    )

    print(formatted_text)

    # Verify step counter is correct
    assert step_count == 3

    # Verify each step appears with the correct number
    assert "STEP 1" in formatted_text  # First send_message group
    # Step 2 appears as "STEPS 2-2" since it's a single fetch that uses the squashing format
    assert "STEP 2" in formatted_text  # Fetch message
    assert "STEPS 2-2" not in formatted_text
    assert "STEP 3" in formatted_text  # Second send_message group
    assert "STEP 4" not in formatted_text  # Should not have a 4th step

    # Verify the send_message groups show correct counts
    lines = formatted_text.split("\n")
    send_message_lines = [line for line in lines if "send_messages" in line]
    assert len(send_message_lines) == 2  # Two separate send_message groups
    assert all("message_count=2" in line for line in send_message_lines)

    # Verify messages were not lost
    assert "Message 1" in formatted_text
    assert "Message 2" in formatted_text
    assert "Message 3" in formatted_text
    assert "Message 4" in formatted_text
