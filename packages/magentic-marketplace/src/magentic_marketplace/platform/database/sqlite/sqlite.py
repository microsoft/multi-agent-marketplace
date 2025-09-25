"""SQLite implementation of the database controllers using native sqlite3."""

import asyncio
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import aiosqlite
from pydantic_core import to_json

from ...shared.models import (
    AgentProfile,
    Log,
)
from ..base import (
    ActionTableController,
    AgentTableController,
    BaseDatabaseController,
    DatabaseTooBusyError,
    LogTableController,
)
from ..models import ActionRow, ActionRowData, AgentRow, LogRow
from ..queries import AndQuery, JSONQuery, OrQuery, Query, RangeQueryParams


def _convert_query_to_sql(query: Query) -> str:
    """Convert abstract JSONQuery to SQLite-specific SQL."""
    # Handle composite queries
    if isinstance(query, AndQuery):
        left_sql = _convert_query_to_sql(query.left)
        right_sql = _convert_query_to_sql(query.right)
        return f"({left_sql} AND {right_sql})"
    elif isinstance(query, OrQuery):
        left_sql = _convert_query_to_sql(query.left)
        right_sql = _convert_query_to_sql(query.right)
        return f"({left_sql} OR {right_sql})"

    # Handle basic JSONQuery - must be a JSONQuery at this point
    if not isinstance(query, JSONQuery):
        raise ValueError(f"Expected JSONQuery, got {type(query)}")

    # Handle special NULL operators first
    if query.operator in ["IS NULL", "IS NOT NULL"]:
        return f"json_extract(data, '{query.path}') {query.operator}"

    # Handle value conversion for SQL
    if query.value is None:
        # For NULL values, we need to adjust the operator
        if query.operator == "=":
            return f"json_extract(data, '{query.path}') IS NULL"
        elif query.operator == "!=":
            return f"json_extract(data, '{query.path}') IS NOT NULL"
        else:
            # For other operators with NULL, use NULL as is
            escaped_value = "NULL"
    elif isinstance(query.value, str):
        # For LIKE operations, add wildcards automatically
        if query.operator.upper() == "LIKE":
            escaped_value = f"'%{query.value}%'"
        else:
            escaped_value = f"'{query.value}'"
    else:
        escaped_value = str(query.value)

    # Generate SQL using json_extract for SQLite
    sql_operator = (
        query.operator.upper()
        if query.operator.lower() in ["like", "not like", "in", "not in"]
        else query.operator
    )
    if query.value is None and query.operator not in ["=", "!="]:
        return f"json_extract(data, '{query.path}') {sql_operator} {escaped_value}"
    else:
        return f"json_extract(data, '{query.path}') {sql_operator} {escaped_value}"


# SQL DDL for table creation
CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    data TEXT NOT NULL,
    agent_embedding BLOB
);

CREATE TABLE IF NOT EXISTS actions (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS logs (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    data TEXT NOT NULL
);
"""


class _BoundedSqliteConnectionMixIn:
    def __init__(
        self, db_path: str, semaphore: asyncio.Semaphore, timeout: float = 5
    ) -> None:
        self._db_path = db_path
        self._semaphore = semaphore
        self._timeout = timeout
        self._db: aiosqlite.Connection | None = None

    @property
    @asynccontextmanager
    async def connection(self):
        try:
            await asyncio.wait_for(self._semaphore.acquire(), self._timeout)
        except TimeoutError as e:
            raise DatabaseTooBusyError() from e

        try:
            async with aiosqlite.connect(self._db_path) as db:
                yield db
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            # Convert SQLite errors to DatabaseTooBusyError
            if "locked" in str(e).lower() or "busy" in str(e).lower():
                raise DatabaseTooBusyError(f"SQLite database error: {e}") from e
            # Re-raise other SQLite errors as-is
            raise
        finally:
            # Ensure semaphore is released even if context manager setup fails
            self._semaphore.release()


class SQLiteAgentController(AgentTableController, _BoundedSqliteConnectionMixIn):
    """SQLite implementation of AgentTableController."""

    async def create(self, item: AgentRow) -> AgentRow:
        """Create a new agent."""
        agent_id = item.id or str(uuid.uuid4())

        async with self.connection as db:
            await db.execute(
                "INSERT INTO agents (id, created_at, data, agent_embedding) VALUES (?, ?, ?, ?)",
                (
                    agent_id,
                    item.created_at.isoformat(),
                    item.data.model_dump_json(),  # Store full agent as JSON
                    item.agent_embedding,  # Store embedding as BLOB
                ),
            )
            await db.commit()

        # Return the created agent
        return AgentRow(
            id=agent_id,
            created_at=item.created_at,
            data=item.data,
            agent_embedding=item.agent_embedding,
        )

    async def get_by_id(self, item_id: str) -> AgentRow | None:
        """Get agent by ID."""
        async with self.connection as db:
            async with db.execute(
                "SELECT id, created_at, data, agent_embedding FROM agents WHERE id = ?",
                (item_id,),
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            return None

        # Reconstruct agent from JSON
        agent_data = AgentProfile.model_validate_json(row[2])
        return AgentRow(
            id=row[0],
            created_at=row[1],  # type: ignore  # Pydantic handles datetime string parsing
            data=agent_data,
            agent_embedding=row[3],  # BLOB data or None
        )

    async def get_all(self, params: RangeQueryParams | None = None) -> list[AgentRow]:
        """Get all agents with pagination."""
        sql = "SELECT id, created_at, data, agent_embedding FROM agents ORDER BY created_at"
        sql_params: list[Any] = []

        if params and params.limit:
            sql += " LIMIT ? OFFSET ?"
            sql_params.extend([params.limit, params.offset])
        elif params and params.offset:
            sql += " OFFSET ?"
            sql_params.append(params.offset)

        async with self.connection as db:
            async with db.execute(sql, sql_params) as cursor:
                rows = await cursor.fetchall()

        return [
            AgentRow(
                id=row[0],
                created_at=row[1],  # type: ignore  # Pydantic handles datetime string parsing
                data=AgentProfile.model_validate_json(row[2]),
                agent_embedding=row[3],  # BLOB data or None
            )
            for row in rows
        ]

    async def find(
        self, query: Query, params: RangeQueryParams | None = None
    ) -> list[AgentRow]:
        """Find agents using JSONQuery objects."""
        params = params or RangeQueryParams()
        sql = f"""
        SELECT id, created_at, data, agent_embedding FROM agents
        WHERE {_convert_query_to_sql(query)}
        """
        sql_params: list[Any] = []

        # Add time range filters
        if params.after:
            sql += " AND created_at > ?"
            sql_params.append(params.after.isoformat())
        if params.before:
            sql += " AND created_at < ?"
            sql_params.append(params.before.isoformat())

        sql += " ORDER BY created_at"

        # Add pagination
        if params.limit:
            sql += " LIMIT ? OFFSET ?"
            sql_params.extend([params.limit, params.offset])
        elif params.offset:
            sql += " OFFSET ?"
            sql_params.append(params.offset)

        async with self.connection as db:
            async with db.execute(sql, sql_params) as cursor:
                rows = await cursor.fetchall()

        return [
            AgentRow(
                id=row[0],
                created_at=row[1],  # type: ignore  # Pydantic handles datetime string parsing
                data=AgentProfile.model_validate_json(row[2]),
                agent_embedding=row[3],  # BLOB data or None
            )
            for row in rows
        ]

    async def update(self, item_id: str, updates: dict[str, Any]) -> AgentRow | None:
        """Update an agent."""
        # First check if agent exists
        existing = await self.get_by_id(item_id)
        if not existing:
            return None

        # Build update SQL dynamically
        set_clauses: list[str] = []
        sql_params: list[Any] = []

        for key, value in updates.items():
            if key in ["name", "agent_metadata"]:
                set_clauses.append(f"{key} = ?")
                if key == "agent_metadata":
                    sql_params.append(to_json(value).decode())
                else:
                    sql_params.append(value)

        if not set_clauses:
            return existing

        sql_params.append(item_id)
        sql = f"UPDATE agents SET {', '.join(set_clauses)} WHERE id = ?"

        async with self.connection as db:
            await db.execute(sql, sql_params)
            await db.commit()

        # Return updated agent
        return await self.get_by_id(item_id)

    async def delete(self, item_id: str) -> bool:
        """Delete an agent."""
        async with self.connection as db:
            async with db.execute(
                "DELETE FROM agents WHERE id = ?", (item_id,)
            ) as cursor:
                await db.commit()
                return cursor.rowcount > 0

    async def count(self) -> int:
        """Count total agents."""
        async with self.connection as db:
            async with db.execute("SELECT COUNT(*) FROM agents") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def find_agents_by_id_pattern(self, id_pattern: str) -> list[str]:
        """Find all agent IDs that contain the given ID pattern.

        Args:
            id_pattern: The ID pattern to search for (e.g., "Agent")

        Returns:
            List of agent IDs that contain the pattern

        """
        async with self.connection as db:
            async with db.execute(
                "SELECT id FROM agents WHERE id LIKE ?",
                (f"%{id_pattern}%",),
            ) as cursor:
                rows = await cursor.fetchall()

        return [row[0] for row in rows]


class SQLiteActionController(ActionTableController, _BoundedSqliteConnectionMixIn):
    """SQLite implementation of ActionTableController."""

    async def find(
        self, query: Query, params: RangeQueryParams | None = None
    ) -> list[ActionRow]:
        """Find actions using JSONQuery objects."""
        params = params or RangeQueryParams()
        sql = f"""
        SELECT id, created_at, data FROM actions
        WHERE {_convert_query_to_sql(query)}
        """
        sql_params: list[Any] = []

        # Add time range filters
        if params.after:
            sql += " AND created_at > ?"
            sql_params.append(params.after.isoformat())
        if params.before:
            sql += " AND created_at < ?"
            sql_params.append(params.before.isoformat())

        sql += " ORDER BY created_at"

        # Add pagination
        if params.limit:
            sql += " LIMIT ? OFFSET ?"
            sql_params.extend([params.limit, params.offset])
        elif params.offset:
            sql += " OFFSET ?"
            sql_params.append(params.offset)

        async with self.connection as db:
            async with db.execute(sql, sql_params) as cursor:
                rows = await cursor.fetchall()

        return [
            ActionRow(
                id=row[0],
                created_at=row[1],  # type: ignore  # Pydantic handles datetime string parsing
                data=ActionRowData.model_validate_json(row[2]),
            )
            for row in rows
        ]

    async def create(self, item: ActionRow) -> ActionRow:
        """Create a new action."""
        action_id = item.id or str(uuid.uuid4())

        # Store the full action data (request + result) as JSON
        action_json = item.data.model_dump_json()

        async with self.connection as db:
            await db.execute(
                "INSERT INTO actions (id, created_at, data) VALUES (?, ?, ?)",
                (
                    action_id,
                    item.created_at.isoformat(),
                    action_json,
                ),
            )
            await db.commit()

        # Return the created action
        return ActionRow(
            id=action_id,
            created_at=item.created_at,
            data=item.data,
        )

    async def get_by_id(self, item_id: str) -> ActionRow | None:
        """Get action by ID."""
        async with self.connection as db:
            async with db.execute(
                "SELECT id, created_at, data FROM actions WHERE id = ?",
                (item_id,),
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            return None

        # Reconstruct action from JSON
        action_data = ActionRowData.model_validate_json(row[2])
        return ActionRow(
            id=row[0],
            created_at=row[1],  # type: ignore  # Pydantic handles datetime string parsing
            data=action_data,
        )

    async def get_all(self, params: RangeQueryParams | None = None) -> list[ActionRow]:
        """Get all actions with pagination."""
        sql = "SELECT id, created_at, data FROM actions ORDER BY created_at"
        sql_params: list[Any] = []

        if params and params.limit:
            sql += " LIMIT ? OFFSET ?"
            sql_params.extend([params.limit, params.offset])
        elif params and params.offset:
            sql += " OFFSET ?"
            sql_params.append(params.offset)

        async with self.connection as db:
            async with db.execute(sql, sql_params) as cursor:
                rows = await cursor.fetchall()

        return [
            ActionRow(
                id=row[0],
                created_at=row[1],  # type: ignore  # Pydantic handles datetime string parsing
                data=ActionRowData.model_validate_json(row[2]),
            )
            for row in rows
        ]

    async def update(self, item_id: str, updates: dict[str, Any]) -> ActionRow | None:
        """Update an action."""
        # First check if action exists
        existing = await self.get_by_id(item_id)
        if not existing:
            return None

        # Build update SQL dynamically
        set_clauses: list[str] = []
        sql_params: list[Any] = []

        for key, value in updates.items():
            if key == "action":
                set_clauses.append("action_request = ?")
                sql_params.append(value.model_dump_json())
            elif key == "result":
                set_clauses.append("action_result = ?")
                sql_params.append(value.model_dump_json())
            elif key in ["created_at"]:
                set_clauses.append(f"{key} = ?")
                sql_params.append(
                    value.isoformat() if isinstance(value, datetime) else value
                )

        if not set_clauses:
            return existing

        sql_params.append(item_id)
        sql = f"UPDATE actions SET {', '.join(set_clauses)} WHERE id = ?"

        async with self.connection as db:
            await db.execute(sql, sql_params)
            await db.commit()

        # Return updated action
        return await self.get_by_id(item_id)

    async def delete(self, item_id: str) -> bool:
        """Delete an action."""
        async with self.connection as db:
            async with db.execute(
                "DELETE FROM actions WHERE id = ?", (item_id,)
            ) as cursor:
                await db.commit()
                return cursor.rowcount > 0

    async def count(self) -> int:
        """Count total actions."""
        async with self.connection as db:
            async with db.execute("SELECT COUNT(*) FROM actions") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0


class SQLiteLogController(LogTableController, _BoundedSqliteConnectionMixIn):
    """SQLite implementation of LogTableController."""

    async def find(
        self, query: Query, params: RangeQueryParams | None = None
    ) -> list[LogRow]:
        """Find logs using JSONQuery objects."""
        params = params or RangeQueryParams()
        sql = f"""
        SELECT id, created_at, data FROM logs
        WHERE {_convert_query_to_sql(query)}
        """
        sql_params: list[Any] = []

        # Add time range filters
        if params.after:
            sql += " AND created_at > ?"
            sql_params.append(params.after.isoformat())
        if params.before:
            sql += " AND created_at < ?"
            sql_params.append(params.before.isoformat())

        sql += " ORDER BY created_at"

        # Add pagination
        if params.limit:
            sql += " LIMIT ? OFFSET ?"
            sql_params.extend([params.limit, params.offset])
        elif params.offset:
            sql += " OFFSET ?"
            sql_params.append(params.offset)

        async with self.connection as db:
            async with db.execute(sql, sql_params) as cursor:
                rows = await cursor.fetchall()

        return [
            LogRow(
                id=row[0],
                created_at=row[1],  # type: ignore  # Pydantic handles datetime string parsing
                data=Log.model_validate_json(row[2]),
            )
            for row in rows
        ]

    async def create(self, item: LogRow) -> LogRow:
        """Create a new log record."""
        log_id = item.id or str(uuid.uuid4())

        async with self.connection as db:
            await db.execute(
                "INSERT INTO logs (id, created_at, data) VALUES (?, ?, ?)",
                (
                    log_id,
                    item.created_at.isoformat(),
                    item.data.model_dump_json(),  # Store full log as JSON
                ),
            )
            await db.commit()

        # Return the created log
        return LogRow(id=log_id, created_at=item.created_at, data=item.data)

    async def get_by_id(self, item_id: str) -> LogRow | None:
        """Get log by ID."""
        async with self.connection as db:
            async with db.execute(
                "SELECT id, created_at, data FROM logs WHERE id = ?",
                (item_id,),
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            return None

        # Reconstruct log from JSON
        log_data = Log.model_validate_json(row[2])
        return LogRow(
            id=row[0],
            created_at=row[1],  # type: ignore  # Pydantic handles datetime string parsing
            data=log_data,
        )

    async def get_all(self, params: RangeQueryParams | None = None) -> list[LogRow]:
        """Get all logs with pagination."""
        sql = "SELECT id, created_at, data FROM logs ORDER BY created_at"
        sql_params: list[Any] = []

        if params and params.limit:
            sql += " LIMIT ? OFFSET ?"
            sql_params.extend([params.limit, params.offset])
        elif params and params.offset:
            sql += " OFFSET ?"
            sql_params.append(params.offset)

        async with self.connection as db:
            async with db.execute(sql, sql_params) as cursor:
                rows = await cursor.fetchall()

        return [
            LogRow(
                id=row[0],
                created_at=row[1],  # type: ignore  # Pydantic handles datetime string parsing
                data=Log.model_validate_json(row[2]),
            )
            for row in rows
        ]

    async def update(self, item_id: str, updates: dict[str, Any]) -> LogRow | None:
        """Update a log record."""
        # First check if log exists
        existing = await self.get_by_id(item_id)
        if not existing:
            return None

        # Build update SQL dynamically
        set_clauses: list[str] = []
        sql_params: list[Any] = []

        for key, value in updates.items():
            if key in ["level", "content"]:
                set_clauses.append(f"{key} = ?")
                if key == "content":
                    sql_params.append(to_json(value).decode())
                else:
                    sql_params.append(value)

        if not set_clauses:
            return existing

        sql_params.append(item_id)
        sql = f"UPDATE logs SET {', '.join(set_clauses)} WHERE id = ?"

        async with self.connection as db:
            await db.execute(sql, sql_params)
            await db.commit()

        # Return updated log
        return await self.get_by_id(item_id)

    async def delete(self, item_id: str) -> bool:
        """Delete a log record."""
        async with self.connection as db:
            async with db.execute(
                "DELETE FROM logs WHERE id = ?", (item_id,)
            ) as cursor:
                await db.commit()
                return cursor.rowcount > 0

    async def count(self) -> int:
        """Count total log records."""
        async with self.connection as db:
            async with db.execute("SELECT COUNT(*) FROM logs") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0


class SQLiteDatabaseController(BaseDatabaseController, _BoundedSqliteConnectionMixIn):
    """SQLite implementation of BaseDatabaseController."""

    def __init__(self, db_path: str, db_timeout: float = 5):
        """Initialize SQLite database controller with database path."""
        semaphore = asyncio.Semaphore(1)
        super().__init__(db_path=db_path, semaphore=semaphore, timeout=db_timeout)
        self._agents = SQLiteAgentController(db_path, semaphore, db_timeout)
        self._actions = SQLiteActionController(db_path, semaphore, db_timeout)
        self._logs = SQLiteLogController(db_path, semaphore, db_timeout)

    @property
    def agents(self) -> AgentTableController:
        """Get the agent controller."""
        return self._agents

    @property
    def actions(self) -> ActionTableController:
        """Get the action controller."""
        return self._actions

    @property
    def logs(self) -> LogTableController:
        """Get the log controller."""
        return self._logs

    async def execute(self, command: Any) -> Any:
        """Execute an arbitrary database command."""
        async with self.connection as db:
            async with db.execute(command) as cursor:
                return cursor

    async def initialize(self):
        """Initialize the database tables."""
        async with self.connection as db:
            await db.executescript(CREATE_TABLES_SQL)
            await db.commit()


@asynccontextmanager
async def create_sqlite_database(database_path: str = "marketplace.db"):
    """Create SQLite database controller."""
    controller = SQLiteDatabaseController(database_path)
    try:
        await controller.initialize()
        yield controller
    finally:
        # Any cleanup if needed
        pass
