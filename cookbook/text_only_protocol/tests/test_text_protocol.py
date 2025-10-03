"""Integration tests for text-only protocol."""

from datetime import UTC, datetime
from typing import Any

import pytest
from magentic_marketplace.platform.database.queries.base import QueryParams

from cookbook.text_only_protocol.actions import CheckMessages, SendTextMessage
from cookbook.text_only_protocol.messaging import TextMessage


class TestSendTextMessage:
    """Test suite for SendTextMessage action."""

    @pytest.mark.asyncio
    async def test_send_text_message_success(
        self, test_agents_with_client: dict[str, Any]
    ):
        """Test sending a text message between agents."""
        agents = test_agents_with_client
        alice = agents["alice"]
        bob = agents["bob"]
        database = agents["database"]

        # Verify clean state
        all_actions_before = await database.actions.get_all(QueryParams())
        assert len(all_actions_before) == 0

        # Alice sends a message to Bob
        message = TextMessage(content="Hello Bob!")
        send_action = SendTextMessage(
            from_agent_id=alice.id,
            to_agent_id=bob.id,
            created_at=datetime.now(UTC),
            message=message,
        )

        result = await alice.execute_action(send_action)
        assert result.is_error is False, f"Action should succeed: {result}"

        # Verify action was logged in database
        all_actions_after = await database.actions.get_all(QueryParams())
        assert len(all_actions_after) == 1
        action_entry = all_actions_after[0]
        assert action_entry.data.agent_id == alice.id
        assert action_entry.data.request.name == "SendTextMessage"

    @pytest.mark.asyncio
    async def test_send_text_message_invalid_recipient(
        self, test_agents_with_client: dict[str, Any]
    ):
        """Test that sending to non-existent agent fails."""
        agents = test_agents_with_client
        alice = agents["alice"]
        database = agents["database"]

        # Alice tries to send to non-existent agent
        message = TextMessage(content="Hello nobody!")
        send_action = SendTextMessage(
            from_agent_id=alice.id,
            to_agent_id="non-existent-agent",
            created_at=datetime.now(UTC),
            message=message,
        )

        result = await alice.execute_action(send_action)
        assert result.is_error is True
        assert "not found" in result.content["error"]

        # Verify failed action was still logged
        all_actions = await database.actions.get_all(QueryParams())
        assert len(all_actions) == 1
        assert all_actions[0].data.result.is_error is True


class TestCheckMessages:
    """Test suite for CheckMessages action."""

    @pytest.mark.asyncio
    async def test_check_messages_empty(self, test_agents_with_client: dict[str, Any]):
        """Test checking messages when there are none."""
        agents = test_agents_with_client
        bob = agents["bob"]

        check_action = CheckMessages()
        result = await bob.execute_action(check_action)

        assert result.is_error is False
        assert result.content["messages"] == []
        assert result.content["has_more"] is False

    @pytest.mark.asyncio
    async def test_check_messages_retrieves_sent_messages(
        self, test_agents_with_client: dict[str, Any]
    ):
        """Test that CheckMessages retrieves messages sent to the agent."""
        agents = test_agents_with_client
        alice = agents["alice"]
        bob = agents["bob"]

        # Alice sends two messages to Bob
        for i in range(2):
            message = TextMessage(content=f"Message {i + 1}")
            send_action = SendTextMessage(
                from_agent_id=alice.id,
                to_agent_id=bob.id,
                created_at=datetime.now(UTC),
                message=message,
            )
            await alice.execute_action(send_action)

        # Bob checks his messages
        check_action = CheckMessages()
        result = await bob.execute_action(check_action)

        assert result.is_error is False
        assert len(result.content["messages"]) == 2
        assert result.content["messages"][0]["message"]["content"] == "Message 1"
        assert result.content["messages"][1]["message"]["content"] == "Message 2"
        assert result.content["has_more"] is False

    @pytest.mark.asyncio
    async def test_check_messages_pagination(
        self, test_agents_with_client: dict[str, Any]
    ):
        """Test pagination of messages."""
        agents = test_agents_with_client
        alice = agents["alice"]
        bob = agents["bob"]

        # Alice sends 5 messages to Bob
        for i in range(5):
            message = TextMessage(content=f"Message {i + 1}")
            send_action = SendTextMessage(
                from_agent_id=alice.id,
                to_agent_id=bob.id,
                created_at=datetime.now(UTC),
                message=message,
            )
            await alice.execute_action(send_action)

        # Bob checks with limit of 2
        check_action = CheckMessages(limit=2)
        result = await bob.execute_action(check_action)

        assert result.is_error is False
        assert len(result.content["messages"]) == 2
        assert result.content["has_more"] is True

        # Bob checks next page
        check_action = CheckMessages(limit=2, offset=2)
        result = await bob.execute_action(check_action)

        assert result.is_error is False
        assert len(result.content["messages"]) == 2
        assert result.content["has_more"] is True

    @pytest.mark.asyncio
    async def test_check_messages_only_retrieves_own_messages(
        self, test_agents_with_client: dict[str, Any]
    ):
        """Test that agents only see messages sent to them."""
        agents = test_agents_with_client
        alice = agents["alice"]
        bob = agents["bob"]

        # Alice sends message to Bob
        message_to_bob = TextMessage(content="For Bob")
        send_to_bob = SendTextMessage(
            from_agent_id=alice.id,
            to_agent_id=bob.id,
            created_at=datetime.now(UTC),
            message=message_to_bob,
        )
        await alice.execute_action(send_to_bob)

        # Bob sends message to Alice
        message_to_alice = TextMessage(content="For Alice")
        send_to_alice = SendTextMessage(
            from_agent_id=bob.id,
            to_agent_id=alice.id,
            created_at=datetime.now(UTC),
            message=message_to_alice,
        )
        await bob.execute_action(send_to_alice)

        # Alice checks her messages - should only see Bob's message
        alice_check = CheckMessages()
        alice_result = await alice.execute_action(alice_check)

        assert alice_result.is_error is False
        assert len(alice_result.content["messages"]) == 1
        assert alice_result.content["messages"][0]["message"]["content"] == "For Alice"

        # Bob checks his messages - should only see Alice's message
        bob_check = CheckMessages()
        bob_result = await bob.execute_action(bob_check)

        assert bob_result.is_error is False
        assert len(bob_result.content["messages"]) == 1
        assert bob_result.content["messages"][0]["message"]["content"] == "For Bob"
