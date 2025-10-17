#!/usr/bin/env python3
"""Plot LLM errors from results.txt"""

import re

import matplotlib.pyplot as plt


def parse_results(filename: str) -> list[tuple[int, int, int]]:
    """Parse results.txt and extract limit, run, and LLM error count.

    Args:
        filename: Path to results.txt

    Returns:
        List of tuples (limit, run, llm_error_count)
    """
    data = []

    with open(filename) as f:
        for line in f:
            # Skip the first line if it's not a data line
            if "marketplace_3_9" in line:
                continue

            # Extract limit and run number from schema name
            match = re.search(r"limit_(\d+)_run_(\d+)", line)
            if match:
                limit = int(match.group(1))
                run = int(match.group(2))

                # Extract LLM error count
                error_match = re.search(r"(\d+) LLM errors", line)
                if error_match:
                    llm_errors = int(error_match.group(1))
                    data.append((limit, run, llm_errors))

    return data


def plot_llm_errors(data: list[tuple[int, int, int]]):
    """Plot LLM errors by run.

    Args:
        data: List of tuples (limit, run, llm_error_count)
    """
    # Sort by limit then run
    data.sort(key=lambda x: (x[0], x[1]))

    # Create x-axis labels
    x_labels = [f"Limit {limit}\nRun {run}" for limit, run, _ in data]
    x_positions = list(range(len(data)))
    y_values = [llm_errors for _, _, llm_errors in data]

    # Create the plot
    plt.figure(figsize=(14, 6))
    plt.scatter(
        x_positions, y_values, s=100, alpha=0.7, color="red", edgecolors="black"
    )

    # Add text labels above each point with offset
    for x, y in zip(x_positions, y_values):
        # Calculate offset based on y-axis range to ensure consistent spacing
        y_range = max(y_values) - min(y_values)
        offset = y_range * 0.02 if y_range > 0 else 100
        plt.text(
            x,
            y + offset,
            str(y),
            ha="center",
            va="bottom",
            fontsize=9,
            fontweight="bold",
        )

    # Customize the plot
    plt.xlabel("Experiment Run", fontsize=12)
    plt.ylabel("Number of LLM Errors", fontsize=12)
    plt.title(
        "LLM Errors by Search Limit and Run Number", fontsize=14, fontweight="bold"
    )

    # Set x-axis ticks
    plt.xticks(x_positions, x_labels, rotation=45, ha="right", fontsize=9)

    # Add grid for better readability
    plt.grid(True, alpha=0.3, linestyle="--")

    # Adjust layout to prevent label cutoff
    plt.tight_layout()

    # Save the plot
    output_file = "llm_errors_plot.png"
    plt.savefig(output_file, dpi=300, bbox_inches="tight")
    print(f"Plot saved to: {output_file}")


if __name__ == "__main__":
    data = parse_results("results.txt")
    print(f"Parsed {len(data)} data points")
    plot_llm_errors(data)
