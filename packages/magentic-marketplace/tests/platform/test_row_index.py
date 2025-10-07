"""Tests for row_index functionality across all database tables."""

import asyncio
import tempfile
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import pytest_asyncio

from magentic_marketplace.platform.database.models import (
    ActionRow,
    ActionRowData,
    AgentRow,
    LogRow,
)
from magentic_marketplace.platform.database.queries import RangeQueryParams
from magentic_marketplace.platform.database.sqlite import create_sqlite_database
from magentic_marketplace.platform.database.sqlite.sqlite import (
    SQLiteDatabaseController,
)
from magentic_marketplace.platform.shared.models import (
    ActionExecutionRequest,
    ActionExecutionResult,
    AgentProfile,
    Log,
)


@pytest_asyncio.fixture
async def database() -> AsyncGenerator[SQLiteDatabaseController]:
    """Create a test database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_file:
        db_path = temp_file.name

    async with create_sqlite_database(db_path) as db:
        yield db

    # Cleanup
    try:
        import os

        os.unlink(db_path)
    except Exception:
        pass


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
