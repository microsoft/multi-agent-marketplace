"""A MCP Server for accessing the Magentic Marketplace server."""

import logging
import os
from contextlib import AbstractAsyncContextManager
from types import TracebackType
from typing import Any

from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from magentic_marketplace.platform.client.client import MarketplaceClient
from magentic_marketplace.platform.shared.models import (
    ActionExecutionRequest,
    AgentProfile,
)
from mcp.server.lowlevel import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.models import InitializationOptions
from mcp.shared.message import SessionMessage
from mcp.types import (
    Resource,
    ResourcesCapability,
    ServerCapabilities,
    Tool,
    ToolsCapability,
)
from pydantic import AnyUrl

from ._version import __version__

logger = logging.getLogger(__name__)


class State:
    """State container for the MCP server."""

    def __init__(self, agent_profile: AgentProfile, marketplace_url: str):
        """Initialize the server state.

        Args:
            agent_profile: Agent profile for agent operating this server.
            marketplace_url: URL of the marketplace server.

        """
        logger.info(
            f"Initializing server state for agent {agent_profile.id} at {marketplace_url}"
        )
        self.tools: list[Tool] = []
        self.marketplace_url = marketplace_url
        self.agent_profile = agent_profile
        self.client: MarketplaceClient = MarketplaceClient(marketplace_url)
        logger.debug(f"Created marketplace client for {marketplace_url}")


class Lifespan(AbstractAsyncContextManager[State]):
    """Lifespan manager for the MCP server."""

    def __init__(self, agent_profile: AgentProfile, marketplace_url: str):
        """Initialize the lifespan manager.

        Args:
            agent_profile: Agent profile for the agent operating this server.
            marketplace_url: URL of the marketplace server.

        """
        logger.info(f"Initializing lifespan manager for agent {agent_profile.id}")
        self.state = State(
            agent_profile=agent_profile,
            marketplace_url=marketplace_url,
        )

    async def __aenter__(self) -> State:
        """Enter the async context and initialize the server state."""
        logger.info("Entering lifespan context, initializing server state")
        # Initialize marketplace client
        logger.debug("Connecting to marketplace client")
        try:
            await self.state.client.connect()
        except Exception as e:
            logger.exception(f"Failed to connect to marketplace client: {e}")
            raise

        logger.info(f"Registering agent {self.state.agent_profile.id} with marketplace")
        try:
            result = await self.state.client.agents.register(self.state.agent_profile)
        except Exception as e:
            logger.exception(
                f"Failed to register agent {self.state.agent_profile.id}: {e}"
            )
            raise

        # In case id changed
        if result.agent.id != self.state.agent_profile.id:
            logger.warning(
                f"Agent ID changed during registration: {self.state.agent_profile.id} -> {result.agent.id}"
            )
        self.state.agent_profile = result.agent
        logger.info(f"Successfully registered agent with ID: {result.agent.id}")
        # Set our authorization header for future requests
        self.state.client.set_token(result.token)
        logger.debug("Set authorization token for future requests")

        # Fetch action protocols from marketplace server
        logger.debug("Fetching action protocols from marketplace")
        try:
            await self._fetch_tools(self.state)
            if len(self.state.tools) == 0:
                logger.warning(
                    "No tools were loaded from marketplace - agent may have limited functionality"
                )
            logger.info(
                f"Successfully initialized server state with {len(self.state.tools)} tools"
            )
        except Exception as e:
            logger.exception(f"Failed to fetch tools from marketplace: {e}")
            raise

        return self.state

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        """Exit the async context and clean up resources."""
        logger.info("Exiting lifespan context, cleaning up resources")
        if exc_type:
            logger.error(f"Exception during lifespan: {exc_type.__name__}: {exc_value}")
        await self.state.client.close()
        logger.debug("Closed marketplace client connection")

    async def _fetch_tools(self, state: State) -> None:
        """Fetch action protocols from marketplace server and convert to MCP tools."""
        logger.debug("Fetching action protocols from marketplace server")
        # Get action protocols
        try:
            protocol_response = await state.client.actions.get_protocol()
            logger.debug(f"Retrieved {len(protocol_response.actions)} action protocols")
        except Exception as e:
            logger.exception(f"Failed to retrieve action protocols: {e}")
            raise

        # Convert ActionProtocol to MCP Tool
        try:
            state.tools = [
                Tool(
                    name=action.name,
                    description=action.description,
                    inputSchema=action.parameters,
                )
                for action in protocol_response.actions
            ]
            logger.info(
                f"Successfully converted {len(state.tools)} action protocols to MCP tools"
            )
            for tool in state.tools:
                logger.debug(f"Available tool: {tool.name} - {tool.description}")
                if not tool.description:
                    logger.warning(
                        f"Tool '{tool.name}' has no description - this may confuse users"
                    )
        except Exception as e:
            logger.exception(f"Failed to convert action protocols to MCP tools: {e}")
            raise


class MarketplaceMCPServer(Server[State, Any]):
    """MCP Server subclass that holds agent profile information."""

    def __init__(
        self,
        agent_profile: AgentProfile | dict[str, Any],
        marketplace_url: str | None = None,
    ):
        """Initialize the marketplace MCP server.

        Args:
            agent_profile: Agent profile for the agent operating this server.
            marketplace_url: URL of the marketplace server. If None, uses MARKETPLACE_URL env var or default.

        """
        logger.info("Initializing MarketplaceMCPServer")
        try:
            self.agent_profile = AgentProfile.model_validate(agent_profile)
        except Exception as e:
            logger.exception(f"Invalid agent profile provided: {e}")
            raise

        self.marketplace_url = marketplace_url or os.getenv(
            "MARKETPLACE_URL", "http://localhost:8000"
        )
        if not marketplace_url and not os.getenv("MARKETPLACE_URL"):
            logger.warning(
                "Using default marketplace URL (http://localhost:8000) - consider setting MARKETPLACE_URL env var"
            )
        logger.info(
            f"Server configured for agent {self.agent_profile.id} at {self.marketplace_url}"
        )

        def get_lifespan(server: Server[State, Any]):
            return Lifespan(self.agent_profile, self.marketplace_url)

        super().__init__(name="magentic-marketplace", lifespan=get_lifespan)
        logger.debug("Created base MCP server")

        # Register handlers
        logger.debug("Registering MCP handlers")
        self.list_tools()(self._list_tools)
        self.call_tool()(self._call_tool)
        self.read_resource()(self._read_resource)
        self.list_resources()(self._list_resources)
        logger.info("Successfully registered all MCP handlers")

    async def _list_tools(self) -> list[Tool]:
        """List all available tools fetched from marketplace server."""
        state = self.request_context.lifespan_context
        logger.info(f"Listing {len(state.tools)} available tools")
        for tool in state.tools:
            logger.debug(f"Tool: {tool.name}")
        return state.tools

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool by calling the marketplace server's execute_action endpoint."""
        logger.info(f"Executing tool: {name} with arguments: {arguments}")
        state = self.request_context.lifespan_context

        # Validate tool exists
        available_tools = [tool.name for tool in state.tools]
        if name not in available_tools:
            logger.error(f"Tool '{name}' not found. Available tools: {available_tools}")
            raise ValueError(f"Tool '{name}' not found")

        action_request = ActionExecutionRequest(
            name=name,
            parameters=arguments,
            metadata={"source": "mcp_server"},
        )
        logger.debug(f"Created action execution request for {name}")

        # Execute via the client's request method directly since we need name/parameters
        logger.debug(f"Sending action request to marketplace for {name}")
        try:
            result = await state.client.actions.execute_request(action_request)
            logger.info(f"Successfully executed tool {name}")
            logger.debug(f"Tool {name} result: {result}")
        except Exception as e:
            logger.exception(f"Tool execution failed for '{name}': {e}")
            raise

        return result.model_dump(mode="json")

    async def _list_resources(self):
        logger.debug("Listing available resources")
        resources = [
            Resource(
                name="agent_profile",
                uri=AnyUrl("resource://agent_profile"),
                description="The agent profile of the agent using this MCP Server, as registered with the Marketplace.",
                mimeType="application/json",
            )
        ]
        logger.debug(f"Available resources: {[r.name for r in resources]}")
        return resources

    async def _read_resource(self, resource: AnyUrl):
        logger.debug(f"Reading resource: {resource}")
        if resource.host == "agent_profile":
            logger.info("Returning agent profile resource")
            return [
                ReadResourceContents(
                    mime_type="application/json",
                    content=self.request_context.lifespan_context.agent_profile.model_dump_json(),
                )
            ]
        else:
            logger.error(f"Unrecognized resource: {resource}")
            raise ValueError(f"Unrecognized resource: {resource}")

    async def run(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        read_stream: MemoryObjectReceiveStream[SessionMessage | Exception],
        write_stream: MemoryObjectSendStream[SessionMessage],
        raise_exceptions: bool = False,
    ):
        """Run the server."""
        logger.info("Starting MCP server with initialization options")
        options = InitializationOptions(
            server_name="magentic-marketplace",
            server_version=__version__,
            capabilities=ServerCapabilities(
                resources=ResourcesCapability(),
                tools=ToolsCapability(),
            ),
        )
        logger.debug(
            f"Server options: name={options.server_name}, version={options.server_version}"
        )
        try:
            return await super().run(
                read_stream,
                write_stream,
                initialization_options=options,
                raise_exceptions=raise_exceptions,
                stateless=False,
            )
        except Exception as e:
            logger.exception(f"MCP server run failed: {e}")
            raise

    async def run_stdio(self, raise_exceptions: bool = False):
        """Run the server over stdio."""
        logger.info("Starting MCP server over stdio")
        from mcp.server.stdio import stdio_server

        try:
            async with stdio_server() as (read_stream, write_stream):
                logger.debug("Created stdio streams, running server")
                return await self.run(
                    read_stream, write_stream, raise_exceptions=raise_exceptions
                )
        except Exception as e:
            logger.exception(f"Failed to run MCP server over stdio: {e}")
            if raise_exceptions:
                raise
            logger.warning("Server stopped due to error")
