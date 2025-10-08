"""Integration tests for SendMessage action."""

from datetime import UTC, datetime
from typing import Any

import pytest

from magentic_marketplace.marketplace.actions import SendMessage
from magentic_marketplace.marketplace.actions.messaging import (
    OrderItem,
    OrderProposal,
    Payment,
    TextMessage,
)


class TestSendMessage:
    """Simple test suite for SendMessage action."""

    @pytest.mark.asyncio
    async def test_send_message_creates_database_row(
        self, test_agents_with_client: dict[str, Any]
    ):
        """Test that SendMessage action creates a row in the actions table via HTTP."""
        agents = test_agents_with_client
        customer = agents["customer"]
        business = agents["business"]
        database = agents["database"]

        # Verify clean state
        all_actions_before = await database.actions.get_all()
        assert len(all_actions_before) == 0, (
            "Precondition failed: expected empty action table."
        )

        # Create and execute action through HTTP
        message = TextMessage(content="Hello!")
        send_message = SendMessage(
            from_agent_id=customer.id,
            to_agent_id=business.id,
            created_at=datetime.now(UTC),
            message=message,
        )

        # Execute action through client (goes through actions.py route)
        result = await customer.execute_action(send_message)
        assert result.is_error is False, f"Action should succeed. Failed with: {result}"

        # Verify action was logged in database
        all_actions_after = await database.actions.get_all()
        assert len(all_actions_after) == 1, "Action table should have 1 entry"
        action_entry = all_actions_after[0]
        assert action_entry.data.agent_id == customer.id, (
            "Action agent_id should match sender agent_id"
        )
        assert action_entry.data.request.name == "SendMessage", (
            "Action name should be SendMessage"
        )

    @pytest.mark.asyncio
    async def test_send_message_fails_fake_agent(
        self, test_agents_with_client: dict[str, Any]
    ):
        """Test that SendMessage action fails with non-existent recipient."""
        agents = test_agents_with_client
        customer = agents["customer"]
        database = agents["database"]

        # Verify clean state
        all_actions_before = await database.actions.get_all()
        assert len(all_actions_before) == 0, (
            "Precondition failed: expected empty action table."
        )

        # Create action with fake recipient
        fake_id = "super-fake-id"
        message = TextMessage(content="Hello!")
        send_message = SendMessage(
            from_agent_id=customer.id,
            to_agent_id=fake_id,
            created_at=datetime.now(UTC),
            message=message,
        )

        # Execute action through client - should fail
        result = await customer.execute_action(send_message)
        assert result.is_error is True, f"Action should fail. Succeeded with: {result}"

        # Verify action was still logged even though it failed
        all_actions_after = await database.actions.get_all()
        assert len(all_actions_after) == 1, "Failed action should still be logged"
        action_entry = all_actions_after[0]
        assert action_entry.data.agent_id == customer.id
        assert action_entry.data.result.is_error is True

    @pytest.mark.asyncio
    async def test_send_message_creates_order_proposal_and_order(
        self, test_agents_with_client: dict[str, Any]
    ):
        """Test order proposal and payment flow through HTTP."""
        agents = test_agents_with_client
        customer = agents["customer"]
        business = agents["business"]
        database = agents["database"]

        # Verify clean state
        all_actions_before = await database.actions.get_all()
        assert len(all_actions_before) == 0, (
            "Precondition failed: expected empty action table."
        )

        # Business sends order proposal
        order_proposal_message_id = "proposal-001"
        order_proposal = OrderProposal(
            id=order_proposal_message_id,
            items=[
                OrderItem(id="item1", item_name="Item 1", quantity=2, unit_price=10.0)
            ],
            total_price=20.0,
        )
        send_message_proposal = SendMessage(
            from_agent_id=business.id,
            to_agent_id=customer.id,
            created_at=datetime.now(UTC),
            message=order_proposal,
        )

        # Execute proposal through HTTP
        result_proposal = await business.execute_action(send_message_proposal)
        assert result_proposal.is_error is False, (
            f"Proposal should succeed. Failed with: {result_proposal}"
        )

        # Verify proposal action was logged
        all_actions_after = await database.actions.get_all()
        assert len(all_actions_after) == 1, "Action table should have 1 entry"

        # Use the OrderProposal's own ID for payment reference

        payment = Payment(proposal_message_id=order_proposal_message_id)
        send_message_payment = SendMessage(
            from_agent_id=customer.id,
            to_agent_id=business.id,
            created_at=datetime.now(UTC),
            message=payment,
        )

        # Execute payment through HTTP
        result_payment = await customer.execute_action(send_message_payment)
        assert result_payment.is_error is False, (
            f"Payment should succeed. Failed with: {result_payment}"
        )

        # Verify both actions were logged
        all_actions_final = await database.actions.get_all()
        assert len(all_actions_final) == 2, "Action table should have 2 entries"

        # Verify correct agent IDs for each action
        proposal_action = all_actions_final[0]
        payment_action = all_actions_final[1]
        assert proposal_action.data.agent_id == business.id
        assert payment_action.data.agent_id == customer.id

    @pytest.mark.asyncio
    async def test_send_message_validation_failures(
        self, test_agents_with_client: dict[str, Any]
    ):
        """Test all validation failure scenarios through HTTP."""
        agents = test_agents_with_client
        customer = agents["customer"]
        business = agents["business"]
        database = agents["database"]

        # Test 1: Payment with non-existent proposal_message_id
        fake_proposal_id = "non-existent-proposal-id"
        payment_bad_proposal = Payment(proposal_message_id=fake_proposal_id)
        send_message_bad_payment = SendMessage(
            from_agent_id=customer.id,
            to_agent_id=business.id,
            created_at=datetime.now(UTC),
            message=payment_bad_proposal,
        )

        result_bad_payment = await customer.execute_action(send_message_bad_payment)
        assert result_bad_payment.is_error is True
        assert result_bad_payment.content["error_type"] == "invalid_proposal"
        assert (
            "No unexpired order proposals found"
            in result_bad_payment.content["message"]
        )

        # Verify failed action was logged
        actions_after_bad_payment = await database.actions.get_all()
        assert len(actions_after_bad_payment) == 1
        assert actions_after_bad_payment[0].data.result.is_error is True

        # Test 2: Payment referencing an action that's not an order proposal
        # First create a text message (not a proposal)
        text_message = TextMessage(content="Hello!")
        send_text = SendMessage(
            from_agent_id=business.id,
            to_agent_id=customer.id,
            created_at=datetime.now(UTC),
            message=text_message,
        )

        # Send the text message through HTTP
        result_text = await business.execute_action(send_text)
        assert result_text.is_error is False

        # Get the text message action ID from database since the protocol doesn't return it
        text_actions = await database.actions.get_all()
        text_message_action = [
            a for a in text_actions if a.data.request.name == "SendMessage"
        ][-1]  # Get the latest SendMessage
        text_message_id = text_message_action.id
        assert text_message_id is not None, "Text message should have an ID"

        # Now try to pay for the text message (should fail)
        payment_wrong_type = Payment(proposal_message_id=text_message_id)
        send_payment_wrong = SendMessage(
            from_agent_id=customer.id,
            to_agent_id=business.id,
            created_at=datetime.now(UTC),
            message=payment_wrong_type,
        )

        result_wrong_type = await customer.execute_action(send_payment_wrong)
        assert result_wrong_type.is_error is True
        assert result_wrong_type.content["error_type"] == "invalid_proposal"
        assert (
            "No unexpired order proposals found" in result_wrong_type.content["message"]
        )

        # Verify all actions were logged (2 successful, 2 failed)
        all_actions_final = await database.actions.get_all()
        assert len(all_actions_final) == 3  # 1 failed + 1 text + 1 failed payment
