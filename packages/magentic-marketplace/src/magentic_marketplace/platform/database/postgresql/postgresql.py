"""PostgreSQL implementation of the database controllers using asyncpg."""

import asyncio
import json
import logging
import threading
import uuid
from contextlib import asynccontextmanager
from typing import Any

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
from ..queries import AndQuery, JSONQuery, OrQuery, Query, RangeQueryParams

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


def _convert_query_to_postgres(query: Query) -> tuple[str, list[Any]]:
    """Convert abstract JSONQuery to PostgreSQL-specific SQL with parameters."""
    params = []

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

        # Handle special NULL operators first
        if q.operator in ["IS NULL", "IS NOT NULL"]:
            return f"jsonb_path_query_first(data, '{q.path}') {q.operator}"

        # Handle value conversion for PostgreSQL
        if q.value is None:
            # For NULL values, we need to adjust the operator
            if q.operator == "=":
                return f"jsonb_path_query_first(data, '{q.path}') IS NULL"
            elif q.operator == "!=":
                return f"jsonb_path_query_first(data, '{q.path}') IS NOT NULL"
            else:
                # For other operators with NULL, use NULL as is
                params.append(None)
                return f"jsonb_path_query_first(data, '{q.path}') {q.operator} ${len(params)}"
        else:
            # For jsonb_path_query_first, we need to wrap string values in JSON quotes
            if isinstance(q.value, str):
                params.append(f'"{q.value}"')
            else:
                params.append(json.dumps(q.value))
            param_idx = len(params)

            # Generate SQL using jsonb_path_query_first
            if q.operator.upper() == "LIKE":
                # For LIKE operations, we need to extract as text first
                # Use the string value without JSON quotes for LIKE operations
                params[param_idx - 1] = (
                    q.value
                )  # Replace the JSON-quoted value with plain string
                return f"jsonb_path_query_first(data, '{q.path}') #>> '{{}}' ILIKE ${param_idx}"
            else:
                return f"jsonb_path_query_first(data, '{q.path}') {q.operator} ${param_idx}"

    sql = build_query(query)
    return sql, params


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

-- Add indexes for better performance
CREATE INDEX IF NOT EXISTS agents_created_at_idx ON {schema}.agents(created_at);
CREATE INDEX IF NOT EXISTS agents_row_index_idx ON {schema}.agents(row_index);
CREATE INDEX IF NOT EXISTS actions_created_at_idx ON {schema}.actions(created_at);
CREATE INDEX IF NOT EXISTS actions_row_index_idx ON {schema}.actions(row_index);
CREATE INDEX IF NOT EXISTS logs_created_at_idx ON {schema}.logs(created_at);
CREATE INDEX IF NOT EXISTS logs_row_index_idx ON {schema}.logs(row_index);

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
            async with asyncio.timeout(self._timeout):
                async with self._pool.acquire() as conn:
                    _connection_metrics["successful_requests"] += 1
                    yield conn
        except TimeoutError as e:
            _connection_metrics["connection_timeouts"] += 1
            logger.warning("Database too busy: timeout acquiring connection from pool")
            raise DatabaseTooBusyError("Connection pool timeout") from e
        except (asyncpg.PostgresError, asyncpg.InterfaceError) as e:
            _connection_metrics["db_errors"] += 1
            logger.warning(f"Database too busy: PostgreSQL error: {e}")
            raise DatabaseTooBusyError(f"PostgreSQL error: {e}") from e


class PostgreSQLAgentController(AgentTableController, _BoundedPostgresConnectionMixIn):
    """PostgreSQL implementation of AgentTableController."""

    async def create(self, item: AgentRow) -> AgentRow:
        """Create a new agent."""
        agent_id = item.id or str(uuid.uuid4())

        async with self.connection(is_write=True) as conn:
            row_index = await conn.fetchval(
                f"INSERT INTO {self._schema}.agents (id, created_at, data, agent_embedding) VALUES ($1, $2, $3, $4) RETURNING row_index",
                agent_id,
                item.created_at,
                json.dumps(item.data.model_dump()),
                item.agent_embedding,
            )

        return AgentRow(
            id=agent_id,
            created_at=item.created_at,
            data=item.data,
            agent_embedding=item.agent_embedding,
            index=row_index,
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

    async def get_all(self, params: RangeQueryParams | None = None) -> list[AgentRow]:
        """Get all agents with pagination."""
        sql = f"SELECT row_index, id, created_at, data, agent_embedding FROM {self._schema}.agents ORDER BY row_index"
        sql_params = []

        if params and params.limit:
            sql += " LIMIT $1 OFFSET $2"
            sql_params.extend([params.limit, params.offset])
        elif params and params.offset:
            sql += " OFFSET $1"
            sql_params.append(params.offset)

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

    async def find(
        self, query: Query, params: RangeQueryParams | None = None
    ) -> list[AgentRow]:
        """Find agents using JSONQuery objects."""
        params = params or RangeQueryParams()
        where_clause, query_params = _convert_query_to_postgres(query)

        sql = f"""
        SELECT row_index, id, created_at, data, agent_embedding FROM {self._schema}.agents
        WHERE {where_clause}
        """
        sql_params = query_params[:]

        # Add time range filters
        if params.after:
            sql += f" AND created_at > ${len(sql_params) + 1}"
            sql_params.append(params.after)
        if params.before:
            sql += f" AND created_at < ${len(sql_params) + 1}"
            sql_params.append(params.before)

        sql += " ORDER BY row_index"

        # Add pagination
        if params.limit:
            sql += f" LIMIT ${len(sql_params) + 1} OFFSET ${len(sql_params) + 2}"
            sql_params.extend([params.limit, params.offset])
        elif params.offset:
            sql += f" OFFSET ${len(sql_params) + 1}"
            sql_params.append(params.offset)

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
            if key in ["name", "agent_metadata"]:
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
            return result

    async def find_agents_by_id_pattern(self, id_pattern: str) -> list[str]:
        """Find all agent IDs that contain the given ID pattern."""
        async with self.connection() as conn:
            rows = await conn.fetch(
                f"SELECT id FROM {self._schema}.agents WHERE id ILIKE $1",
                f"%{id_pattern}%",
            )
        return [row["id"] for row in rows]


class PostgreSQLActionController(
    ActionTableController, _BoundedPostgresConnectionMixIn
):
    """PostgreSQL implementation of ActionTableController."""

    async def find(
        self, query: Query, params: RangeQueryParams | None = None
    ) -> list[ActionRow]:
        """Find actions using JSONQuery objects."""
        params = params or RangeQueryParams()
        where_clause, query_params = _convert_query_to_postgres(query)

        sql = f"""
        SELECT row_index, id, created_at, data FROM {self._schema}.actions
        WHERE {where_clause}
        """
        sql_params = query_params[:]

        # Add time range filters
        if params.after:
            sql += f" AND created_at > ${len(sql_params) + 1}"
            sql_params.append(params.after)
        if params.before:
            sql += f" AND created_at < ${len(sql_params) + 1}"
            sql_params.append(params.before)

        # Add index range filters
        if params.after_index is not None:
            sql += f" AND row_index > ${len(sql_params) + 1}"
            sql_params.append(params.after_index)
        if params.before_index is not None:
            sql += f" AND row_index < ${len(sql_params) + 1}"
            sql_params.append(params.before_index)

        sql += " ORDER BY row_index"

        # Add pagination
        if params.limit:
            sql += f" LIMIT ${len(sql_params) + 1} OFFSET ${len(sql_params) + 2}"
            sql_params.extend([params.limit, params.offset])
        elif params.offset:
            sql += f" OFFSET ${len(sql_params) + 1}"
            sql_params.append(params.offset)

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
            # The row_index will be automatically set by the DEFAULT nextval()
            row_index = await conn.fetchval(
                f"INSERT INTO {self._schema}.actions (id, created_at, data) VALUES ($1, $2, $3) RETURNING row_index",
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

    async def get_all(self, params: RangeQueryParams | None = None) -> list[ActionRow]:
        """Get all actions with pagination."""
        sql = f"SELECT row_index, id, created_at, data FROM {self._schema}.actions"
        sql_params = []
        where_clauses = []

        # Add index range filters
        if params:
            if params.after_index is not None:
                where_clauses.append(f"row_index > ${len(sql_params) + 1}")
                sql_params.append(params.after_index)
            if params.before_index is not None:
                where_clauses.append(f"row_index < ${len(sql_params) + 1}")
                sql_params.append(params.before_index)

        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)

        sql += " ORDER BY row_index"

        if params and params.limit:
            sql += f" LIMIT ${len(sql_params) + 1} OFFSET ${len(sql_params) + 2}"
            sql_params.extend([params.limit, params.offset])
        elif params and params.offset:
            sql += f" OFFSET ${len(sql_params) + 1}"
            sql_params.append(params.offset)

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
            return result


class PostgreSQLLogController(LogTableController, _BoundedPostgresConnectionMixIn):
    """PostgreSQL implementation of LogTableController."""

    async def find(
        self, query: Query, params: RangeQueryParams | None = None
    ) -> list[LogRow]:
        """Find logs using JSONQuery objects."""
        params = params or RangeQueryParams()
        where_clause, query_params = _convert_query_to_postgres(query)

        sql = f"""
        SELECT row_index, id, created_at, data FROM {self._schema}.logs
        WHERE {where_clause}
        """
        sql_params = query_params[:]

        # Add time range filters
        if params.after:
            sql += f" AND created_at > ${len(sql_params) + 1}"
            sql_params.append(params.after)
        if params.before:
            sql += f" AND created_at < ${len(sql_params) + 1}"
            sql_params.append(params.before)

        sql += " ORDER BY row_index"

        # Add pagination
        if params.limit:
            sql += f" LIMIT ${len(sql_params) + 1} OFFSET ${len(sql_params) + 2}"
            sql_params.extend([params.limit, params.offset])
        elif params.offset:
            sql += f" OFFSET ${len(sql_params) + 1}"
            sql_params.append(params.offset)

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

        async with self.connection(is_write=True) as conn:
            row_index = await conn.fetchval(
                f"INSERT INTO {self._schema}.logs (id, created_at, data) VALUES ($1, $2, $3) RETURNING row_index",
                log_id,
                item.created_at,
                json.dumps(item.data.model_dump()),
            )

        return LogRow(
            id=log_id, created_at=item.created_at, data=item.data, index=row_index
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

    async def get_all(self, params: RangeQueryParams | None = None) -> list[LogRow]:
        """Get all logs with pagination."""
        sql = f"SELECT row_index, id, created_at, data FROM {self._schema}.logs ORDER BY row_index"
        sql_params = []

        if params and params.limit:
            sql += " LIMIT $1 OFFSET $2"
            sql_params.extend([params.limit, params.offset])
        elif params and params.offset:
            sql += " OFFSET $1"
            sql_params.append(params.offset)

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
            return result


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

    async def execute(self, command: Any) -> Any:
        """Execute an arbitrary database command."""
        async with self._pool.acquire() as conn:
            return await conn.execute(command)

    async def initialize(self):
        """Initialize the database tables."""
        async with self._pool.acquire() as conn:
            # Check if schema already exists
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name = $1)",
                self._schema,
            )

            if not exists:
                # Create the new schema
                await conn.execute(f"CREATE SCHEMA {self._schema}")

            # Create tables in the schema (will be skipped if they already exist due to IF NOT EXISTS)
            await conn.execute(create_tables_sql(self._schema))

    def __del__(self):
        """Write metrics to file when object is destroyed."""
        # Stop the periodic timer
        _stop_metrics_timer()
        # Do a final dump
        _dump_metrics_to_file("postgresql_metrics")


@asynccontextmanager
async def create_postgresql_database(
    schema: str,
    host: str = "localhost",
    port: int = 5432,
    database: str = "marketplace",
    user: str = "postgres",
    password: str | None = None,
    min_size: int = 50,
    max_size: int = 50,
    command_timeout: float = 60,
):
    """Create PostgreSQL database controller with connection pooling.

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

    """
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
    await controller.initialize()
    try:
        yield controller
    finally:
        await pool.close()
