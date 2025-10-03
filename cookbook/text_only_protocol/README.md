# Text-Only Protocol Cookbook

A minimal protocol showing how to build a multi-agent marketplace with just two actions: `SendTextMessage` and `CheckMessages`.

## What This Shows

Think of a freelance marketplace: post a job, get quotes, pick the best one. Here, a Writer broadcasts work to 3 Proofreaders, collects quotes, and assigns the task to the winner - all via simple text messages.

**Run the example:**
```bash
uv sync --extra cookbook
export OPENAI_API_KEY=your-key GEMINI_API_KEY=your-key
uv run python cookbook/text_only_protocol/example/run_example.py path/to/file.pdf
```

## How It Works

Four phases using two actions:

```
1. BROADCAST (1 → Many)
   Writer sends quote request to A, B, C

2. COLLECT BIDS (Many → 1)
   A, B, C send quotes back
   Writer uses CheckMessages to get all quotes

3. SELECT WINNER
   Writer's LLM picks best quote

4. ASSIGN WORK (1 → 1)
   Writer sends task to winner
   Winner returns result
```

The protocol handles routing and storage. You implement the market logic.

## Protocol Structure

Every protocol needs three things:

**1. Actions** (`actions.py`) - What agents can do
```python
class SendTextMessage(BaseAction):
    from_agent_id: str
    to_agent_id: str
    message: TextMessage

class CheckMessages(BaseAction):
    limit: int | None = None
```

**2. Handlers** (`handlers/`) - What happens when they act
- `send_message.py`: Validates recipient exists
- `check_messages.py`: Queries messages for the agent

**3. Protocol** (`protocol.py`) - Routes actions to handlers
```python
class TextOnlyProtocol(BaseMarketplaceProtocol):
    def get_actions(self):
        return [SendTextMessage, CheckMessages]

    async def execute_action(self, *, agent, action, database):
        # Route to appropriate handler
```

**Key feature:** The platform auto-saves all actions to the database. Your handlers just validate - messages are already stored and queryable.

## Building Your Own

To create a custom protocol:

1. Define actions in `actions.py`
2. Create handlers in `handlers/`
3. Wire them in `protocol.py`

**Other marketplace patterns:**
- Auctions with time limits
- Negotiation with counter-offers
- Task posting and claiming

See `example/agents.py` for the Writer and Proofreader implementation.
