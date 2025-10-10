#!/usr/bin/env python3
"""List marketplace experiments stored in PostgreSQL."""

import sys
from datetime import UTC, datetime

import asyncpg


def format_datetime_local(dt: datetime) -> str:
    """Format datetime in local timezone with timezone abbreviation.

    Args:
        dt: Datetime to format (should be timezone-aware)

    Returns:
        Formatted string like "2025-10-09 14:23:45 PDT"

    """
    # Convert to local timezone if needed
    if dt.tzinfo is None:
        # Assume UTC if naive
        dt = dt.replace(tzinfo=UTC)

    # Get local timezone by using astimezone() without arguments
    local_dt = dt.astimezone()

    # Format with timezone abbreviation
    return local_dt.strftime("%Y-%m-%d %H:%M:%S %Z")


async def list_experiments(
    host: str = "localhost",
    port: int = 5432,
    database: str = "marketplace",
    user: str = "postgres",
    password: str | None = None,
    limit: int | None = None,
):
    """List all marketplace experiments from PostgreSQL schemas.

    Args:
        host: PostgreSQL server host
        port: PostgreSQL server port
        database: Database name
        user: Database user
        password: Database password
        limit: Maximum number of experiments to display

    """
    try:
        # Connect to PostgreSQL
        conn = await asyncpg.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
        )

        try:
            # Query for all schemas excluding system schemas
            query = """
            SELECT
                s.schema_name,
                COUNT(DISTINCT t.table_name) as table_count
            FROM information_schema.schemata s
            LEFT JOIN information_schema.tables t
                ON s.schema_name = t.table_schema
            WHERE s.schema_name NOT IN ('pg_catalog', 'information_schema', 'public', 'pg_toast')
                AND s.schema_name NOT LIKE 'pg_temp%'
                AND s.schema_name NOT LIKE 'pg_toast%'
            GROUP BY s.schema_name
            ORDER BY s.schema_name
            """

            rows = await conn.fetch(query)

            # For each schema, get the last activity timestamp
            schema_info = []
            for row in rows:
                schema_name = row["schema_name"]
                table_count = row["table_count"] or 0

                # Try to get the first and last activity from the schema
                first_activity = None
                last_activity = None
                llm_providers = set()
                try:
                    # Check if the tables exist first
                    has_agents = await conn.fetchval(
                        """
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.tables
                            WHERE table_schema = $1 AND table_name = 'agents'
                        )
                        """,
                        schema_name,
                    )
                    has_actions = await conn.fetchval(
                        """
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.tables
                            WHERE table_schema = $1 AND table_name = 'actions'
                        )
                        """,
                        schema_name,
                    )
                    has_logs = await conn.fetchval(
                        """
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.tables
                            WHERE table_schema = $1 AND table_name = 'logs'
                        )
                        """,
                        schema_name,
                    )

                    # Skip schemas that don't have all three required tables
                    if not (has_agents and has_actions and has_logs):
                        continue

                    # Get first agent registration timestamp (earliest agent created_at)
                    if has_agents:
                        first_activity = await conn.fetchval(
                            f"SELECT MIN(created_at) FROM {schema_name}.agents"
                        )

                    # Get last activity across all tables
                    queries = []
                    if has_agents:
                        queries.append(
                            f"SELECT MAX(created_at) as max_created_at FROM {schema_name}.agents"
                        )
                    if has_actions:
                        queries.append(
                            f"SELECT MAX(created_at) as max_created_at FROM {schema_name}.actions"
                        )
                    if has_logs:
                        queries.append(
                            f"SELECT MAX(created_at) as max_created_at FROM {schema_name}.logs"
                        )

                    if queries:
                        union_query = " UNION ALL ".join(queries)
                        last_activity = await conn.fetchval(
                            f"SELECT MAX(max_created_at) FROM ({union_query}) AS dates"
                        )

                    # Get unique LLM providers from logs
                    if has_logs:
                        try:
                            provider_rows = await conn.fetch(
                                f"""
                                SELECT DISTINCT jsonb_path_query_first(data, '$.data.provider') #>> '{{}}' as provider
                                FROM {schema_name}.logs
                                WHERE jsonb_path_query_first(data, '$.data.provider') IS NOT NULL
                                """
                            )
                            llm_providers = {
                                row["provider"]
                                for row in provider_rows
                                if row["provider"]
                            }
                        except Exception:
                            # If we can't get providers, just skip it
                            pass
                except Exception:
                    # If we can't get activity timestamps, just skip it
                    pass

                schema_info.append(
                    {
                        "schema_name": schema_name,
                        "table_count": table_count,
                        "first_activity": first_activity,
                        "last_activity": last_activity,
                        "llm_providers": llm_providers,
                    }
                )

            # Sort by first agent registration (most recent first)
            # Use timezone-aware datetime for comparison
            schema_info.sort(
                key=lambda x: x["first_activity"] or datetime.min.replace(tzinfo=UTC),
                reverse=True,
            )

            rows = schema_info

            if not rows:
                print("No experiments found in PostgreSQL database.")
                print(f"\nDatabase: {database}")
                print(f"Host: {host}:{port}")
                return

            # Apply limit if specified
            total_experiments = len(rows)
            if limit is not None and limit > 0:
                rows = rows[:limit]

            # Print header
            print(f"\n{'=' * 80}")
            print(f"MARKETPLACE EXPERIMENTS (Database: {database})")
            print(f"{'=' * 80}\n")

            if limit is not None and total_experiments > limit:
                print(
                    f"Showing {len(rows)} of {total_experiments} experiment(s) (most recent first):\n"
                )
            else:
                print(f"Found {len(rows)} experiment(s) (most recent first):\n")

            # Print each experiment
            for idx, schema_dict in enumerate(rows, 1):
                schema_name = schema_dict["schema_name"]
                table_count = schema_dict["table_count"] or 0
                first_activity = schema_dict["first_activity"]
                last_activity = schema_dict["last_activity"]
                llm_providers = schema_dict.get("llm_providers", set())

                print(f"{idx}. {schema_name}")

                if first_activity:
                    # Format the datetime
                    if isinstance(first_activity, datetime):
                        formatted_time = format_datetime_local(first_activity)
                        print(f"   First agent registered: {formatted_time}")
                else:
                    print("   First agent registered: N/A (no data)")

                if last_activity:
                    # Format the datetime
                    if isinstance(last_activity, datetime):
                        formatted_time = format_datetime_local(last_activity)
                        print(f"   Last activity: {formatted_time}")
                else:
                    print("   Last activity: N/A (no data)")

                # Get row counts for each table in this schema
                try:
                    agents_count = await conn.fetchval(
                        f"SELECT COUNT(*) FROM {schema_name}.agents"
                    )
                    actions_count = await conn.fetchval(
                        f"SELECT COUNT(*) FROM {schema_name}.actions"
                    )
                    logs_count = await conn.fetchval(
                        f"SELECT COUNT(*) FROM {schema_name}.logs"
                    )

                    print(
                        f"   Data: {agents_count} agents, {actions_count} actions, {logs_count} logs"
                    )
                except Exception:
                    # Table might not exist
                    print("   Data: Unable to query")

                # Display LLM providers
                if llm_providers:
                    providers_str = ", ".join(sorted(llm_providers))
                    print(f"   LLM Providers: {providers_str}")

                print()

        finally:
            await conn.close()

    except asyncpg.InvalidCatalogNameError:
        print(f"Error: Database '{database}' does not exist", file=sys.stderr)
        sys.exit(1)
    except asyncpg.InvalidPasswordError:
        print("Error: Invalid password", file=sys.stderr)
        sys.exit(1)
