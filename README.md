# Magentic Marketplace

Magentic Marketplace is a Python DSK for building and running agentic marketplace simulations. 

![Magentic Marketplace](/.github/images/landing.png)

## Features

- Configure Business and Customer agents that transact in the marketplace
- Run test simulations and evaluate marketplace welfare

## Quick Start

### Installation

```bash
# Step 1: clone repo
git clone https://github.com/microsoft/multi-agent-marketplace.git

# Step 2
uv sync
```
Then configure a [LLM provider](./DEV.md) to make model calls.

### Run simulation

In one terminal spin up a database server with [docker](https://www.docker.com/get-started/):

```bash
docker compose up
```

Then start the simulation in another

```bash
uv run packages/magentic-marketplace/experiments/run_experiment.py example_data/mexican_3_9
```

## Paper
See our paper for more info: TODO