"""Export a PostgreSQL experiment to SQLite database file."""

import sys
from pathlib import Path

from magentic_marketplace.platform.database import connect_to_postgresql_database
from magentic_marketplace.platform.database.converter import convert_postgres_to_sqlite


async def export_experiment(
    experiment_name: str,
    output_dir: str | None = None,
    output_filename: str | None = None,
    postgres_host: str = "localhost",
    postgres_port: int = 5432,
    postgres_user: str = "postgres",
    postgres_password: str = "postgres",
):
    """Export a PostgreSQL experiment database to SQLite.

    Args:
        experiment_name: Name of the experiment (PostgreSQL schema name)
        output_dir: Optional output directory path (defaults to current directory)
        output_filename: Optional output filename (defaults to <experiment_name>.db)
        postgres_host: PostgreSQL host (default: localhost)
        postgres_port: PostgreSQL port (default: 5432)
        postgres_user: PostgreSQL user (default: postgres)
        postgres_password: PostgreSQL password (default: postgres)

    """
    # Determine output path
    if output_filename is None:
        output_filename = f"{experiment_name}.db"

    if output_dir is not None:
        output_path = Path(output_dir) / output_filename
    else:
        output_path = Path(output_filename)

    # Check if output file already exists
    if output_path.exists():
        raise FileExistsError(
            f"Output file already exists: {output_path}. "
            "Please remove it or choose a different output path."
        )

    print(f"Exporting experiment '{experiment_name}' to SQLite...")
    print(f"Output path: {output_path}")

    # Connect to PostgreSQL database
    try:
        async with connect_to_postgresql_database(
            schema=experiment_name,
            host=postgres_host,
            port=postgres_port,
            user=postgres_user,
            password=postgres_password,
            mode="existing",
        ) as db_controller:
            print(
                f"Connected to PostgreSQL database (schema: {experiment_name}, host: {postgres_host})"
            )

            # Convert to SQLite
            result_path = await convert_postgres_to_sqlite(db_controller, output_path)
            print("\nExport completed successfully!")
            print(f"SQLite database saved to: {result_path}")

    except Exception as e:
        print(f"Error: Failed to export experiment: {e}", file=sys.stderr)
        raise
