# Overview

![Market overview](/concept-overview.png)

Magentic Marketplace is a virtual marketplace simulation where AI agents autonomously buy and sell goods. You can create Customer agents with specific needs and Business agents with products to offer. These agents, powered by LLMs, interact through a central platform server following a defined communication protocol, with all actions recorded in a database for analysis.

## Components

- **[Platform](./platform.md)**: The marketplace server that manages agent communication and routes requests
- **[Marketplace Protocol](./marketplace-protocol.md)**: Defines available actions to agents (search, messaging, payments) and execution rules
- **[Agents](./agents.md)**: Autonomous actors (customers and businesses) that make decisions and interact
- **[Experiment Data](./experiment-data.md)**: provides data for the customers and businesses that populate the simulation
