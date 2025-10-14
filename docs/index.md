<div align='center'>
    <img src="magentic-m.svg" alt="Magentic Marketplace Logo" width="200"/>
    <h1>Magentic Marketplace</h1>
</div>

Magentic Marketplace is a Python SDK for running generative simulations of agentic markets.
You can configure business and customer agents that transact and then run simulations that evaluate the market's welfare.

<!-- ![Magentic Marketplace](/.github/images/landing.png) -->

## Quick Start

1. Configure your environment

    ```bash
    # Clone the repo
    git clone https://github.com/microsoft/multi-agent-marketplace.git
    cd multi-agent-marketplace

    # Install dependencies with `uv`. Install from https://docs.astral.sh/uv/
    uv sync --all-extras
    source .venv/bin/activate

    # Configure environment variables in .env. Edit in favorite editor
    cp sample.env .env

    # Start the database server
    docker compose up -d
    ```

2. Run simulations and analyze the outputs

    ```bash
    # Run an experiment (experiment name is optional)
    magentic-marketplace run data/mexican_3_9 --experiment-name test_exp

    # Analyze the results
    magentic-marketplace analyze test_exp
    ```

    View more CLI options with `magentic-marketplace --help`.
