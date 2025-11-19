"""SQLite implementation of the database controllers using native sqlite3."""

import asyncio
import json
import logging
import sqlite3
import threading
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
from ..queries import AndQuery, JSONQuery, OrQuery, Query, QueryParams, RangeQueryParams

# Global metrics tracking
_connection_metrics = {
    "read_requests": 0,
    "write_requests": 0,
    "read_semaphore_timeouts": 0,
    "write_semaphore_timeouts": 0,
    "read_db_errors": 0,
    "write_db_errors": 0,
}

# Global metrics timer
_metrics_timer = None

logger = logging.getLogger(__name__)


def _dump_metrics_to_file(db_path: str):
    """Dump metrics to file."""
    try:
        # Extract base name without extension for metrics file
        db_base = db_path.rsplit(".", 1)[0] if "." in db_path else db_path
        metrics_file = f"{db_base}_metrics.json"
        with open(metrics_file, "w") as f:
            json.dump(_connection_metrics, f, indent=2)
    except Exception:
        # Silently fail to avoid issues during cleanup
        pass


def _start_metrics_timer(db_path: str):
    """Start a repeating timer to dump metrics every 10 seconds."""
    global _metrics_timer

    # Only start one timer globally
    if _metrics_timer is not None:
        return

    def dump_metrics():
        _dump_metrics_to_file(db_path)
        # Schedule next dump
        global _metrics_timer
        _metrics_timer = threading.Timer(10.0, dump_metrics)
        _metrics_timer.daemon = True  # Dies when main thread dies
        _metrics_timer.start()

    # Start the first timer
    _metrics_timer = threading.Timer(10.0, dump_metrics)
    _metrics_timer.daemon = True
    _metrics_timer.start()


def _stop_metrics_timer():
    """Stop the metrics timer."""
    global _metrics_timer
    if _metrics_timer is not None:
        _metrics_timer.cancel()
        _metrics_timer = None


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


def _convert_query_params_to_sql(
    *,
    sql: str,
    query: Query | None = None,
    params: QueryParams | None = None,
    sql_params: list[Any] | None = None,
):
    sql_params = list(sql_params or [])
    where_clauses: list[str] = []

    # Add query filter if provided
    if query is not None:
        where_clauses.append(_convert_query_to_sql(query))

    # Add time range filters
    if params and isinstance(params, RangeQueryParams):
        if params.after:
            where_clauses.append("created_at > ?")
            sql_params.append(params.after.isoformat())
        if params.before:
            where_clauses.append("created_at < ?")
            sql_params.append(params.before.isoformat())

        # Add index range filters
        if params.after_index is not None:
            where_clauses.append("rowid > ?")
            sql_params.append(params.after_index)
        if params.before_index is not None:
            where_clauses.append("rowid < ?")
            sql_params.append(params.before_index)

    if where_clauses:
        # Check if WHERE already exists in sql
        if "WHERE" in sql.upper():
            sql += " AND " + " AND ".join(where_clauses)
        else:
            sql += " WHERE " + " AND ".join(where_clauses)

    sql += " ORDER BY rowid"

    if params and params.limit:
        sql += " LIMIT ? OFFSET ?"
        sql_params.extend([params.limit, params.offset])
    elif params and params.offset:
        sql += " LIMIT -1 OFFSET ?"
        sql_params.append(params.offset)

    return sql, sql_params


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
        self,
        db_path: str,
        read_semaphore: asyncio.Semaphore,
        write_semaphore: asyncio.Semaphore,
        timeout: float = 5,
    ) -> None:
        self._db_path = db_path
        self._read_semaphore = read_semaphore
        self._write_semaphore = write_semaphore
        self._timeout = timeout
        self._db: aiosqlite.Connection | None = None

    @asynccontextmanager
    async def _get_connection(self, is_write: bool = False):
        # Track metrics based on operation type
        if is_write:
            _connection_metrics["write_requests"] += 1
        else:
            _connection_metrics["read_requests"] += 1

        # Choose appropriate semaphore based on operation type
        semaphore = self._write_semaphore if is_write else self._read_semaphore

        try:
            await asyncio.wait_for(semaphore.acquire(), self._timeout)
        except TimeoutError as e:
            if is_write:
                _connection_metrics["write_semaphore_timeouts"] += 1
            else:
                _connection_metrics["read_semaphore_timeouts"] += 1
            logger.warning(
                f"Database too busy: timeout acquiring semaphore for {self._db_path} ({'write' if is_write else 'read'} operation)"
            )
            raise DatabaseTooBusyError() from e

        try:
            async with aiosqlite.connect(self._db_path) as db:
                yield db
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            if is_write:
                _connection_metrics["write_db_errors"] += 1
            else:
                _connection_metrics["read_db_errors"] += 1
            # Convert SQLite errors to DatabaseTooBusyError
            if "locked" in str(e).lower() or "busy" in str(e).lower():
                logger.warning(
                    f"Database too busy: SQLite lock/busy error for {self._db_path} ({'write' if is_write else 'read'} operation): {e}"
                )
                raise DatabaseTooBusyError(f"SQLite database error: {e}") from e
            # Re-raise other SQLite errors as-is
            raise
        finally:
            # Ensure semaphore is released even if context manager setup fails
            semaphore.release()

    @property
    @asynccontextmanager
    async def connection(self):
        # Default to read operation
        async with self._get_connection(is_write=False) as db:
            yield db

    async def _batched_get_all(
        self,
        table_name: str,
        base_sql: str,
        params: RangeQueryParams | None = None,
        batch_size: int = 1000,
    ) -> list[Any]:
        """Fetch all rows using batching and return raw database rows.

        Args:
            table_name: Name of the table (for logging)
            base_sql: Base SQL SELECT query
            params: Range query parameters for filtering
            batch_size: Number of rows to fetch per batch (default: 1000)

        Returns:
            List of all matching raw database rows

        """
        all_results: list[Any] = []

        params = params or RangeQueryParams()

        sql, sql_params = _convert_query_params_to_sql(
            sql=base_sql,
            params=params,
        )

        # If there's a specific limit, we should respect it
        remaining = params.limit
        # Start from params offset
        batch_offset = params.offset

        # Used only for logging
        batch_number = 0

        logger.debug(
            f"Starting batched get_all for {table_name}: batch_size={batch_size}, limit={params.limit}, offset={params.offset}"
        )

        async with self.connection as db:
            async with db.execute(sql, sql_params) as cursor:
                while True:
                    batch_number += 1
                    # Create batch params
                    if remaining is not None:
                        batch_limit = min(batch_size, remaining)
                    else:
                        batch_limit = batch_size

                    logger.debug(
                        f"Fetching {table_name} batch {batch_number}: offset={batch_offset}, limit={batch_limit}"
                    )

                    rows = list(await cursor.fetchmany(batch_limit))

                    logger.debug(
                        f"Retrieved {len(rows)} {table_name} in batch {batch_number}, total so far: {len(all_results) + len(rows)}"
                    )

                    if not rows:
                        break

                    all_results.extend(rows)

                    # If we got fewer rows than batch_size, we've reached the end
                    if len(rows) < batch_size:
                        logger.debug(
                            f"Batch {batch_number} returned fewer rows than batch_size, stopping"
                        )
                        break

                    batch_offset += len(rows)
                    if remaining is not None:
                        remaining -= len(rows)
                        if remaining <= 0:
                            logger.debug(
                                f"Reached limit after batch {batch_number}, stopping"
                            )
                            break

        logger.debug(
            f"Completed batched get_all for {table_name}: {batch_number} batches, {len(all_results)} total rows"
        )
        return all_results

    async def _batched_create_many(
        self,
        table_name: str,
        insert_sql: str,
        records: list[tuple],
        batch_size: int = 1000,
    ) -> None:
        """Create multiple items efficiently in batches using executemany.

        Args:
            table_name: Name of the table (for logging)
            insert_sql: INSERT SQL statement with placeholders
            records: List of tuples containing values to insert
            batch_size: Number of items to insert per batch (default: 1000)

        """
        if not records:
            return

        total_items = len(records)
        batch_number = 0

        logger.debug(
            f"Starting batched create_many for {table_name}: total_items={total_items}, batch_size={batch_size}"
        )

        # Process in batches
        for i in range(0, total_items, batch_size):
            batch_number += 1
            batch = records[i : i + batch_size]
            batch_len = len(batch)

            logger.debug(
                f"Inserting {table_name} batch {batch_number}: {batch_len} items (offset={i})"
            )

            async with self._get_connection(is_write=True) as db:
                await db.executemany(insert_sql, batch)
                await db.commit()

            logger.debug(
                f"Successfully inserted {table_name} batch {batch_number}: {batch_len} items, total so far: {min(i + batch_size, total_items)}"
            )

        logger.debug(
            f"Completed batched create_many for {table_name}: {batch_number} batches, {total_items} total items"
        )


class SQLiteAgentController(AgentTableController, _BoundedSqliteConnectionMixIn):
    """SQLite implementation of AgentTableController."""

    async def create(self, item: AgentRow) -> AgentRow:
        """Create a new agent."""
        agent_id = item.id or str(uuid.uuid4())

        async with self._get_connection(is_write=True) as db:
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

            # Get the rowid that was automatically assigned
            async with db.execute(
                "SELECT rowid FROM agents WHERE id = ?",
                (agent_id,),
            ) as cursor:
                row = await cursor.fetchone()
                row_index = row[0] if row else None

        # Return the created agent
        return AgentRow(
            id=agent_id,
            created_at=item.created_at,
            data=item.data,
            agent_embedding=item.agent_embedding,
            index=row_index,
        )

    async def create_many(self, items: list[AgentRow], batch_size: int = 1000) -> None:
        """Create multiple agents efficiently in batches.

        Args:
            items: List of agent rows to insert
            batch_size: Number of items to insert per batch (default: 1000)

        """
        # Prepare records for insertion
        records = [
            (
                item.id or str(uuid.uuid4()),
                item.created_at.isoformat(),
                item.data.model_dump_json(),
                item.agent_embedding,
            )
            for item in items
        ]

        await self._batched_create_many(
            table_name="agents",
            insert_sql="INSERT INTO agents (id, created_at, data, agent_embedding) VALUES (?, ?, ?, ?)",
            records=records,
            batch_size=batch_size,
        )

    async def get_by_id(self, item_id: str) -> AgentRow | None:
        """Get agent by ID."""
        async with self.connection as db:
            async with db.execute(
                "SELECT rowid, id, created_at, data, agent_embedding FROM agents WHERE id = ?",
                (item_id,),
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            return None

        # Reconstruct agent from JSON
        agent_data = AgentProfile.model_validate_json(row[3])
        return AgentRow(
            id=row[1],
            created_at=row[2],  # type: ignore  # Pydantic handles datetime string parsing
            data=agent_data,
            agent_embedding=row[4],  # BLOB data or None
            index=row[0],
        )

    async def get_all(
        self, params: RangeQueryParams | None = None, batch_size: int = 1000
    ) -> list[AgentRow]:
        """Get all agents with pagination, fetching in batches.

        Args:
            params: Range query parameters for filtering
            batch_size: Number of rows to fetch per batch (default: 1000)

        Returns:
            List of all matching agent rows

        """
        rows = await self._batched_get_all(
            table_name="agents",
            base_sql="SELECT rowid, id, created_at, data, agent_embedding FROM agents",
            params=params,
            batch_size=batch_size,
        )

        return [
            AgentRow(
                id=row[1],
                created_at=row[2],  # type: ignore  # Pydantic handles datetime string parsing
                data=AgentProfile.model_validate_json(row[3]),
                agent_embedding=row[4],  # BLOB data or None
                index=row[0],
            )
            for row in rows
        ]

    async def find(
        self, query: Query, params: RangeQueryParams | None = None
    ) -> list[AgentRow]:
        """Find agents using JSONQuery objects."""
        sql, sql_params = _convert_query_params_to_sql(
            sql="SELECT rowid, id, created_at, data, agent_embedding FROM agents",
            query=query,
            params=params,
        )

        async with self.connection as db:
            async with db.execute(sql, sql_params) as cursor:
                rows = await cursor.fetchall()

        return [
            AgentRow(
                id=row[1],
                created_at=row[2],  # type: ignore  # Pydantic handles datetime string parsing
                data=AgentProfile.model_validate_json(row[3]),
                agent_embedding=row[4],  # BLOB data or None
                index=row[0],
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
            if key == "data":
                # Handle AgentProfile update
                set_clauses.append("data = ?")
                if isinstance(value, str):
                    sql_params.append(value)
                else:
                    sql_params.append(to_json(value).decode())
            elif key in ["name", "agent_metadata"]:
                set_clauses.append(f"{key} = ?")
                if key == "agent_metadata":
                    sql_params.append(to_json(value).decode())
                else:
                    sql_params.append(value)

        if not set_clauses:
            return existing

        sql_params.append(item_id)
        sql = f"UPDATE agents SET {', '.join(set_clauses)} WHERE id = ?"

        async with self._get_connection(is_write=True) as db:
            await db.execute(sql, sql_params)
            await db.commit()

        # Return updated agent
        return await self.get_by_id(item_id)

    async def delete(self, item_id: str) -> bool:
        """Delete an agent."""
        async with self._get_connection(is_write=True) as db:
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


class SQLiteActionController(ActionTableController, _BoundedSqliteConnectionMixIn):
    """SQLite implementation of ActionTableController."""

    async def find(
        self, query: Query, params: RangeQueryParams | None = None
    ) -> list[ActionRow]:
        """Find actions using JSONQuery objects."""
        sql, sql_params = _convert_query_params_to_sql(
            sql="SELECT rowid, id, created_at, data FROM actions",
            query=query,
            params=params,
        )

        async with self.connection as db:
            async with db.execute(sql, sql_params) as cursor:
                rows = await cursor.fetchall()

        return [
            ActionRow(
                id=row[1],
                created_at=row[2],  # type: ignore  # Pydantic handles datetime string parsing
                data=ActionRowData.model_validate_json(row[3]),
                index=row[0],
            )
            for row in rows
        ]

    async def create(self, item: ActionRow) -> ActionRow:
        """Create a new action."""
        action_id = item.id or str(uuid.uuid4())

        # Store the full action data (request + result) as JSON
        action_json = item.data.model_dump_json()

        async with self._get_connection(is_write=True) as db:
            await db.execute(
                "INSERT INTO actions (id, created_at, data) VALUES (?, ?, ?)",
                (
                    action_id,
                    item.created_at.isoformat(),
                    action_json,
                ),
            )
            await db.commit()

            # Get the rowid that was automatically assigned
            async with db.execute(
                "SELECT rowid FROM actions WHERE id = ?",
                (action_id,),
            ) as cursor:
                row = await cursor.fetchone()
                row_index = row[0] if row else None

        # Return the created action with index
        return ActionRow(
            id=action_id,
            created_at=item.created_at,
            data=item.data,
            index=row_index,
        )

    async def create_many(self, items: list[ActionRow], batch_size: int = 1000) -> None:
        """Create multiple actions efficiently in batches.

        Args:
            items: List of action rows to insert
            batch_size: Number of items to insert per batch (default: 1000)

        """
        # Prepare records for insertion
        records = [
            (
                item.id or str(uuid.uuid4()),
                item.created_at.isoformat(),
                item.data.model_dump_json(),
            )
            for item in items
        ]

        await self._batched_create_many(
            table_name="actions",
            insert_sql="INSERT INTO actions (id, created_at, data) VALUES (?, ?, ?)",
            records=records,
            batch_size=batch_size,
        )

    async def get_by_id(self, item_id: str) -> ActionRow | None:
        """Get action by ID."""
        async with self.connection as db:
            async with db.execute(
                "SELECT rowid, id, created_at, data FROM actions WHERE id = ?",
                (item_id,),
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            return None

        # Reconstruct action from JSON
        action_data = ActionRowData.model_validate_json(row[3])
        return ActionRow(
            id=row[1],
            created_at=row[2],  # type: ignore  # Pydantic handles datetime string parsing
            data=action_data,
            index=row[0],
        )

    async def get_all(
        self, params: RangeQueryParams | None = None, batch_size: int = 1000
    ) -> list[ActionRow]:
        """Get all actions with pagination, fetching in batches.

        Args:
            params: Range query parameters for filtering
            batch_size: Number of rows to fetch per batch (default: 1000)

        Returns:
            List of all matching action rows

        """
        rows = await self._batched_get_all(
            table_name="actions",
            base_sql="SELECT rowid, id, created_at, data FROM actions",
            params=params,
            batch_size=batch_size,
        )

        return [
            ActionRow(
                id=row[1],
                created_at=row[2],  # type: ignore  # Pydantic handles datetime string parsing
                data=ActionRowData.model_validate_json(row[3]),
                index=row[0],
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

        async with self._get_connection(is_write=True) as db:
            await db.execute(sql, sql_params)
            await db.commit()

        # Return updated action
        return await self.get_by_id(item_id)

    async def delete(self, item_id: str) -> bool:
        """Delete an action."""
        async with self._get_connection(is_write=True) as db:
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
        sql, sql_params = _convert_query_params_to_sql(
            sql="SELECT rowid, id, created_at, data FROM logs",
            query=query,
            params=params,
        )

        async with self.connection as db:
            async with db.execute(sql, sql_params) as cursor:
                rows = await cursor.fetchall()

        return [
            LogRow(
                id=row[1],
                created_at=row[2],  # type: ignore  # Pydantic handles datetime string parsing
                data=Log.model_validate_json(row[3]),
                index=row[0],
            )
            for row in rows
        ]

    async def create(self, item: LogRow) -> LogRow:
        """Create a new log record."""
        log_id = item.id or str(uuid.uuid4())

        async with self._get_connection(is_write=True) as db:
            await db.execute(
                "INSERT INTO logs (id, created_at, data) VALUES (?, ?, ?)",
                (
                    log_id,
                    item.created_at.isoformat(),
                    item.data.model_dump_json(),  # Store full log as JSON
                ),
            )
            await db.commit()

            # Get the rowid that was automatically assigned
            async with db.execute(
                "SELECT rowid FROM logs WHERE id = ?",
                (log_id,),
            ) as cursor:
                row = await cursor.fetchone()
                row_index = row[0] if row else None

        # Return the created log
        return LogRow(
            id=log_id, created_at=item.created_at, data=item.data, index=row_index
        )

    async def create_many(self, items: list[LogRow], batch_size: int = 1000) -> None:
        """Create multiple logs efficiently in batches.

        Args:
            items: List of log rows to insert
            batch_size: Number of items to insert per batch (default: 1000)

        """
        # Prepare records for insertion
        records = [
            (
                item.id or str(uuid.uuid4()),
                item.created_at.isoformat(),
                item.data.model_dump_json(),
            )
            for item in items
        ]

        await self._batched_create_many(
            table_name="logs",
            insert_sql="INSERT INTO logs (id, created_at, data) VALUES (?, ?, ?)",
            records=records,
            batch_size=batch_size,
        )

    async def get_by_id(self, item_id: str) -> LogRow | None:
        """Get log by ID."""
        async with self.connection as db:
            async with db.execute(
                "SELECT rowid, id, created_at, data FROM logs WHERE id = ?",
                (item_id,),
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            return None

        # Reconstruct log from JSON
        log_data = Log.model_validate_json(row[3])
        return LogRow(
            id=row[1],
            created_at=row[2],  # type: ignore  # Pydantic handles datetime string parsing
            data=log_data,
            index=row[0],
        )

    async def get_all(
        self, params: RangeQueryParams | None = None, batch_size: int = 1000
    ) -> list[LogRow]:
        """Get all logs with pagination, fetching in batches.

        Args:
            params: Range query parameters for filtering
            batch_size: Number of rows to fetch per batch (default: 1000)

        Returns:
            List of all matching log rows

        """
        rows = await self._batched_get_all(
            table_name="logs",
            base_sql="SELECT rowid, id, created_at, data FROM logs",
            params=params,
            batch_size=batch_size,
        )

        return [
            LogRow(
                id=row[1],
                created_at=row[2],  # type: ignore  # Pydantic handles datetime string parsing
                data=Log.model_validate_json(row[3]),
                index=row[0],
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

        async with self._get_connection(is_write=True) as db:
            await db.execute(sql, sql_params)
            await db.commit()

        # Return updated log
        return await self.get_by_id(item_id)

    async def delete(self, item_id: str) -> bool:
        """Delete a log record."""
        async with self._get_connection(is_write=True) as db:
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

    def __init__(
        self, db_path: str, db_timeout: float = 5, max_read_connections: int = 3
    ):
        """Initialize SQLite database controller with database path."""
        # Create separate semaphores for read and write operations
        read_semaphore = asyncio.Semaphore(max_read_connections)
        write_semaphore = asyncio.Semaphore(
            1
        )  # Write operations limited to 1 to prevent conflicts

        super().__init__(
            db_path=db_path,
            read_semaphore=read_semaphore,
            write_semaphore=write_semaphore,
            timeout=db_timeout,
        )
        self._agents = SQLiteAgentController(
            db_path, read_semaphore, write_semaphore, db_timeout
        )
        self._actions = SQLiteActionController(
            db_path, read_semaphore, write_semaphore, db_timeout
        )
        self._logs = SQLiteLogController(
            db_path, read_semaphore, write_semaphore, db_timeout
        )

        # Start periodic metrics dumping
        _start_metrics_timer(db_path)

    @staticmethod
    async def from_cached(
        db_path: str, db_timeout: float = 5, max_read_connections: int = 3
    ):
        """Create a new controller for the given database path.

        Args:
            db_path: Path to the SQLite database file
            db_timeout: Connection timeout in seconds
            max_read_connections: Maximum concurrent read connections

        Returns:
            SQLiteDatabaseController instance

        """
        controller = SQLiteDatabaseController(db_path, db_timeout, max_read_connections)
        await controller.initialize()
        return controller

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

    @property
    def row_index_column(self) -> str:
        """Get the name of the row index column for this database."""
        return "rowid"

    async def execute(self, command: Any) -> Any:
        """Execute an arbitrary database command."""
        async with self._get_connection(is_write=True) as db:
            async with db.execute(command) as cursor:
                return cursor

    async def initialize(self):
        """Initialize the database tables."""
        async with self._get_connection(is_write=True) as db:
            await db.executescript(CREATE_TABLES_SQL)
            await db.commit()

    def __del__(self):
        """Write metrics to file when object is destroyed."""
        # Stop the periodic timer
        _stop_metrics_timer()
        # Do a final dump
        _dump_metrics_to_file(self._db_path)


@asynccontextmanager
async def connect_to_sqlite_database(database_path: str = "marketplace.db"):
    """Create SQLite database controller."""
    controller = SQLiteDatabaseController(database_path)
    await controller.initialize()
    try:
        yield controller
    finally:
        # Any cleanup if needed
        pass
