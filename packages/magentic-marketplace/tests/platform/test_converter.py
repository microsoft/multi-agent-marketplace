"""Tests for database converter (PostgreSQL to SQLite)."""

import tempfile
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio

from magentic_marketplace.platform.database.converter import convert_postgres_to_sqlite
from magentic_marketplace.platform.database.models import (
    ActionRow,
    ActionRowData,
    AgentRow,
    LogRow,
)
from magentic_marketplace.platform.database.postgresql.postgresql import (
    PostgreSQLDatabaseController,
)
from magentic_marketplace.platform.database.sqlite import connect_to_sqlite_database
from magentic_marketplace.platform.shared.models import (
    ActionExecutionRequest,
    ActionExecutionResult,
    AgentProfile,
    Log,
)

# Skip these tests if PostgreSQL is not available
pytest_plugins = ("pytest_asyncio",)

# Note: These tests require PostgreSQL to be running
# You can skip them by running: pytest -m "not postgres"
pytestmark = pytest.mark.postgres


@pytest_asyncio.fixture
async def postgres_test_db() -> AsyncGenerator[PostgreSQLDatabaseController]:
    """Create a test PostgreSQL database."""
    # Import here to avoid import errors if asyncpg is not installed
    from magentic_marketplace.platform.database import connect_to_postgresql_database

    test_schema = f"test_converter_{uuid.uuid4().hex}"

    try:
        async with connect_to_postgresql_database(
            schema=test_schema,
            host="localhost",
            port=5432,
            password="postgres",
        ) as db:
            yield db
    finally:
        # Cleanup: drop the test schema
        try:
            import asyncpg

            conn = await asyncpg.connect(
                host="localhost",
                port=5432,
                user="postgres",
                password="postgres",
                database="postgres",
            )
            await conn.execute(f"DROP SCHEMA IF EXISTS {test_schema} CASCADE")
            await conn.close()
        except Exception:
            pass


class TestDatabaseConverter:
    """Test the database converter."""

    @pytest.mark.asyncio
    async def test_convert_empty_database(self, postgres_test_db):
        """Test converting an empty PostgreSQL database to SQLite."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_file:
            sqlite_path = Path(temp_file.name)

        try:
            # Convert
            result_path = await convert_postgres_to_sqlite(
                postgres_test_db, sqlite_path
            )

            assert result_path == sqlite_path
            assert sqlite_path.exists()

            # Verify the SQLite database is empty
            async with connect_to_sqlite_database(str(sqlite_path)) as sqlite_db:
                agents = await sqlite_db.agents.get_all()
                actions = await sqlite_db.actions.get_all()
                logs = await sqlite_db.logs.get_all()

                assert len(agents) == 0
                assert len(actions) == 0
                assert len(logs) == 0
        finally:
            sqlite_path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_convert_with_data(self, postgres_test_db):
        """Test converting a PostgreSQL database with data to SQLite."""
        # Add some test data to PostgreSQL
        agent1 = await postgres_test_db.agents.create(
            AgentRow(
                id="agent-1",
                created_at=datetime.now(UTC),
                data=AgentProfile(id="agent-1", metadata={}),
            )
        )
        agent2 = await postgres_test_db.agents.create(
            AgentRow(
                id="agent-2",
                created_at=datetime.now(UTC),
                data=AgentProfile(id="agent-2", metadata={}),
            )
        )

        action1 = await postgres_test_db.actions.create(
            ActionRow(
                id="action-1",
                created_at=datetime.now(UTC),
                data=ActionRowData(
                    agent_id="agent-1",
                    request=ActionExecutionRequest(name="TestAction", parameters={}),
                    result=ActionExecutionResult(is_error=False, content={}),
                ),
            )
        )

        log1 = await postgres_test_db.logs.create(
            LogRow(
                id="log-1",
                created_at=datetime.now(UTC),
                data=Log(
                    level="info",
                    name="test_log",
                    message="Test log message",
                ),
            )
        )

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_file:
            sqlite_path = Path(temp_file.name)

        try:
            # Convert
            result_path = await convert_postgres_to_sqlite(
                postgres_test_db, sqlite_path
            )

            assert result_path == sqlite_path
            assert sqlite_path.exists()

            # Verify the SQLite database has the data
            async with connect_to_sqlite_database(str(sqlite_path)) as sqlite_db:
                agents = await sqlite_db.agents.get_all()
                actions = await sqlite_db.actions.get_all()
                logs = await sqlite_db.logs.get_all()

                # Check counts
                assert len(agents) == 2
                assert len(actions) == 1
                assert len(logs) == 1

                # Check that rowids match the PostgreSQL row_index
                assert agents[0].index == agent1.index
                assert agents[1].index == agent2.index
                assert actions[0].index == action1.index
                assert logs[0].index == log1.index

                # Check IDs match
                assert agents[0].id == "agent-1"
                assert agents[1].id == "agent-2"
                assert actions[0].id == "action-1"
                assert logs[0].id == "log-1"
        finally:
            sqlite_path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_convert_preserves_order(self, postgres_test_db):
        """Test that conversion preserves row_index order as rowid."""
        # Add multiple items in specific order
        for i in range(5):
            await postgres_test_db.agents.create(
                AgentRow(
                    id=f"agent-{i}",
                    created_at=datetime.now(UTC),
                    data=AgentProfile(id=f"agent-{i}", metadata={}),
                )
            )

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_file:
            sqlite_path = Path(temp_file.name)

        try:
            # Convert
            await convert_postgres_to_sqlite(postgres_test_db, sqlite_path)

            # Verify order is preserved
            async with connect_to_sqlite_database(str(sqlite_path)) as sqlite_db:
                agents = await sqlite_db.agents.get_all()

                # Check that rowids are sequential
                assert len(agents) == 5
                for i, agent in enumerate(agents, start=1):
                    assert agent.index == i
                    assert agent.id == f"agent-{i - 1}"
        finally:
            sqlite_path.unlink(missing_ok=True)
