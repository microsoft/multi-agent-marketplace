"""Tests for HistoryStorage."""

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from magentic_marketplace.marketplace.actions import FetchMessages, FetchMessagesResponse
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
    for i in range(3):
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
