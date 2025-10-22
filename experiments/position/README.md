# Position Bias Experiments

## Setup
Configure models in `run_n_experiments.py`:
```python
# For closed-source models (default):
MODELS = [
    {"provider": "openai", "model": "gpt-4.1"},
    {"provider": "openai", "model": "gpt-4o"},
    {"provider": "gemini", "model": "gemini-2.5-flash"},
    {"provider": "anthropic", "model": "claude-sonnet-4-5"},
]

# For open-source models (comment out above, uncomment qwen models in the file)
```

## Run
```bash
python run_n_experiments.py
python generate_position_data.py
python generate_proposal_data.py
python plot_position_bias.py
python plot_proposal_bias.py
```

Results are saved in `results/`.
