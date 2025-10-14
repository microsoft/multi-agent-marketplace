"""Database converter for migrating PostgreSQL data to SQLite."""

import logging
from pathlib import Path

from .models import ActionRow, AgentRow, LogRow
from .postgresql.postgresql import PostgreSQLDatabaseController
from .sqlite import connect_to_sqlite_database
from .sqlite.sqlite import SQLiteDatabaseController

logger = logging.getLogger(__name__)


class DatabaseConverter:
    """Convert PostgreSQL database to SQLite format."""

    def __init__(
        self,
        source_db: PostgreSQLDatabaseController,
        target_path: str | Path,
    ):
        """Initialize converter.

        Args:
            source_db: Source PostgreSQL database controller
            target_path: Path where the SQLite database file should be created

        """
        self.source_db = source_db
        self.target_path = Path(target_path)

    async def convert(self) -> Path:
        """Convert PostgreSQL database to SQLite.

        Returns:
            Path to the created SQLite database file

        Raises:
            ValueError: If verification fails

        """
        logger.info(f"Starting conversion to {self.target_path}")

        # Ensure parent directory exists
        self.target_path.parent.mkdir(parents=True, exist_ok=True)

        # Create SQLite database
        async with connect_to_sqlite_database(str(self.target_path)) as target_db:
            # Copy data in order
            await self._copy_agents(target_db)
            await self._copy_actions(target_db)
            await self._copy_logs(target_db)

            # Verify the conversion
            await self._verify_conversion(target_db)

        logger.info(f"Conversion completed successfully: {self.target_path}")
        return self.target_path

    async def _copy_agents(self, target_db: SQLiteDatabaseController) -> None:
        """Copy agents from PostgreSQL to SQLite in row_index order."""
        logger.info("Copying agents table...")

        # Get all agents ordered by row_index
        agents = await self.source_db.agents.get_all()

        # Sort by index to ensure correct order (should already be sorted, but be explicit)
        agents.sort(key=lambda a: a.index if a.index is not None else 0)

        # Prepare rows without the index (SQLite will auto-assign rowid)
        new_agents = [
            AgentRow(
                id=agent.id,
                created_at=agent.created_at,
                data=agent.data,
                agent_embedding=agent.agent_embedding,
            )
            for agent in agents
        ]

        # Bulk insert all agents using create_many
        await target_db.agents.create_many(new_agents)

        logger.info(f"Copied {len(agents)} agents")

    async def _copy_actions(self, target_db: SQLiteDatabaseController) -> None:
        """Copy actions from PostgreSQL to SQLite in row_index order."""
        logger.info("Copying actions table...")

        # Get all actions ordered by row_index
        actions = await self.source_db.actions.get_all()

        # Sort by index to ensure correct order
        actions.sort(key=lambda a: a.index if a.index is not None else 0)

        # Prepare rows without the index (SQLite will auto-assign rowid)
        new_actions = [
            ActionRow(
                id=action.id,
                created_at=action.created_at,
                data=action.data,
            )
            for action in actions
        ]

        # Bulk insert all actions using create_many
        await target_db.actions.create_many(new_actions)

        logger.info(f"Copied {len(actions)} actions")

    async def _copy_logs(self, target_db: SQLiteDatabaseController) -> None:
        """Copy logs from PostgreSQL to SQLite in row_index order."""
        logger.info("Copying logs table...")

        # Get all logs ordered by row_index
        logs = await self.source_db.logs.get_all()

        # Sort by index to ensure correct order
        logs.sort(key=lambda log: log.index if log.index is not None else 0)

        # Prepare rows without the index (SQLite will auto-assign rowid)
        new_logs = [
            LogRow(
                id=log.id,
                created_at=log.created_at,
                data=log.data,
            )
            for log in logs
        ]

        # Bulk insert all logs using create_many
        await target_db.logs.create_many(new_logs)

        logger.info(f"Copied {len(logs)} logs")

    async def _verify_conversion(self, target_db: SQLiteDatabaseController) -> None:
        """Verify that the conversion was successful.

        Checks:
        1. Row counts match between source and target
        2. SQLite rowid matches PostgreSQL row_index for each row

        Raises:
            ValueError: If verification fails

        """
        logger.info("Verifying conversion...")

        # Verify agents
        await self._verify_table(
            "agents",
            await self.source_db.agents.get_all(),
            await target_db.agents.get_all(),
        )

        # Verify actions
        await self._verify_table(
            "actions",
            await self.source_db.actions.get_all(),
            await target_db.actions.get_all(),
        )

        # Verify logs
        await self._verify_table(
            "logs",
            await self.source_db.logs.get_all(),
            await target_db.logs.get_all(),
        )

        logger.info("Verification completed successfully")

    async def _verify_table(
        self,
        table_name: str,
        source_rows: list[AgentRow] | list[ActionRow] | list[LogRow],
        target_rows: list[AgentRow] | list[ActionRow] | list[LogRow],
    ) -> None:
        """Verify a single table.

        Args:
            table_name: Name of the table being verified
            source_rows: Rows from PostgreSQL (with row_index)
            target_rows: Rows from SQLite (with rowid as index)

        Raises:
            ValueError: If verification fails

        """
        # Check row counts
        if len(source_rows) != len(target_rows):
            raise ValueError(
                f"{table_name}: Row count mismatch - "
                f"PostgreSQL has {len(source_rows)}, SQLite has {len(target_rows)}"
            )

        # Sort both by index to compare
        source_rows.sort(key=lambda r: r.index if r.index is not None else 0)
        target_rows.sort(key=lambda r: r.index if r.index is not None else 0)

        # Verify each row
        for source_row, target_row in zip(source_rows, target_rows, strict=True):
            # Check that SQLite rowid matches PostgreSQL row_index
            if source_row.index != target_row.index:
                raise ValueError(
                    f"{table_name}: Index mismatch for row with id={source_row.id} - "
                    f"PostgreSQL row_index={source_row.index}, SQLite rowid={target_row.index}"
                )

            # Check that IDs match
            if source_row.id != target_row.id:
                raise ValueError(
                    f"{table_name}: ID mismatch at index {source_row.index} - "
                    f"PostgreSQL id={source_row.id}, SQLite id={target_row.id}"
                )

        logger.info(
            f"{table_name}: Verified {len(source_rows)} rows - all indices match"
        )


async def convert_postgres_to_sqlite(
    source_db: PostgreSQLDatabaseController,
    target_path: str | Path,
) -> Path:
    """Convert a PostgreSQL database to SQLite.

    Convenience function that creates a converter and runs the conversion.

    Args:
        source_db: Source PostgreSQL database controller
        target_path: Path where the SQLite database file should be created

    Returns:
        Path to the created SQLite database file

    Raises:
        ValueError: If verification fails

    """
    converter = DatabaseConverter(source_db, target_path)
    return await converter.convert()
