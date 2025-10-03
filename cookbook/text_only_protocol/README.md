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
1. One agent sends messages, another reads them
2. Two agents have a conversation

## How It Works

Think of message sending like mailing letters. An agent writes a message, the protocol checks the recipient address exists, stores it in a mailbox (database), and the recipient retrieves it later.

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

## Adding a New Action

Here's how to extend the protocol with a `DeleteMessage` action:

**Step 1** - Define in `actions.py`:
```python
class DeleteMessage(BaseAction):
    type: Literal["delete_message"] = "delete_message"
    message_id: str
```

**Step 2** - Create handler in `handlers/delete_message.py`:
```python
async def execute_delete_message(action, database):
    # Your logic here
    return ActionExecutionResult(content={"status": "deleted"})
```

**Step 3** - Update `protocol.py`:
```python
def get_actions(self):
    return [SendTextMessage, CheckMessages, DeleteMessage]

async def execute_action(self, ...):
    # Add routing
    elif action.type == "delete_message":
        return await execute_delete_message(action, database)
```

**Step 4** - Add test in `tests/test_text_protocol.py`

## Key Concepts

**Actions auto-persist**: The platform automatically saves all actions to the database. Handlers just validate and return results.

**Composable queries**: Combine filters to find specific data:
```python
query = to_agent("bob") & from_agent("alice") & action_type("send_text_message")
```

**Error handling**: Return `ActionExecutionResult` with `is_error=True`:
```python
return ActionExecutionResult(
    content={"error": "Agent not found"},
    is_error=True
)
```

## Learn More

- See `tests/test_text_protocol.py` for testing patterns
- See `example/agents.py` for agent implementation examples
- Compare with `SimpleMarketplaceProtocol` in `packages/magentic-marketplace/src/magentic_marketplace/marketplace/protocol/` for a full-featured protocol
