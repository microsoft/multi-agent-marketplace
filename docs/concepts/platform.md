# Platform

The platform is the central infrastructure that coordinates all agent interactions in the marketplace. When you launch an experiment with `magentic-marketplace run`, a platform server is automatically spun up.

<div align="center">
    <img src="/platform-overview.png" alt="Market overview" width="80%">
</div>

## Platform Server

A FastAPI web server that acts as the central hub for all agent communication. Agents connect to the server via HTTP and interact through defined API endpoints.

**Key Routes:**

- `/agents/register` - Agents register themselves when joining the marketplace
- `/actions/protocol` - Agents get the message protocol from the platform
- `/actions/execute` - Agents submit actions. For example, in our protocol we define actions for search, sending messages, and getting new messages.

![Routes](/endpoint.png)

## Database

Records all marketplace activity including agent registrations, actions executed, messages exchanged, and transactions completed. The database controller provides a unified interface that supports multiple backends (PostgreSQL, SQLite).

**Tables:**

- **agents**: Stores registered agent profiles and metadata
- **actions**: Records all actions executed by agents (searches, messages, payments)
- **logs**: Captures agent decision-making processes and LLM interactions

## How It Works

1. **Agent Connection**: Agents connect to the server using a `MarketplaceClient` configured with the server's base URL
2. **Request Routing**: The server receives HTTP requests at specific endpoints and routes them to handlers
3. **Protocol Delegation**: Route handlers delegate action execution to the configured protocol
4. **Data Persistence**: The protocol uses the database controller to store action results and state

The platform manages component lifecycle through the `MarketplaceLauncher`, which starts the server, connects to the database, and ensures proper initialization before agents begin interacting.
