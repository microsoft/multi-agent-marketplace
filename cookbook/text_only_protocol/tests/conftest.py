"""Test fixtures for text-only protocol.

This file provides reusable test fixtures:
- test_database: Temporary SQLite database for unit tests
- test_agents_with_client: Full integration test setup with server and agents
"""

import asyncio
import socket
import tempfile
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from magentic_marketplace.platform.agent.base import BaseAgent
from magentic_marketplace.platform.database.models import AgentRow
from magentic_marketplace.platform.database.sqlite import create_sqlite_database
from magentic_marketplace.platform.database.sqlite.sqlite import (
    SQLiteDatabaseController,
)
from magentic_marketplace.platform.launcher import MarketplaceLauncher
from magentic_marketplace.platform.shared.models import AgentProfile

from cookbook.text_only_protocol.protocol import TextOnlyProtocol


class MinimalTestAgent(BaseAgent[AgentProfile]):
    """Bare-bones agent for testing protocol actions.

    Only implements the required abstract methods. Used to test protocol
    functionality without complex agent logic.
    """

    def __init__(self, base_url: str, profile: AgentProfile) -> None:
        """Initialize minimal test agent."""
        super().__init__(profile, base_url)

    async def step(self) -> None:
        """Perform agent step (no-op for tests)."""
        pass


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop]:
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def test_database() -> AsyncGenerator[SQLiteDatabaseController]:
    """Provide a clean temporary database for each test.

    Creates a SQLite database in a temp file, yields it for the test,
    then cleans up the file afterward.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_file:
        db_path = temp_file.name

    async with create_sqlite_database(db_path) as database:
        yield database

    try:
        import os

        os.unlink(db_path)
    except Exception:
        pass


@pytest_asyncio.fixture
async def test_agent_alice(test_database: SQLiteDatabaseController) -> AgentProfile:
    """Create and register Alice in the test database."""
    agent = AgentProfile(id="alice", metadata={})

    agent_row = AgentRow(id=agent.id, created_at=datetime.now(UTC), data=agent)
    await test_database.agents.create(agent_row)
    return agent


@pytest_asyncio.fixture
async def test_agent_bob(test_database: SQLiteDatabaseController) -> AgentProfile:
    """Create and register Bob in the test database."""
    agent = AgentProfile(id="bob", metadata={})

    agent_row = AgentRow(id=agent.id, created_at=datetime.now(UTC), data=agent)
    await test_database.agents.create(agent_row)
    return agent


@pytest.fixture
def protocol() -> TextOnlyProtocol:
    """Provide protocol instance for testing."""
    return TextOnlyProtocol()


@pytest_asyncio.fixture
async def integration_test_setup() -> AsyncGenerator[dict[str, Any]]:
    """Start a real marketplace server for integration testing.

    This fixture:
    1. Creates a temporary database
    2. Finds a free port to avoid conflicts
    3. Starts the marketplace server
    4. Yields server URL and database connection
    5. Cleans everything up when test completes
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_file:
        db_path = temp_file.name

    def database_factory():
        return create_sqlite_database(db_path)

    # Find available port automatically
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        free_port = s.getsockname()[1]

    launcher = MarketplaceLauncher(
        protocol=TextOnlyProtocol(),
        database_factory=database_factory,
        port=free_port,
    )

    try:
        await launcher.start_server()

        async with create_sqlite_database(db_path) as database:
            yield {
                "launcher": launcher,
                "database": database,
                "server_url": launcher.server_url,
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
    """Create two test agents (Alice and Bob) connected to the marketplace.

    This is the main fixture for integration tests. It provides:
    - alice: MinimalTestAgent connected and authenticated
    - bob: MinimalTestAgent connected and authenticated
    - database: Direct database access for verification

    Both agents are registered with the server and ready to execute actions.
    """
    server_url = integration_test_setup["server_url"]
    database = integration_test_setup["database"]

    alice_profile = AgentProfile(id="alice", metadata={})
    bob_profile = AgentProfile(id="bob", metadata={})

    alice = MinimalTestAgent(server_url, alice_profile)
    bob = MinimalTestAgent(server_url, bob_profile)

    try:
        # Connect to server
        await alice.client.connect()
        await bob.client.connect()

        # Register and authenticate both agents
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
        # Clean disconnect
        if hasattr(alice, "client") and hasattr(alice.client, "close"):
            await alice.client.close()
        if hasattr(bob, "client") and hasattr(bob.client, "close"):
            await bob.client.close()
