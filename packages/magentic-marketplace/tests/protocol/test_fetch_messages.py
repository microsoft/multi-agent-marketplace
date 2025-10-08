"""Integration tests for FetchMessages action."""

from datetime import UTC, datetime
from typing import Any

import pytest

from magentic_marketplace.marketplace.actions import (
    FetchMessages,
    FetchMessagesResponse,
    SendMessage,
)
from magentic_marketplace.marketplace.actions.messaging import TextMessage
from magentic_marketplace.platform.database.models import AgentRow
from magentic_marketplace.platform.shared.models import AgentProfile


class TestFetchMessages:
    """Simple test suite for FetchMessages action."""

    @pytest.mark.asyncio
    async def test_fetch_messages_returns_agent_specific_rows(
        self, test_agents_with_client: dict[str, Any]
    ):
        """Test that FetchMessages only returns messages for the requesting agent via HTTP."""
        agents = test_agents_with_client
        customer = agents["customer"]
        business = agents["business"]
        database = agents["database"]

        # Send messages between agents
        message_from_biz = SendMessage(
            from_agent_id=business.id,
            to_agent_id=customer.id,
            created_at=datetime.now(UTC),
            message=TextMessage(content="Message to customer"),
        )

        message_from_customer = SendMessage(
            from_agent_id=customer.id,
            to_agent_id=business.id,
            created_at=datetime.now(UTC),
            message=TextMessage(content="Message to business"),
        )

        # Execute messages through HTTP
        await business.execute_action(message_from_biz)
        await customer.execute_action(message_from_customer)

        # Verify messages were logged
        curr_db_state = await database.actions.get_all()
        assert len(curr_db_state) == 2, (
            "Should have 2 send_message actions in the database"
        )

        # Customer fetches their messages
        result = await customer.execute_action(FetchMessages())
        assert result.is_error is False, f"Action should succeed. Failed with: {result}"

        parsed_response = FetchMessagesResponse.model_validate(result.content)
        assert len(parsed_response.messages) == 1, (
            "Response should have 1 message for customer"
        )
        assert parsed_response.messages[0].to_agent_id == customer.id, (
            "Fetched message should be for the customer agent"
        )
        assert parsed_response.has_more is False

        # Business fetches their messages
        result = await business.execute_action(FetchMessages())
        assert result.is_error is False, f"Action should succeed. Failed with: {result}"

        parsed_response = FetchMessagesResponse.model_validate(result.content)
        assert len(parsed_response.messages) == 1, (
            "Response should have 1 message for business"
        )
        assert parsed_response.messages[0].to_agent_id == business.id, (
            "Fetched message should be for the business agent"
        )

        # Verify fetch actions were logged
        all_actions = await database.actions.get_all()
        assert len(all_actions) == 4, (
            "Should have 2 send_message + 2 fetch_messages actions"
        )

        fetch_actions = [
            a for a in all_actions if a.data.request.name == "FetchMessages"
        ]
        assert len(fetch_actions) == 2, "Should have 2 fetch_messages actions"

    @pytest.mark.asyncio
    async def test_fetch_messages_multiple_and_filtering(
        self, test_agents_with_client: dict[str, Any]
    ):
        """Test fetching multiple messages and filtering by sender through HTTP."""
        agents = test_agents_with_client
        customer = agents["customer"]
        business = agents["business"]
        database = agents["database"]

        # Create a third agent directly in the database for this test
        test_agent_supplier = AgentProfile(id="test-supplier", metadata={})
        agent_row = AgentRow(
            id=test_agent_supplier.id,
            created_at=datetime.now(UTC),
            data=test_agent_supplier,
        )
        await database.agents.create(agent_row)

        # Send 3 messages from business to customer
        for i in range(3):
            message = SendMessage(
                from_agent_id=business.id,
                to_agent_id=customer.id,
                created_at=datetime.now(UTC),
                message=TextMessage(content=f"Business message {i + 1}"),
            )
            await business.execute_action(message)

        # Send 2 messages from supplier to customer (simulate via customer agent)
        for i in range(2):
            message = SendMessage(
                from_agent_id=test_agent_supplier.id,
                to_agent_id=customer.id,
                created_at=datetime.now(UTC),
                message=TextMessage(content=f"Supplier message {i + 1}"),
            )
            # Use customer agent to execute since we don't have a supplier agent client
            await customer.execute_action(message)

        # Test 1: Fetch all messages for customer (should get all 5)
        result = await customer.execute_action(FetchMessages())
        assert result.is_error is False, f"Action should succeed. Failed with: {result}"
        parsed_response = FetchMessagesResponse.model_validate(result.content)

        assert len(parsed_response.messages) == 5, (
            f"Response should have 5 messages for customer, got {len(parsed_response.messages)}"
        )

        # Verify all messages are for the customer
        for msg in parsed_response.messages:
            assert msg.to_agent_id == customer.id, (
                "All fetched messages should be for the customer agent"
            )

        # Test 2: Fetch messages from business only (should get 3)
        result = await customer.execute_action(FetchMessages(from_agent_id=business.id))
        assert result.is_error is False, f"Action should succeed. Failed with: {result}"
        parsed_response = FetchMessagesResponse.model_validate(result.content)

        assert len(parsed_response.messages) == 3, (
            f"Response should have 3 messages from business, got {len(parsed_response.messages)}"
        )

        # Verify all messages are from business and to customer
        for msg in parsed_response.messages:
            assert msg.from_agent_id == business.id, (
                "All fetched messages should be from the business agent"
            )
            assert msg.to_agent_id == customer.id, (
                "All fetched messages should be for the customer agent"
            )

        # Test 3: Fetch messages from supplier only (should get 2)
        result = await customer.execute_action(
            FetchMessages(from_agent_id=test_agent_supplier.id)
        )
        assert result.is_error is False, f"Action should succeed. Failed with: {result}"
        parsed_response = FetchMessagesResponse.model_validate(result.content)

        assert len(parsed_response.messages) == 2, (
            f"Response should have 2 messages from supplier, got {len(parsed_response.messages)}"
        )

        # Verify all messages are from supplier and to customer
        for msg in parsed_response.messages:
            assert msg.from_agent_id == test_agent_supplier.id, (
                "All fetched messages should be from the supplier agent"
            )
            assert msg.to_agent_id == customer.id, (
                "All fetched messages should be for the customer agent"
            )

        # Verify all actions were logged (5 send_message + 3 fetch_messages)
        all_actions = await database.actions.get_all()
        assert len(all_actions) == 8, (
            "Should have 5 send_message + 3 fetch_messages actions"
        )

        fetch_actions = [
            a for a in all_actions if a.data.request.name == "FetchMessages"
        ]
        assert len(fetch_actions) == 3, "Should have 3 fetch_messages actions"
