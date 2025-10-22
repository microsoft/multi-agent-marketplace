#!/usr/bin/env python3
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

"""Create position bias plot from CSV data."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

BAR_COLOR = "lightgray"
FIG_SIZE = (10, 5)
DPI = 300
LABEL_FONT_SIZE = 12
TITLE_FONT_SIZE = 12
BASELINE_COLOR = "darkgray"


def create_position_bias_plot_from_csv(
    csv_file: str, models: list[str] | None = None
) -> None:
    """Create position bias plot from CSV data."""
    # Read the CSV data
    df = pd.read_csv(csv_file)

    if not models:
        models = sorted(df["model"].unique())

    # Create comparison plot
    create_comparison_plot(df, models)


def create_comparison_plot(df: pd.DataFrame, models: list[str]) -> Path:
    """Create a comparison plot showing position bias across multiple models."""
    plt.style.use("default")
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.size": 10,
            "axes.labelsize": 10,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
        }
    )

    # Create horizontal subplots - one per model with shared y-axis
    _, axes = plt.subplots(1, len(models), figsize=FIG_SIZE, sharey=True)
    if len(models) == 1:
        axes = [axes]

    for model_idx, model in enumerate(models):
        ax = axes[model_idx]
        model_df = df[df["model"] == model]
        total_runs = len(model_df)

        # Calculate selection rates for each restaurant order
        order_rates = []
        order_errors = []

        for order in [1, 2, 3]:
            if total_runs == 0:
                order_rates.append(0)
                order_errors.append(0)
                continue

            # Calculate selection rate for this restaurant order
            wins = len(model_df[model_df["restaurant_order"] == order])
            rate = wins / total_runs if total_runs > 0 else 0

            # Calculate 95% confidence interval
            if total_runs > 0:
                z = 1.96  # 95% confidence
                p = rate
                n = total_runs
                denominator = 1 + z**2 / n
                half_width = (
                    z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denominator
                )
                error = half_width
            else:
                error = 0

            order_rates.append(rate)
            order_errors.append(error)

        # Add horizontal dashed line at 33.3% (random chance)
        ax.axhline(y=0.333, color=BASELINE_COLOR, linestyle="--", linewidth=1, zorder=0)

        # Create bar chart for this model
        x = np.arange(3)  # Three positions
        ax.bar(
            x,
            order_rates,
            yerr=order_errors,
            color=BAR_COLOR,
            alpha=1.0,
            edgecolor="black",
            linewidth=1,
            capsize=3,
            error_kw={"color": "#333333", "linewidth": 1, "capthick": 1},
        )

        # Add value labels
        for j, (rate, error) in enumerate(zip(order_rates, order_errors, strict=False)):
            ax.text(
                j,
                rate + error + 0.02,
                f"{rate * 100:.1f}%",
                ha="center",
                va="bottom",
                fontweight="bold",
            )

        # Styling for each subplot
        display_name = {
            "gpt-4o": "GPT-4o",
            "gpt-4.1": "GPT-4.1",
            "gemini-2.5-flash": "Gemini-2.5-Flash",
            "qwen3_4b": "Qwen3-4B",
        }.get(model, model)
        ax.set_title(f"{display_name}", fontsize=TITLE_FONT_SIZE)
        ax.set_xticks(x)
        ax.set_xticklabels(["1st", "2nd", "3rd"], fontsize=LABEL_FONT_SIZE)

        # Only add x-label to middle subplot
        if model_idx == len(models) // 2:
            ax.set_xlabel("Position", fontsize=LABEL_FONT_SIZE, labelpad=10)
        ax.set_ylim(0, 1.1)
        ax.set_yticks([0.25, 0.5, 0.75, 1.0])

        # Only add y-label and tick labels to first subplot
        if model_idx == 0:
            ax.set_ylabel("Avg. Selection Rate", fontsize=LABEL_FONT_SIZE)
            ax.set_yticklabels(["25%", "50%", "75%", "100%"], fontsize=LABEL_FONT_SIZE)
            # Add "Random chance" text label
            ax.text(
                0.30,
                0.35,
                "Random",
                fontsize=10,
                color=BASELINE_COLOR,
                ha="right",
                style="italic",
                weight="bold",
            )

        ax.set_axisbelow(True)

        # Remove top and right spines
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    plt.tight_layout()

    # Save comparison plot
    output_path = Path(
        "paper_experiments/position/results/position_bias_comparison.png"
    )
    plt.savefig(output_path, dpi=DPI, bbox_inches="tight")
    print(f"Plot saved as: {output_path}")
    plt.close()

    return output_path


if __name__ == "__main__":
    file_path = (
        "paper_experiments/position/results/position_bias_results_all_models.csv"
    )
    # Read CSV to get all available models
    df = pd.read_csv(file_path)
    models = sorted(df["model"].unique())
    print(f"Found models: {models}")

    # Create comparison plot with all models
    create_comparison_plot(df, models)

    # Additionally create individual plots for each model from their model-specific CSVs
    for model in models:
        model_csv = Path(
            f"paper_experiments/position/results/position_bias_results_{model}.csv"
        )
        if model_csv.exists():
            print(f"\nCreating individual plot for {model}...")
            model_df = pd.read_csv(model_csv)
            create_comparison_plot(model_df, [model])
            # Copy to model-specific name
            import shutil

            output_path = Path(
                f"paper_experiments/position/results/position_bias_{model}.png"
            )
            shutil.copy(
                "paper_experiments/position/results/position_bias_comparison.png",
                output_path,
            )
            print(f"Saved: {output_path}")
