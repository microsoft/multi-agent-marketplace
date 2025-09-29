# Magentic Marketplace

Magentic Marketplace is a Python SDK for building and running agentic marketplace simulations. 

![Magentic Marketplace](/.github/images/landing.png)

## Features

- Configure business and customer agents that transact in the marketplace
- Run test simulations and evaluate marketplace welfare

## Quick Start

### Installation

```bash
git clone https://github.com/microsoft/multi-agent-marketplace.git

uv sync
```
Then configure a [LLM provider](./DEV.md) to make model calls.

### Run simulation

First, start a database server in the background with [docker](https://www.docker.com/get-started/):

```bash
docker compose up -d
```

Then run the simulation:

```bash
uv run packages/magentic-marketplace/experiments/run_experiment.py example_data/mexican_3_9
```

## Paper
See our paper for more info: TODO