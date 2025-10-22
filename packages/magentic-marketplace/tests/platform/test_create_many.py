"""Comprehensive tests for create_many batching functionality across all database implementations."""

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
    params=[
        "sqlite",
        pytest.param("postgresql", marks=pytest.mark.postgres)
        if POSTGRESQL_AVAILABLE
        else None,
    ],
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

        try:
            async with connect_to_sqlite_database(db_path) as db:
                yield db
        finally:
            # Cleanup SQLite database file
            try:
                os.unlink(db_path)
            except Exception:
                pass

    elif db_type == "postgresql":
        # PostgreSQL setup
        host = os.environ.get("POSTGRES_HOST", "localhost")
        port = int(os.environ.get("POSTGRES_PORT", "5432"))
        database = os.environ.get("POSTGRES_DB", "marketplace_test")
        user = os.environ.get("POSTGRES_USER", "postgres")
        password = os.environ.get("POSTGRES_PASSWORD", None)

        # Generate unique schema name for this test run
        import uuid

        schema = f"test_create_many_{uuid.uuid4().hex[:16]}"

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
        finally:
            # Cleanup: drop the test schema
            try:
                import asyncpg

                conn = await asyncpg.connect(
                    host=host,
                    port=port,
                    database=database,
                    user=user,
                    password=password,
                )
                await conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
                await conn.close()
            except Exception:
                pass
    else:
        raise ValueError(f"Unknown database type: {db_type}")


class TestCreateManyAgents:
    """Test create_many batch insertion for agents."""

    @pytest.mark.asyncio
    async def test_create_many_default_batch(self, database):
        """Test create_many with default batch size."""
        base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)

        # Prepare 50 agents
        agents = [
            AgentRow(
                id=f"agent-{i:03d}",
                created_at=base_time,
                data=AgentProfile(id=f"agent-{i:03d}", metadata={"order": i}),
            )
            for i in range(50)
        ]

        # Bulk create
        await database.agents.create_many(agents, batch_size=10)

        # Verify all were created
        created_agents = await database.agents.get_all()
        assert len(created_agents) == 50

        # Verify IDs match
        created_ids = {agent.id for agent in created_agents}
        assert created_ids == {f"agent-{i:03d}" for i in range(50)}

    @pytest.mark.asyncio
    async def test_create_many_empty_list(self, database):
        """Test create_many with empty list."""
        await database.agents.create_many([])
        agents = await database.agents.get_all()
        assert len(agents) == 0

    @pytest.mark.asyncio
    async def test_create_many_single_item(self, database):
        """Test create_many with a single item."""
        agent = AgentRow(
            id="single-agent",
            created_at=datetime.now(UTC),
            data=AgentProfile(id="single-agent", metadata={}),
        )

        await database.agents.create_many([agent], batch_size=10)

        agents = await database.agents.get_all()
        assert len(agents) == 1
        assert agents[0].id == "single-agent"

    @pytest.mark.asyncio
    async def test_create_many_exact_batch_boundary(self, database):
        """Test create_many when item count equals batch size."""
        agents = [
            AgentRow(
                id=f"agent-{i}",
                created_at=datetime.now(UTC),
                data=AgentProfile(id=f"agent-{i}", metadata={}),
            )
            for i in range(10)
        ]

        # Create with batch_size exactly matching item count
        await database.agents.create_many(agents, batch_size=10)

        created = await database.agents.get_all()
        assert len(created) == 10

    @pytest.mark.asyncio
    async def test_create_many_preserves_order(self, database):
        """Test that create_many maintains insertion order."""
        # Create agents in specific order
        agents = [
            AgentRow(
                id=f"agent-{i:02d}",
                created_at=datetime.now(UTC),
                data=AgentProfile(id=f"agent-{i:02d}", metadata={"order": i}),
            )
            for i in range(20)
        ]

        await database.agents.create_many(agents, batch_size=7)

        # Verify order is preserved
        created = await database.agents.get_all()
        assert len(created) == 20

        # Check that indices are sequential starting from 1
        for i, agent in enumerate(created, start=1):
            assert agent.index == i
            # Verify IDs are in the order we inserted
            assert agent.id == f"agent-{i - 1:02d}"


class TestCreateManyActions:
    """Test create_many batch insertion for actions."""

    @pytest.mark.asyncio
    async def test_create_many_actions(self, database):
        """Test create_many for actions."""
        base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)

        # Prepare 30 actions
        actions = [
            ActionRow(
                id=f"action-{i:03d}",
                created_at=base_time,
                data=ActionRowData(
                    agent_id="test-agent",
                    request=ActionExecutionRequest(
                        name="TestAction", parameters={"i": i}
                    ),
                    result=ActionExecutionResult(is_error=False, content={}),
                ),
            )
            for i in range(30)
        ]

        # Bulk create
        await database.actions.create_many(actions, batch_size=10)

        # Verify all were created
        created_actions = await database.actions.get_all()
        assert len(created_actions) == 30

    @pytest.mark.asyncio
    async def test_create_many_multiple_batches(self, database):
        """Test create_many requiring multiple batches."""
        # Create 25 items with batch size of 10 (requires 3 batches)
        actions = [
            ActionRow(
                id=f"action-{i}",
                created_at=datetime.now(UTC),
                data=ActionRowData(
                    agent_id="test",
                    request=ActionExecutionRequest(name="Test", parameters={}),
                    result=ActionExecutionResult(is_error=False, content={}),
                ),
            )
            for i in range(25)
        ]

        await database.actions.create_many(actions, batch_size=10)

        created = await database.actions.get_all()
        assert len(created) == 25


class TestCreateManyLogs:
    """Test create_many batch insertion for logs."""

    @pytest.mark.asyncio
    async def test_create_many_logs(self, database):
        """Test create_many for logs."""
        base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)

        # Prepare 40 logs
        logs = [
            LogRow(
                id=f"log-{i:03d}",
                created_at=base_time,
                data=Log(
                    level="info",
                    name=f"test_log_{i}",
                    message=f"Test message {i}",
                ),
            )
            for i in range(40)
        ]

        # Bulk create
        await database.logs.create_many(logs, batch_size=15)

        # Verify all were created
        created_logs = await database.logs.get_all()
        assert len(created_logs) == 40

    @pytest.mark.asyncio
    async def test_create_many_odd_batch_size(self, database):
        """Test create_many with odd batch size."""
        # Create 33 logs with batch size of 10
        logs = [
            LogRow(
                id=f"log-{i:03d}",
                created_at=datetime.now(UTC),
                data=Log(
                    level="info",
                    name=f"test_log_{i}",
                    message=f"Test message {i}",
                ),
            )
            for i in range(33)
        ]

        # Bulk create
        await database.logs.create_many(logs, batch_size=10)

        # Verify all were created
        created_logs = await database.logs.get_all()
        assert len(created_logs) == 33
