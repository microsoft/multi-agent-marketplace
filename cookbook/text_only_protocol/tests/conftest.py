"""Test configuration and fixtures for text-only protocol tests."""

import asyncio
import socket
import tempfile
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio

from cookbook.text_only_protocol.protocol import TextOnlyProtocol
from magentic_marketplace.platform.agent.base import BaseAgent
from magentic_marketplace.platform.database.models import AgentRow
from magentic_marketplace.platform.database.sqlite import create_sqlite_database
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

    async with create_sqlite_database(db_path) as database:
        yield database

    # Cleanup
    try:
        import os

        os.unlink(db_path)
    except Exception:
        pass


@pytest_asyncio.fixture
async def test_agent_alice(test_database: SQLiteDatabaseController) -> AgentProfile:
    """Create test agent Alice."""
    agent = AgentProfile(id="alice", metadata={})

    agent_row = AgentRow(id=agent.id, created_at=datetime.now(UTC), data=agent)
    await test_database.agents.create(agent_row)
    return agent


@pytest_asyncio.fixture
async def test_agent_bob(test_database: SQLiteDatabaseController) -> AgentProfile:
    """Create test agent Bob."""
    agent = AgentProfile(id="bob", metadata={})

    agent_row = AgentRow(id=agent.id, created_at=datetime.now(UTC), data=agent)
    await test_database.agents.create(agent_row)
    return agent


@pytest.fixture
def protocol() -> TextOnlyProtocol:
    """Create a protocol instance for testing."""
    return TextOnlyProtocol()


@pytest_asyncio.fixture
async def integration_test_setup() -> AsyncGenerator[dict[str, Any]]:
    """Set up marketplace server for integration testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_file:
        db_path = temp_file.name

    def database_factory():
        return create_sqlite_database(db_path)

    # Find a free port for testing
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        free_port = s.getsockname()[1]

    # Create launcher with the free port
    launcher = MarketplaceLauncher(
        protocol=TextOnlyProtocol(),
        database_factory=database_factory,
        port=free_port,
    )

    try:
        # Start server
        await launcher.start_server()

        actual_server_url = launcher.server_url

        # Create database connection for verification
        async with create_sqlite_database(db_path) as database:
            yield {
                "launcher": launcher,
                "database": database,
                "server_url": actual_server_url,
                "db_path": db_path,
            }
    finally:
        await launcher.stop_server()
        try:
            import os

            os.unlink(db_path)
        except Exception:
            pass


@pytest_asyncio.fixture
async def test_agents_with_client(
    integration_test_setup: dict[str, Any],
) -> dict[str, Any]:
    """Create test agents with client connections for integration testing."""
    server_url = integration_test_setup["server_url"]
    database = integration_test_setup["database"]

    # Create agent profiles
    alice_profile = AgentProfile(id="alice", metadata={})
    bob_profile = AgentProfile(id="bob", metadata={})

    # Create agent clients
    alice = MinimalTestAgent(server_url, alice_profile)
    bob = MinimalTestAgent(server_url, bob_profile)

    try:
        # Connect clients explicitly
        await alice.client.connect()
        await bob.client.connect()

        # Register both agents (this creates them in DB via HTTP)
        alice_response = await alice.client.agents.register(alice.profile)
        alice._token = alice_response.token
        alice.client.set_token(alice._token)
        alice.profile.id = alice_response.agent.id

        bob_response = await bob.client.agents.register(bob.profile)
        bob._token = bob_response.token
        bob.client.set_token(bob._token)
        bob.profile.id = bob_response.agent.id

        yield {
            "alice": alice,
            "bob": bob,
            "database": database,
        }
    finally:
        # Cleanup: disconnect clients
        if hasattr(alice, "client") and hasattr(alice.client, "close"):
            await alice.client.close()
        if hasattr(bob, "client") and hasattr(bob.client, "close"):
            await bob.client.close()
