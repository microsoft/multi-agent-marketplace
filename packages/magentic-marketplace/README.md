# Magentic Marketplace

A Python SDK for building and running agentic marketplace simulations.

## Features

- **Modular**: Swap protocols, agents, and databases easily.
- **Easy CLI**: Run any marketplace with dynamic protocol and agent loading
- **Flexible Database**: Bring-your-own-database, or use the provided SQLite implementation.
- **Built-in Auth**: JWT authentication and agent registration system
- **Comprehensive Logging**: Structured logging with marketplace state tracking

## Quick Start

### Installation

```bash
# Navigate to the repository
cd /path/to/agentic-economics/v2/magentic-marketplace

# Install dependencies and activate environment
uv sync --active
```

**VSCode Setup**: Add the package to your Python path by updating your VSCode settings:

1. Open VSCode settings (Cmd/Ctrl + ,)
2. Search for "python extra paths"  
3. Add: `/path/to/agentic-economics/v2/magentic_marketplace`

Or add to your `.vscode/settings.json`:

```json
{
    "python.analysis.extraPaths": [
        "agentic-economics/v2/magentic_marketplace"
    ]
}
```

### Run the example

Run the example via the provided CLI:

```bash
python -m magentic_marketplace \
  --protocol marketplace_example.protocol.MarketplaceProtocol \
  --agent marketplace_example.agents.GreeterAgent \
  --agent marketplace_example.agents.FetcherAgent
```

## Implementation Guide

To create your own marketplace, you need to implement three core components:

### 1. Actions

Actions are Pydantic models that define the structure of marketplace interactions:

```python
from typing import Literal
from magentic_marketplace.shared.models import BaseAction

class PlaceBid(BaseAction):
    """Place a bid on an item."""
    type: Literal["PlaceBid"] = "PlaceBid"
    item_id: str
    amount: float
    max_quantity: int = 1

class AcceptBid(BaseAction):
    """Accept a bid from another agent."""
    type: Literal["AcceptBid"] = "AcceptBid"
    bid_id: str
    quantity: int = 1
```

### 2. Protocol

Extend `BaseMarketplaceProtocol` to define your marketplace's rules:

```python
from typing import Annotated
from magentic_marketplace.protocol.base import BaseMarketplaceProtocol
from magentic_marketplace.shared.models import ActionExecutionResult
from pydantic import Field, TypeAdapter

# Create discriminated union for type-safe action handling
AuctionAction = Annotated[PlaceBid | AcceptBid, Field(discriminator="type")]
AuctionActionAdapter = TypeAdapter(AuctionAction)

class AuctionProtocol(BaseMarketplaceProtocol):
    def get_actions(self):
        """Define available actions in this marketplace."""
        return [PlaceBid, AcceptBid]

    async def execute_action(self, *, agent, action, database):
        """Execute action with Pydantic discriminated union."""
        # Parse action into discriminated union - TypeAdapter handles validation
        parsed_action: AuctionAction = AuctionActionAdapter.validate_python(action.parameters)

        if isinstance(parsed_action, PlaceBid):
            # Validate bid amount
            if parsed_action.amount <= 0:
                return ActionExecutionResult(
                    content="Bid amount must be positive",
                    is_error=True
                )

            # Store bid in database
            await self._store_bid(agent.id, parsed_action, database)

            return ActionExecutionResult(
                content=f"Bid placed: ${parsed_action.amount} for {parsed_action.max_quantity}x {parsed_action.item_id}"
            )

        elif isinstance(parsed_action, AcceptBid):
            # Type-safe access to acceptance fields
            return await self._handle_bid_acceptance(agent.id, parsed_action, database)

    async def _store_bid(self, agent_id: str, bid: PlaceBid, database):
        """Custom helper method for storing bids."""
        # Implementation details...
        pass

    async def _handle_bid_acceptance(self, agent_id: str, acceptance: AcceptBid, database):
        """Handle bid acceptance with full type safety."""
        # Implementation details...
        return ActionExecutionResult(content=f"Accepted bid {acceptance.bid_id}")
```

### 3. Agents

Extend `BaseAgent` to implement agent strategies:

```python
from magentic_marketplace.agent.base import BaseAgent

class BuyerAgent(BaseAgent):
    def __init__(self, server_url: str, name: str, budget: float = 1000.0):
        super().__init__(server_url, name)
        self.budget = budget

    async def _run(self):
        """Implement your agent's strategy."""
        # Get available items
        items = await self._discover_items()

        for item in items:
            if self._should_bid(item):
                bid_amount = self._calculate_bid(item)

                result = await self.execute_action(
                    PlaceBid(
                        item_id=item.id,
                        amount=bid_amount,
                        max_quantity=1
                    )
                )

                if not result.is_error:
                    self.budget -= bid_amount

    async def _discover_items(self):
        """Find items to bid on."""
        # Query database for available items
        # Implementation details...
        pass

    def _should_bid(self, item) -> bool:
        """Decide whether to bid on an item."""
        return item.starting_price <= self.budget * 0.1

    def _calculate_bid(self, item) -> float:
        """Calculate bid amount."""
        return item.starting_price * 1.05  # Bid 5% above starting price

class SellerAgent(BaseAgent):
    async def _run(self):
        """List items and respond to bids."""
        # Your selling strategy here
        pass
```

## CLI Reference

### Basic Usage

```bash
python -m magentic_marketplace --protocol MODULE.PROTOCOL --agent MODULE.AGENT [OPTIONS]
```

### Arguments

| Argument | Required | Description | Example |
|----------|----------|-------------|---------|
| `--protocol` | Yes | Module path to protocol class | `my_market.AuctionProtocol` |
| `--agent` | Yes | Module path to agent class (repeatable) | `my_agents.BuyerAgent` |
| `--host` | No | Server host (default: 127.0.0.1) | `0.0.0.0` |
| `--port` | No | Server port (default: 8000) | `9000` |
| `--database` | No | SQLite database path (default: marketplace.db) | `auction.db` |

### Database Handling Flags (Mutually Exclusive)

| Flag | Description | Use Case |
|------|-------------|----------|
| `--db-exists-continue` | Continue with existing database | Resume previous session |
| `--db-exists-delete` | Delete existing database | Always start fresh |
| `--db-exists-exit` | Exit if database exists | Safety check |

### Examples

```bash
# Development - interactive database handling
python -m magentic_marketplace \
  --protocol auction.protocol.AuctionProtocol \
  --agent auction.agents.BuyerAgent \
  --agent auction.agents.SellerAgent

# Production - automated deployment
python -m magentic_marketplace \
  --protocol trading.HighFrequencyProtocol \
  --agent trading.MarketMakerAgent \
  --agent trading.ArbitrageAgent \
  --host 0.0.0.0 \
  --port 8080 \
  --database /data/trading.db \
  --db-exists-continue

# Testing - always fresh state
python -m magentic_marketplace \
  --protocol test.TestProtocol \
  --agent test.TestAgent \
  --database test.db \
  --db-exists-delete
```

## Advanced Features

### Database Queries

Type-safe, composable database queries:

```python
from magentic_marketplace.database.sqlite import queries

# Find all failed actions by a specific agent
query = (queries.actions.by_agent(agent_id) &
         queries.actions.result_is_error())

failed_actions = await database.actions.find(query)

# Find recent high-value bids using action class
query = (queries.actions.action(PlaceBid) &
         queries.actions.parameter("amount", 100, operator=">="))

high_bids = await database.actions.find(
    query,
    DbRangeQueryParams(limit=10, after=one_hour_ago)
)

# Find all bid acceptances for a specific item
query = (queries.actions.action(AcceptBid) &
         queries.actions.parameter("bid_id", "bid_123"))

acceptances = await database.actions.find(query)
```

### Logging Integration

Built-in structured logging that writes to both standard Python logging and the marketplace database:

```python
from magentic_marketplace.logger import MarketplaceLogger

# In your protocol or agent
logger = MarketplaceLogger("auction_protocol", client)

# Async methods wait for log to be stored in database
await logger.ainfo("Auction started", {"auction_id": auction.id})

# Fire-and-forget methods log immediately to Python logger, database write is queued
logger.info("Auction started", {"auction_id": auction.id})
```

### State Monitoring

Query marketplace state at runtime:

```python
from magentic_marketplace.launcher import MarketplaceLauncher

launcher = MarketplaceLauncher(protocol, database_factory)
await launcher.start_server()

# Get current state
state = await launcher.query_marketplace_state()
print(f"Active agents: {len(state.agents)}")
print(f"Available actions: {[a.name for a in state.action_protocols]}")
```

## Architecture

The marketplace follows a clean, layered architecture:

- **Agents** only interact through the client API (no direct server/database access)
- **Protocol** contains all business logic (server is just infrastructure)
- **Server** orchestrates but doesn't define marketplace rules
- **Database** provides type-safe, queryable persistence

## Database Persistence

The marketplace automatically tracks and persists all activity regardless of your protocol implementation:

### Automatically Saved Data

| Data Type | What's Saved | When | Use Cases |
|-----------|--------------|------|-----------|
| **Agent Registration** | Agent metadata, unique ID, registration timestamp | On agent registration/re-registration | Agent discovery, authentication, audit trails |
| **Action Execution** | Full action request, result, executing agent, timestamp | Every action execution | Analysis, replay, debugging, protocol optimization |
| **Logs** | Structured log entries with level, content, metadata | When using MarketplaceLogger | Monitoring, debugging, compliance, analytics |

### Agent Data Structure

```python
# Stored in agents table
{
    "id": "agent_uuid",
    "created_at": "2024-01-15T10:30:00Z",
    "agent": {
        "id": "agent_uuid",
        "name": "BuyerAgent-001",
        "metadata": {
            "budget": 1000.0,
            "strategy": "conservative",
            # Any custom fields from your agent
        }
    }
}
```

### Action Execution Records

```python
# Stored in actions table
{
    "id": "action_uuid",
    "created_at": "2024-01-15T10:31:15Z",
    "agent_id": "agent_uuid",
    "action_request": {
        "name": "PlaceBid",
        "parameters": {
            "type": "PlaceBid",
            "item_id": "item_123",
            "amount": 50.0,
            "max_quantity": 2
        }
    },
    "action_result": {
        "content": "Bid placed successfully",
        "is_error": false,
        "metadata": {"bid_id": "bid_456"}
    }
}
```

### Query Historical Data

Access all this data through type-safe queries:

```python
# All actions by an agent
agent_actions = await database.actions.find(
    queries.actions.by_agent("agent_uuid")
)

# Recent errors across all agents
recent_errors = await database.actions.find(
    queries.actions.result_is_error(),
    DbRangeQueryParams(after=one_hour_ago)
)

# Specific action type with parameters
high_bids = await database.actions.find(
    queries.actions.action(PlaceBid) &
    queries.actions.parameter("amount", 100, operator=">=")
)
```

### Benefits

- **Complete Audit Trail**: Every marketplace interaction is recorded
- **Protocol Agnostic**: Works with any protocol implementation
- **Rich Analytics**: Query patterns, agent behavior, market dynamics
- **Debugging**: Full action replay and error analysis
- **Compliance**: Immutable record of all marketplace activity

## Examples

See the `marketplace_example/` directory for a complete working example with:
- Simple greeting protocol
- Greeter and Fetcher agents
- Full CLI integration
- Database queries
- Logging integration

Run it with:

```bash
python -m magentic_marketplace \
  --protocol marketplace_example.protocol.MarketplaceProtocol \
  --agent marketplace_example.agents.GreeterAgent \
  --agent marketplace_example.agents.FetcherAgent
```