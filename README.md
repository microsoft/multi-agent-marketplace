# Magentic Marketplace

Magentic Marketplace is a Python SDK for building and running agentic marketplace simulations. 

![Magentic Marketplace](/.github/images/landing.png)

## Features

- Configure business and customer agents that transact in the marketplace
- Run test simulations and evaluate marketplace welfare

## Quick Start

### 1. Download the source code

```bash
git clone https://github.com/microsoft/multi-agent-marketplace.git
cd multi-agent-marketplace
```

### 2. Install the python dependencies with [`uv`](https://docs.astral.sh/uv/getting-started/installation/)

```bash
uv sync --all-extras
source .venv/bin/activate
```

### 3. Configure your environment variables

```bash
cp sample.env .env
```

Open `.env` in your favorite text editor. Fill out at least `LLM_PROVIDER`, `LLM_MODEL`, and the `<PROVIDER>_API_KEY` for that model.

e.g.

```bash
# .env
OPENAI_API_KEY="sk-..."
LLM_PROVIDER="openai" # or "anthropic" or "gemini"
LLM_MODEL="gpt-4.1"
```

### 4. Start a database server via [Docker](https://www.docker.com/get-started/)

```bash
docker compose up -d
```

### 5. Run an experiment

```bash
magentic-marketplace experiment data/mexican_3_9
```

### 6. Analyze the results

NOTE: This actually doesn't work yet!

```bash
magentic-marketplace analytics data/mexican_3_9
```

## Paper
See our paper for more info: TODO