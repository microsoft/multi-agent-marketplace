"""Comprehensive tests for get_all batching functionality across all database implementations."""

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
from magentic_marketplace.platform.database.postgresql import (
    connect_to_postgresql_database,
)
from magentic_marketplace.platform.database.queries import RangeQueryParams
from magentic_marketplace.platform.database.sqlite import connect_to_sqlite_database
from magentic_marketplace.platform.shared.models import (
    ActionExecutionRequest,
    ActionExecutionResult,
    AgentProfile,
    Log,
)


@pytest_asyncio.fixture(
    params=["sqlite", pytest.param("postgresql", marks=pytest.mark.postgres)],
    ids=lambda x: f"db={x}" if x else "db=postgres-unavailable",
)
async def database(request) -> AsyncGenerator[BaseDatabaseController]:
    """Create a test database - parameterized to test both SQLite and PostgreSQL."""
    db_type = request.param

    if db_type is None:
        pytest.skip("PostgreSQL not available")
        return  # type: ignore

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
async def large_database(database) -> BaseDatabaseController:
    """Create a database with records for batching tests."""
    base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)

    # Create 100 agents
    for i in range(100):
        await database.agents.create(
            AgentRow(
                id=f"agent-{i:03d}",
                created_at=base_time + timedelta(seconds=i),
                data=AgentProfile(id=f"agent-{i:03d}", metadata={"order": i}),
            )
        )

    # Create 100 actions
    for i in range(100):
        await database.actions.create(
            ActionRow(
                id=f"action-{i:03d}",
                created_at=base_time + timedelta(seconds=i),
                data=ActionRowData(
                    agent_id="test-agent",
                    request=ActionExecutionRequest(
                        name="TestAction", parameters={"order": i}
                    ),
                    result=ActionExecutionResult(is_error=False, content={}),
                ),
            )
        )

    # Create 100 logs
    for i in range(100):
        await database.logs.create(
            LogRow(
                id=f"log-{i:03d}",
                created_at=base_time + timedelta(seconds=i),
                data=Log(
                    level="info",
                    name=f"test_log_{i:03d}",
                    message=f"Test log {i}",
                ),
            )
        )

    return database


class TestAgentBatching:
    """Test batching functionality for agents.get_all()."""

    @pytest.mark.asyncio
    async def test_agent_get_all_with_batching(self, large_database):
        """Test that get_all retrieves all agents using batching."""
        agents = await large_database.agents.get_all(batch_size=10)

        # Should get all 100 agents across 10 batches
        assert len(agents) == 100
        # Verify they are in order by index
        for i, agent in enumerate(agents, start=1):
            assert agent.index == i
            assert agent.id == f"agent-{i - 1:03d}"

    @pytest.mark.asyncio
    async def test_agent_get_all_with_limit(self, large_database):
        """Test batching with limit."""
        params = RangeQueryParams(limit=35)
        agents = await large_database.agents.get_all(params, batch_size=10)

        # Should get exactly 35 agents across 4 batches
        assert len(agents) == 35

    @pytest.mark.asyncio
    async def test_agent_get_all_with_offset(self, large_database):
        """Test batching with offset."""
        params = RangeQueryParams(offset=50)
        agents = await large_database.agents.get_all(params, batch_size=10)

        # Should get 50 agents (100 - 50)
        assert len(agents) == 50
        assert agents[0].index == 51

    @pytest.mark.asyncio
    async def test_agent_get_all_with_limit_and_offset(self, large_database):
        """Test batching with both limit and offset."""
        params = RangeQueryParams(limit=25, offset=20)
        agents = await large_database.agents.get_all(params, batch_size=10)

        # Should get exactly 25 agents starting at index 21
        assert len(agents) == 25
        assert agents[0].index == 21
        assert agents[-1].index == 45

    @pytest.mark.asyncio
    async def test_agent_get_all_batch_size_larger_than_total(self, large_database):
        """Test batch size larger than total records."""
        agents = await large_database.agents.get_all(batch_size=200)

        # Should get all 100 agents in one batch
        assert len(agents) == 100

    @pytest.mark.asyncio
    async def test_agent_get_all_preserves_order(self, large_database):
        """Test that batching preserves order."""
        agents = await large_database.agents.get_all(batch_size=7)

        # Verify strict ordering
        indices = [agent.index for agent in agents]
        assert indices == list(range(1, 101))


class TestActionBatching:
    """Test batching functionality for actions.get_all()."""

    @pytest.mark.asyncio
    async def test_action_get_all_with_batching(self, large_database):
        """Test that get_all retrieves all actions using batching."""
        actions = await large_database.actions.get_all(batch_size=10)

        # Should get all 100 actions
        assert len(actions) == 100
        for i, action in enumerate(actions, start=1):
            assert action.index == i

    @pytest.mark.asyncio
    async def test_action_get_all_with_limit(self, large_database):
        """Test batching respects limit."""
        params = RangeQueryParams(limit=42)
        actions = await large_database.actions.get_all(params, batch_size=10)

        assert len(actions) == 42
        assert actions[0].index == 1
        assert actions[-1].index == 42

    @pytest.mark.asyncio
    async def test_action_get_all_preserves_order(self, large_database):
        """Test that batching preserves order."""
        actions = await large_database.actions.get_all(batch_size=13)

        indices = [action.index for action in actions]
        assert indices == list(range(1, 101))


class TestLogBatching:
    """Test batching functionality for logs.get_all()."""

    @pytest.mark.asyncio
    async def test_log_get_all_with_batching(self, large_database):
        """Test that get_all retrieves all logs using batching."""
        logs = await large_database.logs.get_all(batch_size=10)

        # Should get all 100 logs
        assert len(logs) == 100
        for i, log in enumerate(logs, start=1):
            assert log.index == i

    @pytest.mark.asyncio
    async def test_log_get_all_with_limit(self, large_database):
        """Test batching respects limit."""
        params = RangeQueryParams(limit=28)
        logs = await large_database.logs.get_all(params, batch_size=10)

        assert len(logs) == 28

    @pytest.mark.asyncio
    async def test_log_get_all_batch_size_one(self, database):
        """Test extreme case: batch size of 1."""
        # Create only 10 records for this test
        base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
        for i in range(10):
            await database.logs.create(
                LogRow(
                    id=f"log-{i}",
                    created_at=base_time + timedelta(seconds=i),
                    data=Log(level="info", name=f"log_{i}", message=f"Log {i}"),
                )
            )

        logs = await database.logs.get_all(batch_size=1)

        assert len(logs) == 10
        # Verify ordering
        for i, log in enumerate(logs, start=1):
            assert log.index == i

    @pytest.mark.asyncio
    async def test_log_get_all_preserves_order(self, large_database):
        """Test that batching preserves order."""
        logs = await large_database.logs.get_all(batch_size=11)

        indices = [log.index for log in logs]
        assert indices == list(range(1, 101))


class TestCrossTableBatchingConsistency:
    """Test that batching behavior is consistent across all table types."""

    @pytest.mark.asyncio
    async def test_all_tables_same_batch_behavior(self, large_database):
        """Test that all three table types handle batching identically."""
        batch_size = 10
        params = RangeQueryParams(limit=60, offset=20)

        agents = await large_database.agents.get_all(params, batch_size=batch_size)
        actions = await large_database.actions.get_all(params, batch_size=batch_size)
        logs = await large_database.logs.get_all(params, batch_size=batch_size)

        # All should return same count
        assert len(agents) == len(actions) == len(logs) == 60

        # All should respect offset
        assert agents[0].index == 21
        assert actions[0].index == 21
        assert logs[0].index == 21

        # All should maintain ordering
        assert [a.index for a in agents] == list(range(21, 81))
        assert [a.index for a in actions] == list(range(21, 81))
        assert [log.index for log in logs] == list(range(21, 81))


class TestBatchingEdgeCases:
    """Test edge cases and boundary conditions for batching."""

    @pytest.mark.asyncio
    async def test_empty_result_with_batching(self, database):
        """Test batching with empty result set."""
        agents = await database.agents.get_all(batch_size=10)
        assert len(agents) == 0

    @pytest.mark.asyncio
    async def test_limit_not_multiple_of_batch_size(self, large_database):
        """Test limit that is not a multiple of batch size."""
        params = RangeQueryParams(limit=37)
        agents = await large_database.agents.get_all(params, batch_size=10)

        # Should get exactly 37 agents (3 full batches + partial)
        assert len(agents) == 37

    @pytest.mark.asyncio
    async def test_offset_at_end_of_data(self, large_database):
        """Test offset near the end of available data."""
        params = RangeQueryParams(offset=95)
        agents = await large_database.agents.get_all(params, batch_size=10)

        # Should get remaining 5 agents
        assert len(agents) == 5
        assert agents[0].index == 96

    @pytest.mark.asyncio
    async def test_offset_beyond_data(self, large_database):
        """Test offset beyond available data."""
        params = RangeQueryParams(offset=150)
        agents = await large_database.agents.get_all(params, batch_size=10)

        # Should return empty list
        assert len(agents) == 0

    @pytest.mark.asyncio
    async def test_batching_stops_at_limit(self, large_database):
        """Test that batching stops exactly at the limit, not at batch boundary."""
        # Limit that falls in the middle of a batch
        params = RangeQueryParams(limit=33)
        agents = await large_database.agents.get_all(params, batch_size=10)

        # Should get exactly 33, not 40 (4 full batches)
        assert len(agents) == 33
        assert agents[-1].index == 33
