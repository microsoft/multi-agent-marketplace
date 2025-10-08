"""Tests for row_index functionality across all database tables."""

import asyncio
import os
import tempfile
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import pytest_asyncio

from magentic_marketplace.platform.database.base import BaseDatabaseController
from magentic_marketplace.platform.database.models import (
    ActionRow,
    ActionRowData,
    AgentRow,
    LogRow,
)
from magentic_marketplace.platform.database.queries import RangeQueryParams
from magentic_marketplace.platform.database.sqlite import connect_to_sqlite_database
from magentic_marketplace.platform.shared.models import (
    ActionExecutionRequest,
    ActionExecutionResult,
    AgentProfile,
    Log,
)

# Check if PostgreSQL is available
POSTGRESQL_AVAILABLE = False
try:
    from magentic_marketplace.platform.database.postgresql import (
        connect_to_postgresql_database,
    )

    POSTGRESQL_AVAILABLE = True
except ImportError:
    pass


@pytest_asyncio.fixture(
    params=["sqlite", "postgresql"] if POSTGRESQL_AVAILABLE else ["sqlite"],
    ids=lambda x: f"db={x}",
)
async def database(request) -> AsyncGenerator[BaseDatabaseController]:
    """Create a test database - parameterized to test both SQLite and PostgreSQL."""
    db_type = request.param

    if db_type == "sqlite":
        # SQLite setup
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_file:
            db_path = temp_file.name

        async with connect_to_sqlite_database(db_path) as db:
            yield db

        # Cleanup
        try:
            os.unlink(db_path)
        except Exception:
            pass

    elif db_type == "postgresql":
        # PostgreSQL setup - check for connection info from environment
        host = os.environ.get("POSTGRES_HOST", "localhost")
        port = int(os.environ.get("POSTGRES_PORT", "5432"))
        database = os.environ.get("POSTGRES_DB", "marketplace_test")
        user = os.environ.get("POSTGRES_USER", "postgres")
        password = os.environ.get("POSTGRES_PASSWORD", None)

        # Generate unique schema name for this test run
        import uuid

        schema = f"test_{uuid.uuid4().hex[:16]}"

        try:
            async with connect_to_postgresql_database(  # pyright: ignore[reportPossiblyUnboundVariable]
                schema=schema,
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
                min_size=1,
                max_size=2,
            ) as db:
                yield db
        except Exception as e:
            pytest.skip(f"PostgreSQL not available: {e}")
    else:
        raise ValueError(f"Unknown database type: {db_type}")


class TestRowIndexIncrement:
    """Test that row_index correctly increments for all table types."""

    @pytest.mark.asyncio
    async def test_agent_row_index_increments(self, database):
        """Test that agent row_index increments correctly."""
        # Create multiple agents
        agents = []
        for i in range(5):
            agent = AgentRow(
                id=f"agent-{i}",
                created_at=datetime.now(UTC),
                data=AgentProfile(id=f"agent-{i}", metadata={}),
            )
            created_agent = await database.agents.create(agent)
            agents.append(created_agent)

        # Verify indices are sequential starting from 1
        assert agents[0].index == 1
        assert agents[1].index == 2
        assert agents[2].index == 3
        assert agents[3].index == 4
        assert agents[4].index == 5

    @pytest.mark.asyncio
    async def test_action_row_index_increments(self, database):
        """Test that action row_index increments correctly."""
        # Create multiple actions
        actions = []
        for i in range(5):
            action = ActionRow(
                id=f"action-{i}",
                created_at=datetime.now(UTC),
                data=ActionRowData(
                    agent_id="test-agent",
                    request=ActionExecutionRequest(
                        name="TestAction", parameters={"test": i}
                    ),
                    result=ActionExecutionResult(is_error=False, content={}),
                ),
            )
            created_action = await database.actions.create(action)
            actions.append(created_action)

        # Verify indices are sequential starting from 1
        assert actions[0].index == 1
        assert actions[1].index == 2
        assert actions[2].index == 3
        assert actions[3].index == 4
        assert actions[4].index == 5

    @pytest.mark.asyncio
    async def test_log_row_index_increments(self, database):
        """Test that log row_index increments correctly."""
        # Create multiple logs
        logs = []
        for i in range(5):
            log = LogRow(
                id=f"log-{i}",
                created_at=datetime.now(UTC),
                data=Log(
                    level="info",
                    name=f"test_log_{i}",
                    message=f"Test log {i}",
                ),
            )
            created_log = await database.logs.create(log)
            logs.append(created_log)

        # Verify indices are sequential starting from 1
        assert logs[0].index == 1
        assert logs[1].index == 2
        assert logs[2].index == 3
        assert logs[3].index == 4
        assert logs[4].index == 5


class TestRowIndexUniqueness:
    """Test that row_index values are unique when inserting concurrently."""

    @pytest.mark.asyncio
    async def test_concurrent_agent_inserts_have_unique_indices(self, database):
        """Test that concurrent agent insertions get unique indices."""

        async def create_agent(i):
            agent = AgentRow(
                id=f"agent-{i}",
                created_at=datetime.now(UTC),
                data=AgentProfile(id=f"agent-{i}", metadata={}),
            )
            return await database.agents.create(agent)

        # Create 10 agents concurrently
        agents = await asyncio.gather(*[create_agent(i) for i in range(10)])

        # Extract all indices
        indices = [agent.index for agent in agents]

        # Verify all indices are unique
        assert len(indices) == len(set(indices)), "Row indices must be unique"

        # Verify all indices are present (should be 1-10)
        assert set(indices) == set(range(1, 11))

    @pytest.mark.asyncio
    async def test_concurrent_action_inserts_have_unique_indices(self, database):
        """Test that concurrent action insertions get unique indices."""

        async def create_action(i):
            action = ActionRow(
                id=f"action-{i}",
                created_at=datetime.now(UTC),
                data=ActionRowData(
                    agent_id="test-agent",
                    request=ActionExecutionRequest(
                        name="TestAction", parameters={"test": i}
                    ),
                    result=ActionExecutionResult(is_error=False, content={}),
                ),
            )
            return await database.actions.create(action)

        # Create 10 actions concurrently
        actions = await asyncio.gather(*[create_action(i) for i in range(10)])

        # Extract all indices
        indices = [action.index for action in actions]

        # Verify all indices are unique
        assert len(indices) == len(set(indices)), "Row indices must be unique"

        # Verify all indices are present (should be 1-10)
        assert set(indices) == set(range(1, 11))

    @pytest.mark.asyncio
    async def test_concurrent_log_inserts_have_unique_indices(self, database):
        """Test that concurrent log insertions get unique indices."""

        async def create_log(i):
            log = LogRow(
                id=f"log-{i}",
                created_at=datetime.now(UTC),
                data=Log(
                    level="info",
                    name=f"test_log_{i}",
                    message=f"Test log {i}",
                ),
            )
            return await database.logs.create(log)

        # Create 10 logs concurrently
        logs = await asyncio.gather(*[create_log(i) for i in range(10)])

        # Extract all indices
        indices = [log.index for log in logs]

        # Verify all indices are unique
        assert len(indices) == len(set(indices)), "Row indices must be unique"

        # Verify all indices are present (should be 1-10)
        assert set(indices) == set(range(1, 11))


class TestRowIndexAlwaysSet:
    """Test that index is always set when fetching from database."""

    @pytest.mark.asyncio
    async def test_action_get_by_id_has_index(self, database):
        """Test that get_by_id always returns action with index set."""
        # Create an action
        action = ActionRow(
            id="action-1",
            created_at=datetime.now(UTC),
            data=ActionRowData(
                agent_id="test-agent",
                request=ActionExecutionRequest(
                    name="TestAction", parameters={"test": 1}
                ),
                result=ActionExecutionResult(is_error=False, content={}),
            ),
        )
        created_action = await database.actions.create(action)
        assert created_action.index is not None

        # Fetch by ID
        fetched_action = await database.actions.get_by_id("action-1")
        assert fetched_action is not None
        assert fetched_action.index is not None, (
            "get_by_id must return action with index set"
        )

    @pytest.mark.asyncio
    async def test_action_get_all_has_index(self, database):
        """Test that get_all always returns actions with index set."""
        # Create multiple actions
        for i in range(3):
            await database.actions.create(
                ActionRow(
                    id=f"action-{i}",
                    created_at=datetime.now(UTC),
                    data=ActionRowData(
                        agent_id="test-agent",
                        request=ActionExecutionRequest(
                            name="TestAction", parameters={"test": i}
                        ),
                        result=ActionExecutionResult(is_error=False, content={}),
                    ),
                )
            )

        # Fetch all
        actions = await database.actions.get_all()
        assert len(actions) == 3
        for action in actions:
            assert action.index is not None, (
                "get_all must return actions with index set"
            )

    @pytest.mark.asyncio
    async def test_action_find_has_index(self, database):
        """Test that find always returns actions with index set."""
        from magentic_marketplace.platform.database.queries import (
            actions as action_queries,
        )

        # Create multiple actions
        for i in range(3):
            await database.actions.create(
                ActionRow(
                    id=f"action-{i}",
                    created_at=datetime.now(UTC),
                    data=ActionRowData(
                        agent_id="test-agent",
                        request=ActionExecutionRequest(
                            name="TestAction", parameters={"test": i}
                        ),
                        result=ActionExecutionResult(is_error=False, content={}),
                    ),
                )
            )

        # Find actions
        query = action_queries.agent_id(value="test-agent", operator="=")
        actions = await database.actions.find(query)
        assert len(actions) == 3
        for action in actions:
            assert action.index is not None, "find must return actions with index set"

    @pytest.mark.asyncio
    async def test_agent_get_by_id_has_index(self, database):
        """Test that get_by_id always returns agent with index set."""
        # Create an agent
        agent = AgentRow(
            id="agent-1",
            created_at=datetime.now(UTC),
            data=AgentProfile(id="agent-1", metadata={}),
        )
        created_agent = await database.agents.create(agent)
        assert created_agent.index is not None

        # Fetch by ID
        fetched_agent = await database.agents.get_by_id("agent-1")
        assert fetched_agent is not None
        assert fetched_agent.index is not None, (
            "get_by_id must return agent with index set"
        )

    @pytest.mark.asyncio
    async def test_agent_get_all_has_index(self, database):
        """Test that get_all always returns agents with index set."""
        # Create multiple agents
        for i in range(3):
            await database.agents.create(
                AgentRow(
                    id=f"agent-{i}",
                    created_at=datetime.now(UTC),
                    data=AgentProfile(id=f"agent-{i}", metadata={}),
                )
            )

        # Fetch all
        agents = await database.agents.get_all()
        assert len(agents) == 3
        for agent in agents:
            assert agent.index is not None, "get_all must return agents with index set"

    @pytest.mark.asyncio
    async def test_log_get_by_id_has_index(self, database):
        """Test that get_by_id always returns log with index set."""
        # Create a log
        log = LogRow(
            id="log-1",
            created_at=datetime.now(UTC),
            data=Log(level="info", name="test_log", message="Test log"),
        )
        created_log = await database.logs.create(log)
        assert created_log.index is not None

        # Fetch by ID
        fetched_log = await database.logs.get_by_id("log-1")
        assert fetched_log is not None
        assert fetched_log.index is not None, "get_by_id must return log with index set"

    @pytest.mark.asyncio
    async def test_log_get_all_has_index(self, database):
        """Test that get_all always returns logs with index set."""
        # Create multiple logs
        for i in range(3):
            await database.logs.create(
                LogRow(
                    id=f"log-{i}",
                    created_at=datetime.now(UTC),
                    data=Log(
                        level="info", name=f"test_log_{i}", message=f"Test log {i}"
                    ),
                )
            )

        # Fetch all
        logs = await database.logs.get_all()
        assert len(logs) == 3
        for log in logs:
            assert log.index is not None, "get_all must return logs with index set"


class TestRowIndexRangeQueries:
    """Test that before_index and after_index range queries work correctly."""

    @pytest.mark.asyncio
    async def test_agent_after_index_query(self, database):
        """Test querying agents after a specific index."""
        # Create 10 agents
        for i in range(10):
            await database.agents.create(
                AgentRow(
                    id=f"agent-{i}",
                    created_at=datetime.now(UTC),
                    data=AgentProfile(id=f"agent-{i}", metadata={}),
                )
            )

        # Query agents with index > 5
        params = RangeQueryParams(after_index=5)
        agents = await database.agents.get_all(params)

        # Should get agents with indices 6-10
        assert len(agents) == 5
        indices = [agent.index for agent in agents]
        assert all(idx > 5 for idx in indices)
        assert set(indices) == {6, 7, 8, 9, 10}

    @pytest.mark.asyncio
    async def test_agent_before_index_query(self, database):
        """Test querying agents before a specific index."""
        # Create 10 agents
        for i in range(10):
            await database.agents.create(
                AgentRow(
                    id=f"agent-{i}",
                    created_at=datetime.now(UTC),
                    data=AgentProfile(id=f"agent-{i}", metadata={}),
                )
            )

        # Query agents with index < 6
        params = RangeQueryParams(before_index=6)
        agents = await database.agents.get_all(params)

        # Should get agents with indices 1-5
        assert len(agents) == 5
        indices = [agent.index for agent in agents]
        assert all(idx < 6 for idx in indices)
        assert set(indices) == {1, 2, 3, 4, 5}

    @pytest.mark.asyncio
    async def test_agent_index_range_query(self, database):
        """Test querying agents within a specific index range."""
        # Create 10 agents
        for i in range(10):
            await database.agents.create(
                AgentRow(
                    id=f"agent-{i}",
                    created_at=datetime.now(UTC),
                    data=AgentProfile(id=f"agent-{i}", metadata={}),
                )
            )

        # Query agents with 3 < index < 8
        params = RangeQueryParams(after_index=3, before_index=8)
        agents = await database.agents.get_all(params)

        # Should get agents with indices 4-7
        assert len(agents) == 4
        indices = [agent.index for agent in agents]
        assert all(3 < idx < 8 for idx in indices)
        assert set(indices) == {4, 5, 6, 7}

    @pytest.mark.asyncio
    async def test_action_after_index_query(self, database):
        """Test querying actions after a specific index."""
        # Create 10 actions
        for i in range(10):
            await database.actions.create(
                ActionRow(
                    id=f"action-{i}",
                    created_at=datetime.now(UTC),
                    data=ActionRowData(
                        agent_id="test-agent",
                        request=ActionExecutionRequest(
                            name="TestAction", parameters={"test": i}
                        ),
                        result=ActionExecutionResult(is_error=False, content={}),
                    ),
                )
            )

        # Query actions with index > 7
        params = RangeQueryParams(after_index=7)
        actions = await database.actions.get_all(params)

        # Should get actions with indices 8-10
        assert len(actions) == 3
        indices = [action.index for action in actions]
        assert all(idx > 7 for idx in indices)
        assert set(indices) == {8, 9, 10}

    @pytest.mark.asyncio
    async def test_action_before_index_query(self, database):
        """Test querying actions before a specific index."""
        # Create 10 actions
        for i in range(10):
            await database.actions.create(
                ActionRow(
                    id=f"action-{i}",
                    created_at=datetime.now(UTC),
                    data=ActionRowData(
                        agent_id="test-agent",
                        request=ActionExecutionRequest(
                            name="TestAction", parameters={"test": i}
                        ),
                        result=ActionExecutionResult(is_error=False, content={}),
                    ),
                )
            )

        # Query actions with index < 4
        params = RangeQueryParams(before_index=4)
        actions = await database.actions.get_all(params)

        # Should get actions with indices 1-3
        assert len(actions) == 3
        indices = [action.index for action in actions]
        assert all(idx < 4 for idx in indices)
        assert set(indices) == {1, 2, 3}

    @pytest.mark.asyncio
    async def test_log_after_index_query(self, database):
        """Test querying logs after a specific index."""
        # Create 10 logs
        for i in range(10):
            await database.logs.create(
                LogRow(
                    id=f"log-{i}",
                    created_at=datetime.now(UTC),
                    data=Log(
                        level="info",
                        name=f"test_log_{i}",
                        message=f"Test log {i}",
                    ),
                )
            )

        # Query logs with index > 6
        params = RangeQueryParams(after_index=6)
        logs = await database.logs.get_all(params)

        # Should get logs with indices 7-10
        assert len(logs) == 4
        indices = [log.index for log in logs]
        assert all(idx > 6 for idx in indices)
        assert set(indices) == {7, 8, 9, 10}

    @pytest.mark.asyncio
    async def test_log_index_range_query(self, database):
        """Test querying logs within a specific index range."""
        # Create 10 logs
        for i in range(10):
            await database.logs.create(
                LogRow(
                    id=f"log-{i}",
                    created_at=datetime.now(UTC),
                    data=Log(
                        level="info",
                        name=f"test_log_{i}",
                        message=f"Test log {i}",
                    ),
                )
            )

        # Query logs with 2 < index < 9
        params = RangeQueryParams(after_index=2, before_index=9)
        logs = await database.logs.get_all(params)

        # Should get logs with indices 3-8
        assert len(logs) == 6
        indices = [log.index for log in logs]
        assert all(2 < idx < 9 for idx in indices)
        assert set(indices) == {3, 4, 5, 6, 7, 8}
