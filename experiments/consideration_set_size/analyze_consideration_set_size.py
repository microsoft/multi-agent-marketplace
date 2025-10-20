"""Analyze consideration set size experiments.

Take all analytics_results_* files in a directory and create a CSV with the results for each
dataset. CSV will have the form of

Model, Dataset, Limit, Run, Customer Utility
gpt-4.1, mexican_3_9, 1, 1, 63

"""

import argparse
import glob
import json
import os
from collections import defaultdict


def compile_results_csv(input_dir):
    """Compile results from JSON files into a CSV."""
    all_results: dict[str, list[dict]] = defaultdict(list)

    for filepath in glob.glob(
        os.path.join(input_dir, "analytics_results_search_limit_*.json")
    ):
        with open(filepath) as f:
            data = json.load(f)

            # Get the last part of the filename without extension
            filename = os.path.basename(filepath)
            parts = (
                filename.replace("analytics_results_search_limit_", "")
                .replace(".json", "")
                .split("_")
            )

            if len(parts) < 8:
                print(f"Filename {filename} does not match expected pattern.")
                continue

            # Get relevant variables from the filename.
            model = parts[0]
            dataset = "_".join(parts[1:4])
            limit = int(parts[5])
            run = int(parts[7])
            all_results[dataset].append(
                {
                    "model": model,
                    "dataset": dataset,
                    "limit": limit,
                    "run": run,
                    "customer_utility": data.get(
                        "total_marketplace_customer_utility", 0
                    ),
                }
            )

    for dataset, results in all_results.items():
        # Get the optimal welfare value for this dataset
        dataset_path = os.path.join(data_dir, dataset, "baseline_utilities.json")
        with open(dataset_path) as f:
            baseline_data = json.load(f)
            baseline_utility = baseline_data["pick_optimal_baseline"]["constant"]

            with open(f"output_{dataset}.csv", "w") as f:
                f.write(
                    "Model,Dataset,Welfare Type,Limit,Run,Welfare,Welfare Optimal\n"
                )
                for result in results:
                    model = result["model"]
                    dataset = result["dataset"]
                    limit = result["limit"]
                    run = result["run"]
                    customer_utility = result["customer_utility"]
                    f.write(
                        f"{model},{dataset},customer,{limit},{run},{customer_utility},{baseline_utility}\n"
                    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-dir",
        type=str,
        required=True,
        help="Directory with analytics_results_*.json files.",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        required=True,
        help="Directory with dataset files.",
    )
    args = parser.parse_args()

    input_dir = args.input_dir
    data_dir = args.data_dir

    compile_results_csv(input_dir)
