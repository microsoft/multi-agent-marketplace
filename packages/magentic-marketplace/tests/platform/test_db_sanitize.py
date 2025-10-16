"""Tests for Unicode fixing in PostgreSQL database layer."""

from datetime import UTC, datetime

import pytest
import pytest_asyncio

from magentic_marketplace.platform.database.models import (
    ActionRow,
    ActionRowData,
    LogRow,
)
from magentic_marketplace.platform.database.postgresql.utils import (
    fix_json_for_postgres,
)
from magentic_marketplace.platform.shared.models import (
    ActionExecutionRequest,
    ActionExecutionResult,
    Log,
)


class TestFixJsonForPostgres:
    """Tests for _fix_json_for_postgres helper function."""

    def test_fix_null_bytes_in_string(self):
        """Test that null bytes are fixed in strings."""
        data = {"message": "Hello\u0000World"}
        fixed = fix_json_for_postgres(data)
        assert "\u0000" not in fixed["message"]
        assert "Hello" in fixed["message"]
        assert "World" in fixed["message"]

    def test_fix_nested_dict(self):
        """Test fixing nested dictionaries."""
        data = {"outer": {"inner": "Dirty\u0000String", "clean": "Clean String"}}
        fixed = fix_json_for_postgres(data)
        assert "\u0000" not in fixed["outer"]["inner"]
        assert "Dirty" in fixed["outer"]["inner"]
        assert fixed["outer"]["clean"] == "Clean String"

    def test_fix_list_with_strings(self):
        """Test fixing lists with strings."""
        data = {"items": ["Hello\u0000World", "Clean"]}
        fixed = fix_json_for_postgres(data)
        assert "\u0000" not in fixed["items"][0]
        assert "Hello" in fixed["items"][0]
        assert fixed["items"][1] == "Clean"

    def test_preserve_clean_strings(self):
        """Test that clean strings are preserved."""
        data = {"message": "Hello World"}
        fixed = fix_json_for_postgres(data)
        assert fixed["message"] == "Hello World"

    def test_preserve_non_string_types(self):
        """Test that non-string types are preserved."""
        data = {"int": 42, "float": 3.14, "bool": True, "none": None}
        fixed = fix_json_for_postgres(data)
        assert fixed["int"] == 42
        assert fixed["float"] == 3.14
        assert fixed["bool"] is True
        assert fixed["none"] is None


@pytest.mark.asyncio
class TestPostgreSQLUnicodeFix:
    """Integration tests for PostgreSQL unicode fixing on insert."""

    @pytest_asyncio.fixture
    async def db(self):
        """Create a PostgreSQL database controller for testing."""
        from magentic_marketplace.platform.database.postgresql.postgresql import (
            PostgreSQLDatabaseController,
        )

        # Skip if no PostgreSQL available
        try:
            controller = await PostgreSQLDatabaseController.from_cached(
                schema=f"test_unicode_{int(datetime.now().timestamp())}",
                host="localhost",
                port=5432,
                database="marketplace",
                user="postgres",
                password="postgres",
                min_size=2,
                max_size=2,
                mode="create_new",
            )
            yield controller

            # Cleanup
            async with controller._pool.acquire() as conn:
                await conn.execute(f"DROP SCHEMA {controller._schema} CASCADE")
            await controller._pool.close()
        except Exception as e:
            pytest.skip(f"PostgreSQL not available: {e}")

    async def test_action_with_null_bytes(self, db):
        """Test that actions with null bytes are fixed on insert."""
        action_data = ActionRowData(
            agent_id="test-agent",
            request=ActionExecutionRequest(
                name="test_action", parameters={}, metadata={}
            ),
            result=ActionExecutionResult(
                content="Response\u0000with\u0000null\u0000bytes", is_error=False
            ),
        )

        action_row = ActionRow(
            id="test-action-1", created_at=datetime.now(UTC), data=action_data
        )

        # This should succeed even with null bytes (ftfy will fix them on retry)
        created = await db.actions.create(action_row)
        assert created.id == "test-action-1"

        # Verify we can read it back
        retrieved = await db.actions.get_by_id("test-action-1")
        assert retrieved is not None
        assert "\u0000" not in str(retrieved.data.result.content)

    async def test_log_with_null_bytes(self, db):
        """Test that logs with null bytes are fixed on insert."""
        log_data = Log(
            level="info",
            name="test-logger",
            message="Log\u0000message\u0000with\u0000nulls",
            data={"key": "value\u0000dirty"},
        )

        log_row = LogRow(id="test-log-1", created_at=datetime.now(UTC), data=log_data)

        # This should succeed even with null bytes (ftfy will fix them on retry)
        created = await db.logs.create(log_row)
        assert created.id == "test-log-1"

        # Verify we can read it back
        retrieved = await db.logs.get_by_id("test-log-1")
        assert retrieved is not None
        assert "\u0000" not in str(retrieved.data.message)
        assert "\u0000" not in str(retrieved.data.data)
