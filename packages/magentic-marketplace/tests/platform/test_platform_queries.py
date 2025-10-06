"""Integration tests for database query operations."""

from datetime import UTC, datetime, timedelta

import pytest

from magentic_marketplace.platform.database.models import (
    ActionRow,
    ActionRowData,
    AgentRow,
    LogRow,
)
from magentic_marketplace.platform.database.queries import RangeQueryParams
from magentic_marketplace.platform.database.queries import actions as actions_query
from magentic_marketplace.platform.database.queries import agents as agents_query
from magentic_marketplace.platform.database.queries import logs as logs_query
from magentic_marketplace.platform.database.sqlite.sqlite import (
    SQLiteDatabaseController,
)
from magentic_marketplace.platform.shared.models import (
    ActionExecutionRequest,
    ActionExecutionResult,
    AgentProfile,
    BaseAction,
    Log,
)


class DummyAction(BaseAction):
    """Dummy action for testing."""

    test_field: str
    numeric_field: int = 0


class TestAgentsQuery:
    """Test suite for AgentsQuery operations."""

    @pytest.mark.asyncio
    async def test_query_by_id_equals(self, test_database: SQLiteDatabaseController):
        """Test querying agents by ID with equals operator."""
        # Create test agents
        agent1 = AgentProfile(id="agent-001", metadata={"type": "customer"})
        agent2 = AgentProfile(id="agent-002", metadata={"type": "business"})

        await test_database.agents.create(
            AgentRow(id=agent1.id, created_at=datetime.now(UTC), data=agent1)
        )
        await test_database.agents.create(
            AgentRow(id=agent2.id, created_at=datetime.now(UTC), data=agent2)
        )

        # Query for specific agent
        query = agents_query.id(value="agent-001", operator="=")
        results = await test_database.agents.find(query)

        assert len(results) == 1
        assert results[0].data.id == "agent-001"

    @pytest.mark.asyncio
    async def test_query_by_id_not_equals(
        self, test_database: SQLiteDatabaseController
    ):
        """Test querying agents by ID with not equals operator."""
        agent1 = AgentProfile(id="agent-001", metadata={"type": "customer"})
        agent2 = AgentProfile(id="agent-002", metadata={"type": "business"})

        await test_database.agents.create(
            AgentRow(id=agent1.id, created_at=datetime.now(UTC), data=agent1)
        )
        await test_database.agents.create(
            AgentRow(id=agent2.id, created_at=datetime.now(UTC), data=agent2)
        )

        # Query for agents not matching specific ID
        query = agents_query.id(value="agent-001", operator="!=")
        results = await test_database.agents.find(query)

        assert len(results) == 1
        assert results[0].data.id == "agent-002"

    @pytest.mark.asyncio
    async def test_query_metadata_field(self, test_database: SQLiteDatabaseController):
        """Test querying agents by metadata field."""
        agent1 = AgentProfile(
            id="agent-001", metadata={"type": "customer", "priority": 1}
        )
        agent2 = AgentProfile(
            id="agent-002", metadata={"type": "business", "priority": 2}
        )
        agent3 = AgentProfile(
            id="agent-003", metadata={"type": "customer", "priority": 3}
        )

        await test_database.agents.create(
            AgentRow(id=agent1.id, created_at=datetime.now(UTC), data=agent1)
        )
        await test_database.agents.create(
            AgentRow(id=agent2.id, created_at=datetime.now(UTC), data=agent2)
        )
        await test_database.agents.create(
            AgentRow(id=agent3.id, created_at=datetime.now(UTC), data=agent3)
        )

        # Query by metadata type
        query = agents_query.metadata(path="type", value="customer", operator="=")
        results = await test_database.agents.find(query)

        assert len(results) == 2
        assert all(r.data.metadata["type"] == "customer" for r in results)

    @pytest.mark.asyncio
    async def test_compound_query_and(self, test_database: SQLiteDatabaseController):
        """Test AND compound query on agents."""
        agent1 = AgentProfile(
            id="agent-001", metadata={"type": "customer", "status": "active"}
        )
        agent2 = AgentProfile(
            id="agent-002", metadata={"type": "customer", "status": "inactive"}
        )
        agent3 = AgentProfile(
            id="agent-003", metadata={"type": "business", "status": "active"}
        )

        await test_database.agents.create(
            AgentRow(id=agent1.id, created_at=datetime.now(UTC), data=agent1)
        )
        await test_database.agents.create(
            AgentRow(id=agent2.id, created_at=datetime.now(UTC), data=agent2)
        )
        await test_database.agents.create(
            AgentRow(id=agent3.id, created_at=datetime.now(UTC), data=agent3)
        )

        # Query for customers that are active
        query = agents_query.metadata(
            path="type", value="customer", operator="="
        ) & agents_query.metadata(path="status", value="active", operator="=")
        results = await test_database.agents.find(query)

        assert len(results) == 1
        assert results[0].data.id == "agent-001"

    @pytest.mark.asyncio
    async def test_compound_query_or(self, test_database: SQLiteDatabaseController):
        """Test OR compound query on agents."""
        agent1 = AgentProfile(id="agent-001", metadata={"type": "customer"})
        agent2 = AgentProfile(id="agent-002", metadata={"type": "business"})
        agent3 = AgentProfile(id="agent-003", metadata={"type": "supplier"})

        await test_database.agents.create(
            AgentRow(id=agent1.id, created_at=datetime.now(UTC), data=agent1)
        )
        await test_database.agents.create(
            AgentRow(id=agent2.id, created_at=datetime.now(UTC), data=agent2)
        )
        await test_database.agents.create(
            AgentRow(id=agent3.id, created_at=datetime.now(UTC), data=agent3)
        )

        # Query for customers OR businesses
        query = agents_query.metadata(
            path="type", value="customer", operator="="
        ) | agents_query.metadata(path="type", value="business", operator="=")
        results = await test_database.agents.find(query)

        assert len(results) == 2
        types = {r.data.metadata["type"] for r in results}
        assert types == {"customer", "business"}


class TestActionsQuery:
    """Test suite for ActionsQuery operations."""

    @pytest.mark.asyncio
    async def test_query_by_agent_id(self, test_database: SQLiteDatabaseController):
        """Test querying actions by agent_id."""
        now = datetime.now(UTC)

        # Create dummy actions for different agents
        action1 = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(
                name="DummyAction",
                parameters={"test_field": "value1", "numeric_field": 10},
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )
        action2 = ActionRowData(
            agent_id="agent-002",
            request=ActionExecutionRequest(
                name="DummyAction",
                parameters={"test_field": "value2", "numeric_field": 20},
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        await test_database.actions.create(
            ActionRow(id="action-001", created_at=now, data=action1)
        )
        await test_database.actions.create(
            ActionRow(id="action-002", created_at=now, data=action2)
        )

        # Query by agent_id
        query = actions_query.agent_id(value="agent-001", operator="=")
        results = await test_database.actions.find(query)

        assert len(results) == 1
        assert results[0].data.agent_id == "agent-001"

    @pytest.mark.asyncio
    async def test_query_by_request_name(self, test_database: SQLiteDatabaseController):
        """Test querying actions by request name."""
        now = datetime.now(UTC)

        action1 = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(name="ActionType1", parameters={}),
            result=ActionExecutionResult(is_error=False, content={}),
        )
        action2 = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(name="ActionType2", parameters={}),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        await test_database.actions.create(
            ActionRow(id="action-001", created_at=now, data=action1)
        )
        await test_database.actions.create(
            ActionRow(id="action-002", created_at=now, data=action2)
        )

        # Query by request name
        query = actions_query.request_name(value="ActionType1", operator="=")
        results = await test_database.actions.find(query)

        assert len(results) == 1
        assert results[0].data.request.name == "ActionType1"

    @pytest.mark.asyncio
    async def test_query_by_request_action_type(
        self, test_database: SQLiteDatabaseController
    ):
        """Test querying actions by action type using request_action helper."""
        now = datetime.now(UTC)

        action1 = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(
                name=DummyAction.get_name(), parameters={"test_field": "value1"}
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )
        action2 = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(name="OtherAction", parameters={}),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        await test_database.actions.create(
            ActionRow(id="action-001", created_at=now, data=action1)
        )
        await test_database.actions.create(
            ActionRow(id="action-002", created_at=now, data=action2)
        )

        # Query by action type
        query = actions_query.request_action(action=DummyAction, operator="=")
        results = await test_database.actions.find(query)

        assert len(results) == 1
        assert results[0].data.request.name == DummyAction.get_name()

    @pytest.mark.asyncio
    async def test_query_by_request_parameters(
        self, test_database: SQLiteDatabaseController
    ):
        """Test querying actions by request parameters."""
        now = datetime.now(UTC)

        action1 = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(
                name="DummyAction",
                parameters={"test_field": "value1", "numeric_field": 10},
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )
        action2 = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(
                name="DummyAction",
                parameters={"test_field": "value2", "numeric_field": 20},
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        await test_database.actions.create(
            ActionRow(id="action-001", created_at=now, data=action1)
        )
        await test_database.actions.create(
            ActionRow(id="action-002", created_at=now, data=action2)
        )

        # Query by parameter value
        query = actions_query.request_parameters(
            path="test_field", value="value1", operator="="
        )
        results = await test_database.actions.find(query)

        assert len(results) == 1
        assert results[0].data.request.parameters["test_field"] == "value1"

    @pytest.mark.asyncio
    async def test_query_by_numeric_parameter_comparison(
        self, test_database: SQLiteDatabaseController
    ):
        """Test querying actions by numeric parameters with comparison operators."""
        now = datetime.now(UTC)

        action1 = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(
                name="DummyAction", parameters={"numeric_field": 10}
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )
        action2 = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(
                name="DummyAction", parameters={"numeric_field": 20}
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )
        action3 = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(
                name="DummyAction", parameters={"numeric_field": 30}
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        await test_database.actions.create(
            ActionRow(id="action-001", created_at=now, data=action1)
        )
        await test_database.actions.create(
            ActionRow(id="action-002", created_at=now, data=action2)
        )
        await test_database.actions.create(
            ActionRow(id="action-003", created_at=now, data=action3)
        )

        # Test > operator
        query = actions_query.request_parameters(
            path="numeric_field", value=15, operator=">"
        )
        results = await test_database.actions.find(query)
        assert len(results) == 2
        assert all(r.data.request.parameters["numeric_field"] > 15 for r in results)

        # Test >= operator
        query = actions_query.request_parameters(
            path="numeric_field", value=20, operator=">="
        )
        results = await test_database.actions.find(query)
        assert len(results) == 2
        assert all(r.data.request.parameters["numeric_field"] >= 20 for r in results)

        # Test < operator
        query = actions_query.request_parameters(
            path="numeric_field", value=25, operator="<"
        )
        results = await test_database.actions.find(query)
        assert len(results) == 2
        assert all(r.data.request.parameters["numeric_field"] < 25 for r in results)

        # Test <= operator
        query = actions_query.request_parameters(
            path="numeric_field", value=20, operator="<="
        )
        results = await test_database.actions.find(query)
        assert len(results) == 2
        assert all(r.data.request.parameters["numeric_field"] <= 20 for r in results)

    @pytest.mark.asyncio
    async def test_query_by_result_is_error(
        self, test_database: SQLiteDatabaseController
    ):
        """Test querying actions by result error status."""
        now = datetime.now(UTC)

        action1 = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(name="DummyAction", parameters={}),
            result=ActionExecutionResult(is_error=False, content={}),
        )
        action2 = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(name="DummyAction", parameters={}),
            result=ActionExecutionResult(
                is_error=True, content={"error": "Something went wrong"}
            ),
        )

        await test_database.actions.create(
            ActionRow(id="action-001", created_at=now, data=action1)
        )
        await test_database.actions.create(
            ActionRow(id="action-002", created_at=now, data=action2)
        )

        # Query for errors
        query = actions_query.result_is_error(value=True, operator="=")
        results = await test_database.actions.find(query)

        assert len(results) == 1
        assert results[0].data.result.is_error is True

        # Query for successes
        query = actions_query.result_is_error(value=False, operator="=")
        results = await test_database.actions.find(query)

        assert len(results) == 1
        assert results[0].data.result.is_error is False

    @pytest.mark.asyncio
    async def test_compound_query_actions(
        self, test_database: SQLiteDatabaseController
    ):
        """Test compound queries on actions."""
        now = datetime.now(UTC)

        action1 = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(
                name="DummyAction", parameters={"numeric_field": 10}
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )
        action2 = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(
                name="DummyAction", parameters={"numeric_field": 20}
            ),
            result=ActionExecutionResult(is_error=True, content={}),
        )
        action3 = ActionRowData(
            agent_id="agent-002",
            request=ActionExecutionRequest(
                name="DummyAction", parameters={"numeric_field": 30}
            ),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        await test_database.actions.create(
            ActionRow(id="action-001", created_at=now, data=action1)
        )
        await test_database.actions.create(
            ActionRow(id="action-002", created_at=now, data=action2)
        )
        await test_database.actions.create(
            ActionRow(id="action-003", created_at=now, data=action3)
        )

        # Query for agent-001 AND not error
        query = actions_query.agent_id(
            value="agent-001", operator="="
        ) & actions_query.result_is_error(value=False, operator="=")
        results = await test_database.actions.find(query)

        assert len(results) == 1
        assert results[0].data.agent_id == "agent-001"
        assert results[0].data.result.is_error is False


class TestLogsQuery:
    """Test suite for LogQuery operations."""

    @pytest.mark.asyncio
    async def test_query_by_level(self, test_database: SQLiteDatabaseController):
        """Test querying logs by level."""
        now = datetime.now(UTC)

        log1 = Log(
            name="test", level="info", message="Info message", data={}, metadata={}
        )
        log2 = Log(
            name="test", level="error", message="Error message", data={}, metadata={}
        )
        log3 = Log(
            name="test", level="info", message="Another info", data={}, metadata={}
        )

        await test_database.logs.create(LogRow(id="log-001", created_at=now, data=log1))
        await test_database.logs.create(LogRow(id="log-002", created_at=now, data=log2))
        await test_database.logs.create(LogRow(id="log-003", created_at=now, data=log3))

        # Query for info logs
        query = logs_query.level(value="info", operator="=")
        results = await test_database.logs.find(query)

        assert len(results) == 2
        assert all(r.data.level == "info" for r in results)

    @pytest.mark.asyncio
    async def test_query_by_name(self, test_database: SQLiteDatabaseController):
        """Test querying logs by name."""
        now = datetime.now(UTC)

        log1 = Log(
            name="module1", level="info", message="Message 1", data={}, metadata={}
        )
        log2 = Log(
            name="module2", level="info", message="Message 2", data={}, metadata={}
        )
        log3 = Log(
            name="module1", level="error", message="Message 3", data={}, metadata={}
        )

        await test_database.logs.create(LogRow(id="log-001", created_at=now, data=log1))
        await test_database.logs.create(LogRow(id="log-002", created_at=now, data=log2))
        await test_database.logs.create(LogRow(id="log-003", created_at=now, data=log3))

        # Query for module1 logs
        query = logs_query.name(value="module1", operator="=")
        results = await test_database.logs.find(query)

        assert len(results) == 2
        assert all(r.data.name == "module1" for r in results)

    @pytest.mark.asyncio
    async def test_query_by_message(self, test_database: SQLiteDatabaseController):
        """Test querying logs by message."""
        now = datetime.now(UTC)

        log1 = Log(
            name="test", level="info", message="Hello world", data={}, metadata={}
        )
        log2 = Log(
            name="test", level="info", message="Goodbye world", data={}, metadata={}
        )

        await test_database.logs.create(LogRow(id="log-001", created_at=now, data=log1))
        await test_database.logs.create(LogRow(id="log-002", created_at=now, data=log2))

        # Query by exact message
        query = logs_query.message(value="Hello world", operator="=")
        results = await test_database.logs.find(query)

        assert len(results) == 1
        assert results[0].data.message == "Hello world"

    @pytest.mark.asyncio
    async def test_query_by_data_field(self, test_database: SQLiteDatabaseController):
        """Test querying logs by data field."""
        now = datetime.now(UTC)

        log1 = Log(
            name="test",
            level="info",
            message="Message 1",
            data={"user_id": "user-001", "action": "login"},
            metadata={},
        )
        log2 = Log(
            name="test",
            level="info",
            message="Message 2",
            data={"user_id": "user-002", "action": "logout"},
            metadata={},
        )
        log3 = Log(
            name="test",
            level="info",
            message="Message 3",
            data={"user_id": "user-001", "action": "logout"},
            metadata={},
        )

        await test_database.logs.create(LogRow(id="log-001", created_at=now, data=log1))
        await test_database.logs.create(LogRow(id="log-002", created_at=now, data=log2))
        await test_database.logs.create(LogRow(id="log-003", created_at=now, data=log3))

        # Query by data.user_id
        query = logs_query.data(path="user_id", value="user-001", operator="=")
        results = await test_database.logs.find(query)

        assert len(results) == 2
        assert all(
            isinstance(r.data.data, dict) and r.data.data["user_id"] == "user-001"
            for r in results
        )

    @pytest.mark.asyncio
    async def test_query_by_metadata_field(
        self, test_database: SQLiteDatabaseController
    ):
        """Test querying logs by metadata field."""
        now = datetime.now(UTC)

        log1 = Log(
            name="test",
            level="info",
            message="Message 1",
            data={},
            metadata={"source": "api", "version": "1.0"},
        )
        log2 = Log(
            name="test",
            level="info",
            message="Message 2",
            data={},
            metadata={"source": "cli", "version": "1.0"},
        )
        log3 = Log(
            name="test",
            level="info",
            message="Message 3",
            data={},
            metadata={"source": "api", "version": "2.0"},
        )

        await test_database.logs.create(LogRow(id="log-001", created_at=now, data=log1))
        await test_database.logs.create(LogRow(id="log-002", created_at=now, data=log2))
        await test_database.logs.create(LogRow(id="log-003", created_at=now, data=log3))

        # Query by metadata.source
        query = logs_query.metadata(path="source", value="api", operator="=")
        results = await test_database.logs.find(query)

        assert len(results) == 2
        assert all(
            r.data.metadata and r.data.metadata["source"] == "api" for r in results
        )

    @pytest.mark.asyncio
    async def test_compound_query_logs(self, test_database: SQLiteDatabaseController):
        """Test compound queries on logs."""
        now = datetime.now(UTC)

        log1 = Log(
            name="module1", level="error", message="Error 1", data={}, metadata={}
        )
        log2 = Log(name="module1", level="info", message="Info 1", data={}, metadata={})
        log3 = Log(
            name="module2", level="error", message="Error 2", data={}, metadata={}
        )

        await test_database.logs.create(LogRow(id="log-001", created_at=now, data=log1))
        await test_database.logs.create(LogRow(id="log-002", created_at=now, data=log2))
        await test_database.logs.create(LogRow(id="log-003", created_at=now, data=log3))

        # Query for module1 AND error level
        query = logs_query.name(value="module1", operator="=") & logs_query.level(
            value="error", operator="="
        )
        results = await test_database.logs.find(query)

        assert len(results) == 1
        assert results[0].data.name == "module1"
        assert results[0].data.level == "error"


class TestRangeQueryParams:
    """Test suite for RangeQueryParams (pagination and time filtering)."""

    @pytest.mark.asyncio
    async def test_query_with_limit(self, test_database: SQLiteDatabaseController):
        """Test querying with limit parameter."""
        now = datetime.now(UTC)

        # Create 5 agents
        for i in range(5):
            agent = AgentProfile(id=f"agent-{i:03d}", metadata={})
            await test_database.agents.create(
                AgentRow(id=agent.id, created_at=now, data=agent)
            )

        # Query with limit
        query = agents_query.query(path="$.id", value=None, operator="IS NOT NULL")
        params = RangeQueryParams(limit=3)
        results = await test_database.agents.find(query, params)

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_query_with_offset(self, test_database: SQLiteDatabaseController):
        """Test querying with offset parameter."""
        now = datetime.now(UTC)

        # Create 5 agents
        for i in range(5):
            agent = AgentProfile(id=f"agent-{i:03d}", metadata={})
            await test_database.agents.create(
                AgentRow(id=agent.id, created_at=now, data=agent)
            )

        # Query with offset
        query = agents_query.query(path="$.id", value=None, operator="IS NOT NULL")
        params = RangeQueryParams(offset=2, limit=2)
        results = await test_database.agents.find(query, params)

        assert len(results) == 2
        # Results should be the 3rd and 4th agents (0-indexed: 2, 3)
        assert results[0].data.id == "agent-002"
        assert results[1].data.id == "agent-003"

    @pytest.mark.asyncio
    async def test_query_with_after_time_filter(
        self, test_database: SQLiteDatabaseController
    ):
        """Test querying with after time filter."""
        base_time = datetime.now(UTC)

        # Create actions at different times
        action1 = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(name="DummyAction", parameters={}),
            result=ActionExecutionResult(is_error=False, content={}),
        )
        action2 = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(name="DummyAction", parameters={}),
            result=ActionExecutionResult(is_error=False, content={}),
        )
        action3 = ActionRowData(
            agent_id="agent-001",
            request=ActionExecutionRequest(name="DummyAction", parameters={}),
            result=ActionExecutionResult(is_error=False, content={}),
        )

        await test_database.actions.create(
            ActionRow(id="action-001", created_at=base_time, data=action1)
        )
        await test_database.actions.create(
            ActionRow(
                id="action-002",
                created_at=base_time + timedelta(minutes=5),
                data=action2,
            )
        )
        await test_database.actions.create(
            ActionRow(
                id="action-003",
                created_at=base_time + timedelta(minutes=10),
                data=action3,
            )
        )

        # Query for actions after base_time + 3 minutes
        query = actions_query.agent_id(value="agent-001", operator="=")
        params = RangeQueryParams(after=base_time + timedelta(minutes=3))
        results = await test_database.actions.find(query, params)

        assert len(results) == 2
        assert all(r.created_at > base_time + timedelta(minutes=3) for r in results)

    @pytest.mark.asyncio
    async def test_query_with_before_time_filter(
        self, test_database: SQLiteDatabaseController
    ):
        """Test querying with before time filter."""
        base_time = datetime.now(UTC)

        # Create logs at different times
        log1 = Log(name="test", level="info", message="Message 1", data={}, metadata={})
        log2 = Log(name="test", level="info", message="Message 2", data={}, metadata={})
        log3 = Log(name="test", level="info", message="Message 3", data={}, metadata={})

        await test_database.logs.create(
            LogRow(id="log-001", created_at=base_time, data=log1)
        )
        await test_database.logs.create(
            LogRow(id="log-002", created_at=base_time + timedelta(minutes=5), data=log2)
        )
        await test_database.logs.create(
            LogRow(
                id="log-003", created_at=base_time + timedelta(minutes=10), data=log3
            )
        )

        # Query for logs before base_time + 7 minutes
        query = logs_query.name(value="test", operator="=")
        params = RangeQueryParams(before=base_time + timedelta(minutes=7))
        results = await test_database.logs.find(query, params)

        assert len(results) == 2
        assert all(r.created_at < base_time + timedelta(minutes=7) for r in results)

    @pytest.mark.asyncio
    async def test_query_with_time_range(self, test_database: SQLiteDatabaseController):
        """Test querying with both after and before time filters."""
        base_time = datetime.now(UTC)

        # Create actions at different times
        for i in range(6):
            action = ActionRowData(
                agent_id="agent-001",
                request=ActionExecutionRequest(name="DummyAction", parameters={}),
                result=ActionExecutionResult(is_error=False, content={}),
            )
            await test_database.actions.create(
                ActionRow(
                    id=f"action-{i:03d}",
                    created_at=base_time + timedelta(minutes=i * 2),
                    data=action,
                )
            )

        # Query for actions between 3 and 9 minutes after base_time
        query = actions_query.agent_id(value="agent-001", operator="=")
        params = RangeQueryParams(
            after=base_time + timedelta(minutes=3),
            before=base_time + timedelta(minutes=9),
        )
        results = await test_database.actions.find(query, params)

        assert len(results) == 3  # Actions at 4, 6, and 8 minutes
        assert all(
            base_time + timedelta(minutes=3)
            < r.created_at
            < base_time + timedelta(minutes=9)
            for r in results
        )

    @pytest.mark.asyncio
    async def test_query_with_all_params(self, test_database: SQLiteDatabaseController):
        """Test querying with all range parameters combined."""
        base_time = datetime.now(UTC)

        # Create actions at different times (changed from agents for time range testing)
        for i in range(10):
            action = ActionRowData(
                agent_id="agent-001",
                request=ActionExecutionRequest(
                    name="DummyAction", parameters={"index": i}
                ),
                result=ActionExecutionResult(is_error=False, content={}),
            )
            await test_database.actions.create(
                ActionRow(
                    id=f"action-{i:03d}",
                    created_at=base_time + timedelta(minutes=i),
                    data=action,
                )
            )

        # Query with time range, offset, and limit
        query = actions_query.agent_id(value="agent-001", operator="=")
        params = RangeQueryParams(
            after=base_time + timedelta(minutes=2),
            before=base_time + timedelta(minutes=8),
            offset=1,
            limit=2,
        )
        results = await test_database.actions.find(query, params)

        # Should get actions 3-7 (5 total), then skip 1 (offset), then take 2 (limit)
        assert len(results) == 2
        assert results[0].id == "action-004"
        assert results[1].id == "action-005"
