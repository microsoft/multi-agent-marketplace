"""Command-line interface for magentic-marketplace."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from magentic_marketplace.experiments.extract_agent_llm_traces import (
    run_extract_traces,
)
from magentic_marketplace.experiments.list_experiments import list_experiments
from magentic_marketplace.experiments.run_analytics import run_analytics
from magentic_marketplace.experiments.run_audit import run_audit
from magentic_marketplace.experiments.run_experiment import run_marketplace_experiment
from magentic_marketplace.experiments.utils import setup_logging


def run_experiment_command(args):
    """Handle the experiment subcommand."""
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)

    # Set logging level if provided
    if hasattr(args, "log_level"):
        numeric_level = getattr(logging, args.log_level.upper())
        logging.getLogger().setLevel(numeric_level)

    # Convert paths to Path objects
    data_dir = Path(args.data_dir)

    # Validate data directory structure
    if not data_dir.exists():
        logger.error(f"Data directory does not exist: {data_dir}")
        sys.exit(1)

    businesses_dir = data_dir / "businesses"
    customers_dir = data_dir / "customers"

    if not businesses_dir.exists():
        logger.error(f"Businesses directory does not exist: {businesses_dir}")
        sys.exit(1)

    if not customers_dir.exists():
        logger.error(f"Customers directory does not exist: {customers_dir}")
        sys.exit(1)

    # Try load .env
    env_file = getattr(args, "env_file", ".env")
    did_load_env = load_dotenv(env_file)
    if did_load_env:
        logger.info(f"Loaded environment variables from env file at path: {env_file}")
    else:
        logger.warning(
            f"No environment variables loaded from env file at path: {env_file}"
        )

    logger.info(
        "Marketplace Experiment Runner\n"
        "This experiment will:\n"
        f"1. Load businesses from: {businesses_dir}\n"
        f"2. Load customers from: {customers_dir}\n"
        f"3. Create a Postgres database schema: {args.experiment_name}\n"
        "4. Start a marketplace server with simple marketplace protocol\n"
        "5. Register all business and customer agents\n"
        "6. Run the marketplace simulation\n"
    )

    # Run the experiment
    asyncio.run(
        run_marketplace_experiment(
            data_dir=data_dir,
            experiment_name=args.experiment_name,
            search_algorithm=args.search_algorithm,
            search_bandwidth=args.search_bandwidth,
            customer_max_steps=args.customer_max_steps,
            postgres_host=args.postgres_host,
            postgres_port=args.postgres_port,
            postgres_password=args.postgres_password,
            override=args.override_db,
        )
    )


def run_analysis_command(args):
    """Handle the analytics subcommand."""
    save_to_json = not args.no_save_json
    asyncio.run(
        run_analytics(args.database_name, args.db_type, save_to_json=save_to_json)
    )


def run_extract_traces_command(args):
    """Handle the extract-traces subcommand."""
    asyncio.run(run_extract_traces(args.database_name, args.db_type))


def run_audit_command(args):
    """Handle the audit subcommand."""
    save_to_json = not args.no_save_json
    asyncio.run(run_audit(args.database_name, args.db_type, save_to_json=save_to_json))


def list_experiments_command(args):
    """Handle the list-experiments subcommand."""
    asyncio.run(
        list_experiments(
            host=args.postgres_host,
            port=args.postgres_port,
            database=args.postgres_database,
            user=args.postgres_user,
            password=args.postgres_password,
            limit=args.limit,
        )
    )


def main():
    """Run main CLI."""
    parser = argparse.ArgumentParser(
        prog="magentic-marketplace",
        description="Magentic Marketplace - Python SDK for building and running agentic marketplace simulations",
    )

    # Add subcommands
    subparsers = parser.add_subparsers(
        dest="command", help="Available commands", required=True
    )

    # experiment subcommand
    experiment_parser = subparsers.add_parser(
        "run", help="Run a marketplace experiment using YAML configuration files"
    )
    experiment_parser.set_defaults(func=run_experiment_command)

    experiment_parser.add_argument(
        "data_dir",
        type=str,
        help="Path to the data directory containing businesses/ and customers/ subdirectories",
    )

    experiment_parser.add_argument(
        "--search-algorithm",
        type=str,
        default="lexical",
        help="Search algorithm for customer agents (default: lexical)",
    )

    experiment_parser.add_argument(
        "--search-bandwidth",
        type=int,
        default=10,
        help="Search bandwidth for customer agents (default: 10)",
    )

    experiment_parser.add_argument(
        "--customer-max-steps",
        type=int,
        default=100,
        help="Maximum number of steps a customer agent can take before stopping.",
    )

    experiment_parser.add_argument(
        "--experiment-name",
        default=None,
        help="Provide a name for this experiment. Will be used as the 'schema' name in postgres",
    )

    experiment_parser.add_argument(
        "--env-file",
        default=".env",
        help=".env file with environment variables to load.",
    )

    experiment_parser.add_argument(
        "--postgres-host",
        default="localhost",
        help="PostgreSQL host (default: localhost)",
    )

    experiment_parser.add_argument(
        "--postgres-port",
        type=int,
        default=5432,
        help="PostgreSQL port (default: 5432)",
    )

    experiment_parser.add_argument(
        "--postgres-password",
        default="postgres",
        help="PostgreSQL password (default: postgres)",
    )

    experiment_parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level (default: INFO)",
    )

    experiment_parser.add_argument(
        "--override-db",
        action="store_true",
        help="Override the existing database schema if it exists.",
    )

    # analytics subcommand
    analytics_parser = subparsers.add_parser(
        "analyze", help="Analyze marketplace simulation data"
    )
    analytics_parser.set_defaults(func=run_analysis_command)

    analytics_parser.add_argument(
        "database_name", help="Postgres schema name or path to the SQLite database file"
    )

    analytics_parser.add_argument(
        "--db-type",
        choices=["sqlite", "postgres"],
        default="postgres",
        help="Type of database to use (default: postgres)",
    )

    analytics_parser.add_argument(
        "--no-save-json",
        action="store_true",
        help="Disable saving analytics to JSON file",
    )

    # extract-traces subcommand
    extract_traces_parser = subparsers.add_parser(
        "extract-traces",
        help="Extract LLM traces from marketplace simulation and save to markdown files",
    )
    extract_traces_parser.set_defaults(func=run_extract_traces_command)

    extract_traces_parser.add_argument(
        "database_name", help="Postgres schema name or path to the SQLite database file"
    )

    extract_traces_parser.add_argument(
        "--db-type",
        choices=["sqlite", "postgres"],
        default="postgres",
        help="Type of database to use (default: postgres)",
    )

    # audit subcommand
    audit_parser = subparsers.add_parser(
        "audit",
        help="Audit marketplace simulation to verify customers received all proposals",
    )
    audit_parser.set_defaults(func=run_audit_command)

    audit_parser.add_argument(
        "database_name", help="Postgres schema name or path to the SQLite database file"
    )

    audit_parser.add_argument(
        "--db-type",
        choices=["sqlite", "postgres"],
        default="postgres",
        help="Type of database to use (default: postgres)",
    )

    audit_parser.add_argument(
        "--no-save-json",
        action="store_true",
        help="Disable saving audit results to JSON file",
    )

    # list-experiments subcommand
    list_experiments_parser = subparsers.add_parser(
        "list",
        help="List all marketplace experiments stored in PostgreSQL",
    )
    list_experiments_parser.set_defaults(func=list_experiments_command)

    list_experiments_parser.add_argument(
        "--postgres-host",
        default="localhost",
        help="PostgreSQL host (default: localhost)",
    )

    list_experiments_parser.add_argument(
        "--postgres-port",
        type=int,
        default=5432,
        help="PostgreSQL port (default: 5432)",
    )

    list_experiments_parser.add_argument(
        "--postgres-database",
        default="marketplace",
        help="PostgreSQL database name (default: marketplace)",
    )

    list_experiments_parser.add_argument(
        "--postgres-user",
        default="postgres",
        help="PostgreSQL user (default: postgres)",
    )

    list_experiments_parser.add_argument(
        "--postgres-password",
        default="postgres",
        help="PostgreSQL password (default: postgres)",
    )

    list_experiments_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of experiments to display",
    )

    # Parse arguments and execute the appropriate function
    args = parser.parse_args()

    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\nExecution interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
