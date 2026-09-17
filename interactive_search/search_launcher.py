"""Module to launch a marketplace server with businesses and a single customer agent for interactive search experiments."""

import asyncio
import traceback
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import requests
from magentic_marketplace.experiments.utils.yaml_loader import (
    load_businesses_from_yaml,
    load_customers_from_yaml,
)
from magentic_marketplace.marketplace.actions.actions import (
    Search,
    SearchAlgorithm,
    SearchResponse,
)
from magentic_marketplace.marketplace.agents.business.agent import BusinessAgent
from magentic_marketplace.marketplace.agents.customer.agent import CustomerAgent
from magentic_marketplace.marketplace.protocol.protocol import SimpleMarketplaceProtocol
from magentic_marketplace.marketplace.shared.models import BusinessAgentProfile
from magentic_marketplace.platform.database.postgresql.postgresql import (
    connect_to_postgresql_database,
)
from magentic_marketplace.platform.launcher import MarketplaceLauncher


class SearchMarketLauncher:
    """Class to manage launching the marketplace server for interactive search experiments with a set of business agents and a single customer agent."""

    def __init__(
        self,
        data_dir: str,
        postgres_host: str,
        postgres_port: int,
        postgres_password: str,
        search_algorithm: str = "lexical",
    ):
        """Initialize the launcher with empty lists for agents and tasks."""
        self.business_agents = []
        self.customer_agent = None
        self.tasks = []
        self.marketplace_launcher = None

        # Get the SearchAlgorithm enum value from the string value provided
        if search_algorithm.lower() == "lexical":
            self.search_algorithm = SearchAlgorithm.LEXICAL
        elif search_algorithm.lower() == "optimal":
            self.search_algorithm = SearchAlgorithm.OPTIMAL
        elif search_algorithm.lower() == "filtered":
            self.search_algorithm = SearchAlgorithm.FILTERED
        elif search_algorithm.lower() == "simple":
            self.search_algorithm = SearchAlgorithm.SIMPLE
        elif search_algorithm.lower() == "rnr":
            self.search_algorithm = SearchAlgorithm.RNR
        else:
            raise ValueError(f"Invalid search algorithm: {search_algorithm}")

        self.search_algorithm = search_algorithm

        self.business_profiles = []
        self.customer_profiles = []

        self.load_data(
            data_dir=data_dir,
            postgres_host=postgres_host,
            postgres_port=postgres_port,
            postgres_password=postgres_password,
        )

    def load_data(
        self,
        data_dir: str,
        postgres_host: str,
        postgres_port: int,
        postgres_password: str,
    ):
        """Load businesses and customers from YAML files."""
        businesses_dir = Path(data_dir) / "businesses"
        customers_dir = Path(data_dir) / "customers"

        print(f"Loading data from: {data_dir}")
        self.business_profiles = load_businesses_from_yaml(businesses_dir)
        self.customer_profiles = load_customers_from_yaml(customers_dir)

        print(f"Loaded {len(self.business_profiles)} businesses")
        print(f"Loaded {len(self.customer_profiles)} customers")

        experiment_name = f"marketplace_interactive_search_{len(self.business_profiles)}_{int(datetime.now().timestamp() * 1000)}"

        def database_factory():
            return connect_to_postgresql_database(
                schema=experiment_name,
                host=postgres_host,
                port=postgres_port,
                password=postgres_password,
                mode="create_new",
            )

        self.marketplace_launcher = MarketplaceLauncher(
            protocol=SimpleMarketplaceProtocol(),
            database_factory=database_factory,
            server_log_level="warning",
            experiment_name=experiment_name,
        )

        print(
            f"Using protocol: {self.marketplace_launcher.protocol.__class__.__name__}"
        )

    @asynccontextmanager
    async def start(self):
        """Startup platform, businesses, and customer task."""
        async with self.marketplace_launcher:
            print(
                f"Marketplace server running at: {self.marketplace_launcher.server_url}"
            )

            # Create agents from loaded profiles
            business_agents = [
                BusinessAgent(business, self.marketplace_launcher.server_url)
                for business in self.business_profiles
            ]
            self.business_agents.extend(business_agents)

            # only create one customer agent for interactive search
            customer_agent = CustomerAgent(
                self.customer_profiles[0],
                self.marketplace_launcher.server_url,
                search_algorithm=self.search_algorithm,
            )
            self.customer_agent = customer_agent

            # Create agent launcher and run agents with dependency management
            try:
                # Startup business agents tasks only
                primary_tasks = [
                    asyncio.create_task(agent.run()) for agent in business_agents
                ]
                self.tasks.extend(primary_tasks)
                print(f"Started {len(primary_tasks)} tasks for business agents")

                # Startup customer agent task
                customer_task = asyncio.create_task(customer_agent.run())
                self.tasks.append(customer_task)

                print("Started task for customer agent")

                await asyncio.sleep(1)
            except KeyboardInterrupt:
                print("Marketplace interrupted by user")

            yield self.marketplace_launcher

    async def stop(self):
        """Stop all running tasks and agents."""
        for agent in self.business_agents:
            agent.shutdown()

        if self.customer_agent:
            self.customer_agent.shutdown()

        await asyncio.sleep(0.1)

        await asyncio.gather(*self.tasks)

        await asyncio.sleep(0.2)

    async def search(self, query) -> list[BusinessAgentProfile]:
        """Issue search queries using the customer agent and return the resulting business profiles."""
        try:
            response = await self.customer_agent.execute_action(
                Search(
                    query=query,
                    search_algorithm=self.search_algorithm,
                    limit=10,
                    page=1,
                )
            )
            if response.is_error:
                print(f"Search action failed: {response.error_message}")
                return

            parsed_response = SearchResponse.model_validate(response.content)
            businesses_results = parsed_response.businesses

            # Print results
            return businesses_results

        except requests.RequestException as e:
            print(f"Request failed: {e}")
            traceback.print_exc()

    async def interactive_search(self, show_all_searchable_text: bool = False):
        """Issue search queries interactively from the customer agent."""
        while True:
            query = input("Query (or 'exit' to quit): ")
            if query.lower() == "exit":
                break
            try:
                print(f"Searching for: {query}")
                response = await self.customer_agent.execute_action(
                    Search(
                        query=query,
                        search_algorithm=self.search_algorithm,
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
                    if show_all_searchable_text:
                        print(
                            f"- {b.business.name}: {b.business.get_searchable_text()}"
                        )
                    else:
                        print(f"- {b.business.name}")

            except requests.RequestException as e:
                print(f"Request failed: {e}")
                traceback.print_exc()
