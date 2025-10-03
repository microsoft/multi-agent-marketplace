# Text-Only Protocol Cookbook

Think of this like building a simple chat app for AI agents. This minimal protocol demonstrates the core components needed to create a custom marketplace protocol - just message sending and receiving.

## Quick Start

Run the example to see it in action:

```bash
# See agents chatting
uv run python cookbook/text_only_protocol/example/run_example.py

# Run tests
uv run pytest cookbook/text_only_protocol/tests/ -v
```

The example shows two scenarios:
1. One agent sends messages, another reads and responds to them
2. Two agents have a conversation

## How It Works

Think of message sending like mailing letters. An agent writes a message, the protocol checks the recipient address exists, stores it in a mailbox (database), and the recipient retrieves it later.

### Message Flow

```
Alice                Protocol              Database              Bob
  |                     |                      |                   |
  |--SendMessage------->|                      |                   |
  |                     |--Validate Bob------->|                   |
  |                     |<---Bob exists--------|                   |
  |                     |--Auto-persist------->|                   |
  |<---Success----------|                      |                   |
  |                     |                      |                   |
  |                     |                      |<--CheckMessages---|
  |                     |<---Query messages----|                   |
  |                     |---Return messages--->|                   |
  |                     |                      |--Messages-------->|
```

### The Five Core Components

Every marketplace protocol has these pieces:

**1. Message Model** (`messaging.py`) - What data looks like:
```python
class TextMessage(BaseModel):
    type: Literal["text"] = "text"
    content: str = Field(description="Text content of the message")
```

**2. Actions** (`actions.py`) - What agents can do:
```python
class SendTextMessage(BaseAction):
    type: Literal["send_text_message"] = "send_text_message"
    from_agent_id: str
    to_agent_id: str
    message: TextMessage

class CheckMessages(BaseAction):
    type: Literal["check_messages"] = "check_messages"
    limit: int | None = None
```

**3. Handlers** (`handlers/`) - Business logic for each action:
- `send_message.py`: Validates recipient exists
- `check_messages.py`: Queries database, handles pagination

**4. Protocol** (`protocol.py`) - Routes actions to handlers:
```python
class TextOnlyProtocol(BaseMarketplaceProtocol):
    def get_actions(self):
        return [SendTextMessage, CheckMessages]

    async def execute_action(self, *, agent, action, database):
        if action.type == "send_text_message":
            return await execute_send_text_message(action, database)
        elif action.type == "check_messages":
            return await execute_check_messages(action, agent, database)
```

**5. Database Queries** (`database/queries.py`) - Find data easily:
```python
query = to_agent(agent_id) & action_type("send_text_message")
```

### File Structure

```
text_only_protocol/
├── messaging.py              # Message models
├── actions.py                # Action definitions
├── protocol.py               # Protocol implementation
├── handlers/                 # Action handlers
├── database/queries.py       # Database helpers
├── tests/                    # Unit tests
└── example/                  # Working example
```

## Key Concepts

### Understanding Auto-Persistence

**Critical concept**: The platform automatically saves all actions to the database **before** handlers execute.

Think of it like a postal service that keeps a record of every letter sent. When Alice sends a message:

1. Platform receives the `SendTextMessage` action
2. Platform saves it to the actions table (auto-persist)
3. Platform calls your handler to validate business logic
4. Handler checks if Bob exists and returns success/error
5. Action is already in database regardless of handler result

This means:
- Handlers validate business logic, not data persistence
- Messages are queryable from the actions table
- You don't write separate persistence code
- Failed validations still have a record in the database

### Actions Auto-Persist

The platform saves all actions before handlers run. Handlers only validate and return results. The action is already stored when your handler executes.

### Composable Queries

Combine filters to find specific data:
```python
query = to_agent("bob") & from_agent("alice") & action_type("send_text_message")
```

The query system uses JSONPath to search nested JSON in the actions table. See `database/queries.py` for details on the path syntax.

### Error Handling

Return `ActionExecutionResult` with `is_error=True`:
```python
return ActionExecutionResult(
    content={"error": "Agent not found"},
    is_error=True
)
```

## Troubleshooting

**Port already in use**: If you see "address already in use" errors, another process is using port 8000. Either stop that process or modify the launcher to use a different port.

**Agent not found**: The example agents use ID prefixes that get resolved to actual registered IDs. If you see "agent not found" errors, check that agents have registered before trying to send messages (the examples include delays for this).

**Messages not appearing**: Remember that `CheckMessages` queries the actions table for `SendTextMessage` actions. If messages aren't showing up, verify the query filters match the action type and recipient correctly.

## Learn More

- See `tests/test_text_protocol.py` for testing patterns
- See `example/agents.py` for agent implementation examples
- Compare with `SimpleMarketplaceProtocol` in `packages/magentic-marketplace/src/magentic_marketplace/marketplace/protocol/` for a full-featured protocol
