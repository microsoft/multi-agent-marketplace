#!/usr/bin/env python3
"""Run marketplace experiments for position bias data folders."""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from magentic_marketplace.experiments.run_experiment import run_marketplace_experiment

# Configuration
NUM_RUNS_PER_FOLDER = 5

# Models to test - add/remove models here
MODELS = [
    {"provider": "openai", "model": "gpt-4.1"},
    {"provider": "openai", "model": "gpt-4o"},
    {"provider": "gemini", "model": "gemini-2.5-flash"},
    {"provider": "anthropic", "model": "claude-sonnet-4-5"},
]

# Qwen configuration + GPT-OSS-20B
# MODELS = [
#     {
#         "provider": "openai",
#         "model": "qwen3-4b",  # Shortened for database compatibility
#         "actual_model": "Qwen/Qwen3-4B-Instruct-2507",  # Actual model name for API
#         "base_url": "http://localhost:8001/v1",
#         "api_key": "dummy",
#     },
#     {
#         "provider": "openai",
#         "model": "qwen3-14b",  # Shortened for database compatibility
#         "actual_model": "Qwen/Qwen3-14B",  # Actual model name for API
#         "base_url": "http://localhost:8001/v1",
#         "api_key": "dummy",
#     },
#     {
#         "provider": "openai",
#         "model": "gpt-oss-20b",  # Shortened for database compatibility
#         "actual_model": "openai/gpt-oss-20b",  # Actual model name for API
#         "base_url": "http://localhost:8001/v1",
#         "api_key": "dummy",
#     },
# ]

DATA_FOLDERS = [
    "business_0001_first",
    "business_0001_second",
    "business_0001_third",
    "contractors_first",
    "contractors_second",
    "contractors_third",
]


async def main():
    """Run experiments for each position bias data folder."""
    load_dotenv()

    base_dir = Path("data/position_bias")
    export_dir = Path("paper_experiments/position/results")
    export_dir.mkdir(exist_ok=True, parents=True)

    for model_config in MODELS:
        provider = model_config["provider"]
        model = model_config["model"]

        # Set environment variables for this model
        os.environ["LLM_PROVIDER"] = provider
        os.environ["LLM_MODEL"] = model_config.get("actual_model", model)

        # Set base URL and API key if provided (for local models)
        if "base_url" in model_config:
            os.environ["OPENAI_BASE_URL"] = model_config["base_url"]
        if "api_key" in model_config:
            os.environ["OPENAI_API_KEY"] = model_config["api_key"]

        print(f"\n{'=' * 80}")
        print(f"Running experiments with {provider}/{model}")
        print(f"{'=' * 80}\n")

        for folder_name in DATA_FOLDERS:
            for run_num in range(NUM_RUNS_PER_FOLDER):
                run_number = run_num + 1
                clean_model = (
                    model.replace("-", "_").replace(".", "_").replace("/", "_")
                )
                experiment_name = f"pos_{folder_name}_{clean_model}_r{run_number}"
                data_dir = base_dir / folder_name
                db_filename = f"position_{folder_name}_{clean_model}_run{run_number}.db"
                db_path = export_dir / db_filename

                if db_path.exists():
                    print(f"Skipping {experiment_name} - already exists")
                    continue

                print(f"\nRunning: {experiment_name}")

                await run_marketplace_experiment(
                    data_dir=data_dir,
                    experiment_name=experiment_name,
                    search_algorithm="simple",
                    search_bandwidth=10,
                    customer_max_steps=100,
                    postgres_host="localhost",
                    postgres_port=5432,
                    postgres_password="postgres",
                    override=True,
                    export_sqlite=True,
                    export_dir=str(export_dir),
                    export_filename=db_filename,
                )


if __name__ == "__main__":
    asyncio.run(main())
