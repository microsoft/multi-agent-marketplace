<div align="center">
<img src="docs/public/magentic-marketplace.svg" style="width: 80%" alt="Magentic Marketplace Logo">

_Simulation Environment for Agentic Marketplaces_

</div>

---

<div align="center">
   <video src="https://github.com/user-attachments/assets/5b897387-d96c-4e7a-9bd2-b6c53eaeabb9" style="max-height: 450px;">
   </video>
</div>

Magentic Marketplace is a Python SDK for running simulations of agentic markets.
You can configure business and customer agents that transact and then run simulations that evaluate the market's welfare.

[**Learn more about Magentic Marketplace at our documentation website.**](https://microsoft.github.io/multi-agent-marketplace/)

## What can you do with this?

- **Evaluate LLM models** - Compare how different models (GPT-4, Claude, Gemini, local models) perform as marketplace agents
- **Test market designs** - Experiment with different search algorithms, communication protocols, and marketplace rules
- **Study agent behavior** - Measure welfare outcomes, identify biases, and test resistance to manipulation
- **Extend to new domains** - Adapt the framework beyond restaurants/contractors to other two-sided markets

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

## FAQ

- [How can I test my LLM?](https://microsoft.github.io/multi-agent-marketplace/usage/env.html)
- [How can I create a new protocol?]()
- [How can I access the log and evaluate?](https://microsoft.github.io/multi-agent-marketplace/usage/cli-analyze.html)
