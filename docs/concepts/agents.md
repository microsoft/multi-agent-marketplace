# Agents

Agents are autonomous actors that make decisions and interact in the marketplace. Each agent has a profile, runs in a continuous loop, and executes actions through the platform.

## Marketplace Agents

For our marketplace, we created two basic agents that interact: a CustomerAgent and a BusinessAgent. Each agent inherits from a [BaseAgent](https://github.com/microsoft/multi-agent-marketplace/blob/main/packages/magentic-marketplace/src/magentic_marketplace/platform/agent/base.py) class which handles the agent loop to register the agent, then continuously run by calling the `step()` function.

### Agent Lifecycle

1. **Initialization**: Agent created with profile and server URL
2. **Registration**: Agent registers with marketplace server
3. **Active Loop**: Agent repeatedly executes `step()` method
4. **Shutdown**: Agent receives shutdown signal and cleanly disconnects

## [CustomerAgent](https://github.com/microsoft/multi-agent-marketplace/blob/main/packages/magentic-marketplace/src/magentic_marketplace/marketplace/agents/customer/agent.py)

The customer agent implements shopping behavior: searches for businesses, sends inquiries, evaluates proposals, and makes purchases.

```python
class CustomerAgent(BaseSimpleMarketplaceAgent):
    async def step(self):
        # Use LLM to decide next action
        action = await self._generate_customer_action()

        # Execute the chosen action
        if action:
            await self._execute_customer_action(action)
```

## [BusinessAgent](https://github.com/microsoft/multi-agent-marketplace/blob/main/packages/magentic-marketplace/src/magentic_marketplace/marketplace/agents/business/agent.py)

Implements service behavior: monitors for customer messages, responds to inquiries, creates order proposals, and processes payments.

```python
class BusinessAgent(BaseSimpleMarketplaceAgent):
    async def step(self):
        # Fetch new messages from customers
        messages = await self.fetch_messages()

        # Process and respond to each customer
        if messages:
            await self._handle_customer_messages(messages)
        else:
            await asyncio.sleep(self._polling_interval)
```
