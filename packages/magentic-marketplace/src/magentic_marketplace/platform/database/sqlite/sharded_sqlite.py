"""Sharded SQLite implementation for high-throughput database operations."""

import asyncio
import hashlib
import logging
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
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

logger = logging.getLogger(__name__)

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


def _get_shard_for_id(item_id: str, num_shards: int) -> int:
    """Get shard number for a given ID using hash-based distribution."""
    hash_value = int(hashlib.md5(item_id.encode()).hexdigest(), 16)
    return hash_value % num_shards


class _ShardedBoundedSqliteConnectionMixIn:
    """Base class for sharded SQLite connections with bounded connection pools."""

    def __init__(
        self,
        base_path: str,
        table_name: str,
        num_shards: int,
        max_read_connections_per_shard: int = 3,
        timeout: float = 5,
    ) -> None:
        self._base_path = base_path
        self._table_name = table_name
        self._num_shards = num_shards
        self._timeout = timeout

        # Create folder structure: base_path/table_name/shard_{i}.db
        self._table_dir = Path(base_path) / table_name
        self._shard_paths = [
            str(self._table_dir / f"shard_{i}.db") for i in range(num_shards)
        ]

        # Create per-shard semaphores
        self._read_semaphores = [
            asyncio.Semaphore(max_read_connections_per_shard) for _ in range(num_shards)
        ]
        # Write connections must always be limited to 1 per shard to prevent conflicts
        self._write_semaphores = [
            asyncio.Semaphore(1) for _ in range(num_shards)
        ]

    def _get_shard_path(self, shard_id: int) -> str:
        """Get the database path for a specific shard."""
        return self._shard_paths[shard_id]

    def _get_shard_for_id(self, item_id: str) -> int:
        """Get shard number for a given ID."""
        return _get_shard_for_id(item_id, self._num_shards)

    @asynccontextmanager
    async def _connection_for_shard(self, shard_id: int, is_write: bool = False):
        """Get a connection to a specific shard."""
        semaphore = (
            self._write_semaphores[shard_id]
            if is_write
            else self._read_semaphores[shard_id]
        )
        try:
            await asyncio.wait_for(semaphore.acquire(), self._timeout)
        except TimeoutError as e:
            logger.warning(
                f"Database too busy: timeout acquiring semaphore for {self._table_name} shard {shard_id} ({'write' if is_write else 'read'} operation)"
            )
            raise DatabaseTooBusyError() from e

        try:
            db_path = self._get_shard_path(shard_id)
            # Ensure the directory exists before connecting
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            async with aiosqlite.connect(db_path) as db:
                # Apply performance optimizations
                await db.execute("PRAGMA journal_mode=WAL")
                await db.execute("PRAGMA synchronous=NORMAL")
                yield db
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            # Convert SQLite errors to DatabaseTooBusyError
            if "locked" in str(e).lower() or "busy" in str(e).lower():
                logger.warning(
                    f"Database too busy: SQLite lock/busy error for {self._table_name} shard {shard_id} ({'write' if is_write else 'read'} operation): {e}"
                )
                raise DatabaseTooBusyError(f"SQLite database error: {e}") from e
            # Re-raise other SQLite errors as-is
            raise
        finally:
            # Ensure semaphore is released even if context manager setup fails
            semaphore.release()

    @asynccontextmanager
    async def _read_connection_for_id(self, item_id: str):
        """Get a read connection to the shard containing the given ID."""
        shard_id = self._get_shard_for_id(item_id)
        async with self._connection_for_shard(shard_id, is_write=False) as db:
            yield db

    @asynccontextmanager
    async def _write_connection_for_id(self, item_id: str):
        """Get a write connection to the shard containing the given ID."""
        shard_id = self._get_shard_for_id(item_id)
        async with self._connection_for_shard(shard_id, is_write=True) as db:
            yield db

    @asynccontextmanager
    async def _read_connection_for_shard(self, shard_id: int):
        """Get a read connection to a specific shard."""
        async with self._connection_for_shard(shard_id, is_write=False) as db:
            yield db

    @asynccontextmanager
    async def _write_connection_for_shard(self, shard_id: int):
        """Get a write connection to a specific shard."""
        async with self._connection_for_shard(shard_id, is_write=True) as db:
            yield db

    async def _execute_on_all_shards(self, sql: str, params: list[Any] | None = None):
        """Execute SQL on all shards and return combined results (read operations)."""
        params = params or []
        all_results: list[sqlite3.Row] = []

        # Execute on all shards concurrently
        async def execute_on_shard(shard_id: int):
            async with self._read_connection_for_shard(shard_id) as db:
                async with db.execute(sql, params) as cursor:
                    return await cursor.fetchall()

        # Run all shard queries concurrently
        tasks = [execute_on_shard(i) for i in range(self._num_shards)]
        shard_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Combine results, filtering out exceptions
        for result in shard_results:
            if isinstance(result, BaseException):
                # Log exceptions that occurred during shard execution
                continue
            all_results.extend(result)

        return all_results

    async def merge_shards_to_file(self, target_db_path: str, table_name: str):
        """Merge all shards for this table into a target database file."""
        # Connect to target database
        async with aiosqlite.connect(target_db_path) as target_db:
            # Apply performance optimizations to target database
            await target_db.execute("PRAGMA journal_mode=WAL")
            await target_db.execute("PRAGMA synchronous=NORMAL")
            # Create the table schema in target if it doesn't exist
            if table_name == "agents":
                await target_db.execute("""
                    CREATE TABLE IF NOT EXISTS agents (
                        id TEXT PRIMARY KEY,
                        created_at TEXT NOT NULL,
                        data TEXT NOT NULL,
                        agent_embedding BLOB
                    )
                """)
            elif table_name == "actions":
                await target_db.execute("""
                    CREATE TABLE IF NOT EXISTS actions (
                        id TEXT PRIMARY KEY,
                        created_at TEXT NOT NULL,
                        data TEXT NOT NULL
                    )
                """)
            elif table_name == "logs":
                await target_db.execute("""
                    CREATE TABLE IF NOT EXISTS logs (
                        id TEXT PRIMARY KEY,
                        created_at TEXT NOT NULL,
                        data TEXT NOT NULL
                    )
                """)

            # Copy data from all shards
            for shard_id in range(self._num_shards):
                async with self._read_connection_for_shard(shard_id) as shard_db:
                    # Get all rows from this shard
                    if table_name == "agents":
                        query = (
                            "SELECT id, created_at, data, agent_embedding FROM agents"
                        )
                        async with shard_db.execute(query) as cursor:
                            rows = await cursor.fetchall()
                            for row in rows:
                                await target_db.execute(
                                    "INSERT OR REPLACE INTO agents (id, created_at, data, agent_embedding) VALUES (?, ?, ?, ?)",
                                    row,
                                )
                    elif table_name == "actions":
                        query = "SELECT id, created_at, data FROM actions"
                        async with shard_db.execute(query) as cursor:
                            rows = await cursor.fetchall()
                            for row in rows:
                                await target_db.execute(
                                    "INSERT OR REPLACE INTO actions (id, created_at, data) VALUES (?, ?, ?)",
                                    row,
                                )
                    elif table_name == "logs":
                        query = "SELECT id, created_at, data FROM logs"
                        async with shard_db.execute(query) as cursor:
                            rows = await cursor.fetchall()
                            for row in rows:
                                await target_db.execute(
                                    "INSERT OR REPLACE INTO logs (id, created_at, data) VALUES (?, ?, ?)",
                                    row,
                                )

            await target_db.commit()


class ShardedSQLiteAgentController(
    AgentTableController, _ShardedBoundedSqliteConnectionMixIn
):
    """Sharded SQLite implementation of AgentTableController."""

    async def create(self, item: AgentRow) -> AgentRow:
        """Create a new agent in the appropriate shard."""
        agent_id = item.id or str(uuid.uuid4())

        async with self._write_connection_for_id(agent_id) as db:
            await db.execute(
                "INSERT INTO agents (id, created_at, data, agent_embedding) VALUES (?, ?, ?, ?)",
                (
                    agent_id,
                    item.created_at.isoformat(),
                    item.data.model_dump_json(),
                    item.agent_embedding,
                ),
            )
            await db.commit()

        return AgentRow(
            id=agent_id,
            created_at=item.created_at,
            data=item.data,
            agent_embedding=item.agent_embedding,
        )

    async def get_by_id(self, item_id: str) -> AgentRow | None:
        """Get agent by ID from the appropriate shard."""
        async with self._read_connection_for_id(item_id) as db:
            async with db.execute(
                "SELECT id, created_at, data, agent_embedding FROM agents WHERE id = ?",
                (item_id,),
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            return None

        agent_data = AgentProfile.model_validate_json(row[2])
        return AgentRow(
            id=row[0],
            created_at=row[1],
            data=agent_data,
            agent_embedding=row[3],
        )

    async def get_all(self, params: RangeQueryParams | None = None) -> list[AgentRow]:
        """Get all agents from all shards with pagination."""
        sql = "SELECT id, created_at, data, agent_embedding FROM agents ORDER BY created_at"
        sql_params: list[Any] = []

        # Note: For sharded databases, pagination is complex and may not be exact
        # This implementation fetches from all shards and then applies pagination
        rows = await self._execute_on_all_shards(sql, sql_params)

        # Sort combined results by created_at
        rows.sort(key=lambda x: x[1])

        # Apply pagination to combined results
        if params:
            start = params.offset
            end = start + params.limit if params.limit else None
            rows = rows[start:end]

        return [
            AgentRow(
                id=row[0],
                created_at=row[1],
                data=AgentProfile.model_validate_json(row[2]),
                agent_embedding=row[3],
            )
            for row in rows
        ]

    async def find(
        self, query: Query, params: RangeQueryParams | None = None
    ) -> list[AgentRow]:
        """Find agents across all shards using JSONQuery objects."""
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

        # Execute on all shards
        rows = await self._execute_on_all_shards(sql, sql_params)

        # Sort combined results
        rows.sort(key=lambda x: x[1])

        # Apply pagination to combined results
        if params.limit:
            start = params.offset
            end = start + params.limit
            rows = rows[start:end]
        elif params.offset:
            rows = rows[params.offset :]

        return [
            AgentRow(
                id=row[0],
                created_at=row[1],
                data=AgentProfile.model_validate_json(row[2]),
                agent_embedding=row[3],
            )
            for row in rows
        ]

    async def update(self, item_id: str, updates: dict[str, Any]) -> AgentRow | None:
        """Update an agent in the appropriate shard."""
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

        async with self._write_connection_for_id(item_id) as db:
            await db.execute(sql, sql_params)
            await db.commit()

        return await self.get_by_id(item_id)

    async def delete(self, item_id: str) -> bool:
        """Delete an agent from the appropriate shard."""
        async with self._write_connection_for_id(item_id) as db:
            async with db.execute(
                "DELETE FROM agents WHERE id = ?", (item_id,)
            ) as cursor:
                await db.commit()
                return cursor.rowcount > 0

    async def count(self) -> int:
        """Count total agents across all shards."""
        count_sql = "SELECT COUNT(*) FROM agents"
        rows = await self._execute_on_all_shards(count_sql)
        return sum(row[0] for row in rows)

    async def find_agents_by_id_pattern(self, id_pattern: str) -> list[str]:
        """Find all agent IDs across all shards that contain the given ID pattern."""
        sql = "SELECT id FROM agents WHERE id LIKE ?"
        params = [f"%{id_pattern}%"]

        rows = await self._execute_on_all_shards(sql, params)
        return [row[0] for row in rows]

    async def merge_to_file(self, target_db_path: str):
        """Merge all agent shards into the target database file."""
        await self.merge_shards_to_file(target_db_path, "agents")


class ShardedSQLiteActionController(
    ActionTableController, _ShardedBoundedSqliteConnectionMixIn
):
    """Sharded SQLite implementation of ActionTableController."""

    async def find(
        self, query: Query, params: RangeQueryParams | None = None
    ) -> list[ActionRow]:
        """Find actions across all shards using JSONQuery objects."""
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

        # Execute on all shards
        rows = await self._execute_on_all_shards(sql, sql_params)

        # Sort combined results
        rows.sort(key=lambda x: x[1])

        # Apply pagination to combined results
        if params.limit:
            start = params.offset
            end = start + params.limit
            rows = rows[start:end]
        elif params.offset:
            rows = rows[params.offset :]

        return [
            ActionRow(
                id=row[0],
                created_at=row[1],
                data=ActionRowData.model_validate_json(row[2]),
            )
            for row in rows
        ]

    async def create(self, item: ActionRow) -> ActionRow:
        """Create a new action in the appropriate shard."""
        action_id = item.id or str(uuid.uuid4())
        action_json = item.data.model_dump_json()

        async with self._write_connection_for_id(action_id) as db:
            await db.execute(
                "INSERT INTO actions (id, created_at, data) VALUES (?, ?, ?)",
                (
                    action_id,
                    item.created_at.isoformat(),
                    action_json,
                ),
            )
            await db.commit()

        return ActionRow(
            id=action_id,
            created_at=item.created_at,
            data=item.data,
        )

    async def get_by_id(self, item_id: str) -> ActionRow | None:
        """Get action by ID from the appropriate shard."""
        async with self._read_connection_for_id(item_id) as db:
            async with db.execute(
                "SELECT id, created_at, data FROM actions WHERE id = ?",
                (item_id,),
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            return None

        action_data = ActionRowData.model_validate_json(row[2])
        return ActionRow(
            id=row[0],
            created_at=row[1],
            data=action_data,
        )

    async def get_all(self, params: RangeQueryParams | None = None) -> list[ActionRow]:
        """Get all actions from all shards with pagination."""
        sql = "SELECT id, created_at, data FROM actions ORDER BY created_at"

        rows = await self._execute_on_all_shards(sql)

        # Sort combined results by created_at
        rows.sort(key=lambda x: x[1])

        # Apply pagination to combined results
        if params:
            start = params.offset
            end = start + params.limit if params.limit else None
            rows = rows[start:end]

        return [
            ActionRow(
                id=row[0],
                created_at=row[1],
                data=ActionRowData.model_validate_json(row[2]),
            )
            for row in rows
        ]

    async def update(self, item_id: str, updates: dict[str, Any]) -> ActionRow | None:
        """Update an action in the appropriate shard."""
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

        async with self._write_connection_for_id(item_id) as db:
            await db.execute(sql, sql_params)
            await db.commit()

        return await self.get_by_id(item_id)

    async def delete(self, item_id: str) -> bool:
        """Delete an action from the appropriate shard."""
        async with self._write_connection_for_id(item_id) as db:
            async with db.execute(
                "DELETE FROM actions WHERE id = ?", (item_id,)
            ) as cursor:
                await db.commit()
                return cursor.rowcount > 0

    async def count(self) -> int:
        """Count total actions across all shards."""
        count_sql = "SELECT COUNT(*) FROM actions"
        rows = await self._execute_on_all_shards(count_sql)
        return sum(row[0] for row in rows)

    async def merge_to_file(self, target_db_path: str):
        """Merge all action shards into the target database file."""
        await self.merge_shards_to_file(target_db_path, "actions")


class ShardedSQLiteLogController(
    LogTableController, _ShardedBoundedSqliteConnectionMixIn
):
    """Sharded SQLite implementation of LogTableController."""

    async def find(
        self, query: Query, params: RangeQueryParams | None = None
    ) -> list[LogRow]:
        """Find logs across all shards using JSONQuery objects."""
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

        # Execute on all shards
        rows = await self._execute_on_all_shards(sql, sql_params)

        # Sort combined results
        rows.sort(key=lambda x: x[1])

        # Apply pagination to combined results
        if params.limit:
            start = params.offset
            end = start + params.limit
            rows = rows[start:end]
        elif params.offset:
            rows = rows[params.offset :]

        return [
            LogRow(
                id=row[0],
                created_at=row[1],
                data=Log.model_validate_json(row[2]),
            )
            for row in rows
        ]

    async def create(self, item: LogRow) -> LogRow:
        """Create a new log record in the appropriate shard."""
        log_id = item.id or str(uuid.uuid4())

        async with self._write_connection_for_id(log_id) as db:
            await db.execute(
                "INSERT INTO logs (id, created_at, data) VALUES (?, ?, ?)",
                (
                    log_id,
                    item.created_at.isoformat(),
                    item.data.model_dump_json(),
                ),
            )
            await db.commit()

        return LogRow(id=log_id, created_at=item.created_at, data=item.data)

    async def get_by_id(self, item_id: str) -> LogRow | None:
        """Get log by ID from the appropriate shard."""
        async with self._read_connection_for_id(item_id) as db:
            async with db.execute(
                "SELECT id, created_at, data FROM logs WHERE id = ?",
                (item_id,),
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            return None

        log_data = Log.model_validate_json(row[2])
        return LogRow(
            id=row[0],
            created_at=row[1],
            data=log_data,
        )

    async def get_all(self, params: RangeQueryParams | None = None) -> list[LogRow]:
        """Get all logs from all shards with pagination."""
        sql = "SELECT id, created_at, data FROM logs ORDER BY created_at"

        rows = await self._execute_on_all_shards(sql)

        # Sort combined results by created_at
        rows.sort(key=lambda x: x[1])

        # Apply pagination to combined results
        if params:
            start = params.offset
            end = start + params.limit if params.limit else None
            rows = rows[start:end]

        return [
            LogRow(
                id=row[0],
                created_at=row[1],
                data=Log.model_validate_json(row[2]),
            )
            for row in rows
        ]

    async def update(self, item_id: str, updates: dict[str, Any]) -> LogRow | None:
        """Update a log record in the appropriate shard."""
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

        async with self._write_connection_for_id(item_id) as db:
            await db.execute(sql, sql_params)
            await db.commit()

        return await self.get_by_id(item_id)

    async def delete(self, item_id: str) -> bool:
        """Delete a log record from the appropriate shard."""
        async with self._write_connection_for_id(item_id) as db:
            async with db.execute(
                "DELETE FROM logs WHERE id = ?", (item_id,)
            ) as cursor:
                await db.commit()
                return cursor.rowcount > 0

    async def count(self) -> int:
        """Count total log records across all shards."""
        count_sql = "SELECT COUNT(*) FROM logs"
        rows = await self._execute_on_all_shards(count_sql)
        return sum(row[0] for row in rows)

    async def merge_to_file(self, target_db_path: str):
        """Merge all log shards into the target database file."""
        await self.merge_shards_to_file(target_db_path, "logs")


class ShardedSQLiteDatabaseController(BaseDatabaseController):
    """Sharded SQLite implementation of BaseDatabaseController.

    This controller creates separate database files for each table, with each
    table sharded across multiple database files for improved IO throughput.

    Architecture:
    - Each table (agents, actions, logs) is stored in its own set of sharded databases
    - Each table has a configurable number of shards
    - Rows are distributed to shards based on hash(id) % num_shards
    - Find operations search across all shards and merge results
    - Get operations go directly to the appropriate shard
    """

    def __init__(
        self,
        base_path: str,
        agent_shards: int = 4,
        action_shards: int = 4,
        log_shards: int = 4,
        db_timeout: float = 5,
        max_read_connections_per_shard: int = 3,
    ):
        """Initialize sharded SQLite database controller.

        Args:
            base_path: Base path for database files (without extension)
            agent_shards: Number of shards for agent table
            action_shards: Number of shards for action table
            log_shards: Number of shards for log table
            db_timeout: Connection timeout in seconds
            max_read_connections_per_shard: Maximum concurrent read connections per shard

        """
        self._base_path = base_path
        self._agent_shards = agent_shards
        self._action_shards = action_shards
        self._log_shards = log_shards
        self._timeout = db_timeout

        # Initialize controllers - each creates its own per-shard semaphores
        self._agents = ShardedSQLiteAgentController(
            base_path,
            "agents",
            agent_shards,
            max_read_connections_per_shard,
            db_timeout,
        )
        self._actions = ShardedSQLiteActionController(
            base_path,
            "actions",
            action_shards,
            max_read_connections_per_shard,
            db_timeout,
        )
        self._logs = ShardedSQLiteLogController(
            base_path,
            "logs",
            log_shards,
            max_read_connections_per_shard,
            db_timeout,
        )

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
        """Execute an arbitrary database command on all shards."""
        # This is a simplified implementation that executes on agent shards
        # In practice, you might want to specify which table/shards to execute on
        results = []
        for i in range(self._agent_shards):
            async with self._agents._write_connection_for_shard(i) as db:
                async with db.execute(command) as cursor:
                    results.append(await cursor.fetchall())
        return results

    async def initialize(self):
        """Initialize all database tables across all shards."""
        # SQL DDL for all tables - each shard will contain all three tables
        create_all_tables_sql = """
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

        # Initialize all shards concurrently
        async def init_shard(controller, shard_id: int):
            async with controller._write_connection_for_shard(shard_id) as db:
                await db.executescript(create_all_tables_sql)
                await db.commit()

        # Create tasks for all shard initializations
        tasks = []

        # Agent shards - each contains all tables but only agents table will be used
        for i in range(self._agent_shards):
            tasks.append(init_shard(self._agents, i))

        # Action shards - each contains all tables but only actions table will be used
        for i in range(self._action_shards):
            tasks.append(init_shard(self._actions, i))

        # Log shards - each contains all tables but only logs table will be used
        for i in range(self._log_shards):
            tasks.append(init_shard(self._logs, i))

        # Run all initializations concurrently
        await asyncio.gather(*tasks)

    async def merge_all_shards(self, target_db_path: str):
        """Merge all shards from all tables into a single SQLite database file.

        Args:
            target_db_path: Path to the target merged database file

        Note:
            This creates a new merged file and leaves the original shards intact.
            The merged file will contain all data from all shards across all tables.

        """
        # Create target database with all table schemas
        async with aiosqlite.connect(target_db_path) as target_db:
            # Apply performance optimizations to target database
            await target_db.execute("PRAGMA journal_mode=WAL")
            await target_db.execute("PRAGMA synchronous=NORMAL")
            await target_db.executescript("""
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
            """)
            await target_db.commit()

        # Merge each table type serially to avoid database locking issues
        await self._agents.merge_to_file(target_db_path)
        await self._actions.merge_to_file(target_db_path)
        await self._logs.merge_to_file(target_db_path)


@asynccontextmanager
async def create_sharded_sqlite_database(
    base_path: str = "marketplace_sharded",
    agent_shards: int = 4,
    action_shards: int = 4,
    log_shards: int = 4,
    db_timeout: float = 5,
    max_read_connections_per_shard: int = 100,
):
    """Create sharded SQLite database controller.

    Args:
        base_path: Base path for database files (without extension)
        agent_shards: Number of shards for agent table
        action_shards: Number of shards for action table
        log_shards: Number of shards for log table
        db_timeout: Connection timeout in seconds
        max_read_connections_per_shard: Maximum concurrent read connections per shard

    """
    controller = ShardedSQLiteDatabaseController(
        base_path=base_path,
        agent_shards=agent_shards,
        action_shards=action_shards,
        log_shards=log_shards,
        db_timeout=db_timeout,
        max_read_connections_per_shard=max_read_connections_per_shard,
    )
    try:
        await controller.initialize()
        yield controller
    finally:
        # Any cleanup if needed
        pass
