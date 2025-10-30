"""Functional tests for MCP server demonstrating all marketplace actions."""

import asyncio
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from magentic_marketplace.marketplace.actions import (
    FetchMessages,
    FetchMessagesResponse,
    Search,
    SearchAlgorithm,
    SearchResponse,
    SendMessage,
    TextMessage,
)
from magentic_marketplace.marketplace.protocol import SimpleMarketplaceProtocol
from magentic_marketplace.marketplace.shared.models import (
    Business,
    BusinessAgentProfile,
    Customer,
    CustomerAgentProfile,
)
from magentic_marketplace.platform.client import MarketplaceClient
from magentic_marketplace.platform.database.sqlite import connect_to_sqlite_database
from magentic_marketplace.platform.server import MarketplaceServer
from magentic_marketplace.platform.shared.models import ActionExecutionResult
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import TextResourceContents
from pydantic import AnyUrl


@pytest.fixture
def business_agent_profile():
    """Return a business agent profile."""
    # Register business
    return BusinessAgentProfile.from_business(
        Business(
            id="sweet_bakery",
            name="Sweet Dreams Bakery",
            description="Artisan bakery specializing in custom birthday cakes and gluten-free options with delivery",
            rating=4.5,
            progenitor_customer="customer_000",
            menu_features={"birthday cake": 58.0},
            amenity_features={
                "delivery": True,
                "custom_decorations": True,
                "parking": False,
            },
            min_price_factor=0.8,
        )
    )


@pytest.fixture
def customer_agent_profile():
    """Return a customer agent profile."""
    return CustomerAgentProfile.from_customer(
        Customer(
            id="alice_customer",
            name="Alice Smith",
            request="Looking for a bakery with gluten-free birthday cakes",
            menu_features={"birthday cake": 60.0},
            amenity_features=["delivery", "custom_decorations"],
        )
    )


@dataclass
class MarketplaceServerInfo:
    """Info about the server fixture."""

    server: MarketplaceServer
    server_url: str
    db_path: str


@pytest_asyncio.fixture
async def marketplace_server(business_agent_profile: BusinessAgentProfile):
    """Create and manage marketplace server lifecycle."""
    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_file:
        db_path = temp_file.name

    def database_factory():
        return connect_to_sqlite_database(db_path)

    server = MarketplaceServer(database_factory, SimpleMarketplaceProtocol())

    # Start server task on port 8765
    server_task, shutdown_server = server.create_server_task(port=8765)

    # Give server time to start
    async with MarketplaceClient("http://localhost:8765") as client:
        exceptions: list[Exception] = []
        healthy = False
        for _ in range(30):
            try:
                await client.health_check()
                healthy = True
                break
            except Exception as e:
                exceptions.append(e)
                await asyncio.sleep(1)
        if not healthy:
            raise RuntimeError(
                "Server did not startup in time.\n\t"
                + "\n\t".join([str(e) for e in exceptions])
            )

        # register a business
        await client.agents.register(business_agent_profile)

    try:
        yield MarketplaceServerInfo(
            server=server,
            server_url="http://127.0.0.1:8765",
            db_path=db_path,
        )
    finally:
        # Cancel server task and suppress the expected CancelledError
        shutdown_server()
        try:
            await server_task
        except asyncio.CancelledError:
            # This is expected when cancelling - suppress it
            pass

        # Cleanup database file
        try:
            os.unlink(db_path)
        except Exception:
            pass


def create_mcp_client_session(
    marketplace_server: MarketplaceServerInfo,
    customer_agent_profile: CustomerAgentProfile,
):
    """Create MCP client session - not a fixture to avoid context issues."""
    server_url = marketplace_server.server_url

    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "magentic_marketplace_mcp",
            "--agent-profile",
            customer_agent_profile.model_dump_json(),
            "--marketplace-url",
            server_url,
        ],
    )

    return stdio_client(params)


@pytest.mark.asyncio
async def test_list_tools(
    marketplace_server: MarketplaceServerInfo,
    customer_agent_profile: CustomerAgentProfile,
):
    """Test that the server's listed tools are the three expected tools from the SimpleMarketplaceProtocol."""
    async with create_mcp_client_session(
        marketplace_server, customer_agent_profile
    ) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as client:
            result = await client.initialize()
            print(result.capabilities.model_dump_json(indent=2))
            result = await client.list_tools()

            tool_names = [tool.name for tool in result.tools]

            assert Search.get_name() in tool_names
            assert SendMessage.get_name() in tool_names
            assert FetchMessages.get_name() in tool_names
            assert len(tool_names) == 3


@pytest.mark.asyncio
async def test_end_to_end(
    marketplace_server: MarketplaceServerInfo,
    customer_agent_profile: CustomerAgentProfile,
):
    """Test the MCP server through all of its actions.

    1. Read the MCP server's agent-profile resource to determine our server-registered id
    2. Search for businesses
    3. Send a message to the first found business.
    4. Send a message to ourselves
    5. Fetch new messages (the one we sent to ourselves)
    """
    async with create_mcp_client_session(
        marketplace_server, customer_agent_profile
    ) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as client:
            await client.initialize()

            result = await client.read_resource(AnyUrl("resource://agent_profile"))
            assert result.contents
            assert isinstance(result.contents[0], TextResourceContents)
            assert result.contents[0].mimeType == "application/json"
            result = CustomerAgentProfile.model_validate_json(result.contents[0].text)
            assert result.model_dump_json(
                exclude={"id"}
            ) == customer_agent_profile.model_dump_json(exclude={"id"})

            from_agent_id = result.id

            result = await client.call_tool(
                Search.get_name(),
                Search(
                    query="Bakery", search_algorithm=SearchAlgorithm.SIMPLE, limit=1
                ).model_dump(),
            )
            assert not result.isError
            assert result.structuredContent is not None
            result = ActionExecutionResult.model_validate(result.structuredContent)
            assert result.is_error is False
            result = SearchResponse.model_validate(result.content)
            assert len(result.businesses) == 1

            to_agent_id = result.businesses[0].id

            result = await client.call_tool(
                SendMessage.get_name(),
                SendMessage(
                    from_agent_id=from_agent_id,
                    to_agent_id=to_agent_id,
                    message=TextMessage(
                        content=f"Hello, {result.businesses[0].business.name}!"
                    ),
                    created_at=datetime.now(UTC),
                ).model_dump(),
            )
            assert not result.isError
            assert result.structuredContent is not None
            result = ActionExecutionResult.model_validate(result.structuredContent)
            assert result.is_error is False

            note_to_self = "Note to self."
            result = await client.call_tool(
                SendMessage.get_name(),
                SendMessage(
                    from_agent_id=from_agent_id,
                    to_agent_id=from_agent_id,
                    message=TextMessage(content=note_to_self),
                    created_at=datetime.now(UTC),
                ).model_dump(),
            )
            assert not result.isError
            assert result.structuredContent is not None
            result = ActionExecutionResult.model_validate(result.structuredContent)
            assert result.is_error is False

            result = await client.call_tool(
                FetchMessages.get_name(), FetchMessages().model_dump()
            )
            assert not result.isError
            assert result.structuredContent is not None
            result = ActionExecutionResult.model_validate(result.structuredContent)
            assert result.is_error is False
            result = FetchMessagesResponse.model_validate(result.content)
            assert len(result.messages) == 1
            assert result.messages[0].message.type == "text"
            assert result.messages[0].message.content == note_to_self
