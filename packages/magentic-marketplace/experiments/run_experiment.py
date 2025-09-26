#!/usr/bin/env python3
"""Script to run marketplace experiments using YAML configuration files."""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from utils import load_businesses_from_yaml, load_customers_from_yaml, setup_logging

from magentic_marketplace.marketplace.agents import BusinessAgent, CustomerAgent
from magentic_marketplace.marketplace.protocol.protocol import SimpleMarketplaceProtocol
from magentic_marketplace.platform.database import (
    create_postgresql_database,
)
from magentic_marketplace.platform.launcher import AgentLauncher, MarketplaceLauncher


async def run_marketplace_experiment(
    data_dir: Path,
    db_file: str,
    search_algorithm: str = "simple",
):
    """Run a marketplace experiment using YAML configuration files."""
    # Load businesses and customers from YAML files
    businesses_dir = data_dir / "businesses"
    customers_dir = data_dir / "customers"

    print(f"Loading data from: {data_dir}")
    businesses = load_businesses_from_yaml(businesses_dir)
    customers = load_customers_from_yaml(customers_dir)

    print(f"Loaded {len(businesses)} businesses and {len(customers)} customers")

    # Create the marketplace launcher
    def database_factory():
        return create_postgresql_database(password="postgres")
        # return create_sqlite_database(db_file)
        # return create_sharded_sqlite_database(os.path.splitext(db_file)[0], 8, 8, 8)

    marketplace_launcher = MarketplaceLauncher(
        protocol=SimpleMarketplaceProtocol(),
        database_factory=database_factory,
        title="Marketplace Experiment",
        description=f"Experiment with {len(businesses)} businesses and {len(customers)} customers",
        db_file_cleanup=db_file,
        server_log_level="warning",
    )

    print(f"Using protocol: {marketplace_launcher.protocol.__class__.__name__}")

    # Use marketplace launcher as async context manager
    async with marketplace_launcher:
        # Create logger
        logger = await marketplace_launcher.create_logger("marketplace_experiment")
        logger.info(
            f"Marketplace experiment started: businesses={len(businesses)}, customers={len(customers)}, data_dir={data_dir}",
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
    parser = argparse.ArgumentParser(
        description="Run marketplace experiments using YAML configuration files"
    )
    parser.add_argument(
        "data_dir",
        type=str,
        help="Path to the data directory containing businesses/ and customers/ subdirectories",
    )
    parser.add_argument(
        "--db-file",
        type=str,
        default="marketplace.db",
        help="SQLite database file name (default: marketplace.db)",
    )
    parser.add_argument(
        "--search-algorithm",
        type=str,
        default="simple",
        help="Search algorithm for customer agents (default: simple)",
    )
    parser.add_argument(
        "--clean-db",
        action="store_true",
        help="Remove existing database file before running",
    )

    args = parser.parse_args()

    # Convert paths to Path objects
    data_dir = Path(args.data_dir)

    # Validate data directory structure
    if not data_dir.exists():
        print(f"Error: Data directory does not exist: {data_dir}", file=sys.stderr)
        sys.exit(1)

    businesses_dir = data_dir / "businesses"
    customers_dir = data_dir / "customers"

    if not businesses_dir.exists():
        print(
            f"Error: Businesses directory does not exist: {businesses_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    if not customers_dir.exists():
        print(
            f"Error: Customers directory does not exist: {customers_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Clean up existing database file if requested
    if os.path.exists(args.db_file):
        if args.clean_db:
            os.remove(args.db_file)
            print(f"Removed existing database file: {args.db_file}")
        else:
            print(
                f"Error: Database file already exists: {args.db_file}.\nOverwrite with --clean-db, or provide different --db-file"
            )
            sys.exit(1)

    # Setup logging
    setup_logging()

    print("Marketplace Experiment Runner")
    print("This experiment will:")
    print(f"1. Load businesses from: {businesses_dir}")
    print(f"2. Load customers from: {customers_dir}")
    print(f"3. Create a SQLite database: {args.db_file}")
    print("4. Start a marketplace server with simple marketplace protocol")
    print("5. Register all business and customer agents")
    print("6. Run the marketplace simulation")
    print()

    # Run the experiment
    asyncio.run(
        run_marketplace_experiment(
            data_dir=data_dir,
            db_file=args.db_file,
            search_algorithm=args.search_algorithm,
        )
    )


if __name__ == "__main__":
    main()
