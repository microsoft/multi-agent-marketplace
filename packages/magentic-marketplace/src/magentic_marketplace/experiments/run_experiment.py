#!/usr/bin/env python3
"""Script to run marketplace experiments using YAML configuration files."""

import socket
from datetime import datetime
from pathlib import Path

from magentic_marketplace.experiments.utils import (
    load_businesses_from_yaml,
    load_customers_from_yaml,
)
from magentic_marketplace.marketplace.agents import BusinessAgent, CustomerAgent
from magentic_marketplace.marketplace.protocol.protocol import SimpleMarketplaceProtocol
from magentic_marketplace.platform.database import (
    connect_to_postgresql_database,
)
from magentic_marketplace.platform.database.converter import convert_postgres_to_sqlite
from magentic_marketplace.platform.launcher import AgentLauncher, MarketplaceLauncher


async def run_marketplace_experiment(
    data_dir: str | Path,
    experiment_name: str | None = None,
    search_algorithm: str = "simple",
    search_bandwidth: int = 10,
    customer_max_steps: int | None = None,
    postgres_host: str = "localhost",
    postgres_port: int = 5432,
    postgres_password: str = "postgres",
    db_pool_min_size: int = 2,
    db_pool_max_size: int = 10,
    server_host: str = "127.0.0.1",
    server_port: int = 0,
    override: bool = False,
    export_sqlite: bool = False,
    export_dir: str | None = None,
    export_filename: str | None = None,
):
    """Run a marketplace experiment using YAML configuration files."""
    # Load businesses and customers from YAML files
    data_dir = Path(data_dir)
    businesses_dir = data_dir / "businesses"
    customers_dir = data_dir / "customers"

    print(f"Loading data from: {data_dir}")
    businesses = load_businesses_from_yaml(businesses_dir)
    customers = load_customers_from_yaml(customers_dir)

    print(f"Loaded {len(customers)} customers and {len(businesses)} businesses")

    if experiment_name is None:
        experiment_name = f"marketplace_{len(customers)}_{len(businesses)}_{int(datetime.now().timestamp() * 1000)}"

    def database_factory():
        return connect_to_postgresql_database(
            schema=experiment_name,
            host=postgres_host,
            port=postgres_port,
            password=postgres_password,
            min_size=db_pool_min_size,
            max_size=db_pool_max_size,
            mode="override" if override else "create_new",
        )

    # Auto-assign port if set to 0
    if server_port == 0:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((server_host, 0))
            server_port = s.getsockname()[1]
        print(f"Auto-assigned server port: {server_port}")

    marketplace_launcher = MarketplaceLauncher(
        protocol=SimpleMarketplaceProtocol(),
        database_factory=database_factory,
        host=server_host,
        port=server_port,
        server_log_level="warning",
        experiment_name=experiment_name,
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
                search_bandwidth=search_bandwidth,
                max_steps=customer_max_steps,
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

        # Convert PostgreSQL database to SQLite (if requested)
        if export_sqlite:
            # Determine output path
            if export_filename is None:
                export_filename = f"{experiment_name}.db"

            if export_dir is not None:
                sqlite_path = Path(export_dir) / export_filename
            else:
                sqlite_path = Path(export_filename)

            # Check if output file already exists
            if sqlite_path.exists():
                raise FileExistsError(
                    f"Output file already exists: {sqlite_path}. "
                    "Please remove it or choose a different output path using --export-filename or --export-dir."
                )

            logger.info(f"Converting database to SQLite: {sqlite_path}")
            if marketplace_launcher.server:
                db = marketplace_launcher.server.state.database_controller
                await convert_postgres_to_sqlite(db, sqlite_path)
                logger.info(f"Database conversion complete: {sqlite_path}")

        print(f"\nRun analytics with: magentic-marketplace analyze {experiment_name}")
