<div align="center">
<img src="docs/public/magentic-marketplace.svg" style="width: 80%" alt="Magentic Marketplace Logo">

_Simulation Environment for Agentic Marketplaces_

</div>

---

<div align="center">
<video src="https://github.com/user-attachments/assets/3e5da6c0-42d2-47f5-8b54-23d23a5f6d25" style="max-height: 450px;">
</video>
</div>

Magentic Marketplace is a Python SDK for running generative simulations of agentic markets.
You can configure business and customer agents that transact and then run simulations that evaluate the market's welfare.

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

   You can also run experiments from python scripts, see [experiments/example.py](experiments/example.py).

   View more CLI options with `magentic-marketplace --help`.

## More information

For more information on dev setup and debugging see [DEV.md](DEV.md).
