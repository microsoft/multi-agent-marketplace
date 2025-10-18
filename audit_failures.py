#!/usr/bin/env python3
"""Audit databases for 'LLM decision failed' errors in logs."""

import asyncio

import asyncpg
from magentic_marketplace.marketplace.actions import ActionAdapter, SendMessage
from magentic_marketplace.platform.database import (
    connect_to_postgresql_database,
)
from magentic_marketplace.platform.database.queries import logs as log_queries


async def get_all_schemas(
    host: str = "localhost",
    port: int = 5432,
    database: str = "marketplace",
    user: str = "postgres",
    password: str = "postgres",
) -> list[str]:
    """Get all experiment schemas from the PostgreSQL database.

    Args:
        host: PostgreSQL server host
        port: PostgreSQL server port
        database: Database name
        user: Database user
        password: Database password

    Returns:
        List of schema names

    """
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
        SELECT s.schema_name
        FROM information_schema.schemata s
        LEFT JOIN information_schema.tables t ON s.schema_name = t.table_schema
        WHERE s.schema_name NOT IN ('pg_catalog', 'information_schema', 'public', 'pg_toast')
            AND s.schema_name NOT LIKE 'pg_temp%'
            AND s.schema_name NOT LIKE 'pg_toast%'
        GROUP BY s.schema_name
        ORDER BY s.schema_name
        """

        rows = await conn.fetch(query)

        # Filter to only schemas that have the required tables
        schemas = []
        for row in rows:
            schema_name = row["schema_name"]

            # Check if required tables exist
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

            # Only include schemas with all required tables
            if has_agents and has_actions and has_logs:
                schemas.append(schema_name)

        return schemas

    finally:
        await conn.close()


async def get_log_level_counts(schema_name: str) -> dict[str, int]:
    """Get count of each log level in a database.

    Args:
        schema_name: The PostgreSQL schema name (experiment name)

    Returns:
        Dictionary mapping log level to count

    """
    async with connect_to_postgresql_database(
        schema=schema_name,
        host="localhost",
        port=5432,
        password="postgres",
        mode="existing",
    ) as db_controller:
        # Get all logs
        all_logs = await db_controller.logs.get_all()

        # Count by level
        level_counts: dict[str, int] = {}
        for log_row in all_logs:
            level = log_row.data.level
            level_counts[level] = level_counts.get(level, 0) + 1

        return level_counts


async def audit_database(
    schema_name: str,
) -> tuple[str, bool, int, int, int, int, int, int, int]:
    """Audit a single database for LLM decision failed and database busy errors.

    Args:
        schema_name: The PostgreSQL schema name (experiment name)

    Returns:
        Tuple of (schema_name, has_errors, llm_error_count, db_busy_count, wrong_customer_id_count,
                  total_send_messages, text_messages, payment_messages, order_proposal_messages)
    """
    try:
        async with connect_to_postgresql_database(
            schema=schema_name,
            host="localhost",
            port=5432,
            password="postgres",
            mode="existing",
        ) as db_controller:
            # Query for LLM decision failed logs
            llm_query = log_queries.message(
                value="%LLM decision failed%", operator="LIKE"
            )
            llm_error_logs = await db_controller.logs.find(llm_query)
            llm_error_count = len(llm_error_logs)

            # Query for database too busy logs
            db_busy_query = log_queries.message(
                value="%Database too busy%", operator="LIKE"
            )
            db_busy_logs = await db_controller.logs.find(db_busy_query)
            db_busy_count = len(db_busy_logs)

            # Query for wrong customer id logs
            biz_msg = "Error: Failed to send message to"
            cust_msg = "Failed to send message to"
            wrong_customer_id_query = log_queries.message(
                value=f"%{cust_msg}%", operator="LIKE"
            )

            wrong_customer_id_logs = await db_controller.logs.find(
                wrong_customer_id_query
            )
            wrong_customer_id_count = len(wrong_customer_id_logs)

            # Query actions table for send message statistics
            all_actions = await db_controller.actions.get_all()

            total_send_messages = 0
            text_messages = 0
            payment_messages = 0
            order_proposal_messages = 0

            for action_row in all_actions:
                action_request = action_row.data.request
                action_result = action_row.data.result

                # Parse action using ActionAdapter like in run_analytics.py
                try:
                    action = ActionAdapter.validate_python(action_request.parameters)

                    # Check if this is a SendMessage action
                    if isinstance(action, SendMessage):
                        # Only count if the action didn't error
                        if not action_result.is_error:
                            total_send_messages += 1
                            # Get the message type
                            message = action.message
                            message_type = message.type

                            if message_type == "text":
                                text_messages += 1
                            elif message_type == "payment":
                                payment_messages += 1
                            elif message_type == "order_proposal":
                                order_proposal_messages += 1
                except Exception:
                    # Skip actions that can't be parsed
                    pass

            has_errors = (
                llm_error_count > 0 or db_busy_count > 0 or wrong_customer_id_count > 0
            )

            return (
                schema_name,
                has_errors,
                llm_error_count,
                db_busy_count,
                wrong_customer_id_count,
                total_send_messages,
                text_messages,
                payment_messages,
                order_proposal_messages,
            )

    except Exception as e:
        print(f"Error accessing {schema_name}: {e}")
        return schema_name, False, 0, 0, 0, 0, 0, 0, 0


async def main():
    """Run audit on all databases."""
    print("Auditing database logs for errors...\n")

    schemas = await get_all_schemas()

    if not schemas:
        print("No experiment schemas found.")
        return

    schemas.sort()

    for schema in schemas:
        level_counts = await get_log_level_counts(schema)

        (
            schema_name,
            has_errors,
            llm_error_count,
            db_busy_count,
            wrong_customer_id_count,
            total_send_messages,
            text_messages,
            payment_messages,
            order_proposal_messages,
        ) = await audit_database(schema)

        status = "YES" if has_errors else "NO "

        error_str = f"{llm_error_count} LLM errors, {db_busy_count} DB busy, {wrong_customer_id_count} Fake business ID"

        level_str = ", ".join(
            [f"{level}: {count}" for level, count in sorted(level_counts.items())]
        )

        messages_str = f"Messages: {total_send_messages} total ({text_messages} text, {payment_messages} pay, {order_proposal_messages} order_proposal)"
        print(
            f"{status} - {schema_name} - Logs: {error_str}, {level_str}; {messages_str}"
        )


if __name__ == "__main__":
    asyncio.run(main())
