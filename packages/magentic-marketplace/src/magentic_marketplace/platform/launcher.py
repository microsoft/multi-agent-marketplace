"""Marketplace launcher for coordinating server, protocol, and agents."""

import asyncio
from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from types import TracebackType
from typing import Any, TypeVar

from pydantic import BaseModel

from .agent.base import BaseAgent
from .client import MarketplaceClient
from .database.base import BaseDatabaseController
from .logger import MarketplaceLogger
from .protocol.base import BaseMarketplaceProtocol
from .server import MarketplaceServer
from .shared.models import ActionProtocol, AgentProfile, Log

# TypeVar for any agent profile that extends AgentProfile
AnyProfile = TypeVar("AnyProfile", bound=AgentProfile)


class MarketplaceState(BaseModel):
    """Current state of the marketplace."""

    server_health: dict[str, Any]
    agents: list[AgentProfile]
    action_protocols: list[ActionProtocol]
    recent_logs: list[Log]


class MarketplaceLauncher:
    """Launches and manages the marketplace server and protocol."""

    def __init__(
        self,
        protocol: BaseMarketplaceProtocol,
        database_factory: Callable[
            [], AbstractAsyncContextManager[BaseDatabaseController, bool | None]
        ],
        *,
        host: str = "127.0.0.1",
        port: int = 8000,
        title: str = "Marketplace API",
        description: str = "A marketplace for autonomous agents",
        server_log_level: str = "info",
        experiment_name: str | None = None,
    ):
        """Initialize the marketplace launcher.

        Args:
            protocol: The marketplace protocol defining business logic
            database_factory: Factory function to create database controller
            host: Server host address
            port: Server port
            title: API documentation title
            description: API documentation description
            server_log_level: FastAPI server log level (debug, info, warning, error, critical)
            experiment_name: Name of the experiment

        """
        self.protocol = protocol
        self.database_factory = database_factory
        self.host = host
        self.port = port
        self.title = title
        self.description = description
        self.server_log_level = server_log_level
        self.experiment_name = experiment_name

        self.server: MarketplaceServer | None = None
        self.server_task: asyncio.Task[None] | None = None
        self._stop_server_fn: Callable[[], None] | None = None
        self.server_url = f"http://{host}:{port}"
        self._exit_stack: AsyncExitStack | None = None

    async def start_server(
        self,
        *,
        max_retries: int = 10,
        retry_delay: float = 0.1,
        max_delay: float = 5.0,
    ) -> None:
        """Start the marketplace server.

        Args:
            max_retries: Maximum number of health check attempts
            retry_delay: Initial delay between retries in seconds
            max_delay: Maximum delay between retries in seconds

        """
        # Create and configure server
        self.server = MarketplaceServer(
            database_factory=self.database_factory,
            protocol=self.protocol,
            title=self.title,
            description=self.description,
        )
        print("Creating MarketplaceServer...")

        # Start server in background
        self.server_task, self._stop_server_fn = self.server.create_server_task(
            host=self.host, port=self.port, log_level=self.server_log_level
        )

        # Wait for server to start with health check and backoff
        last_exception = None
        current_delay = retry_delay
        for _ in range(max_retries):
            try:
                async with MarketplaceClient(self.server_url) as client:
                    await client.health_check()
                    print(
                        f"MarketplaceServer is running and healthy at {self.server_url}"
                    )
                    return
            except Exception as e:
                last_exception = e
                await asyncio.sleep(current_delay)
                current_delay = min(current_delay * 2, max_delay)  # Exponential backoff

        # Failed to connect
        raise RuntimeError(
            f"Server failed to become healthy after {max_retries} attempts"
        ) from last_exception

    async def stop_server(self) -> None:
        """Stop the marketplace server."""
        if self._stop_server_fn:
            print("Stopping server...")
            self._stop_server_fn()

        if self.server_task:
            try:
                await self.server_task
            except asyncio.CancelledError:
                pass

        print("Server stopped")

    async def create_logger(self, name: str = __name__) -> MarketplaceLogger:
        """Create a logger connected to the marketplace.

        Args:
            name: Logger name

        Returns:
            MarketplaceLogger instance

        """
        if self._exit_stack is None:
            raise RuntimeError(
                "MarketplaceLauncher must be used as an async context manager"
            )

        client = await self._exit_stack.enter_async_context(
            MarketplaceClient(self.server_url)
        )
        logger = MarketplaceLogger(name, client)
        return logger

    async def query_marketplace_state(self) -> MarketplaceState:
        """Query the current state of the marketplace.

        Returns:
            MarketplaceState with current marketplace information

        """
        async with MarketplaceClient(self.server_url) as client:
            # Get server health
            health = await client.health_check()

            # Get all registered agents
            agents: list[AgentProfile] = []
            offset = 0
            limit = 100
            has_more = True

            while has_more:
                agents_response = await client.agents.list(offset=offset, limit=limit)
                agents.extend(agents_response.items)
                has_more = agents_response.has_more or False
                offset += limit

            # Get available action protocols
            protocols = await client.actions.get_protocol()

            # Get recent logs
            logs_response = await client.logs.list(limit=10)

            return MarketplaceState(
                server_health=health,
                agents=agents,
                action_protocols=protocols.actions,
                recent_logs=logs_response.items,
            )

    async def __aenter__(self):
        """Async context manager entry."""
        self._exit_stack = AsyncExitStack()
        await self._exit_stack.__aenter__()
        await self.start_server()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit."""
        try:
            await self.stop_server()
        finally:
            if self._exit_stack is not None:
                await self._exit_stack.__aexit__(exc_type, exc_val, exc_tb)
                self._exit_stack = None


class AgentLauncher:
    """Launches and manages agents against a running marketplace server."""

    def __init__(self, base_url: str):
        """Initialize the agent launcher.

        Args:
            base_url: URL of the running marketplace server

        """
        self.base_url = base_url
        self._exit_stack: AsyncExitStack | None = None

    async def run_agents(self, *agents: BaseAgent[Any]) -> None:
        """Run a list of agents concurrently.

        Args:
            agents: List of agents to run

        """
        if not agents:
            return

        print(f"\nRunning {len(agents)} agents...")

        # Start all agents as concurrent tasks
        agent_tasks = [asyncio.create_task(agent.run()) for agent in agents]

        # Wait for all agents to complete
        await asyncio.gather(*agent_tasks)

        print("All agents completed")

    async def run_agents_with_dependencies(
        self,
        primary_agents: Sequence[BaseAgent[Any]],
        dependent_agents: Sequence[BaseAgent[Any]],
    ) -> None:
        """Run agents where dependent agents shutdown when primary agents complete.

        This method runs primary agents (e.g., customers) and dependent agents (e.g., businesses)
        concurrently, but signals dependent agents to shutdown gracefully once all primary
        agents have completed their tasks.

        Args:
            primary_agents: Agents that drive the experiment lifecycle (e.g., customers)
            dependent_agents: Agents that should shutdown when primary agents complete (e.g., businesses)

        """
        if not primary_agents and not dependent_agents:
            return

        print(
            f"\nRunning {len(primary_agents)} primary agents and {len(dependent_agents)} dependent agents..."
        )

        # Start all agents as concurrent tasks
        primary_tasks = [asyncio.create_task(agent.run()) for agent in primary_agents]
        dependent_tasks = [
            asyncio.create_task(agent.run()) for agent in dependent_agents
        ]

        try:
            # Wait for primary agents (e.g., customers) to complete
            print(f"Waiting for {len(primary_agents)} primary agents to complete...")
            await asyncio.gather(*primary_tasks)
            print("All primary agents completed")

            # Signal dependent agents (e.g., businesses) to shutdown gracefully
            print(f"Signaling {len(dependent_agents)} dependent agents to shutdown...")
            for agent in dependent_agents:
                agent.shutdown()

            # Give agents a brief moment to process shutdown signal
            await asyncio.sleep(0.1)

            # Wait for dependent agents to complete graceful shutdown
            # (includes logger cleanup in agent on_will_stop hooks)
            await asyncio.gather(*dependent_tasks)
            print("All dependent agents shut down gracefully")

            # Brief final pause to ensure all cleanup is complete
            await asyncio.sleep(0.2)

        except Exception as e:
            # On any error, signal all agents to shutdown
            print(f"Error during execution: {e}")
            for agent in list(primary_agents) + list(dependent_agents):
                agent.shutdown()

            # Give agents time to process shutdown signal
            await asyncio.sleep(0.1)

            # Wait for all to shutdown, suppressing exceptions during cleanup
            await asyncio.gather(
                *primary_tasks, *dependent_tasks, return_exceptions=True
            )

            # Brief final pause for any remaining cleanup
            await asyncio.sleep(0.2)
            raise

    async def create_logger(self, name: str = __name__) -> MarketplaceLogger:
        """Create a logger connected to the marketplace.

        Args:
            name: Logger name

        Returns:
            MarketplaceLogger instance

        """
        if self._exit_stack is None:
            raise RuntimeError("AgentLauncher must be used as an async context manager")

        client = await self._exit_stack.enter_async_context(
            MarketplaceClient(self.base_url)
        )
        logger = MarketplaceLogger(name, client)
        return logger

    async def query_marketplace_state(self) -> MarketplaceState:
        """Query the current state of the marketplace.

        Returns:
            MarketplaceState with current marketplace information

        """
        async with MarketplaceClient(self.base_url) as client:
            # Get server health
            health = await client.health_check()

            # Get all registered agents
            agents: list[AgentProfile] = []
            offset = 0
            limit = 100
            has_more = True

            while has_more:
                agents_response = await client.agents.list(offset=offset, limit=limit)
                agents.extend(agents_response.items)
                has_more = agents_response.has_more or False
                offset += limit

            # Get available action protocols
            protocols = await client.actions.get_protocol()

            # Get recent logs
            logs_response = await client.logs.list(limit=10)

            return MarketplaceState(
                server_health=health,
                agents=agents,
                action_protocols=protocols.actions,
                recent_logs=logs_response.items,
            )

    async def __aenter__(self):
        """Async context manager entry."""
        self._exit_stack = AsyncExitStack()
        await self._exit_stack.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit."""
        if self._exit_stack is not None:
            await self._exit_stack.__aexit__(exc_type, exc_val, exc_tb)
            self._exit_stack = None
