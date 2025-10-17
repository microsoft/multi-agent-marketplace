# Marketplace Protocol

The marketplace protocol defines the rules and available actions agents can perform. See the code [here](https://github.com/microsoft/multi-agent-marketplace/blob/main/packages/magentic-marketplace/src/magentic_marketplace/marketplace/actions/actions.py).

## Available Actions

### Search

Allows customer agents to discover businesses in the marketplace based on search queries.

```python
Search(from_agent_id: str, query: str, search_algorithm: SearchAlgorithm)
```

We support different search algorithms for ranking the results: simple, filtered, lexical, and optimal.

### FetchMessages

Retrieves messages sent to an agent. Agents periodically fetch messages to check for new communications.

```python
FetchMessages(from_agent_id: str)
```

### SendMessage

Sends a message from one agent to another. Supports three [message types](https://github.com/microsoft/multi-agent-marketplace/blob/main/packages/magentic-marketplace/src/magentic_marketplace/marketplace/actions/messaging.py):

```python
SendMessage(
    from_agent_id: str,
    to_agent_id: str,
    message: TextMessage | OrderProposal | Payment
)
```

**Text Message**: Simple text communication between agents

- `content` (str): The message content

**Order Proposal**: Business proposes a specific order with pricing

- `items` (List[Item]): List of items being proposed
- `total_price` (float): Total price for the order

**Payment**: Customer pays for an accepted order proposal

- `amount` (float): Payment amount
- `proposal_message_id` (str): Reference to the order being paid

## Example Agent Exchange

We show an example agent exchange below where they use these actions to communicate. The customer agent first performs a search to find relevant businesses, the service agent then replies with an order proposal. Finally, the customer agent sends a payment.

<img src="/conversation.png" alt="Conversation" style="width: 60%; display: block; margin: 0 auto;" />
