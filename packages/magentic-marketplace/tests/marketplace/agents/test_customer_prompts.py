"""Tests for customer prompts event history formatting."""

from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from magentic_marketplace.marketplace.actions import (
    FetchMessagesResponse,
    ReceivedMessage,
    SearchResponse,
)
from magentic_marketplace.marketplace.actions.messaging import (
    OrderItem,
    OrderProposal,
    TextMessage,
)
from magentic_marketplace.marketplace.agents.customer.models import (
    AssistantPayMessageRequest,
    AssistantTextMessageRequest,
    CustomerAction,
    CustomerSendMessageResults,
    Messages,
)
from magentic_marketplace.marketplace.agents.customer.prompts import PromptsHandler
from magentic_marketplace.marketplace.agents.proposal_storage import (
    OrderProposalStorage,
)
from magentic_marketplace.marketplace.shared.models import (
    Business,
    BusinessAgentProfile,
    Customer,
)
from magentic_marketplace.platform.shared.models import ActionExecutionResult


@pytest.fixture
def customer():
    """Return a test customer."""
    return Customer(
        id="test-customer-001",
        name="Test Customer",
        request="Looking for test items",
        menu_features={"item": 10.0},
        amenity_features=["delivery"],
    )


@pytest.fixture
def logger():
    """Return a mock logger for testing."""
    mock_logger = Mock()
    mock_logger.warning = Mock()
    return mock_logger


@pytest.fixture
def proposal_storage():
    """Return a proposal storage instance for testing."""
    return OrderProposalStorage()


@pytest.fixture
def prompts_handler(customer, proposal_storage, logger):
    """Return a PromptsHandler instance with empty event history."""
    return PromptsHandler(
        customer=customer,
        proposal_storage=proposal_storage,
        completed_transactions=[],
        event_history=[],
        logger=logger,
    )


def test_format_event_history_empty(prompts_handler: PromptsHandler):
    """Test that empty event history returns empty string and step 0."""
    formatted_text, step_count = prompts_handler.format_event_history()

    assert formatted_text == ""
    assert step_count == 0


def test_format_search_businesses_event_success(prompts_handler: PromptsHandler):
    """Test formatting of successful search_businesses event."""
    action = CustomerAction(
        action_type="search_businesses",
        reason="Looking for bakeries",
        search_query="bakery",
    )

    business1 = BusinessAgentProfile(
        id="business-001",
        business=Business(
            id="business-001",
            name="Best Bakery",
            description="We sell the best bread",
            rating=4.5,
            progenitor_customer="customer-000",
            menu_features={"bread": 5.0},
            amenity_features={"delivery": True},
            min_price_factor=0.8,
        ),
    )
    business2 = BusinessAgentProfile(
        id="business-002",
        business=Business(
            id="business-002",
            name="Great Cakes",
            description="Delicious cakes and pastries",
            rating=4.8,
            progenitor_customer="customer-000",
            menu_features={"cake": 20.0},
            amenity_features={"delivery": True},
            min_price_factor=0.8,
        ),
    )

    result = SearchResponse(businesses=[business1, business2], search_algorithm="test")

    prompts_handler.event_history = [(action, result)]  # type: ignore[assignment]  # type: ignore[assignment]
    formatted_text, step_count = prompts_handler.format_event_history()

    # Verify step count
    assert step_count == 1  # Should be 1 after processing 1 event

    # Verify content
    assert "STEP 1" in formatted_text
    assert "search_businesses" in formatted_text
    assert "Best Bakery" in formatted_text
    assert "Great Cakes" in formatted_text
    assert "business-001" in formatted_text
    assert "business-002" in formatted_text
    assert "Rating: 4.50" in formatted_text
    assert "Rating: 4.80" in formatted_text


def test_format_search_businesses_event_no_results(prompts_handler: PromptsHandler):
    """Test formatting of search_businesses event with no results."""
    action = CustomerAction(
        action_type="search_businesses",
        reason="Looking for rare items",
        search_query="unicorn",
    )

    result = SearchResponse(businesses=[], search_algorithm="test")

    prompts_handler.event_history = [(action, result)]  # type: ignore[assignment]  # type: ignore[assignment]
    formatted_text, step_count = prompts_handler.format_event_history()

    assert step_count == 1
    assert "STEP 1" in formatted_text
    assert "search_businesses" in formatted_text
    assert "No businesses found" in formatted_text


def test_format_search_businesses_event_error(prompts_handler: PromptsHandler):
    """Test formatting of failed search_businesses event."""
    action = CustomerAction(
        action_type="search_businesses",
        reason="Search attempt",
        search_query="test",
    )

    result = ActionExecutionResult(
        is_error=True,
        content="Network error",
    )

    prompts_handler.event_history = [(action, result)]  # type: ignore[assignment]  # type: ignore[assignment]
    formatted_text, step_count = prompts_handler.format_event_history()

    assert step_count == 1
    assert "STEP 1" in formatted_text
    assert "Failed to search businesses" in formatted_text
    assert "Network error" in formatted_text


def test_format_check_messages_event_no_messages(prompts_handler: PromptsHandler):
    """Test formatting of check_messages event with no new messages."""
    action = CustomerAction(
        action_type="check_messages",
        reason="Checking for responses",
    )

    result = FetchMessagesResponse(messages=[], has_more=False)

    prompts_handler.event_history = [(action, result)]  # type: ignore[assignment]
    formatted_text, step_count = prompts_handler.format_event_history()

    assert step_count == 1
    assert "STEP 1" in formatted_text
    assert "check_messages" in formatted_text
    assert "📭 No new messages" in formatted_text


def test_format_check_messages_event_with_text_messages(
    prompts_handler: PromptsHandler,
):
    """Test formatting of check_messages event with text messages."""
    action = CustomerAction(
        action_type="check_messages",
        reason="Checking for responses",
    )

    text_msg = ReceivedMessage(
        from_agent_id="business-001",
        to_agent_id="test-customer-001",
        created_at=datetime.now(UTC),
        message=TextMessage(type="text", content="Hello! We have fresh bread today."),
        index=0,
    )

    result = FetchMessagesResponse(messages=[text_msg], has_more=False)

    prompts_handler.event_history = [(action, result)]  # type: ignore[assignment]
    formatted_text, step_count = prompts_handler.format_event_history()

    assert step_count == 1
    assert "STEP 1" in formatted_text
    assert "check_messages" in formatted_text
    assert "📨 Received text from business-001" in formatted_text
    assert "Hello! We have fresh bread today." in formatted_text


def test_format_check_messages_event_with_order_proposal(
    prompts_handler: PromptsHandler,
):
    """Test formatting of check_messages event with order proposal."""
    action = CustomerAction(
        action_type="check_messages",
        reason="Checking for responses",
    )

    proposal_msg = ReceivedMessage(
        from_agent_id="business-001",
        to_agent_id="test-customer-001",
        created_at=datetime.now(UTC),
        message=OrderProposal(
            type="order_proposal",
            id="proposal-123",
            items=[
                OrderItem(
                    id="item-1",
                    item_name="Bread",
                    quantity=2,
                    unit_price=5.0,
                )
            ],
            total_price=10.0,
            special_instructions="Fresh bread ready for pickup",
        ),
        index=0,
    )

    result = FetchMessagesResponse(messages=[proposal_msg], has_more=False)

    prompts_handler.event_history = [(action, result)]  # type: ignore[assignment]
    formatted_text, step_count = prompts_handler.format_event_history()

    assert step_count == 1
    assert "STEP 1" in formatted_text
    assert "📨 Received order_proposal from business-001" in formatted_text
    assert "proposal-123" in formatted_text
    assert "10.0" in formatted_text


def test_format_check_messages_event_error(prompts_handler: PromptsHandler):
    """Test formatting of failed check_messages event."""
    action = CustomerAction(
        action_type="check_messages",
        reason="Checking for responses",
    )

    result = ActionExecutionResult(
        is_error=True,
        content="Connection timeout",
    )

    prompts_handler.event_history = [(action, result)]  # type: ignore[assignment]
    formatted_text, step_count = prompts_handler.format_event_history()

    assert step_count == 1
    assert "STEP 1" in formatted_text
    assert "Failed to fetch messages" in formatted_text
    assert "Connection timeout" in formatted_text


def test_format_send_messages_event_text_only(prompts_handler: PromptsHandler):
    """Test formatting of send_messages event with only text messages."""
    text_msg1 = AssistantTextMessageRequest(
        type="text",
        content="Do you have fresh bread?",
        to_business_id="business-001",
    )
    text_msg2 = AssistantTextMessageRequest(
        type="text",
        content="What are your hours?",
        to_business_id="business-002",
    )

    action = CustomerAction(
        action_type="send_messages",
        reason="Inquiring about products",
        messages=Messages(text_messages=[text_msg1, text_msg2], pay_messages=[]),
    )

    result = CustomerSendMessageResults(
        text_message_results=[(True, ""), (True, "")],
        pay_message_results=[],
    )

    prompts_handler.event_history = [(action, result)]  # type: ignore[assignment]
    formatted_text, step_count = prompts_handler.format_event_history()

    assert step_count == 1
    assert "STEP 1" in formatted_text
    assert "send_messages message_count=2" in formatted_text
    assert "Do you have fresh bread?" in formatted_text
    assert "What are your hours?" in formatted_text
    assert "✅ Message sent successfully" in formatted_text
    # Should appear twice (once for each successful message)
    assert formatted_text.count("✅ Message sent successfully") == 2


def test_format_send_messages_event_payment_success(prompts_handler: PromptsHandler):
    """Test formatting of send_messages event with successful payment."""
    pay_msg = AssistantPayMessageRequest(
        type="payment",
        proposal_message_id="proposal-123",
        to_business_id="business-001",
        payment_message="Thanks for the great offer!",
    )

    action = CustomerAction(
        action_type="send_messages",
        reason="Accepting proposal",
        messages=Messages(text_messages=[], pay_messages=[pay_msg]),
    )

    result = CustomerSendMessageResults(
        text_message_results=[],
        pay_message_results=[(True, "")],
    )

    prompts_handler.event_history = [(action, result)]  # type: ignore[assignment]
    formatted_text, step_count = prompts_handler.format_event_history()

    assert step_count == 1
    assert "STEP 1" in formatted_text
    assert "send_messages message_count=1" in formatted_text
    assert "proposal-123" in formatted_text
    assert "🎉 PAYMENT COMPLETED SUCCESSFULLY!" in formatted_text


def test_format_send_messages_event_payment_failure(prompts_handler: PromptsHandler):
    """Test formatting of send_messages event with failed payment."""
    pay_msg = AssistantPayMessageRequest(
        type="payment",
        proposal_message_id="proposal-123",
        to_business_id="business-001",
        payment_message="Accepting your proposal",
    )

    action = CustomerAction(
        action_type="send_messages",
        reason="Accepting proposal",
        messages=Messages(text_messages=[], pay_messages=[pay_msg]),
    )

    result = CustomerSendMessageResults(
        text_message_results=[],
        pay_message_results=[(False, "Insufficient funds")],
    )

    prompts_handler.event_history = [(action, result)]  # type: ignore[assignment]
    formatted_text, step_count = prompts_handler.format_event_history()

    assert step_count == 1
    assert "STEP 1" in formatted_text
    assert "send_messages message_count=1" in formatted_text
    assert "Message failed to send: Insufficient funds" in formatted_text


def test_format_send_messages_event_mixed(prompts_handler: PromptsHandler):
    """Test formatting of send_messages event with both text and payment."""
    text_msg = AssistantTextMessageRequest(
        type="text",
        content="Thanks for the proposal!",
        to_business_id="business-001",
    )
    pay_msg = AssistantPayMessageRequest(
        type="payment",
        proposal_message_id="proposal-123",
        to_business_id="business-001",
        payment_message="Payment for order",
    )

    action = CustomerAction(
        action_type="send_messages",
        reason="Responding and paying",
        messages=Messages(text_messages=[text_msg], pay_messages=[pay_msg]),
    )

    result = CustomerSendMessageResults(
        text_message_results=[(True, "")],
        pay_message_results=[(True, "")],
    )

    prompts_handler.event_history = [(action, result)]  # type: ignore[assignment]
    formatted_text, step_count = prompts_handler.format_event_history()

    assert step_count == 1
    assert "STEP 1" in formatted_text
    assert "send_messages message_count=2" in formatted_text
    assert "Thanks for the proposal!" in formatted_text
    assert "proposal-123" in formatted_text
    assert "✅ Message sent successfully" in formatted_text
    assert "🎉 PAYMENT COMPLETED SUCCESSFULLY!" in formatted_text


def test_format_log_event(prompts_handler: PromptsHandler):
    """Test formatting of string log events."""
    log_msg = "Error: Something went wrong in the system"

    prompts_handler.event_history = [log_msg]  # type: ignore[assignment]
    formatted_text, step_count = prompts_handler.format_event_history()

    assert step_count == 1
    assert "STEP 1" in formatted_text
    assert "Error: Something went wrong in the system" in formatted_text


def test_format_multiple_events(prompts_handler: PromptsHandler):
    """Test formatting of multiple events in sequence."""
    # Event 1: Search
    search_action = CustomerAction(
        action_type="search_businesses",
        reason="Looking for bakeries",
        search_query="bakery",
    )
    business = BusinessAgentProfile(
        id="business-001",
        business=Business(
            id="business-001",
            name="Best Bakery",
            description="Fresh bread daily",
            rating=4.5,
            progenitor_customer="customer-000",
            menu_features={"bread": 5.0},
            amenity_features={"delivery": True},
            min_price_factor=0.8,
        ),
    )
    search_result = SearchResponse(businesses=[business], search_algorithm="test")

    # Event 2: Send message
    send_action = CustomerAction(
        action_type="send_messages",
        reason="Inquiring",
        messages=Messages(
            text_messages=[
                AssistantTextMessageRequest(
                    type="text",
                    content="Do you have sourdough?",
                    to_business_id="business-001",
                )
            ],
            pay_messages=[],
        ),
    )
    send_result = CustomerSendMessageResults(
        text_message_results=[(True, "")],
        pay_message_results=[],
    )

    # Event 3: Check messages
    check_action = CustomerAction(
        action_type="check_messages",
        reason="Looking for response",
    )
    check_result = FetchMessagesResponse(messages=[], has_more=False)

    prompts_handler.event_history = [  # type: ignore[assignment]
        (search_action, search_result),
        (send_action, send_result),
        (check_action, check_result),
    ]

    formatted_text, step_count = prompts_handler.format_event_history()

    # Verify step count
    assert step_count == 3  # Should be 3 after processing 3 events

    # Verify all steps are present
    assert "STEP 1" in formatted_text
    assert "STEP 2" in formatted_text
    assert "STEP 3" in formatted_text
    assert "STEP 4" not in formatted_text  # Should not have a 4th step

    # Verify content from each event
    assert "Best Bakery" in formatted_text
    assert "Do you have sourdough?" in formatted_text
    assert "📭 No new messages" in formatted_text


def test_format_step_header_single_step(prompts_handler: PromptsHandler):
    """Test step header formatting for single steps."""
    lines = prompts_handler._format_step_header(current_step=1)

    assert len(lines) == 1
    assert "STEP 1" in lines[0]
    assert "agent-Test Customer (test-customer-001)" in lines[0]
    assert "===" in lines[0]


def test_format_step_header_multiple_steps(prompts_handler: PromptsHandler):
    """Test step header formatting for grouped steps."""
    lines = prompts_handler._format_step_header(current_step=5, steps_in_group=3)

    assert len(lines) == 1
    assert "STEPS 3-5" in lines[0]
    assert "agent-Test Customer (test-customer-001)" in lines[0]
    assert "===" in lines[0]


def test_format_state_context(prompts_handler: PromptsHandler):
    """Test that format_state_context includes event history."""
    # Add some events
    action = CustomerAction(
        action_type="check_messages",
        reason="Checking",
    )
    result = FetchMessagesResponse(messages=[], has_more=False)
    prompts_handler.event_history = [(action, result)]  # type: ignore[assignment]

    state_context, step_count = prompts_handler.format_state_context()

    assert "# Action Trajectory" in state_context
    assert "STEP 1" in state_context
    assert step_count == 1


def test_format_system_prompt(prompts_handler: PromptsHandler):
    """Test that system prompt includes customer details."""
    system_prompt = prompts_handler.format_system_prompt()

    assert "Test Customer" in system_prompt
    assert "test-customer-001" in system_prompt
    assert "Looking for test items" in system_prompt
    assert "search_businesses" in system_prompt
    assert "send_messages" in system_prompt
    assert "check_messages" in system_prompt
    assert "end_transaction" in system_prompt


def test_format_step_prompt(prompts_handler: PromptsHandler):
    """Test step prompt formatting."""
    step_prompt = prompts_handler.format_step_prompt(last_step=5)

    assert "Step 6" in step_prompt
    assert "text" in step_prompt
    assert "pay" in step_prompt
    assert "order_proposal" in step_prompt
