# LLM Provider
To make LLM calls, you need to set a `LLM_PROVIDER` and `LLM_MODEL`. Make a copy of [sample.env](./sample.env) and set your API keys, model provider, and model.

```
cp sample.env .env
```

## Open-Source Model Support by vLLM

Install vllm on NVIDIA GPU
```bash
uv pip install vllm
```

In one terminal, run
```bash
vllm serve 'Qwen/Qwen3-4B-Instruct-2507' --guided-decoding-backend outlines --tensor-parallel-size 1 --port 8001
then set the environment variables and run the experiment
```

You can run the below command to make sure that the vLLM is started correctly
```bash
curl http://localhost:8001/v1/models
```

After the vLLM is started correctly, set the below environment variables
```bash
export OPENAI_BASE_URL="http://localhost:8001/v1"
export LLM_PROVIDER="openai"
export OPENAI_API_KEY="dummy"
export LLM_MODEL="Qwen/Qwen3-4B-Instruct-2507"
export LLM_MAX_CONCURRENCY="64" # Limit max concurrent requests to the LLM provider.
magentic-marketplace run data/mexican_3_9 --search-algorithm optimal
```


# Database debugging
To see the postgres database, you can use `pgadmin` in your local browser. 

Go to [http://localhost:8080/](http://localhost:8080/).
- Account: admin@example.com
- Password: admin

# Reproducing Malicious and Position Bias Experiments

## Setup
1. Set up Docker and environment:
```bash
cp sample.env .env
# Add your API keys to .env (OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY)
docker compose up -d
```

2. Configure models in `run_n_experiments.py` files:
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

## Run Experiments

**Competitive experiments:**
```bash
python experiments/competitive/run_n_experiments.py
python experiments/competitive/analyze_results.py
python experiments/competitive/plot_results.py
```

**Malicious description experiments:**
```bash
python experiments/malicious/run_n_experiments.py
python experiments/malicious/analyze_results.py
python experiments/malicious/plot_results.py
```

**Position bias experiments:**
```bash
python experiments/position/run_n_experiments.py
python experiments/position/generate_position_data.py
python experiments/position/generate_proposal_data.py
python experiments/position/plot_position_bias.py
python experiments/position/plot_proposal_bias.py
```

Results are saved in `experiments/*/results/` directories.

# Troubleshooting
- With large simulations on linux, the default number of sockets might be taken up. You can see this value with `ulimit -n` and up it with `ulimit -n 60000`
