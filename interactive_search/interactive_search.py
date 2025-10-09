"""A simple interactive search client for the agentic-economics marketplace."""

import argparse
import asyncio
import traceback
from datetime import datetime
from pathlib import Path

import requests
from magentic_marketplace.experiments.utils import load_businesses_from_yaml
from magentic_marketplace.experiments.utils.yaml_loader import load_customers_from_yaml
from magentic_marketplace.marketplace.actions import (
    Search,
    SearchAlgorithm,
    SearchResponse,
)
from magentic_marketplace.marketplace.agents import BusinessAgent
from magentic_marketplace.marketplace.agents.customer.agent import CustomerAgent
from magentic_marketplace.marketplace.protocol.protocol import SimpleMarketplaceProtocol
from magentic_marketplace.platform.database import (
    connect_to_postgresql_database,
)
from magentic_marketplace.platform.launcher import AgentLauncher, MarketplaceLauncher


async def main(
    data_dir: str, postgres_host: str, postgres_port: int, postgres_password: str
) -> None:
    """Run a simple interactive search client for the agentic-economics marketplace."""
    # Startup platform and business tasks
    businesses_dir = Path(args.data_dir) / "businesses"
    customers_dir = Path(args.data_dir) / "customers"

    print(f"Loading data from: {data_dir}")
    businesses = load_businesses_from_yaml(businesses_dir)
    customers = load_customers_from_yaml(customers_dir)

    print(f"Loaded {len(businesses)} businesses")
    print(f"Loaded {len(customers)} customers")

    experiment_name = f"marketplace_interactive_search_{len(businesses)}_{int(datetime.now().timestamp() * 1000)}"

    def database_factory():
        return connect_to_postgresql_database(
            schema=experiment_name,
            host=postgres_host,
            port=postgres_port,
            password=postgres_password,
            mode="create_new",
        )

    marketplace_launcher = MarketplaceLauncher(
        # host="localhost",
        # port=5555,
        protocol=SimpleMarketplaceProtocol(),
        database_factory=database_factory,
        server_log_level="warning",
        experiment_name=experiment_name,
    )

    print(f"Using protocol: {marketplace_launcher.protocol.__class__.__name__}")

    async with marketplace_launcher:
        print(f"Marketplace server running at: {marketplace_launcher.server_url}")

        # Create agents from loaded profiles
        business_agents = [
            BusinessAgent(business, marketplace_launcher.server_url)
            for business in businesses
        ]

        # only create one customer agent for interactive search
        customer_agent = CustomerAgent(
            customers[0],
            marketplace_launcher.server_url,
            search_algorithm=SearchAlgorithm.LEXICAL,
        )

        # Create agent launcher and run agents with dependency management
        # async with AgentLauncher(marketplace_launcher.server_url) as agent_launcher:
        try:
            # Startup business agents tasks only
            primary_tasks = [
                asyncio.create_task(agent.run()) for agent in business_agents
            ]
            print(f"Started {len(primary_tasks)} tasks for business agents")

            # Startup customer agent task
            customer_task = asyncio.create_task(customer_agent.run())
            print("Started task for customer agent")

            await asyncio.sleep(1)

            while True:
                query = input("Query (or 'exit' to quit): ")
                if query.lower() == "exit":
                    break
                try:
                    print(f"Searching for: {query}")
                    response = await customer_agent.execute_action(
                        Search(
                            query=query,
                            search_algorithm=SearchAlgorithm.LEXICAL,
                            limit=10,
                            page=1,
                        )
                    )
                    if response.is_error:
                        print(f"Search action failed: {response.error_message}")
                        continue

                    print("Search action succeeded")
                    parsed_response = SearchResponse.model_validate(response.content)
                    businesses_results = parsed_response.businesses
                    print(f"Found {len(businesses_results)} businesses:")

                    # Print results
                    for b in businesses_results:
                        print(f"- {b.business.name}")

                except requests.RequestException as e:
                    print(f"Request failed: {e}")
                    traceback.print_exc()

            # Signal dependent agents (e.g., businesses) to shutdown gracefully
            print(f"Signaling {len(business_agents)} dependent agents to shutdown...")
            for agent in business_agents:
                agent.shutdown()

            customer_agent.shutdown()

            # Give agents a brief moment to process shutdown signal
            await asyncio.sleep(0.1)

            # Wait for dependent agents to complete graceful shutdown
            # (includes logger cleanup in agent on_will_stop hooks)
            await asyncio.gather(*primary_tasks)
            await asyncio.gather(customer_task)
            print("All dependent agents shut down gracefully")

            # Brief final pause to ensure all cleanup is complete
            await asyncio.sleep(0.2)

        except KeyboardInterrupt:
            logger.warning("Simulation interrupted by user")


if __name__ == "__main__":
    # Add argument parsing for data dir using argparse
    parser = argparse.ArgumentParser(
        description="Interactive search client for the multi-agent-marketplace"
    )
    parser.add_argument(
        "--data-dir", help="Path to the dataset directory", required=True
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
        "--postgres-password",
        default="postgres",
        help="PostgreSQL password (default: postgres)",
    )

    args = parser.parse_args()

    asyncio.run(
        main(
            args.data_dir,
            args.postgres_host,
            args.postgres_port,
            args.postgres_password,
        )
    )
