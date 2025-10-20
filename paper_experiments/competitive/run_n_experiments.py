#!/usr/bin/env python3
"""Run marketplace experiments for each data folder."""

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
#         "base_url": "http://localhost:8001/v1",  # Different port for 14B model
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
    "contractors_authority",
    "contractors_control",
    "contractors_loss_aversion",
    "contractors_prompt_injection_basic",
    "contractors_prompt_injection_strong",
    "contractors_social_proof",
    "mexican_authority",
    "mexican_control",
    "mexican_loss_aversion",
    "mexican_prompt_injection_basic",
    "mexican_prompt_injection_strong",
    "mexican_social_proof",
]


async def main():
    """Run experiments for each data folder."""
    load_dotenv()

    base_dir = Path("data/competitive_description")
    export_dir = Path("paper_experiments/competitive/results")
    export_dir.mkdir(exist_ok=True, parents=True)

    for model_config in MODELS:
        provider = model_config["provider"]
        model = model_config["model"]

        # Set environment variables for this model
        os.environ["LLM_PROVIDER"] = provider
        # Use actual_model if provided, otherwise use model
        os.environ["LLM_MODEL"] = model_config.get("actual_model", model)

        # Set base_url and api_key if provided
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
                experiment_name = f"{folder_name}_{clean_model}_run{run_number}"
                data_dir = base_dir / folder_name
                db_filename = f"{folder_name}_{clean_model}_run{run_number}.db"
                db_path = export_dir / db_filename

                if db_path.exists():
                    print(f"Skipping {experiment_name} - already exists")
                    continue

                print(f"\nRunning: {experiment_name}")

                await run_marketplace_experiment(
                    data_dir=data_dir,
                    experiment_name=experiment_name,
                    search_algorithm="lexical",
                    search_bandwidth=10,
                    customer_max_steps=100,
                    postgres_host="localhost",
                    postgres_port=5432,
                    postgres_password="postgres",
                    override=False,
                    export_sqlite=True,
                    export_dir=str(export_dir),
                    export_filename=db_filename,
                )


if __name__ == "__main__":
    asyncio.run(main())
