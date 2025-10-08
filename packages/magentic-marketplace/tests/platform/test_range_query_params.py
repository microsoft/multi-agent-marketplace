"""Comprehensive tests for RangeQueryParams across all database implementations."""

import os
import tempfile
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

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
from magentic_marketplace.platform.database.queries import (
    actions as action_queries,
)
from magentic_marketplace.platform.database.queries import agents as agent_queries
from magentic_marketplace.platform.database.queries import logs as log_queries
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


@pytest_asyncio.fixture
async def populated_database(database) -> BaseDatabaseController:
    """Create a database populated with test data."""
    base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)

    # Create 20 agents with timestamps 1 hour apart
    for i in range(20):
        await database.agents.create(
            AgentRow(
                id=f"agent-{i:02d}",
                created_at=base_time + timedelta(hours=i),
                data=AgentProfile(id=f"agent-{i:02d}", metadata={"order": i}),
            )
        )

    # Create 20 actions with timestamps 1 hour apart
    for i in range(20):
        await database.actions.create(
            ActionRow(
                id=f"action-{i:02d}",
                created_at=base_time + timedelta(hours=i),
                data=ActionRowData(
                    agent_id="test-agent",
                    request=ActionExecutionRequest(
                        name="TestAction", parameters={"order": i}
                    ),
                    result=ActionExecutionResult(is_error=False, content={}),
                ),
            )
        )

    # Create 20 logs with timestamps 1 hour apart
    for i in range(20):
        await database.logs.create(
            LogRow(
                id=f"log-{i:02d}",
                created_at=base_time + timedelta(hours=i),
                data=Log(
                    level="info",
                    name=f"test_log_{i:02d}",
                    message=f"Test log {i}",
                ),
            )
        )

    return database


class TestAgentRangeQueries:
    """Test all RangeQueryParams combinations for agents."""

    @pytest.mark.asyncio
    async def test_agent_get_all_with_after_only(self, populated_database):
        """Test agents.get_all with only after timestamp."""
        base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
        after_time = base_time + timedelta(hours=15)

        params = RangeQueryParams(after=after_time)
        agents = await populated_database.agents.get_all(params)

        # Should get agents 16-19 (4 agents created after hour 15)
        assert len(agents) == 4
        for agent in agents:
            assert agent.created_at > after_time

    @pytest.mark.asyncio
    async def test_agent_get_all_with_before_only(self, populated_database):
        """Test agents.get_all with only before timestamp."""
        base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
        before_time = base_time + timedelta(hours=5)

        params = RangeQueryParams(before=before_time)
        agents = await populated_database.agents.get_all(params)

        # Should get agents 0-4 (5 agents created before hour 5)
        assert len(agents) == 5
        for agent in agents:
            assert agent.created_at < before_time

    @pytest.mark.asyncio
    async def test_agent_get_all_with_after_and_before(self, populated_database):
        """Test agents.get_all with both after and before timestamps."""
        base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
        after_time = base_time + timedelta(hours=5)
        before_time = base_time + timedelta(hours=15)

        params = RangeQueryParams(after=after_time, before=before_time)
        agents = await populated_database.agents.get_all(params)

        # Should get agents 6-14 (9 agents created between hours 5 and 15)
        assert len(agents) == 9
        for agent in agents:
            assert after_time < agent.created_at < before_time

    @pytest.mark.asyncio
    async def test_agent_get_all_with_after_index_only(self, populated_database):
        """Test agents.get_all with only after_index."""
        params = RangeQueryParams(after_index=10)
        agents = await populated_database.agents.get_all(params)

        # Should get agents with index > 10 (indices 11-20)
        assert len(agents) == 10
        for agent in agents:
            assert agent.index > 10

    @pytest.mark.asyncio
    async def test_agent_get_all_with_before_index_only(self, populated_database):
        """Test agents.get_all with only before_index."""
        params = RangeQueryParams(before_index=6)
        agents = await populated_database.agents.get_all(params)

        # Should get agents with index < 6 (indices 1-5)
        assert len(agents) == 5
        for agent in agents:
            assert agent.index < 6

    @pytest.mark.asyncio
    async def test_agent_get_all_with_after_index_and_before_index(
        self, populated_database
    ):
        """Test agents.get_all with both after_index and before_index."""
        params = RangeQueryParams(after_index=5, before_index=15)
        agents = await populated_database.agents.get_all(params)

        # Should get agents with 5 < index < 15 (indices 6-14)
        assert len(agents) == 9
        for agent in agents:
            assert 5 < agent.index < 15

    @pytest.mark.asyncio
    async def test_agent_get_all_with_limit_only(self, populated_database):
        """Test agents.get_all with only limit."""
        params = RangeQueryParams(limit=5)
        agents = await populated_database.agents.get_all(params)

        # Should get first 5 agents
        assert len(agents) == 5
        indices = [agent.index for agent in agents]
        assert indices == [1, 2, 3, 4, 5]

    @pytest.mark.asyncio
    async def test_agent_get_all_with_offset_only(self, populated_database):
        """Test agents.get_all with only offset."""
        params = RangeQueryParams(offset=15)
        agents = await populated_database.agents.get_all(params)

        # Should get agents starting from index 16 (indices 16-20)
        assert len(agents) == 5
        for agent in agents:
            assert agent.index > 15

    @pytest.mark.asyncio
    async def test_agent_get_all_with_limit_and_offset(self, populated_database):
        """Test agents.get_all with both limit and offset."""
        params = RangeQueryParams(limit=5, offset=10)
        agents = await populated_database.agents.get_all(params)

        # Should get 5 agents starting from index 11 (indices 11-15)
        assert len(agents) == 5
        indices = [agent.index for agent in agents]
        assert indices == [11, 12, 13, 14, 15]

    @pytest.mark.asyncio
    async def test_agent_get_all_with_all_timestamp_filters(self, populated_database):
        """Test agents.get_all with after, before, limit, and offset."""
        base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
        after_time = base_time + timedelta(hours=5)
        before_time = base_time + timedelta(hours=15)

        params = RangeQueryParams(
            after=after_time, before=before_time, limit=3, offset=2
        )
        agents = await populated_database.agents.get_all(params)

        # Should get 3 agents after skipping first 2 in the range
        assert len(agents) == 3
        for agent in agents:
            assert after_time < agent.created_at < before_time

    @pytest.mark.asyncio
    async def test_agent_get_all_with_all_index_filters(self, populated_database):
        """Test agents.get_all with after_index, before_index, limit, and offset."""
        params = RangeQueryParams(after_index=5, before_index=15, limit=4, offset=2)
        agents = await populated_database.agents.get_all(params)

        # Should get 4 agents after skipping first 2 in the range (indices 8-11)
        assert len(agents) == 4
        indices = [agent.index for agent in agents]
        assert indices == [8, 9, 10, 11]

    @pytest.mark.asyncio
    async def test_agent_get_all_with_combined_timestamp_and_index_filters(
        self, populated_database
    ):
        """Test agents.get_all with both timestamp and index filters."""
        base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
        after_time = base_time + timedelta(hours=3)
        before_time = base_time + timedelta(hours=17)

        params = RangeQueryParams(
            after=after_time,
            before=before_time,
            after_index=5,
            before_index=15,
            limit=5,
            offset=1,
        )
        agents = await populated_database.agents.get_all(params)

        # Should satisfy all filters
        assert len(agents) == 5
        for agent in agents:
            assert after_time < agent.created_at < before_time
            assert 5 < agent.index < 15

    @pytest.mark.asyncio
    async def test_agent_find_with_after_index(self, populated_database):
        """Test agents.find with after_index filter."""
        query = agent_queries.id(value="agent-", operator="LIKE")
        params = RangeQueryParams(after_index=10)
        agents = await populated_database.agents.find(query, params)

        # Should get agents with index > 10
        assert len(agents) == 10
        for agent in agents:
            assert agent.index > 10

    @pytest.mark.asyncio
    async def test_agent_find_with_before_index(self, populated_database):
        """Test agents.find with before_index filter."""
        query = agent_queries.id(value="agent-", operator="LIKE")
        params = RangeQueryParams(before_index=11)
        agents = await populated_database.agents.find(query, params)

        # Should get agents with index < 11
        assert len(agents) == 10
        for agent in agents:
            assert agent.index < 11

    @pytest.mark.asyncio
    async def test_agent_find_with_all_filters(self, populated_database):
        """Test agents.find with all RangeQueryParams filters."""
        base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
        query = agent_queries.id(value="agent-", operator="LIKE")
        params = RangeQueryParams(
            after=base_time + timedelta(hours=2),
            before=base_time + timedelta(hours=18),
            after_index=3,
            before_index=17,
            limit=5,
            offset=2,
        )
        agents = await populated_database.agents.find(query, params)

        # Should satisfy all filters
        assert len(agents) == 5
        for agent in agents:
            assert agent.created_at > base_time + timedelta(hours=2)
            assert agent.created_at < base_time + timedelta(hours=18)
            assert agent.index > 3
            assert agent.index < 17


class TestActionRangeQueries:
    """Test all RangeQueryParams combinations for actions."""

    @pytest.mark.asyncio
    async def test_action_get_all_with_after_only(self, populated_database):
        """Test actions.get_all with only after timestamp."""
        base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
        after_time = base_time + timedelta(hours=12)

        params = RangeQueryParams(after=after_time)
        actions = await populated_database.actions.get_all(params)

        # Should get actions created after hour 12
        assert len(actions) == 7
        for action in actions:
            assert action.created_at > after_time

    @pytest.mark.asyncio
    async def test_action_get_all_with_before_only(self, populated_database):
        """Test actions.get_all with only before timestamp."""
        base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
        before_time = base_time + timedelta(hours=8)

        params = RangeQueryParams(before=before_time)
        actions = await populated_database.actions.get_all(params)

        # Should get actions created before hour 8
        assert len(actions) == 8
        for action in actions:
            assert action.created_at < before_time

    @pytest.mark.asyncio
    async def test_action_get_all_with_after_and_before(self, populated_database):
        """Test actions.get_all with both after and before timestamps."""
        base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
        after_time = base_time + timedelta(hours=4)
        before_time = base_time + timedelta(hours=12)

        params = RangeQueryParams(after=after_time, before=before_time)
        actions = await populated_database.actions.get_all(params)

        # Should get actions between hours 4 and 12
        assert len(actions) == 7
        for action in actions:
            assert after_time < action.created_at < before_time

    @pytest.mark.asyncio
    async def test_action_get_all_with_after_index_only(self, populated_database):
        """Test actions.get_all with only after_index."""
        params = RangeQueryParams(after_index=15)
        actions = await populated_database.actions.get_all(params)

        # Should get actions with index > 15
        assert len(actions) == 5
        for action in actions:
            assert action.index > 15

    @pytest.mark.asyncio
    async def test_action_get_all_with_before_index_only(self, populated_database):
        """Test actions.get_all with only before_index."""
        params = RangeQueryParams(before_index=4)
        actions = await populated_database.actions.get_all(params)

        # Should get actions with index < 4
        assert len(actions) == 3
        for action in actions:
            assert action.index < 4

    @pytest.mark.asyncio
    async def test_action_get_all_with_index_range(self, populated_database):
        """Test actions.get_all with both after_index and before_index."""
        params = RangeQueryParams(after_index=3, before_index=13)
        actions = await populated_database.actions.get_all(params)

        # Should get actions with 3 < index < 13
        assert len(actions) == 9
        for action in actions:
            assert 3 < action.index < 13

    @pytest.mark.asyncio
    async def test_action_get_all_with_limit_and_offset(self, populated_database):
        """Test actions.get_all with limit and offset."""
        params = RangeQueryParams(limit=7, offset=8)
        actions = await populated_database.actions.get_all(params)

        # Should get 7 actions starting from index 9
        assert len(actions) == 7
        indices = [action.index for action in actions]
        assert indices == [9, 10, 11, 12, 13, 14, 15]

    @pytest.mark.asyncio
    async def test_action_get_all_with_all_filters(self, populated_database):
        """Test actions.get_all with all RangeQueryParams filters."""
        base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)

        params = RangeQueryParams(
            after=base_time + timedelta(hours=2),
            before=base_time + timedelta(hours=16),
            after_index=4,
            before_index=14,
            limit=4,
            offset=1,
        )
        actions = await populated_database.actions.get_all(params)

        # Should satisfy all filters
        assert len(actions) == 4
        for action in actions:
            assert action.created_at > base_time + timedelta(hours=2)
            assert action.created_at < base_time + timedelta(hours=16)
            assert action.index > 4
            assert action.index < 14

    @pytest.mark.asyncio
    async def test_action_find_with_after_index(self, populated_database):
        """Test actions.find with after_index filter."""
        query = action_queries.agent_id(value="test-agent", operator="=")
        params = RangeQueryParams(after_index=12)
        actions = await populated_database.actions.find(query, params)

        # Should get actions with index > 12
        assert len(actions) == 8
        for action in actions:
            assert action.index > 12

    @pytest.mark.asyncio
    async def test_action_find_with_before_index(self, populated_database):
        """Test actions.find with before_index filter."""
        query = action_queries.agent_id(value="test-agent", operator="=")
        params = RangeQueryParams(before_index=8)
        actions = await populated_database.actions.find(query, params)

        # Should get actions with index < 8
        assert len(actions) == 7
        for action in actions:
            assert action.index < 8

    @pytest.mark.asyncio
    async def test_action_find_with_all_filters(self, populated_database):
        """Test actions.find with all RangeQueryParams filters."""
        base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
        query = action_queries.agent_id(value="test-agent", operator="=")
        params = RangeQueryParams(
            after=base_time + timedelta(hours=3),
            before=base_time + timedelta(hours=17),
            after_index=5,
            before_index=16,
            limit=6,
            offset=1,
        )
        actions = await populated_database.actions.find(query, params)

        # Should satisfy all filters
        assert len(actions) == 6
        for action in actions:
            assert action.created_at > base_time + timedelta(hours=3)
            assert action.created_at < base_time + timedelta(hours=17)
            assert action.index > 5
            assert action.index < 16


class TestLogRangeQueries:
    """Test all RangeQueryParams combinations for logs."""

    @pytest.mark.asyncio
    async def test_log_get_all_with_after_only(self, populated_database):
        """Test logs.get_all with only after timestamp."""
        base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
        after_time = base_time + timedelta(hours=10)

        params = RangeQueryParams(after=after_time)
        logs = await populated_database.logs.get_all(params)

        # Should get logs created after hour 10
        assert len(logs) == 9
        for log in logs:
            assert log.created_at > after_time

    @pytest.mark.asyncio
    async def test_log_get_all_with_before_only(self, populated_database):
        """Test logs.get_all with only before timestamp."""
        base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
        before_time = base_time + timedelta(hours=6)

        params = RangeQueryParams(before=before_time)
        logs = await populated_database.logs.get_all(params)

        # Should get logs created before hour 6
        assert len(logs) == 6
        for log in logs:
            assert log.created_at < before_time

    @pytest.mark.asyncio
    async def test_log_get_all_with_after_and_before(self, populated_database):
        """Test logs.get_all with both after and before timestamps."""
        base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
        after_time = base_time + timedelta(hours=7)
        before_time = base_time + timedelta(hours=14)

        params = RangeQueryParams(after=after_time, before=before_time)
        logs = await populated_database.logs.get_all(params)

        # Should get logs between hours 7 and 14
        assert len(logs) == 6
        for log in logs:
            assert after_time < log.created_at < before_time

    @pytest.mark.asyncio
    async def test_log_get_all_with_after_index_only(self, populated_database):
        """Test logs.get_all with only after_index."""
        params = RangeQueryParams(after_index=8)
        logs = await populated_database.logs.get_all(params)

        # Should get logs with index > 8
        assert len(logs) == 12
        for log in logs:
            assert log.index > 8

    @pytest.mark.asyncio
    async def test_log_get_all_with_before_index_only(self, populated_database):
        """Test logs.get_all with only before_index."""
        params = RangeQueryParams(before_index=10)
        logs = await populated_database.logs.get_all(params)

        # Should get logs with index < 10
        assert len(logs) == 9
        for log in logs:
            assert log.index < 10

    @pytest.mark.asyncio
    async def test_log_get_all_with_index_range(self, populated_database):
        """Test logs.get_all with both after_index and before_index."""
        params = RangeQueryParams(after_index=6, before_index=18)
        logs = await populated_database.logs.get_all(params)

        # Should get logs with 6 < index < 18
        assert len(logs) == 11
        for log in logs:
            assert 6 < log.index < 18

    @pytest.mark.asyncio
    async def test_log_get_all_with_limit_only(self, populated_database):
        """Test logs.get_all with only limit."""
        params = RangeQueryParams(limit=8)
        logs = await populated_database.logs.get_all(params)

        # Should get first 8 logs
        assert len(logs) == 8
        indices = [log.index for log in logs]
        assert indices == [1, 2, 3, 4, 5, 6, 7, 8]

    @pytest.mark.asyncio
    async def test_log_get_all_with_offset_only(self, populated_database):
        """Test logs.get_all with only offset."""
        params = RangeQueryParams(offset=12)
        logs = await populated_database.logs.get_all(params)

        # Should get logs starting from index 13
        assert len(logs) == 8
        for log in logs:
            assert log.index > 12

    @pytest.mark.asyncio
    async def test_log_get_all_with_limit_and_offset(self, populated_database):
        """Test logs.get_all with both limit and offset."""
        params = RangeQueryParams(limit=6, offset=5)
        logs = await populated_database.logs.get_all(params)

        # Should get 6 logs starting from index 6
        assert len(logs) == 6
        indices = [log.index for log in logs]
        assert indices == [6, 7, 8, 9, 10, 11]

    @pytest.mark.asyncio
    async def test_log_get_all_with_all_filters(self, populated_database):
        """Test logs.get_all with all RangeQueryParams filters."""
        base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)

        params = RangeQueryParams(
            after=base_time + timedelta(hours=1),
            before=base_time + timedelta(hours=19),
            after_index=2,
            before_index=18,
            limit=5,
            offset=3,
        )
        logs = await populated_database.logs.get_all(params)

        # Should satisfy all filters
        assert len(logs) == 5
        for log in logs:
            assert log.created_at > base_time + timedelta(hours=1)
            assert log.created_at < base_time + timedelta(hours=19)
            assert log.index > 2
            assert log.index < 18

    @pytest.mark.asyncio
    async def test_log_find_with_after_index(self, populated_database):
        """Test logs.find with after_index filter."""
        query = log_queries.level(value="info", operator="=")
        params = RangeQueryParams(after_index=11)
        logs = await populated_database.logs.find(query, params)

        # Should get logs with index > 11
        assert len(logs) == 9
        for log in logs:
            assert log.index > 11

    @pytest.mark.asyncio
    async def test_log_find_with_before_index(self, populated_database):
        """Test logs.find with before_index filter."""
        query = log_queries.level(value="info", operator="=")
        params = RangeQueryParams(before_index=9)
        logs = await populated_database.logs.find(query, params)

        # Should get logs with index < 9
        assert len(logs) == 8
        for log in logs:
            assert log.index < 9

    @pytest.mark.asyncio
    async def test_log_find_with_all_filters(self, populated_database):
        """Test logs.find with all RangeQueryParams filters."""
        base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
        query = log_queries.level(value="info", operator="=")
        params = RangeQueryParams(
            after=base_time + timedelta(hours=2),
            before=base_time + timedelta(hours=18),
            after_index=4,
            before_index=17,
            limit=7,
            offset=2,
        )
        logs = await populated_database.logs.find(query, params)

        # Should satisfy all filters
        assert len(logs) == 7
        for log in logs:
            assert log.created_at > base_time + timedelta(hours=2)
            assert log.created_at < base_time + timedelta(hours=18)
            assert log.index > 4
            assert log.index < 17


class TestOrderByRowIndex:
    """Test that results are ordered by row_index, not created_at."""

    @pytest.mark.asyncio
    async def test_agents_ordered_by_row_index_not_created_at(self, database):
        """Test that agents are returned in row_index order even if created_at differs."""
        base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)

        # Create agents with reversed timestamps
        for i in range(10):
            await database.agents.create(
                AgentRow(
                    id=f"agent-{i}",
                    created_at=base_time + timedelta(hours=9 - i),  # Reversed
                    data=AgentProfile(id=f"agent-{i}", metadata={}),
                )
            )

        # Get all agents
        agents = await database.agents.get_all()

        # Verify they are ordered by row_index (1, 2, 3, ...), not by created_at
        indices = [agent.index for agent in agents]
        assert indices == list(range(1, 11))

        # Verify created_at is in descending order (reversed)
        for i in range(len(agents) - 1):
            assert agents[i].created_at > agents[i + 1].created_at

    @pytest.mark.asyncio
    async def test_actions_ordered_by_row_index_not_created_at(self, database):
        """Test that actions are returned in row_index order even if created_at differs."""
        base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)

        # Create actions with reversed timestamps
        for i in range(10):
            await database.actions.create(
                ActionRow(
                    id=f"action-{i}",
                    created_at=base_time + timedelta(hours=9 - i),  # Reversed
                    data=ActionRowData(
                        agent_id="test-agent",
                        request=ActionExecutionRequest(
                            name="TestAction", parameters={"order": i}
                        ),
                        result=ActionExecutionResult(is_error=False, content={}),
                    ),
                )
            )

        # Get all actions
        actions = await database.actions.get_all()

        # Verify they are ordered by row_index (1, 2, 3, ...), not by created_at
        indices = [action.index for action in actions]
        assert indices == list(range(1, 11))

    @pytest.mark.asyncio
    async def test_logs_ordered_by_row_index_not_created_at(self, database):
        """Test that logs are returned in row_index order even if created_at differs."""
        base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)

        # Create logs with reversed timestamps
        for i in range(10):
            await database.logs.create(
                LogRow(
                    id=f"log-{i}",
                    created_at=base_time + timedelta(hours=9 - i),  # Reversed
                    data=Log(
                        level="info", name=f"test_log_{i}", message=f"Test log {i}"
                    ),
                )
            )

        # Get all logs
        logs = await database.logs.get_all()

        # Verify they are ordered by row_index (1, 2, 3, ...), not by created_at
        indices = [log.index for log in logs]
        assert indices == list(range(1, 11))
