"""Validate the generated customers and businesses."""

import argparse
import json
import os
import random
import sys

import numpy as np
import yaml
from base import Business, Customer


def search_by_menu_items(
    businesses: dict[str, Business], items: list[str]
) -> dict[str, float]:
    """Return a dictionary of businesses that have ALL of the specified menu items (dictionary values are the price totals for the items)."""
    results: dict[str, float] = {}
    for b in businesses.values():
        total_price = 0.0
        has_all_items = True
        for item in items:
            if item in b.menu_features:
                total_price += b.menu_features[item]
            else:
                has_all_items = False
                break
        if has_all_items:
            results[b.id] = total_price
    return results


def get_stats(data: list[float]) -> dict[str, float]:
    """Return descriptive statistics for the given data, sufficient for box-and-whisker plots. Includes a bootstrap 95% confidence interval for the median."""
    np.median(data)

    # Bootstrap a 95% confidence interval for the median
    median_samples: list[float] = []
    for _ in range(10000):
        sample = random.choices(data, k=len(data))  # Sample with replacement
        median_samples.append(float(np.median(sample)))

    return {
        "median": float(np.median(data)),
        "median_ci_lower": float(np.percentile(median_samples, 2.5)),
        "median_ci_upper": float(np.percentile(median_samples, 97.5)),
        "q1": float(np.percentile(data, 25)),
        "q3": float(np.percentile(data, 75)),
        "min": min(data),
        "max": max(data),
    }


def main(data_dir: str, output_json: bool) -> None:
    """Generate various baseline utilities for the customers and businesses in the specified data directory."""
    sys.stderr.write(f"Computing baseline utilities for data in '{data_dir}'...\n")

    # Load the customers
    customers: dict[str, Customer] = {}
    for filename in os.listdir(os.path.join(data_dir, "customers")):
        if filename.endswith(".yaml") or filename.endswith(".yml"):
            with open(os.path.join(data_dir, "customers", filename)) as f:
                data = yaml.safe_load(f)
                customers[data["id"]] = Customer(**data)

    if len(customers) == 0:
        sys.stderr.write("No customers found.\n")
        sys.exit(1)
    print(f"Loaded {len(customers)} customers.")

    # Load the businesses
    businesses: dict[str, Business] = {}
    for filename in os.listdir(os.path.join(data_dir, "businesses")):
        if filename.endswith(".yaml") or filename.endswith(".yml"):
            with open(os.path.join(data_dir, "businesses", filename)) as f:
                data = yaml.safe_load(f)
                businesses[data["id"]] = Business(**data)

    if len(businesses) == 0:
        sys.stderr.write("No businesses found.\n")
        sys.exit(1)
    print(f"Loaded {len(businesses)} businesses.")

    # Samples of various baselines
    pick_any_baseline: list[float] = []
    pick_cheapest_baseline: list[float] = []
    pick_any_with_amenities_baseline: list[float] = []
    pick_optimal_baseline: list[float] = []

    # Run the experiment
    for _i in range(1000):
        pick_any_sum = 0.0
        pick_cheapest_sum = 0.0
        pick_any_with_amenities_sum = 0.0
        pick_optimal_sum = 0.0

        for c in customers.values():
            # Get a list of all matching businesses
            matching_businesses = search_by_menu_items(
                businesses, list(c.menu_features.keys())
            )

            # Get the lowest price
            lowest_price = min(matching_businesses.values())

            any_utilities: list[float] = []
            any_with_amenities_utilities: list[float] = []

            for business_id, total_price in matching_businesses.items():
                b = businesses[business_id]

                if all(b.amenity_features[a] for a in c.amenity_features):
                    # Business has all amenities the customer wants
                    utility = 2 * sum(c.menu_features.values()) - total_price
                    any_with_amenities_utilities.append(utility)
                    any_utilities.append(utility)
                    if total_price == lowest_price:
                        pick_cheapest_sum += utility
                else:
                    # Business does not have all amenities the customer wants
                    utility = -total_price
                    any_utilities.append(utility)
                    if total_price == lowest_price:
                        pick_cheapest_sum += utility

            # Sanity checks
            assert len(any_utilities) > 0, f"No matching businesses for customer {c.id}"
            assert len(any_with_amenities_utilities) > 0, (
                f"No matching businesses with amenities for customer {c.id}"
            )
            assert max(any_utilities) == max(any_with_amenities_utilities)

            # Accumulate the utilities
            pick_optimal_sum += max(any_utilities)
            pick_any_with_amenities_sum += random.choice(any_with_amenities_utilities)
            pick_any_sum += random.choice(any_utilities)

        # Make sure the baselines that should be constant are constant
        if len(pick_cheapest_baseline) > 0:
            assert pick_cheapest_baseline[0] == pick_cheapest_sum, (
                "Pick cheapest baseline should be constant"
            )

        if len(pick_optimal_baseline) > 0:
            assert pick_optimal_baseline[0] == pick_optimal_sum, (
                "Pick optimal baseline should be constant"
            )

        # Store the results
        pick_any_baseline.append(pick_any_sum)
        pick_cheapest_baseline.append(
            pick_cheapest_sum
        )  # Not strictly necessary, but keeps the list lengths consistent
        pick_any_with_amenities_baseline.append(pick_any_with_amenities_sum)
        pick_optimal_baseline.append(
            pick_optimal_sum
        )  # Not strictly necessary, but keeps the list lengths consistent

    # Print the results
    np.percentile(pick_any_baseline, [2.5, 97.5])
    np.percentile(pick_any_with_amenities_baseline, [2.5, 97.5])

    print("\nPick Any with Matching Menu Items:")
    pick_any_baseline_stats = get_stats(pick_any_baseline)
    for k, v in pick_any_baseline_stats.items():
        print(f"  {k}: {v:.2f}")

    print(
        f"\nPick the Cheapest with Matching Menu Items: Constant={pick_cheapest_baseline[0]:.2f}"
    )

    print("\nPick Any with Matching Items and Amenities:")
    pick_any_with_amenities_baseline_stats = get_stats(pick_any_with_amenities_baseline)
    for k, v in pick_any_with_amenities_baseline_stats.items():
        print(f"  {k}: {v:.2f}")

    print(f"\nPick Optimal: Constant={pick_optimal_baseline[0]:.2f}")

    if output_json:
        # Output a JSON file with the stats for each baseline
        results = {
            "pick_any_baseline": pick_any_baseline_stats,
            "pick_cheapest_baseline": {
                "constant": pick_cheapest_baseline[0],
            },
            "pick_any_with_amenities_baseline": pick_any_with_amenities_baseline_stats,
            "pick_optimal_baseline": {
                "constant": pick_optimal_baseline[0],
            },
        }

        with open(os.path.join(data_dir, "baseline_utilities.json"), "w") as f:
            json.dump(results, f, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "data_dir",
        type=str,
        help="Folder containing the data to validate.",
    )

    # flag arguments
    parser.add_argument(
        "--output-json",
        action="store_true",
        help="Write baseline statistics to baseline_utilities.json in the data directory.",
    )

    args = parser.parse_args()
    main(args.data_dir, args.output_json)
