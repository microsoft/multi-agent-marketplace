#!/usr/bin/env python3
"""Script to run marketplace experiments using YAML configuration files."""

from datetime import datetime
from pathlib import Path

from magentic_marketplace.experiments.utils import (
    load_businesses_from_yaml,
    load_customers_from_yaml,
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
