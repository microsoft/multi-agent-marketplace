"""Test configuration and fixtures for simple marketplace tests."""

import asyncio
import os
import socket
import tempfile
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio

from magentic_marketplace.marketplace.protocol.protocol import SimpleMarketplaceProtocol
from magentic_marketplace.marketplace.shared.models import (
    Business,
    BusinessAgentProfile,
    Customer,
    CustomerAgentProfile,
)
from magentic_marketplace.platform.agent.base import BaseAgent
from magentic_marketplace.platform.database.models import AgentRow
from magentic_marketplace.platform.database.sqlite import connect_to_sqlite_database
from magentic_marketplace.platform.database.sqlite.sqlite import (
    SQLiteDatabaseController,
)
from magentic_marketplace.platform.launcher import MarketplaceLauncher
from magentic_marketplace.platform.shared.models import AgentProfile


class MinimalTestAgent(BaseAgent[AgentProfile]):
    """Minimal agent for testing - only implements required methods."""

    def __init__(self, base_url: str, profile: AgentProfile) -> None:
        """Initialize minimal test agent."""
        super().__init__(profile, base_url)

    async def step(self) -> None:
        """Implement required abstract method as no-op for tests."""
        pass


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop]:
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def test_database() -> AsyncGenerator[SQLiteDatabaseController]:
    """Create a temporary test database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_file:
        db_path = temp_file.name

    async with connect_to_sqlite_database(db_path) as database:
        yield database

    # Cleanup
    try:
        import os

        os.unlink(db_path)
    except Exception:
        pass


@pytest_asyncio.fixture
async def test_agent_customer(test_database: SQLiteDatabaseController) -> AgentProfile:
    """Create a test customer agent."""
    agent = AgentProfile(id="test-customer-001", metadata={})

    # Register the agent in the database
    agent_row = AgentRow(id=agent.id, created_at=datetime.now(UTC), data=agent)
    await test_database.agents.create(agent_row)
    return agent


@pytest_asyncio.fixture
async def test_agent_business(test_database: SQLiteDatabaseController) -> AgentProfile:
    """Create a test business agent."""
    agent = AgentProfile(
        id="test-business-001",
        metadata={
            "business": {
                "id": "test-restaurant-001",
                "name": "Test Restaurant",
                "description": "A test restaurant for testing",
                "rating": 4.5,
                "progenitor_customer": "test-customer-002",
                "menu_features": {"pizza": 12.99, "pasta": 10.99},
                "amenity_features": {"delivery": True, "takeout": True},
                "min_price_factor": 0.8,
            }
        },
    )

    # Register the agent in the database
    agent_row = AgentRow(id=agent.id, created_at=datetime.now(UTC), data=agent)
    await test_database.agents.create(agent_row)
    return agent


@pytest.fixture
def protocol() -> SimpleMarketplaceProtocol:
    """Create a protocol instance for testing."""
    return SimpleMarketplaceProtocol()


@pytest_asyncio.fixture
async def integration_test_setup() -> AsyncGenerator[dict[str, Any]]:
    """Set up marketplace server for integration testing."""
    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_file:
        db_path = temp_file.name

    def database_factory():
        return connect_to_sqlite_database(db_path)

    # Find a free port for testing
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        free_port = s.getsockname()[1]

    # Create launcher with the free port
    launcher = MarketplaceLauncher(
        protocol=SimpleMarketplaceProtocol(),
        database_factory=database_factory,
        port=free_port,
    )

    try:
        # Start server
        await launcher.start_server()

        # Use the launcher's server URL which should now have the correct port
        actual_server_url = launcher.server_url

        # Create database connection for verification
        async with connect_to_sqlite_database(db_path) as database:
            yield {
                "launcher": launcher,
                "database": database,
                "server_url": actual_server_url,
                "db_path": db_path,
            }
    finally:
        await launcher.stop_server()
        try:
            os.unlink(db_path)
        except Exception:
            pass


@pytest_asyncio.fixture
async def test_agents_with_client(
    integration_test_setup: dict[str, Any],
) -> AsyncGenerator[dict[str, Any]]:
    """Create test agents with marketplace client."""
    setup = integration_test_setup

    business_profile = Business(
        id="sweet_bakery",
        name="Sweet Dreams Bakery",
        description="Artisan bakery specializing in custom birthday cakes and gluten-free options with delivery",
        rating=4.5,
        progenitor_customer="customer_000",
        menu_features={
            "birthday cake": 58.0,
        },
        amenity_features={
            "delivery": True,
            "custom_decorations": True,
            "parking": False,
            "wifi": True,
        },
        min_price_factor=0.8,
    )
    customer_profile = Customer(
        id="alice_customer",
        name="Alice Smith",
        request="Looking for a bakery with gluten-free birthday cakes",
        menu_features={
            "birthday cake": 60.0,
        },
        amenity_features=["delivery", "custom_decorations"],
    )
    business = MinimalTestAgent(
        setup["server_url"], BusinessAgentProfile.from_business(business_profile)
    )
    customer = MinimalTestAgent(
        setup["server_url"], CustomerAgentProfile.from_customer(customer_profile)
    )

    try:
        # Connect clients explicitly
        await customer.client.connect()
        await business.client.connect()

        # Register both agents (this creates them in DB via HTTP)
        customer_response = await customer.client.agents.register(customer.profile)
        customer.profile.id = customer_response.id
        customer.client.set_agent_id(customer.profile.id)

        business_response = await business.client.agents.register(business.profile)
        business.profile.id = business_response.id
        business.client.set_agent_id(business.profile.id)

        yield {
            "customer": customer,
            "business": business,
            "database": setup["database"],
        }
    finally:
        # Ensure client sessions are properly closed
        if hasattr(customer, "client") and hasattr(customer.client, "close"):
            await customer.client.close()
        if hasattr(business, "client") and hasattr(business.client, "close"):
            await business.client.close()
