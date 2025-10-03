# Text-Only Protocol Cookbook

Think of this like building a simple chat app for AI agents. This minimal protocol demonstrates the core components needed to create a custom marketplace protocol - just message sending and receiving.

## What You'll Build

A PDF proofreading system where a Writer agent extracts text from a PDF, sends it to a Proofreader agent who uses an LLM to correct errors, and returns the corrections. All coordination happens through two simple message-passing actions.

## Quick Start

```bash
# 1. Install dependencies
uv sync --extra cookbook

# 2. Configure LLM (choose one provider)
export LLM_PROVIDER=anthropic
export ANTHROPIC_API_KEY=your-key-here
export LLM_MODEL=claude-3-5-sonnet-20241022

# Or use OpenAI
# export LLM_PROVIDER=openai
# export OPENAI_API_KEY=your-key-here
# export LLM_MODEL=gpt-4

# 3. Run the example
uv run python cookbook/text_only_protocol/example/run_example.py path/to/document.pdf

# 4. Run tests
uv run pytest cookbook/text_only_protocol/tests/ -v
```

**What happens:** Writer agent sends PDF text → Proofreader agent uses LLM to correct it → Writer receives corrections. Both agents coordinate using only `SendTextMessage` and `CheckMessages` actions.

## How It Works

Think of message sending like mailing letters. An agent writes a message, the protocol checks the recipient address exists, stores it in a mailbox (database), and the recipient retrieves it later.

### Message Flow Example

```
Writer              Protocol              Database           Proofreader
  |                     |                      |                   |
  |--SendMessage------->|                      |                   |
  | (PDF text)          |--Validate recip----->|                   |
  |                     |<--Proofreader OK-----|                   |
  |                     |--Auto-persist------->|                   |
  |<--Success-----------|                      |                   |
  |                     |                      |                   |
  |                     |                      |<--CheckMessages---|
  |                     |<--Query messages-----|                   |
  |                     |--Return PDF text---->|                   |
  |                     |                      |---PDF text------->|
  |                     |                      |                   |
  |                     |<--SendMessage--------|                   |
  |                     | (corrections)        |                   |
  |                     |--Auto-persist------->|                   |
  |                     |--Success------------>|                   |
  |                     |                      |                   |
  |<--CheckMessages-----|                      |                   |
  |--Query messages---->|                      |                   |
  |<--Corrections-------|                      |                   |
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

### Auto-Persistence

Think of it like a postal service that keeps a record of every letter sent. The platform automatically saves all actions to the database before handlers execute.

When Writer sends a message:
1. Platform receives the `SendTextMessage` action
2. Platform saves it to the actions table (auto-persist)
3. Platform calls your handler to validate business logic
4. Handler checks if Proofreader exists and returns success/error

This means handlers validate business logic, not data persistence. Messages are queryable from the actions table without writing separate persistence code.

**Why this matters:** You can build complex message-based workflows without writing any database code. The protocol handles all message storage automatically.

### Composable Queries

Combine filters to find specific data:
```python
# Find all messages sent to the proofreader
query = to_agent("proofreader") & action_type("send_text_message")

# Find messages from writer to proofreader
query = to_agent("proofreader") & from_agent("writer") & action_type("send_text_message")
```

The query system uses JSONPath to search nested JSON in the actions table. See `database/queries.py` for details on the path syntax.

**Why this matters:** You can query message history without SQL. The composable query syntax makes it easy to filter actions by recipient, sender, type, or any field in the action data.

### Error Handling

Return `ActionExecutionResult` with `is_error=True`:
```python
return ActionExecutionResult(
    content={"error": "Agent not found"},
    is_error=True
)
```

## Building Your Own Protocol

This example shows the minimal protocol structure. To build your own:

1. **Define your actions** in `actions.py` - What can agents do?
2. **Create handlers** in `handlers/` - What happens when agents perform those actions?
3. **Wire it up** in `protocol.py` - Route actions to handlers
4. **Add queries** (optional) in `database/queries.py` - Make it easy to find data

**Example use cases:**
- Task assignment and completion system
- Auction or bidding protocol
- Multi-agent negotiation
- Request/response workflows

## Learn More

- `tests/test_text_protocol.py`: Testing patterns for protocols
- `example/agents.py`: WriterAgent and ProofreaderAgent implementations
- `example/run_example.py`: How to launch marketplace with custom protocol
- `packages/magentic-marketplace/src/magentic_marketplace/marketplace/protocol/`: Full-featured marketplace protocol with listings, negotiations, and contracts
