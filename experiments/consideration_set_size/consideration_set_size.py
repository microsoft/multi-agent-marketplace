"""Run consideration set size experiments using the Magentic Marketplace package."""

import argparse
import asyncio
import os
from collections.abc import Sequence
from pathlib import Path

from dotenv import load_dotenv
from magentic_marketplace.experiments.run_analytics import run_analytics
from magentic_marketplace.experiments.run_experiment import run_marketplace_experiment

load_dotenv()

DEFAULT_SEARCH_LIMITS = [1, 2, 3]
MODEL_PROVIDER_MAP = {
    "gpt-4o": "openai",
    "gpt-4.1": "openai",
    "gpt-5": "openai",
    "gemini-2.5-flash": "gemini",
    "claude-sonnet-4-20250514": "anthropic",
    "Qwen/Qwen3-4B-Instruct-2507": "openai",
    "openai/gpt-oss-20b": "openai",
    "Qwen/Qwen3-14B": "openai",
}


def parse_search_limits(raw: str) -> list[int]:
    """Parse search limits supplied either as a string or a sequence of strings."""
    print(raw)
    if raw is None:
        return DEFAULT_SEARCH_LIMITS

    return [int(x) for x in raw.split(",") if x.strip().isdigit()]


def sanitize_model_name(model: str) -> str:
    """Remove characters not allowed in experiment identifiers."""
    return model.replace("-", "").replace(".", "")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run consideration set size experiments using Magentic Marketplace",
    )

    parser.add_argument(
        "--dataset",
        default=None,
        help="Path to the dataset directory (relative to repository root unless absolute)",
        required=True,
    )

    parser.add_argument(
        "--runs",
        type=int,
        default=5,
        help="Number of runs per search limit",
    )

    parser.add_argument(
        "--model",
        default=None,
        help="Model name used by agents",
    )

    parser.add_argument(
        "--model-provider",
        dest="model_provider",
        default=None,
        help="Optional override for the LLM provider",
    )

    parser.add_argument(
        "--search-limits",
        type=str,
        help="Comma separated list of search bandwidth limits",
    )

    return parser.parse_args(argv)


async def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and run the experiments."""
    args = parse_args(argv)

    search_limits = parse_search_limits(args.search_limits)

    model_provider = args.model_provider or os.environ.get("LLM_PROVIDER")
    if args.model is not None:
        model_provider = args.model_provider or MODEL_PROVIDER_MAP.get(args.model)
        os.environ["LLM_MODEL"] = args.model
        os.environ["LLM_PROVIDER"] = model_provider

    if model_provider == "gemini":
        print("Set LLM_MAX_CONCURRENCY to 8 for Gemini models.")
        os.environ["LLM_MAX_CONCURRENCY"] = "8"

    model_clean = sanitize_model_name(args.model)

    print("======================================")
    print("Running consideration set size experiments with the following parameters:")
    print(f"Dataset: {args.dataset}")
    print(
        f"Model: {args.model if args.model is not None else os.environ.get('LLM_MODEL')}"
    )
    print(f"Model Provider: {model_provider}")
    print(f"Search Limits: {' '.join(str(limit) for limit in search_limits)}")
    print(f"Runs per setting: {args.runs}")

    # Get only the last part of the dataset path
    dataset_clean = Path(args.dataset).name

    for search_limit in search_limits:
        print("\n======================================")
        print(f"Running with search limit: {search_limit}")

        for run_number in range(1, args.runs + 1):
            print(f"\nRun {run_number}/{args.runs}\n")

            # Check whether the run has already been completed
            cwd = Path.cwd()
            expected_output = cwd / (
                f"analytics_results_search_limit_{args.model}_{dataset_clean}_"
                f"limit_{search_limit}_run_{run_number}.json"
            )
            if expected_output.exists():
                print(
                    f"Run {run_number} with search limit {search_limit} already completed. Skipping."
                )
                continue

            experiment_name = (
                f"{model_clean}_{dataset_clean}_limit_{search_limit}_run_{run_number}"
            )
            if len(experiment_name) > 63:
                experiment_name = experiment_name[:63]
                print(
                    "Warning: Experiment name truncated to 63 characters for database schema compatibility."
                )

            print(f"Experiment Name: {experiment_name}")

            await run_marketplace_experiment(
                data_dir=Path(args.dataset),
                experiment_name=experiment_name,
                search_algorithm="lexical",
                search_bandwidth=search_limit,
                override=True,
                export_sqlite=True,
                customer_max_steps=100,
            )

            _ = await run_analytics(
                experiment_name, db_type="postgres", save_to_json=True
            )

            source = cwd / f"analytics_results_{experiment_name}.json"
            target = cwd / (
                f"analytics_results_search_limit_{args.model}_{dataset_clean}_"
                f"limit_{search_limit}_run_{run_number}.json"
            )

            source.rename(target)

    print("\nAll consideration set size experiments completed.")
    return 0


if __name__ == "__main__":
    asyncio.run(main())
