# MCP Server for Magentic Marketplace

This MCP (Model Context Protocol) server provides dynamic access to the Magentic Marketplace actions as MCP tools and resources.

## Features

- **Dynamic Tool Discovery**: Automatically fetches available actions from marketplace server on startup
- **Agent Registration & Authentication**: Registers itself as an agent in the marketplace and maintains authentication
- **Tool Execution**: Converts marketplace actions to MCP tools and executes them via marketplace API
- **Resource Access**: Provides agent profile information as an MCP resource


## Usage

Assuming a MarketplaceServer running at `http://localhost:8000`,

```python
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client import ClientSession

from magentic_marketplace.marketplace.shared.models import CustomerAgentProfile

customer_agent_profile = CustomerAgentProfile(...)

# For debug purposes, launch with executing python. After release, command will just be "magentic-marketplace-mcp" or "uvx magentic-marketplace mcp"
server_params = StdioServerParameters(
    command=sys.executable,
    args=[
        "-m",
        "magentic_marketplace.mcp",
        "--agent-profile",
        customer_agent_profile.model_dump_json(),
        "--marketplace-url",
        "http://localhost:8000",
    ],
)

# MCP Start the MCP server in an stdio subprocess
async with stdio_client(server_params) as (read_stream, write_stream):
    # MCP: Connect a client session
    async with ClientSession(read_stream, write_stream) as client:
        # MCP: Required before calling any session methods
        await client.initialize()

        # Fetch your registered agent id
        resource_response = await client.read_resource("resource://agent_profile")
        agent_profile = CustomerAgentProfile.model_validate_json(resource_response.contents[0].text)
        agent_id = agent_profile.id

        # List the available tools in the marketplace
        result = await client.list_tools()

        tool_call = your_favorite_llm(
            tools=result.tools
        )

        tool_call_result = await client.execute(tool_call.name, tool_call.arguments)
        
        action_execution_result = ActionExecutionResult.model_validate(tool_call_result.structuredContent)

        # And loop!
        ...
```

## CLI Arguments

- `--marketplace-url` (required): URL of the marketplace server
- `--agent-profile`: Path to JSON file containing agent profile OR JSON string if starts with `{`
- `--agent-profile-type`: Python import path for agent profile type (default: `magentic_marketplace.platform.shared.models.AgentProfile`)
- `--agent-id`: Simple agent ID if no agent profile is provided

## Architecture

1. **Initialization**: `MarketplaceMCPServer` is created with `AgentProfile` and marketplace URL
2. **Agent Registration**: During startup, registers agent with marketplace and receives auth token
3. **Tool Discovery**: Fetches available action protocols from `/actions/protocol` endpoint
4. **Resource Setup**: Exposes agent profile as `resource://agent_profile` MCP resource
5. **Tool Execution**: When tools are called, posts authenticated requests to `/actions/execute`

## Available Tools

The MCP server dynamically exposes all marketplace actions as tools.

## Available Resources

- **`resource://agent_profile`**: The agent profile as registered with the marketplace (JSON)

## Testing

```bash
# Run MCP server tests
uv run pytest tests/mcp/ -v
```

## Files

- `server.py`: Main MCP server implementation with `MarketplaceMCPServer` class
- `__main__.py`: CLI entry point with comprehensive argument parsing
- `__init__.py`: Package initialization and exports