#!/usr/bin/env python3
"""Script to run marketplace experiments using YAML configuration files."""

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from magentic_marketplace.experiments.utils import (
    load_businesses_from_yaml,
    load_customers_from_yaml,
    setup_logging,
)
from magentic_marketplace.marketplace.agents import BusinessAgent, CustomerAgent
from magentic_marketplace.marketplace.protocol.protocol import SimpleMarketplaceProtocol
from magentic_marketplace.platform.database import (
    create_postgresql_database,
)
from magentic_marketplace.platform.launcher import AgentLauncher, MarketplaceLauncher


async def run_marketplace_experiment(
    data_dir: Path,
    experiment_name: str | None = None,
    search_algorithm: str = "simple",
    postgres_host: str = "localhost",
    postgres_port: int = 5432,
    postgres_password: str = "postgres",
):
    """Run a marketplace experiment using YAML configuration files."""
    # Load businesses and customers from YAML files
    businesses_dir = data_dir / "businesses"
    customers_dir = data_dir / "customers"

    print(f"Loading data from: {data_dir}")
    businesses = load_businesses_from_yaml(businesses_dir)
    customers = load_customers_from_yaml(customers_dir)

    print(f"Loaded {len(businesses)} businesses and {len(customers)} customers")

    if experiment_name is None:
        # Auto-generate schema name if not provided
        now = datetime.now()
        experiment_name = now.strftime(
            f"marketplace_{len(businesses)}_businesses_{len(customers)}_customers_%Y_%m_%d_%H_%M"
        )

    # Create the marketplace launcher
    def database_factory():
        return create_postgresql_database(
            schema=experiment_name,
            host=postgres_host,
            port=postgres_port,
            password=postgres_password,
        )

    marketplace_launcher = MarketplaceLauncher(
        protocol=SimpleMarketplaceProtocol(),
        database_factory=database_factory,
        server_log_level="warning",
    )

    print(f"Using protocol: {marketplace_launcher.protocol.__class__.__name__}")

    # Use marketplace launcher as async context manager
    async with marketplace_launcher:
        # Create logger
        logger = await marketplace_launcher.create_logger("marketplace_experiment")
        logger.info(
            f"Marketplace experiment started:\nbusinesses={len(businesses)}\ncustomers={len(customers)}\ndata_dir={data_dir}\nexperiment_name:{experiment_name}",
        )

        # Create agents from loaded profiles
        business_agents = [
            BusinessAgent(business, marketplace_launcher.server_url)
            for business in businesses
        ]

        customer_agents = [
            CustomerAgent(
                customer,
                marketplace_launcher.server_url,
                search_algorithm=search_algorithm,
            )
            for customer in customers
        ]

        # Create agent launcher and run agents with dependency management
        async with AgentLauncher(marketplace_launcher.server_url) as agent_launcher:
            try:
                await agent_launcher.run_agents_with_dependencies(
                    primary_agents=customer_agents, dependent_agents=business_agents
                )
            except KeyboardInterrupt:
                logger.warning("Simulation interrupted by user")


def main():
    """Run experiment."""
    # Setup logging
    setup_logging()

    logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser(
        description="Run marketplace experiments using YAML configuration files"
    )
    parser.add_argument(
        "data_dir",
        type=str,
        help="Path to the data directory containing businesses/ and customers/ subdirectories",
    )
    parser.add_argument(
        "--search-algorithm",
        type=str,
        default="simple",
        help="Search algorithm for customer agents (default: simple)",
    )
    parser.add_argument(
        "--experiment-name",
        default=None,
        help="Provide a name for this experiment. Will be used as the 'schema' name in postgres",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help=".env file with environment variables to load.",
    )
    parser.add_argument(
        "--postgres-host",
        default="localhost",
        help="PostgreSQL host (default: localhost)",
    )
    parser.add_argument(
        "--postgres-port",
        type=int,
        default=5432,
        help="PostgreSQL port (default: 5432)",
    )
    parser.add_argument(
        "--postgres-user",
        default="postgres",
        help="PostgreSQL user (default: postgres)",
    )
    parser.add_argument(
        "--postgres-password",
        default="postgres",
        help="PostgreSQL password (default: postgres)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level (default: INFO)",
    )

    args = parser.parse_args()

    # Set logging level based on CLI argument
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
        logger.error(
            f"Businesses directory does not exist: {businesses_dir}",
        )
        sys.exit(1)

    if not customers_dir.exists():
        logger.error(
            f"Customers directory does not exist: {customers_dir}",
        )
        sys.exit(1)

    # Try load .env
    did_load_env = load_dotenv(args.env_file)
    if did_load_env:
        logger.info(
            f"Loaded environment variables from env file at path: {args.env_file}"
        )
    else:
        logger.warning(
            f"No environment variables loaded from env file at path: {args.env_file}"
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
        )
    )


if __name__ == "__main__":
    main()
