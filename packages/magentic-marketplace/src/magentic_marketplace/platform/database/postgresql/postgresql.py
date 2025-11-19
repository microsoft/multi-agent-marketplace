"""PostgreSQL implementation of the database controllers using asyncpg."""

import asyncio
import json
import logging
import os
import threading
import uuid
from contextlib import asynccontextmanager
from typing import Any, Literal, cast

import asyncpg

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
from .utils import fix_json_for_postgres

SchemaMode = Literal["existing", "override", "create_new"]

logger = logging.getLogger(__name__)

# Global metrics tracking
_connection_metrics = {
    "read_requests": 0,
    "write_requests": 0,
    "connection_timeouts": 0,
    "db_errors": 0,
    "successful_requests": 0,
}

# Global metrics timer
_metrics_timer = None


def _dump_metrics_to_file(database_url: str):
    """Dump metrics to file."""
    try:
        # Create a safe filename from database URL
        safe_url = (
            database_url.replace("://", "_")
            .replace("/", "_")
            .replace(":", "_")
            .replace("@", "_at_")
        )
        metrics_file = f"postgresql_metrics_{safe_url}.json"
        with open(metrics_file, "w") as f:
            json.dump(_connection_metrics, f, indent=2)
    except Exception:
        # Silently fail to avoid issues during cleanup
        pass


def _start_metrics_timer(database_url: str):
    """Start a repeating timer to dump metrics every 10 seconds."""
    global _metrics_timer

    # Only start one timer globally
    if _metrics_timer is not None:
        return

    def dump_metrics():
        _dump_metrics_to_file(database_url)
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


def _format_jsonpath(path: str) -> str:
    """Format a JSONPath for PostgreSQL with quoted keys and explicit cast.

    Converts $.a.b.c to $."a"."b"."c"::jsonpath

    Args:
        path: JSONPath string (e.g., '$.request.name')

    Returns:
        Formatted path with quoted keys and ::jsonpath cast

    """
    # Remove leading $. or $
    path = path.removeprefix("$.")
    path = path.removeprefix("$")

    if not path:
        return "'$'::jsonpath"

    # Split by dots and quote each part
    parts = path.split(".")
    quoted_parts = [f'"{part}"' for part in parts]
    formatted_path = "$." + ".".join(quoted_parts)

    return f"'{formatted_path}'::jsonpath"


def _convert_query_to_postgres(
    query: Query, sql_params: list[Any] | None = None
) -> tuple[str, list[Any]]:
    """Convert abstract JSONQuery to PostgreSQL-specific SQL with parameters.

    Args:
        query: Query object to convert
        sql_params: Existing SQL parameters to maintain numbering consistency

    Returns:
        Tuple of (SQL string, list of all parameters including new ones)

    """
    params = []
    param_offset = len(sql_params or [])

    def build_query(q: Query) -> str:
        nonlocal params

        # Handle composite queries
        if isinstance(q, AndQuery):
            left_sql = build_query(q.left)
            right_sql = build_query(q.right)
            return f"({left_sql} AND {right_sql})"
        elif isinstance(q, OrQuery):
            left_sql = build_query(q.left)
            right_sql = build_query(q.right)
            return f"({left_sql} OR {right_sql})"

        # Handle basic JSONQuery - must be a JSONQuery at this point
        if not isinstance(q, JSONQuery):
            raise ValueError(f"Expected JSONQuery, got {type(q)}")

        # Format the JSONPath with quoted keys and explicit cast
        formatted_path = _format_jsonpath(q.path)

        # Handle special NULL operators first
        if q.operator in ["IS NULL", "IS NOT NULL"]:
            return f"jsonb_path_query_first(data, {formatted_path}) {q.operator}"

        # Handle value conversion for PostgreSQL
        if q.value is None:
            # For NULL values, we need to adjust the operator
            if q.operator == "=":
                return f"jsonb_path_query_first(data, {formatted_path}) IS NULL"
            elif q.operator == "!=":
                return f"jsonb_path_query_first(data, {formatted_path}) IS NOT NULL"
            else:
                # For other operators with NULL, use NULL as is
                params.append(None)
                return f"jsonb_path_query_first(data, {formatted_path}) {q.operator} ${param_offset + len(params)}"
        else:
            # Always extract as text using #>> '{}' for better index usage
            # This matches the functional index expression pattern
            params.append(q.value)
            param_idx = param_offset + len(params)

            # Generate SQL using jsonb_path_query_first with text extraction
            if q.operator.upper() == "LIKE":
                # For LIKE operations, add wildcards
                params[-1] = f"%{q.value}%"
                return f"jsonb_path_query_first(data, {formatted_path}) #>> '{{}}' ILIKE ${param_idx}"
            else:
                # For equality and other comparisons, extract as text
                return f"jsonb_path_query_first(data, {formatted_path}) #>> '{{}}' {q.operator} ${param_idx}"

    sql = build_query(query)
    return sql, params


def _convert_query_params_to_postgres(
    *,
    sql: str,
    query: Query | None = None,
    params: QueryParams | RangeQueryParams | None = None,
    sql_params: list[Any] | None = None,
):
    """Convert query params to PostgreSQL SQL with filters, ordering, and pagination.

    Args:
        sql: Base SQL query
        query: Optional Query object for filtering
        params: Query parameters for filtering and pagination
        sql_params: Existing SQL parameters (for queries that already have WHERE conditions)

    Returns:
        Tuple of (complete SQL string, list of parameters)

    """
    sql_params = list(sql_params or [])
    where_clauses = []

    # Add query filter if provided
    if query is not None:
        query_sql, query_params = _convert_query_to_postgres(query, sql_params)
        where_clauses.append(query_sql)
        sql_params.extend(query_params)

    if params and isinstance(params, RangeQueryParams):
        # Add time range filters
        if params.after:
            where_clauses.append(f"created_at > ${len(sql_params) + 1}")
            sql_params.append(params.after)
        if params.before:
            where_clauses.append(f"created_at < ${len(sql_params) + 1}")
            sql_params.append(params.before)

        # Add index range filters
        if params.after_index is not None:
            where_clauses.append(f"row_index > ${len(sql_params) + 1}")
            sql_params.append(params.after_index)
        if params.before_index is not None:
            where_clauses.append(f"row_index < ${len(sql_params) + 1}")
            sql_params.append(params.before_index)

    if where_clauses:
        # Check if WHERE already exists in sql
        if "WHERE" in sql.upper():
            sql += " AND " + " AND ".join(where_clauses)
        else:
            sql += " WHERE " + " AND ".join(where_clauses)

    sql += " ORDER BY row_index"

    if params and params.limit:
        sql += f" LIMIT ${len(sql_params) + 1} OFFSET ${len(sql_params) + 2}"
        sql_params.extend([params.limit, params.offset])
    elif params and params.offset:
        sql += f" OFFSET ${len(sql_params) + 1}"
        sql_params.append(params.offset)

    return sql, sql_params


def create_tables_sql(schema: str) -> str:
    """Generate SQL DDL for table creation in the specified schema."""
    return f"""
CREATE TABLE IF NOT EXISTS {schema}.agents (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    data JSONB NOT NULL,
    agent_embedding BYTEA,
    row_index BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE
);

CREATE TABLE IF NOT EXISTS {schema}.actions (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    data JSONB NOT NULL,
    row_index BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE
);

CREATE TABLE IF NOT EXISTS {schema}.logs (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    data JSONB NOT NULL,
    row_index BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE
);

-- Add indexes for better performance on core columns
CREATE INDEX IF NOT EXISTS agents_id_idx ON {schema}.agents(id);
CREATE INDEX IF NOT EXISTS agents_created_at_idx ON {schema}.agents(created_at);
CREATE INDEX IF NOT EXISTS agents_row_index_idx ON {schema}.agents(row_index);

CREATE INDEX IF NOT EXISTS actions_id_idx ON {schema}.actions(id);
CREATE INDEX IF NOT EXISTS actions_created_at_idx ON {schema}.actions(created_at);
CREATE INDEX IF NOT EXISTS actions_row_index_idx ON {schema}.actions(row_index);

CREATE INDEX IF NOT EXISTS logs_id_idx ON {schema}.logs(id);
CREATE INDEX IF NOT EXISTS logs_created_at_idx ON {schema}.logs(created_at);
CREATE INDEX IF NOT EXISTS logs_row_index_idx ON {schema}.logs(row_index);

-- Add composite indexes for pagination queries
CREATE INDEX IF NOT EXISTS agents_pagination_idx ON {schema}.agents(row_index, created_at);
CREATE INDEX IF NOT EXISTS actions_pagination_idx ON {schema}.actions(row_index, created_at);
CREATE INDEX IF NOT EXISTS logs_pagination_idx ON {schema}.logs(row_index, created_at);

-- Add GIN indexes for JSONB columns for fast JSON queries
CREATE INDEX IF NOT EXISTS agents_data_gin_idx ON {schema}.agents USING GIN(data);
CREATE INDEX IF NOT EXISTS actions_data_gin_idx ON {schema}.actions USING GIN(data);
CREATE INDEX IF NOT EXISTS logs_data_gin_idx ON {schema}.logs USING GIN(data);
"""


class _BoundedPostgresConnectionMixIn:
    """Base class for PostgreSQL connections with bounded connection pools."""

    def __init__(
        self, connection_pool: asyncpg.Pool, timeout: float = 5, schema: str = "public"
    ) -> None:
        self._pool = connection_pool
        self._timeout = timeout
        self._schema = schema

    @asynccontextmanager
    async def connection(self, is_write: bool = False):
        """Get a connection from the pool."""
        # Track metrics
        if is_write:
            _connection_metrics["write_requests"] += 1
        else:
            _connection_metrics["read_requests"] += 1

        try:
            conn = await asyncio.wait_for(self._pool.acquire(), self._timeout)
            try:
                _connection_metrics["successful_requests"] += 1
                yield cast(asyncpg.connection.Connection, conn)
            finally:
                await self._pool.release(conn)
        except TimeoutError as e:
            _connection_metrics["connection_timeouts"] += 1
            logger.warning("Database too busy: timeout acquiring connection from pool")
            raise DatabaseTooBusyError("Connection pool timeout") from e
        except Exception:
            _connection_metrics["db_errors"] += 1
            raise

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

        # If there's a specific limit, we should respect it
        remaining = params.limit

        # Used only for logging
        batch_number = 0

        logger.debug(
            f"Starting batched get_all for {table_name}: batch_size={batch_size}, limit={params.limit}, offset={params.offset}"
        )

        sql, sql_params = _convert_query_params_to_postgres(
            sql=base_sql,
            params=params,
        )

        async with self.connection() as conn:
            async with conn.transaction():
                cursor = await conn.cursor(sql, *sql_params)
                while True:
                    batch_number += 1

                    # Create batch params
                    if remaining is not None:
                        batch_limit = min(batch_size, remaining)
                    else:
                        batch_limit = batch_size

                    logger.debug(
                        f"Fetching {table_name} batch {batch_number}: offset={len(all_results)}, limit={batch_limit}"
                    )

                    rows = await cursor.fetch(batch_limit)

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


class PostgreSQLAgentController(AgentTableController, _BoundedPostgresConnectionMixIn):
    """PostgreSQL implementation of AgentTableController."""

    async def create(self, item: AgentRow) -> AgentRow:
        """Create a new agent."""
        agent_id = item.id or str(uuid.uuid4())
        agent_json = json.dumps(item.data.model_dump())

        async with self.connection(is_write=True) as conn:
            try:
                row_index = await conn.fetchval(
                    self._get_insert_query(),
                    agent_id,
                    item.created_at,
                    agent_json,
                    item.agent_embedding,
                )
            except asyncpg.UntranslatableCharacterError as e:
                logger.warning(f"Fixing invalid unicode in AGENT insert: {e}")
                fixed_data = fix_json_for_postgres(item.data.model_dump())
                agent_json = json.dumps(fixed_data)
                row_index = await conn.fetchval(
                    self._get_insert_query(),
                    agent_id,
                    item.created_at,
                    agent_json,
                    item.agent_embedding,
                )

        return AgentRow(
            id=agent_id,
            created_at=item.created_at,
            data=item.data,
            agent_embedding=item.agent_embedding,
            index=row_index,
        )

    def _get_insert_query(self) -> str:
        return f"INSERT INTO {self._schema}.agents (id, created_at, data, agent_embedding) VALUES ($1, $2, $3, $4) RETURNING row_index"

    async def create_many(self, items: list[AgentRow], batch_size: int = 1000) -> None:
        """Create multiple agents efficiently in batches using COPY.

        Args:
            items: List of agent rows to insert
            batch_size: Number of items to insert per batch (default: 1000)

        """
        if not items:
            return

        total_items = len(items)
        batch_number = 0

        logger.debug(
            f"Starting batched create_many for agents: total_items={total_items}, batch_size={batch_size}"
        )

        # Process in batches
        for i in range(0, total_items, batch_size):
            batch_number += 1
            batch = items[i : i + batch_size]
            batch_len = len(batch)

            logger.debug(
                f"Inserting agents batch {batch_number}: {batch_len} items (offset={i})"
            )

            # Prepare records for COPY
            records = [
                (
                    item.id or str(uuid.uuid4()),
                    item.created_at,
                    item.data.model_dump_json(),
                    item.agent_embedding,
                )
                for item in batch
            ]

            async with self.connection(is_write=True) as conn:
                await conn.copy_records_to_table(
                    "agents",
                    records=records,
                    columns=[
                        "id",
                        "created_at",
                        "data",
                        "agent_embedding",
                    ],
                    schema_name=self._schema,
                )

            logger.debug(
                f"Successfully inserted agents batch {batch_number}: {batch_len} items, total so far: {min(i + batch_size, total_items)}"
            )

        logger.debug(
            f"Completed batched create_many for agents: {batch_number} batches, {total_items} total items"
        )

    async def get_by_id(self, item_id: str) -> AgentRow | None:
        """Get agent by ID."""
        async with self.connection() as conn:
            row = await conn.fetchrow(
                f"SELECT row_index, id, created_at, data, agent_embedding FROM {self._schema}.agents WHERE id = $1",
                item_id,
            )

        if not row:
            return None

        # Reconstruct agent from JSON
        agent_data = AgentProfile.model_validate_json(row["data"])
        return AgentRow(
            id=row["id"],
            created_at=row["created_at"],
            data=agent_data,
            agent_embedding=row["agent_embedding"],
            index=row["row_index"],
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
            base_sql=f"SELECT row_index, id, created_at, data, agent_embedding FROM {self._schema}.agents",
            params=params,
            batch_size=batch_size,
        )

        return [
            AgentRow(
                id=row["id"],
                created_at=row["created_at"],
                data=AgentProfile.model_validate_json(row["data"]),
                agent_embedding=row["agent_embedding"],
                index=row["row_index"],
            )
            for row in rows
        ]

    async def find(
        self, query: Query, params: RangeQueryParams | None = None
    ) -> list[AgentRow]:
        """Find agents using JSONQuery objects."""
        sql, sql_params = _convert_query_params_to_postgres(
            sql=f"SELECT row_index, id, created_at, data, agent_embedding FROM {self._schema}.agents",
            query=query,
            params=params,
        )

        async with self.connection() as conn:
            rows = await conn.fetch(sql, *sql_params)

        return [
            AgentRow(
                id=row["id"],
                created_at=row["created_at"],
                data=AgentProfile.model_validate_json(row["data"]),
                agent_embedding=row["agent_embedding"],
                index=row["row_index"],
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
        set_clauses = []
        sql_params = []

        for key, value in updates.items():
            if key == "data":
                # Handle full AgentProfile replacement
                param_idx = len(sql_params) + 1
                set_clauses.append(f"data = ${param_idx}::jsonb")
                if isinstance(value, str):
                    sql_params.append(value)
                else:
                    sql_params.append(json.dumps(value))
            elif key in ["name", "agent_metadata"]:
                param_idx = len(sql_params) + 1
                set_clauses.append(f"data = jsonb_set(data, '{{{key}}}', ${param_idx})")
                sql_params.append(json.dumps(value))

        if not set_clauses:
            return existing

        sql_params.append(item_id)
        sql = f"UPDATE {self._schema}.agents SET {', '.join(set_clauses)} WHERE id = ${len(sql_params)}"

        async with self.connection(is_write=True) as conn:
            await conn.execute(sql, *sql_params)

        return await self.get_by_id(item_id)

    async def delete(self, item_id: str) -> bool:
        """Delete an agent."""
        async with self.connection() as conn:
            result = await conn.execute(
                f"DELETE FROM {self._schema}.agents WHERE id = $1", item_id
            )
            return result.split()[-1] != "0"  # Check if any rows were affected

    async def count(self) -> int:
        """Count total agents."""
        async with self.connection() as conn:
            result = await conn.fetchval(f"SELECT COUNT(*) FROM {self._schema}.agents")
            return result or 0


class PostgreSQLActionController(
    ActionTableController, _BoundedPostgresConnectionMixIn
):
    """PostgreSQL implementation of ActionTableController."""

    async def find(
        self, query: Query, params: RangeQueryParams | None = None
    ) -> list[ActionRow]:
        """Find actions using JSONQuery objects."""
        sql, sql_params = _convert_query_params_to_postgres(
            sql=f"SELECT row_index, id, created_at, data FROM {self._schema}.actions",
            query=query,
            params=params,
        )

        async with self.connection() as conn:
            rows = await conn.fetch(sql, *sql_params)

        return [
            ActionRow(
                id=row["id"],
                created_at=row["created_at"],
                data=ActionRowData.model_validate_json(row["data"]),
                index=row["row_index"],
            )
            for row in rows
        ]

    async def create(self, item: ActionRow) -> ActionRow:
        """Create a new action."""
        action_id = item.id or str(uuid.uuid4())
        action_json = json.dumps(item.data.model_dump())

        async with self.connection(is_write=True) as conn:
            try:
                # The row_index will be automatically set by the DEFAULT nextval()
                row_index = await conn.fetchval(
                    self._get_insert_query(),
                    action_id,
                    item.created_at,
                    action_json,
                )
            except asyncpg.UntranslatableCharacterError as e:
                logger.warning(f"Fixing invalid unicode in ACTION insert: {e}")
                fixed_data = fix_json_for_postgres(item.data.model_dump())
                action_json = json.dumps(fixed_data)
                row_index = await conn.fetchval(
                    self._get_insert_query(),
                    action_id,
                    item.created_at,
                    action_json,
                )

        return ActionRow(
            id=action_id,
            created_at=item.created_at,
            data=item.data,
            index=row_index,
        )

    def _get_insert_query(self) -> str:
        return f"INSERT INTO {self._schema}.actions (id, created_at, data) VALUES ($1, $2, $3) RETURNING row_index"

    async def create_many(self, items: list[ActionRow], batch_size: int = 1000) -> None:
        """Create multiple actions efficiently in batches using COPY.

        Args:
            items: List of action rows to insert
            batch_size: Number of items to insert per batch (default: 1000)

        """
        if not items:
            return

        total_items = len(items)
        batch_number = 0

        logger.debug(
            f"Starting batched create_many for actions: total_items={total_items}, batch_size={batch_size}"
        )

        # Process in batches
        for i in range(0, total_items, batch_size):
            batch_number += 1
            batch = items[i : i + batch_size]
            batch_len = len(batch)

            logger.debug(
                f"Inserting actions batch {batch_number}: {batch_len} items (offset={i})"
            )

            # Prepare records for COPY
            records = [
                (
                    item.id or str(uuid.uuid4()),
                    item.created_at,
                    item.data.model_dump_json(),
                )
                for item in batch
            ]

            async with self.connection(is_write=True) as conn:
                await conn.copy_records_to_table(
                    "actions",
                    records=records,
                    columns=["id", "created_at", "data"],
                    schema_name=self._schema,
                )

            logger.debug(
                f"Successfully inserted actions batch {batch_number}: {batch_len} items, total so far: {min(i + batch_size, total_items)}"
            )

        logger.debug(
            f"Completed batched create_many for actions: {batch_number} batches, {total_items} total items"
        )

    async def get_by_id(self, item_id: str) -> ActionRow | None:
        """Get action by ID."""
        async with self.connection() as conn:
            row = await conn.fetchrow(
                f"SELECT row_index, id, created_at, data FROM {self._schema}.actions WHERE id = $1",
                item_id,
            )

        if not row:
            return None

        action_data = ActionRowData.model_validate_json(row["data"])
        return ActionRow(
            id=row["id"],
            created_at=row["created_at"],
            data=action_data,
            index=row["row_index"],
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
            base_sql=f"SELECT row_index, id, created_at, data FROM {self._schema}.actions",
            params=params,
            batch_size=batch_size,
        )

        return [
            ActionRow(
                id=row["id"],
                created_at=row["created_at"],
                data=ActionRowData.model_validate_json(row["data"]),
                index=row["row_index"],
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
        set_clauses = []
        sql_params = []

        for key, value in updates.items():
            if key == "action":
                param_idx = len(sql_params) + 1
                set_clauses.append(
                    f"data = jsonb_set(data, '{{action}}', ${param_idx})"
                )
                sql_params.append(json.dumps(value.model_dump()))
            elif key == "result":
                param_idx = len(sql_params) + 1
                set_clauses.append(
                    f"data = jsonb_set(data, '{{result}}', ${param_idx})"
                )
                sql_params.append(json.dumps(value.model_dump()))
            elif key in ["created_at"]:
                param_idx = len(sql_params) + 1
                set_clauses.append(f"{key} = ${param_idx}")
                sql_params.append(value)

        if not set_clauses:
            return existing

        sql_params.append(item_id)
        sql = f"UPDATE {self._schema}.actions SET {', '.join(set_clauses)} WHERE id = ${len(sql_params)}"

        async with self.connection(is_write=True) as conn:
            await conn.execute(sql, *sql_params)

        return await self.get_by_id(item_id)

    async def delete(self, item_id: str) -> bool:
        """Delete an action."""
        async with self.connection() as conn:
            result = await conn.execute(
                f"DELETE FROM {self._schema}.actions WHERE id = $1", item_id
            )
            return result.split()[-1] != "0"

    async def count(self) -> int:
        """Count total actions."""
        async with self.connection() as conn:
            result = await conn.fetchval(f"SELECT COUNT(*) FROM {self._schema}.actions")
            return result or 0


class PostgreSQLLogController(LogTableController, _BoundedPostgresConnectionMixIn):
    """PostgreSQL implementation of LogTableController."""

    async def find(
        self, query: Query, params: RangeQueryParams | None = None
    ) -> list[LogRow]:
        """Find logs using JSONQuery objects."""
        sql, sql_params = _convert_query_params_to_postgres(
            sql=f"SELECT row_index, id, created_at, data FROM {self._schema}.logs",
            query=query,
            params=params,
        )

        async with self.connection() as conn:
            rows = await conn.fetch(sql, *sql_params)

        return [
            LogRow(
                id=row["id"],
                created_at=row["created_at"],
                data=Log.model_validate_json(row["data"]),
                index=row["row_index"],
            )
            for row in rows
        ]

    async def create(self, item: LogRow) -> LogRow:
        """Create a new log record."""
        log_id = item.id or str(uuid.uuid4())
        log_json = json.dumps(item.data.model_dump())

        async with self.connection(is_write=True) as conn:
            try:
                row_index = await conn.fetchval(
                    self._get_insert_query(),
                    log_id,
                    item.created_at,
                    log_json,
                )
            except asyncpg.UntranslatableCharacterError as e:
                logger.warning(f"Fixing invalid unicode in LOG insert: {e}")
                fixed_data = fix_json_for_postgres(item.data.model_dump())
                log_json = json.dumps(fixed_data)
                row_index = await conn.fetchval(
                    self._get_insert_query(),
                    log_id,
                    item.created_at,
                    log_json,
                )

        return LogRow(
            id=log_id, created_at=item.created_at, data=item.data, index=row_index
        )

    def _get_insert_query(self) -> str:
        return f"INSERT INTO {self._schema}.logs (id, created_at, data) VALUES ($1, $2, $3) RETURNING row_index"

    async def create_many(self, items: list[LogRow], batch_size: int = 1000) -> None:
        """Create multiple logs efficiently in batches using COPY.

        Args:
            items: List of log rows to insert
            batch_size: Number of items to insert per batch (default: 1000)

        """
        if not items:
            return

        total_items = len(items)
        batch_number = 0

        logger.debug(
            f"Starting batched create_many for logs: total_items={total_items}, batch_size={batch_size}"
        )

        # Process in batches
        for i in range(0, total_items, batch_size):
            batch_number += 1
            batch = items[i : i + batch_size]
            batch_len = len(batch)

            logger.debug(
                f"Inserting logs batch {batch_number}: {batch_len} items (offset={i})"
            )

            # Prepare records for COPY
            records = [
                (
                    item.id or str(uuid.uuid4()),
                    item.created_at,
                    item.data.model_dump_json(),
                )
                for item in batch
            ]

            async with self.connection(is_write=True) as conn:
                await conn.copy_records_to_table(
                    "logs",
                    records=records,
                    columns=["id", "created_at", "data"],
                    schema_name=self._schema,
                )

            logger.debug(
                f"Successfully inserted logs batch {batch_number}: {batch_len} items, total so far: {min(i + batch_size, total_items)}"
            )

        logger.debug(
            f"Completed batched create_many for logs: {batch_number} batches, {total_items} total items"
        )

    async def get_by_id(self, item_id: str) -> LogRow | None:
        """Get log by ID."""
        async with self.connection() as conn:
            row = await conn.fetchrow(
                f"SELECT row_index, id, created_at, data FROM {self._schema}.logs WHERE id = $1",
                item_id,
            )

        if not row:
            return None

        log_data = Log.model_validate_json(row["data"])
        return LogRow(
            id=row["id"],
            created_at=row["created_at"],
            data=log_data,
            index=row["row_index"],
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
            base_sql=f"SELECT row_index, id, created_at, data FROM {self._schema}.logs",
            params=params,
            batch_size=batch_size,
        )

        return [
            LogRow(
                id=row["id"],
                created_at=row["created_at"],
                data=Log.model_validate_json(row["data"]),
                index=row["row_index"],
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
        set_clauses = []
        sql_params = []

        for key, value in updates.items():
            if key in ["level", "content"]:
                param_idx = len(sql_params) + 1
                set_clauses.append(f"data = jsonb_set(data, '{{{key}}}', ${param_idx})")
                sql_params.append(json.dumps(value))

        if not set_clauses:
            return existing

        sql_params.append(item_id)
        sql = f"UPDATE {self._schema}.logs SET {', '.join(set_clauses)} WHERE id = ${len(sql_params)}"

        async with self.connection(is_write=True) as conn:
            await conn.execute(sql, *sql_params)

        return await self.get_by_id(item_id)

    async def delete(self, item_id: str) -> bool:
        """Delete a log record."""
        async with self.connection() as conn:
            result = await conn.execute(
                f"DELETE FROM {self._schema}.logs WHERE id = $1", item_id
            )
            return result.split()[-1] != "0"

    async def count(self) -> int:
        """Count total log records."""
        async with self.connection() as conn:
            result = await conn.fetchval(f"SELECT COUNT(*) FROM {self._schema}.logs")
            return result or 0


class PostgreSQLDatabaseController(BaseDatabaseController):
    """PostgreSQL implementation of BaseDatabaseController."""

    def __init__(
        self,
        connection_pool: asyncpg.Pool,
        db_timeout: float = 5,
        schema: str = "public",
    ):
        """Initialize PostgreSQL database controller with connection pool."""
        self._pool = connection_pool
        self._schema = schema
        self._agents = PostgreSQLAgentController(connection_pool, db_timeout, schema)
        self._actions = PostgreSQLActionController(connection_pool, db_timeout, schema)
        self._logs = PostgreSQLLogController(connection_pool, db_timeout, schema)

        # Start periodic metrics dumping
        _start_metrics_timer("postgresql_connection_pool")

    @staticmethod
    async def from_cached(
        schema: str,
        host: str = "localhost",
        port: int = 5432,
        database: str = "marketplace",
        user: str = "postgres",
        password: str | None = None,
        min_size: int = 50,
        max_size: int = 50,
        command_timeout: float = 60,
        db_timeout: float = 5,
        mode: SchemaMode = "create_new",
    ):
        """Create a new controller for the given schema.

        Args:
            schema: Database schema (required)
            host: PostgreSQL server host
            port: PostgreSQL server port
            database: Database name
            user: Database user
            password: Database password
            min_size: Minimum connections in pool
            max_size: Maximum connections in pool
            command_timeout: Command timeout in seconds
            db_timeout: Database timeout in seconds
            mode: schema creation mode

        Returns:
            PostgreSQLDatabaseController instance

        """
        # Create new connection pool and controller
        pool = await asyncpg.create_pool(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            min_size=min_size,
            max_size=max_size,
            command_timeout=command_timeout,
        )

        controller = PostgreSQLDatabaseController(pool, db_timeout, schema)
        await controller.initialize(mode=mode)
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
        return "row_index"

    async def execute(self, command: Any) -> Any:
        """Execute an arbitrary database command."""
        async with self._pool.acquire() as conn:
            return await conn.execute(command)

    async def initialize(self, mode: SchemaMode = "create_new"):
        """Initialize the database tables.

        Args:
            mode: Schema initialization mode

        """
        async with self._pool.acquire() as conn:
            # Check if schema already exists
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name = $1)",
                self._schema,
            )

            if mode == "existing":
                if not exists:
                    raise ValueError(f"Schema '{self._schema}' does not exist")
                return

            elif mode == "create_new":
                if exists:
                    raise ValueError(f"Schema '{self._schema}' already exists")
                await conn.execute(f"CREATE SCHEMA {self._schema}")

            elif mode == "override":
                if exists:
                    await conn.execute(f"DROP SCHEMA {self._schema} CASCADE")
                    logger.info(f"Dropped existing schema '{self._schema}'")
                await conn.execute(f"CREATE SCHEMA {self._schema}")

            else:
                raise ValueError(f"Invalid mode '{mode}'. Must be one of {SchemaMode}.")

            # Create tables in the schema (will be skipped if they already exist due to IF NOT EXISTS)
            await conn.execute(create_tables_sql(self._schema))

    def __del__(self):
        """Write metrics to file when object is destroyed."""
        # Stop the periodic timer
        _stop_metrics_timer()
        # Do a final dump
        _dump_metrics_to_file("postgresql_metrics")


@asynccontextmanager
async def connect_to_postgresql_database(
    schema: str,
    host: str | None = None,
    port: int | None = None,
    database: str | None = None,
    user: str | None = None,
    password: str | None = None,
    min_size: int = 2,
    max_size: int = 10,
    command_timeout: float = 60,
    mode: SchemaMode = "create_new",
):
    """Create PostgreSQL database controller with connection pooling.

    Args:
        schema: Database schema (required)
        host: PostgreSQL server host (defaults to POSTGRES_HOST env var or localhost)
        port: PostgreSQL server port (defaults to POSTGRES_PORT env var or 5432)
        database: Database name (defaults to POSTGRES_DB env var or marketplace)
        user: Database user (defaults to POSTGRES_USER env var or postgres)
        password: Database password (defaults to POSTGRES_PASSWORD env var or None)
        min_size: Minimum connections in pool
        max_size: Maximum connections in pool
        command_timeout: Command timeout in seconds
        mode: Schema creation mode (default: 'create_new')

    """
    # Use environment variables as defaults if parameters are not provided
    host = host or os.environ.get("POSTGRES_HOST", "localhost")
    port = port or int(os.environ.get("POSTGRES_PORT", "5432"))
    database = database or os.environ.get("POSTGRES_DB", "marketplace")
    user = user or os.environ.get("POSTGRES_USER", "postgres")
    password = password or os.environ.get("POSTGRES_PASSWORD")

    pool = await asyncpg.create_pool(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
        min_size=min_size,
        max_size=max_size,
        command_timeout=command_timeout,
    )

    controller = PostgreSQLDatabaseController(pool, schema=schema)
    await controller.initialize(mode=mode)
    try:
        yield controller
    finally:
        await pool.close()
