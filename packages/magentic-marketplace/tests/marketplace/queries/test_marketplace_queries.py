"""Integration tests for marketplace database query operations."""

from datetime import UTC, datetime

import pytest

from magentic_marketplace.marketplace.actions import (
    FetchMessages,
    Search,
    SearchAlgorithm,
    SendOrderProposal,
    SendPayment,
    SendTextMessage,
)
from magentic_marketplace.marketplace.database.queries import actions as actions_queries
from magentic_marketplace.marketplace.database.queries import logs as logs_queries
from magentic_marketplace.platform.database.models import (
    ActionRow,
    ActionRowData,
    LogRow,
)
from magentic_marketplace.platform.database.sqlite.sqlite import (
    SQLiteDatabaseController,
)
from magentic_marketplace.platform.shared.models import (
    ActionExecutionRequest,
    ActionExecutionResult,
    Log,
)


class TestFetchMessagesQueries:
    """Test suite for FetchMessages query helpers."""

    @pytest.mark.asyncio
    async def test_all_fetch_messages(self, test_database: SQLiteDatabaseController):
        """Test querying all FetchMessages actions."""
        now = datetime.now(UTC)

        # Create FetchMessages actions
        fetch_action1 = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(
                name=FetchMessages.get_name(),
                parameters={"from_agent_id": "agent-002", "limit": 10},
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )
        fetch_action2 = ActionRowData(
            agent_id="agent-002",
            request=ActionExecutionRequest(
                name=FetchMessages.get_name(),
                parameters={},
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        # Create a non-FetchMessages action
        other_action = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(
                name=Search.get_name(),
                parameters={"query": "test", "search_algorithm": "simple"},
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        await test_database.actions.create(
            ActionRow(id="action-001", created_at=now, data=fetch_action1)
        )
        await test_database.actions.create(
            ActionRow(id="action-002", created_at=now, data=fetch_action2)
        )
        await test_database.actions.create(
            ActionRow(id="action-003", created_at=now, data=other_action)
        )

        # Query for all FetchMessages
        query = actions_queries.fetch_messages.all()
        results = await test_database.actions.find(query)

        assert len(results) == 2
        assert all(r.data.request.name == FetchMessages.get_name() for r in results)


class TestSearchQueries:
    """Test suite for Search query helpers."""

    @pytest.mark.asyncio
    async def test_all_search_actions(self, test_database: SQLiteDatabaseController):
        """Test querying all Search actions."""
        now = datetime.now(UTC)

        # Create Search actions
        search_action1 = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(
                name=Search.get_name(),
                parameters={
                    "query": "pizza",
                    "search_algorithm": SearchAlgorithm.SIMPLE.value,
                    "limit": 10,
                },
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )
        search_action2 = ActionRowData(
            agent_id="agent-002",
            request=ActionExecutionRequest(
                name=Search.get_name(),
                parameters={
                    "query": "sushi",
                    "search_algorithm": SearchAlgorithm.RNR.value,
                    "limit": 5,
                },
            ),
            result=ActionExecutionResult(
                is_error=True, content={"error": "search failed"}
            ),
        )

        # Create a non-Search action
        other_action = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(
                name=FetchMessages.get_name(),
                parameters={},
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        await test_database.actions.create(
            ActionRow(id="action-001", created_at=now, data=search_action1)
        )
        await test_database.actions.create(
            ActionRow(id="action-002", created_at=now, data=search_action2)
        )
        await test_database.actions.create(
            ActionRow(id="action-003", created_at=now, data=other_action)
        )

        # Query for all Search actions
        query = actions_queries.search.all()
        results = await test_database.actions.find(query)

        assert len(results) == 2
        assert all(r.data.request.name == Search.get_name() for r in results)

    @pytest.mark.asyncio
    async def test_successful_search_actions(
        self, test_database: SQLiteDatabaseController
    ):
        """Test querying only successful Search actions."""
        now = datetime.now(UTC)

        # Create successful Search action
        search_success = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(
                name=Search.get_name(),
                parameters={
                    "query": "pizza",
                    "search_algorithm": SearchAlgorithm.SIMPLE.value,
                    "limit": 10,
                },
            ),
            result=ActionExecutionResult(is_error=False, content={"businesses": []}),
        )

        # Create failed Search action
        search_failed = ActionRowData(
            agent_id="agent-002",
            request=ActionExecutionRequest(
                name=Search.get_name(),
                parameters={
                    "query": "sushi",
                    "search_algorithm": SearchAlgorithm.RNR.value,
                    "limit": 5,
                },
            ),
            result=ActionExecutionResult(
                is_error=True, content={"error": "search failed"}
            ),
        )

        await test_database.actions.create(
            ActionRow(id="action-001", created_at=now, data=search_success)
        )
        await test_database.actions.create(
            ActionRow(id="action-002", created_at=now, data=search_failed)
        )

        # Query for successful Search actions only
        query = actions_queries.search.successful()
        results = await test_database.actions.find(query)

        assert len(results) == 1
        assert results[0].data.request.name == Search.get_name()
        assert results[0].data.result.is_error is False


class TestSendMessageQueries:
    """Test suite for SendMessage query helpers."""

    @pytest.mark.asyncio
    async def test_all_send_message_actions(
        self, test_database: SQLiteDatabaseController
    ):
        """Test querying all SendMessage actions."""
        now = datetime.now(UTC)

        # Create different types of SendMessage actions
        text_message = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(
                name=SendTextMessage.get_name(),
                parameters={
                    "from_agent_id": "agent-001",
                    "to_agent_id": "agent-002",
                    "created_at": now.isoformat(),
                    "content": "Hello!",
                },
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        order_proposal = ActionRowData(
            agent_id="agent-002",
            request=ActionExecutionRequest(
                name=SendOrderProposal.get_name(),
                parameters={
                    "from_agent_id": "agent-002",
                    "to_agent_id": "agent-001",
                    "created_at": now.isoformat(),
                    "id": "proposal-001",
                    "items": [
                        {
                            "id": "item1",
                            "item_name": "Pizza",
                            "quantity": 1,
                            "unit_price": 10.0,
                        }
                    ],
                    "total_price": 10.0,
                },
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        payment = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(
                name=SendPayment.get_name(),
                parameters={
                    "from_agent_id": "agent-001",
                    "to_agent_id": "agent-002",
                    "created_at": now.isoformat(),
                    "proposal_message_id": "proposal-001",
                },
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        # Create a non-SendMessage action
        other_action = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(
                name=Search.get_name(),
                parameters={"query": "test", "search_algorithm": "simple"},
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        await test_database.actions.create(
            ActionRow(id="action-001", created_at=now, data=text_message)
        )
        await test_database.actions.create(
            ActionRow(id="action-002", created_at=now, data=order_proposal)
        )
        await test_database.actions.create(
            ActionRow(id="action-003", created_at=now, data=payment)
        )
        await test_database.actions.create(
            ActionRow(id="action-004", created_at=now, data=other_action)
        )

        # Query for all SendMessage actions
        query = actions_queries.send_message.all()
        results = await test_database.actions.find(query)

        assert len(results) == 3
        message_types = {r.data.request.name for r in results}
        expected_types = {
            SendTextMessage.get_name(),
            SendOrderProposal.get_name(),
            SendPayment.get_name(),
        }
        assert message_types == expected_types

    @pytest.mark.asyncio
    async def test_from_agent_filter(self, test_database: SQLiteDatabaseController):
        """Test querying SendMessage actions from a specific agent."""
        now = datetime.now(UTC)

        # Create messages from different agents
        message_from_001 = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(
                name=SendTextMessage.get_name(),
                parameters={
                    "from_agent_id": "agent-001",
                    "to_agent_id": "agent-002",
                    "created_at": now.isoformat(),
                    "content": "Hello from 001",
                },
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        message_from_002 = ActionRowData(
            agent_id="agent-002",
            request=ActionExecutionRequest(
                name=SendTextMessage.get_name(),
                parameters={
                    "from_agent_id": "agent-002",
                    "to_agent_id": "agent-001",
                    "created_at": now.isoformat(),
                    "content": "Hello from 002",
                },
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        message_from_001_again = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(
                name=SendTextMessage.get_name(),
                parameters={
                    "from_agent_id": "agent-001",
                    "to_agent_id": "agent-003",
                    "created_at": now.isoformat(),
                    "content": "Hello from 001 again",
                },
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        await test_database.actions.create(
            ActionRow(id="action-001", created_at=now, data=message_from_001)
        )
        await test_database.actions.create(
            ActionRow(id="action-002", created_at=now, data=message_from_002)
        )
        await test_database.actions.create(
            ActionRow(id="action-003", created_at=now, data=message_from_001_again)
        )

        # Query for messages from agent-001
        query = actions_queries.send_message.from_agent("agent-001")
        results = await test_database.actions.find(query)

        assert len(results) == 2
        assert all(
            r.data.request.parameters["from_agent_id"] == "agent-001" for r in results
        )

    @pytest.mark.asyncio
    async def test_to_agent_filter(self, test_database: SQLiteDatabaseController):
        """Test querying SendMessage actions to a specific agent."""
        now = datetime.now(UTC)

        # Create messages to different agents
        message_to_001 = ActionRowData(
            agent_id="agent-002",
            request=ActionExecutionRequest(
                name=SendTextMessage.get_name(),
                parameters={
                    "from_agent_id": "agent-002",
                    "to_agent_id": "agent-001",
                    "created_at": now.isoformat(),
                    "content": "Hello to 001",
                },
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        message_to_002 = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(
                name=SendTextMessage.get_name(),
                parameters={
                    "from_agent_id": "agent-001",
                    "to_agent_id": "agent-002",
                    "created_at": now.isoformat(),
                    "content": "Hello to 002",
                },
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        message_to_001_again = ActionRowData(
            agent_id="agent-003",
            request=ActionExecutionRequest(
                name=SendTextMessage.get_name(),
                parameters={
                    "from_agent_id": "agent-003",
                    "to_agent_id": "agent-001",
                    "created_at": now.isoformat(),
                    "content": "Hello to 001 again",
                },
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        await test_database.actions.create(
            ActionRow(id="action-001", created_at=now, data=message_to_001)
        )
        await test_database.actions.create(
            ActionRow(id="action-002", created_at=now, data=message_to_002)
        )
        await test_database.actions.create(
            ActionRow(id="action-003", created_at=now, data=message_to_001_again)
        )

        # Query for messages to agent-001
        query = actions_queries.send_message.to_agent("agent-001")
        results = await test_database.actions.find(query)

        assert len(results) == 2
        assert all(
            r.data.request.parameters["to_agent_id"] == "agent-001" for r in results
        )

    @pytest.mark.asyncio
    async def test_order_proposals_filter(
        self, test_database: SQLiteDatabaseController
    ):
        """Test querying only OrderProposal messages."""
        now = datetime.now(UTC)

        # Create different message types
        text_message = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(
                name=SendTextMessage.get_name(),
                parameters={
                    "from_agent_id": "agent-001",
                    "to_agent_id": "agent-002",
                    "created_at": now.isoformat(),
                    "content": "Hello!",
                },
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        order_proposal1 = ActionRowData(
            agent_id="agent-002",
            request=ActionExecutionRequest(
                name=SendOrderProposal.get_name(),
                parameters={
                    "from_agent_id": "agent-002",
                    "to_agent_id": "agent-001",
                    "created_at": now.isoformat(),
                    "id": "proposal-001",
                    "items": [
                        {
                            "id": "item1",
                            "item_name": "Pizza",
                            "quantity": 1,
                            "unit_price": 10.0,
                        }
                    ],
                    "total_price": 10.0,
                },
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        order_proposal2 = ActionRowData(
            agent_id="agent-002",
            request=ActionExecutionRequest(
                name=SendOrderProposal.get_name(),
                parameters={
                    "from_agent_id": "agent-002",
                    "to_agent_id": "agent-001",
                    "created_at": now.isoformat(),
                    "id": "proposal-002",
                    "items": [
                        {
                            "id": "item2",
                            "item_name": "Pasta",
                            "quantity": 2,
                            "unit_price": 15.0,
                        }
                    ],
                    "total_price": 30.0,
                },
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        await test_database.actions.create(
            ActionRow(id="action-001", created_at=now, data=text_message)
        )
        await test_database.actions.create(
            ActionRow(id="action-002", created_at=now, data=order_proposal1)
        )
        await test_database.actions.create(
            ActionRow(id="action-003", created_at=now, data=order_proposal2)
        )

        # Query for order proposals only
        query = actions_queries.send_message.order_proposals()
        results = await test_database.actions.find(query)

        assert len(results) == 2
        assert all(r.data.request.name == SendOrderProposal.get_name() for r in results)

    @pytest.mark.asyncio
    async def test_order_proposal_by_id(self, test_database: SQLiteDatabaseController):
        """Test querying OrderProposal by proposal ID."""
        now = datetime.now(UTC)

        # Create order proposals with different IDs
        order_proposal1 = ActionRowData(
            agent_id="agent-002",
            request=ActionExecutionRequest(
                name=SendOrderProposal.get_name(),
                parameters={
                    "from_agent_id": "agent-002",
                    "to_agent_id": "agent-001",
                    "created_at": now.isoformat(),
                    "id": "proposal-001",
                    "items": [
                        {
                            "id": "item1",
                            "item_name": "Pizza",
                            "quantity": 1,
                            "unit_price": 10.0,
                        }
                    ],
                    "total_price": 10.0,
                },
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        order_proposal2 = ActionRowData(
            agent_id="agent-002",
            request=ActionExecutionRequest(
                name=SendOrderProposal.get_name(),
                parameters={
                    "from_agent_id": "agent-002",
                    "to_agent_id": "agent-001",
                    "created_at": now.isoformat(),
                    "id": "proposal-002",
                    "items": [
                        {
                            "id": "item2",
                            "item_name": "Pasta",
                            "quantity": 2,
                            "unit_price": 15.0,
                        }
                    ],
                    "total_price": 30.0,
                },
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        await test_database.actions.create(
            ActionRow(id="action-001", created_at=now, data=order_proposal1)
        )
        await test_database.actions.create(
            ActionRow(id="action-002", created_at=now, data=order_proposal2)
        )

        # Query for specific proposal by ID
        query = actions_queries.send_message.order_proposal_id("proposal-001")
        results = await test_database.actions.find(query)

        assert len(results) == 1
        assert results[0].data.request.parameters["id"] == "proposal-001"

    @pytest.mark.asyncio
    async def test_combined_from_and_to_agent_filters(
        self, test_database: SQLiteDatabaseController
    ):
        """Test combining from_agent and to_agent filters."""
        now = datetime.now(UTC)

        # Create messages between different agents
        message_001_to_002 = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(
                name=SendTextMessage.get_name(),
                parameters={
                    "from_agent_id": "agent-001",
                    "to_agent_id": "agent-002",
                    "created_at": now.isoformat(),
                    "content": "From 001 to 002",
                },
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        message_001_to_003 = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(
                name=SendTextMessage.get_name(),
                parameters={
                    "from_agent_id": "agent-001",
                    "to_agent_id": "agent-003",
                    "created_at": now.isoformat(),
                    "content": "From 001 to 003",
                },
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        message_002_to_002 = ActionRowData(
            agent_id="agent-002",
            request=ActionExecutionRequest(
                name=SendTextMessage.get_name(),
                parameters={
                    "from_agent_id": "agent-002",
                    "to_agent_id": "agent-002",
                    "created_at": now.isoformat(),
                    "content": "From 002 to 002",
                },
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        await test_database.actions.create(
            ActionRow(id="action-001", created_at=now, data=message_001_to_002)
        )
        await test_database.actions.create(
            ActionRow(id="action-002", created_at=now, data=message_001_to_003)
        )
        await test_database.actions.create(
            ActionRow(id="action-003", created_at=now, data=message_002_to_002)
        )

        # Query for messages from agent-001 to agent-002
        query = actions_queries.send_message.from_agent(
            "agent-001"
        ) & actions_queries.send_message.to_agent("agent-002")
        results = await test_database.actions.find(query)

        assert len(results) == 1
        assert results[0].data.request.parameters["from_agent_id"] == "agent-001"
        assert results[0].data.request.parameters["to_agent_id"] == "agent-002"


class TestLLMCallQueries:
    """Test suite for LLM call log query helpers."""

    @pytest.mark.asyncio
    async def test_all_llm_call_logs(self, test_database: SQLiteDatabaseController):
        """Test querying all LLM call logs."""
        now = datetime.now(UTC)

        # Create LLM call logs
        llm_call1 = Log(
            name="llm_logger",
            level="info",
            message="LLM call completed",
            data={
                "type": "llm_call",
                "status": "SUCCESS",
                "model": "gpt-4",
                "tokens": 100,
            },
            metadata={},
        )

        llm_call2 = Log(
            name="llm_logger",
            level="error",
            message="LLM call failed",
            data={
                "type": "llm_call",
                "status": "ERROR",
                "model": "gpt-4",
                "error": "timeout",
            },
            metadata={},
        )

        # Create a non-LLM call log
        other_log = Log(
            name="app_logger",
            level="info",
            message="Application started",
            data={"type": "app_event", "event": "startup"},
            metadata={},
        )

        await test_database.logs.create(
            LogRow(id="log-001", created_at=now, data=llm_call1)
        )
        await test_database.logs.create(
            LogRow(id="log-002", created_at=now, data=llm_call2)
        )
        await test_database.logs.create(
            LogRow(id="log-003", created_at=now, data=other_log)
        )

        # Query for all LLM call logs
        query = logs_queries.llm_call.all()
        results = await test_database.logs.find(query)

        assert len(results) == 2
        assert all(
            isinstance(r.data.data, dict) and r.data.data.get("type") == "llm_call"
            for r in results
        )

    @pytest.mark.asyncio
    async def test_llm_calls_by_status(self, test_database: SQLiteDatabaseController):
        """Test querying LLM calls by status."""
        now = datetime.now(UTC)

        # Create LLM calls with different statuses
        llm_success1 = Log(
            name="llm_logger",
            level="info",
            message="LLM call completed",
            data={
                "type": "llm_call",
                "status": "SUCCESS",
                "model": "gpt-4",
                "tokens": 100,
            },
            metadata={},
        )

        llm_success2 = Log(
            name="llm_logger",
            level="info",
            message="LLM call completed",
            data={
                "type": "llm_call",
                "status": "SUCCESS",
                "model": "claude-3",
                "tokens": 150,
            },
            metadata={},
        )

        llm_error = Log(
            name="llm_logger",
            level="error",
            message="LLM call failed",
            data={
                "type": "llm_call",
                "status": "ERROR",
                "model": "gpt-4",
                "error": "timeout",
            },
            metadata={},
        )

        await test_database.logs.create(
            LogRow(id="log-001", created_at=now, data=llm_success1)
        )
        await test_database.logs.create(
            LogRow(id="log-002", created_at=now, data=llm_success2)
        )
        await test_database.logs.create(
            LogRow(id="log-003", created_at=now, data=llm_error)
        )

        # Query for SUCCESS status
        query = logs_queries.llm_call.by_status("SUCCESS")
        results = await test_database.logs.find(query)

        assert len(results) == 2
        assert all(
            isinstance(r.data.data, dict) and r.data.data.get("status") == "SUCCESS"
            for r in results
        )

        # Query for ERROR status
        query = logs_queries.llm_call.by_status("ERROR")
        results = await test_database.logs.find(query)

        assert len(results) == 1
        assert (
            isinstance(results[0].data.data, dict)
            and results[0].data.data.get("status") == "ERROR"
        )

    @pytest.mark.asyncio
    async def test_failed_llm_calls(self, test_database: SQLiteDatabaseController):
        """Test querying only failed LLM calls."""
        now = datetime.now(UTC)

        # Create successful and failed LLM calls
        llm_success = Log(
            name="llm_logger",
            level="info",
            message="LLM call completed",
            data={
                "type": "llm_call",
                "status": "SUCCESS",
                "model": "gpt-4",
                "tokens": 100,
            },
            metadata={},
        )

        llm_error1 = Log(
            name="llm_logger",
            level="error",
            message="LLM call failed - timeout",
            data={
                "type": "llm_call",
                "status": "ERROR",
                "model": "gpt-4",
                "error": "timeout",
            },
            metadata={},
        )

        llm_error2 = Log(
            name="llm_logger",
            level="error",
            message="LLM call failed - rate limit",
            data={
                "type": "llm_call",
                "status": "ERROR",
                "model": "claude-3",
                "error": "rate_limit",
            },
            metadata={},
        )

        await test_database.logs.create(
            LogRow(id="log-001", created_at=now, data=llm_success)
        )
        await test_database.logs.create(
            LogRow(id="log-002", created_at=now, data=llm_error1)
        )
        await test_database.logs.create(
            LogRow(id="log-003", created_at=now, data=llm_error2)
        )

        # Query for failed LLM calls
        query = logs_queries.llm_call.failed()
        results = await test_database.logs.find(query)

        assert len(results) == 2
        assert all(
            isinstance(r.data.data, dict) and r.data.data.get("status") == "ERROR"
            for r in results
        )


class TestCombinedMarketplaceQueries:
    """Test suite for combined marketplace queries."""

    @pytest.mark.asyncio
    async def test_all_actions_query(self, test_database: SQLiteDatabaseController):
        """Test the combined all() query that includes all marketplace actions."""
        now = datetime.now(UTC)

        # Create various marketplace actions
        fetch_action = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(
                name=FetchMessages.get_name(),
                parameters={},
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        search_action = ActionRowData(
            agent_id="agent-002",
            request=ActionExecutionRequest(
                name=Search.get_name(),
                parameters={"query": "pizza", "search_algorithm": "simple"},
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        send_message_action = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(
                name=SendTextMessage.get_name(),
                parameters={
                    "from_agent_id": "agent-001",
                    "to_agent_id": "agent-002",
                    "created_at": now.isoformat(),
                    "content": "Hello!",
                },
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        # Create a non-marketplace action (hypothetical)
        other_action = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(
                name="UnknownAction",
                parameters={},
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        await test_database.actions.create(
            ActionRow(id="action-001", created_at=now, data=fetch_action)
        )
        await test_database.actions.create(
            ActionRow(id="action-002", created_at=now, data=search_action)
        )
        await test_database.actions.create(
            ActionRow(id="action-003", created_at=now, data=send_message_action)
        )
        await test_database.actions.create(
            ActionRow(id="action-004", created_at=now, data=other_action)
        )

        # Query for all marketplace actions (combining all action types)
        query = (
            actions_queries.fetch_messages.all()
            | actions_queries.search.all()
            | actions_queries.send_message.all()
        )
        results = await test_database.actions.find(query)

        assert len(results) == 3
        action_names = {r.data.request.name for r in results}
        expected_names = {
            FetchMessages.get_name(),
            Search.get_name(),
            SendTextMessage.get_name(),
        }
        assert action_names == expected_names
