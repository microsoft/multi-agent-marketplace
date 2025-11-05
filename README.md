# Magentic Marketplace

[Documentation](https://microsoft.github.io/multi-agent-marketplace/) | [Paper](https://arxiv.org/abs/2510.25779)


**Magentic Marketplace** is a Python framework for simulating AI-powered markets. Configure LLM-based buyer and seller agents, run realistic marketplace simulations, and measure economic outcomes like welfare, fairness, and efficiency.

<div align="center">

   <video src="https://github.com/user-attachments/assets/5b897387-d96c-4e7a-9bd2-b6c53eaeabb9" style="max-height: 450px;">
   </video>
</div>


## What can you do with this?

- **Evaluate LLM models** - Compare how different models (OpenAI, Claude, Gemini, local models) perform as marketplace agents
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
- [How can I access the log and evaluate?](https://microsoft.github.io/multi-agent-marketplace/usage/cli-analyze.html)

[**Check out the docs for more info.**](https://microsoft.github.io/multi-agent-marketplace/)

## Citation

If you use this work, please cite:

```
@misc{bansal-arxiv-2025,
      title={Magentic Marketplace: An Open-Source Environment for Studying Agentic Markets}, 
      author={Gagan Bansal and Wenyue Hua and Zezhou Huang and Adam Fourney and Amanda Swearngin and Will Epperson and Tyler Payne and Jake M. Hofman and Brendan Lucier and Chinmay Singh and Markus Mobius and Akshay Nambi and Archana Yadav and Kevin Gao and David M. Rothschild and Aleksandrs Slivkins and Daniel G. Goldstein and Hussein Mozannar and Nicole Immorlica and Maya Murad and Matthew Vogel and Subbarao Kambhampati and Eric Horvitz and Saleema Amershi},
      year={2025},
      eprint={2510.25779},
      archivePrefix={arXiv},
      primaryClass={cs.MA},
      url={https://arxiv.org/abs/2510.25779}, 
}
```
