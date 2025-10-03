# Text-Only Protocol Cookbook

A minimal marketplace protocol that supports only text messaging between agents.

Think of this protocol like a basic chat system for agents. It defines two simple operations: sending a text message and checking received messages. This example demonstrates the minimal components needed to create a functional marketplace protocol.

## What This Example Includes

- **Protocol Implementation**: A complete working protocol with two actions
- **Unit Tests**: Test suite showing how to verify your protocol works
- **Example Agents**: Three agent types demonstrating different use cases
- **Integration Runner**: Script to see the protocol in action

## Protocol Components

### Actions

The protocol supports two actions:

1. **SendTextMessage**: Send a text message to another agent
2. **CheckMessages**: Retrieve messages sent to your agent

### File Structure

```
text_only_protocol/
├── messaging.py              # TextMessage model
├── actions.py                # Action definitions and response models
├── protocol.py               # TextOnlyProtocol implementation
├── handlers/
│   ├── send_message.py      # SendTextMessage handler
│   └── check_messages.py    # CheckMessages handler
├── database/
│   └── queries.py           # Database query helpers
├── tests/
│   ├── conftest.py          # Test fixtures
│   └── test_text_protocol.py  # Unit tests
└── example/
    ├── agents.py            # Example agent implementations
    └── run_example.py       # Integration test runner
```

## Quick Start

### 1. Run Unit Tests

Verify the protocol works correctly:

```bash
uv run pytest cookbook/text_only_protocol/tests/ -v
```

You should see tests passing for:
- Sending messages successfully
- Handling invalid recipients
- Checking messages (empty, with content, pagination)
- Message isolation between agents

### 2. Run Example Agents

See the protocol in action with real agents:

```bash
uv run python cookbook/text_only_protocol/example/run_example.py
```

This runs two example scenarios:
1. **Greeter/Reader**: One agent sends messages, another receives them
2. **Conversation**: Two agents exchange messages back and forth

## How It Works

### Message Flow

Think of message sending like mailing a letter:

1. Agent creates a message with content
2. Protocol validates the recipient exists (like checking the address)
3. Message is stored in the database (delivered to mailbox)
4. Recipient checks their messages (opens mailbox)

### Protocol Components Explained

#### 1. Message Model (`messaging.py`)

Defines what a text message looks like:

```python
class TextMessage(BaseModel):
    type: Literal["text"] = "text"
    content: str = Field(description="Text content of the message")
```

#### 2. Actions (`actions.py`)

Defines what agents can do:

- `SendTextMessage`: Specifies sender, recipient, timestamp, and message
- `CheckMessages`: Specifies pagination options (limit, offset)
- Response models for returning results

#### 3. Handlers (`handlers/`)

Implements the business logic:

- `send_message.py`: Validates recipient exists, returns success
- `check_messages.py`: Queries database for messages, handles pagination

#### 4. Protocol (`protocol.py`)

Routes actions to appropriate handlers:

```python
class TextOnlyProtocol(BaseMarketplaceProtocol):
    def get_actions(self):
        return [SendTextMessage, CheckMessages]

    async def execute_action(self, *, agent, action, database):
        # Route to appropriate handler based on action type
```

#### 5. Database Queries (`database/queries.py`)

Provides composable filters for finding messages:

```python
query = to_agent(agent_id) & action_type("send_text_message")
```

## Example Agents

### GreeterAgent

Sends a fixed number of greeting messages to a target agent.

**Use case**: Testing message sending and message persistence.

```python
greeter = GreeterAgent(
    profile=alice_profile,
    server_url=launcher.server_url,
    target_agent_id="bob",
    message_count=3,
)
```

### ReaderAgent

Periodically checks for new messages and prints them.

**Use case**: Testing message retrieval and polling behavior.

```python
reader = ReaderAgent(
    profile=bob_profile,
    server_url=launcher.server_url,
    check_interval=1.0,
)
```

### ConversationAgent

Checks for messages and responds to them.

**Use case**: Testing bidirectional communication.

```python
alice = ConversationAgent(
    profile=alice_profile,
    server_url=launcher.server_url,
    peer_agent_id="bob",
    initial_message="Hi Bob, how are you?",
)
```

## Key Concepts

### 1. Actions Inherit from BaseAction

Actions are Pydantic models that define parameters and validation:

```python
class SendTextMessage(BaseAction):
    type: Literal["send_text_message"] = "send_text_message"
    from_agent_id: str
    to_agent_id: str
    message: TextMessage
```

### 2. Handlers Return ActionExecutionResult

Handlers process actions and return standardized results:

```python
return ActionExecutionResult(
    content=action.model_dump(mode="json"),
    is_error=False,
)
```

### 3. Database Auto-Persists Actions

The platform automatically stores all actions in the database. Handlers just validate and return results.

### 4. Queries Are Composable

Build complex filters by combining simple queries with `&`:

```python
query = to_agent(bob_id) & from_agent(alice_id) & action_type("send_text_message")
```

### 5. Protocol Routes Actions

The protocol class maps action types to handler functions:

```python
if action_type == "send_text_message":
    return await execute_send_text_message(parsed_action, database)
```

## Testing Strategy

### Unit Tests

Test individual actions in isolation using pytest fixtures:

- Create temporary database
- Register test agents
- Execute actions via client
- Verify database state

See `tests/test_text_protocol.py` for examples.

### Integration Tests

Run real agents communicating via the protocol:

- Start marketplace server
- Create agent instances
- Let agents interact
- Observe behavior

See `example/run_example.py` for examples.

## Extending the Protocol

To add a new action to this protocol:

1. **Define the action** in `actions.py`:
   ```python
   class DeleteMessage(BaseAction):
       type: Literal["delete_message"] = "delete_message"
       message_id: str
   ```

2. **Create a handler** in `handlers/delete_message.py`:
   ```python
   async def execute_delete_message(action, database):
       # Implementation
       return ActionExecutionResult(...)
   ```

3. **Update the protocol** in `protocol.py`:
   ```python
   def get_actions(self):
       return [SendTextMessage, CheckMessages, DeleteMessage]

   async def execute_action(self, *, agent, action, database):
       # Add routing for new action
       elif action_type == "delete_message":
           return await execute_delete_message(...)
   ```

4. **Add tests** in `tests/test_text_protocol.py`:
   ```python
   async def test_delete_message(test_agents_with_client):
       # Test the new action
   ```

## Common Patterns

### Validating Action Prerequisites

Check conditions before executing an action:

```python
target_agent = await database.agents.get_by_id(action.to_agent_id)
if target_agent is None:
    return ActionExecutionResult(
        content={"error": "Agent not found"},
        is_error=True,
    )
```

### Paginating Results

Use limit +1 pattern to check for more results:

```python
limit = action.limit + 1 if action.limit else None
results = await database.actions.find(query, RangeQueryParams(limit=limit))

has_more = False
if action.limit and len(results) > action.limit:
    results = results[:action.limit]
    has_more = True
```

### Filtering by Action Type

Combine query filters to find specific actions:

```python
query = (
    queries.to_agent(agent_id) &
    queries.action_type("send_text_message")
)
```

## Comparison with SimpleMarketplaceProtocol

This text-only protocol is a simplified version of `SimpleMarketplaceProtocol`:

| Feature | TextOnlyProtocol | SimpleMarketplaceProtocol |
|---------|------------------|---------------------------|
| Actions | 2 (send, check) | 3 (send, fetch, search) |
| Message types | 1 (text) | 3 (text, order, payment) |
| Validation | Basic recipient check | Order proposal validation |
| Use case | Learning/simple messaging | Full marketplace transactions |

The text-only protocol demonstrates the core concepts without the complexity of order processing and business logic.

## Next Steps

After understanding this example, you can:

1. Add more action types (edit message, delete message, etc.)
2. Add more message types (images, files, structured data)
3. Implement more complex validation logic
4. Add search or filtering capabilities
5. Create more sophisticated agent behaviors

See the full `SimpleMarketplaceProtocol` implementation in `packages/magentic-marketplace/src/magentic_marketplace/marketplace/protocol/` for a more complete example.
