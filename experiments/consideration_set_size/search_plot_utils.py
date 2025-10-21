"""Utility functions for creating search limit plots from CSV data."""

from pathlib import Path

import matplotlib.colors as mcolors
import pandas as pd
from matplotlib import pyplot as plt

FIG_SIZE = (8, 4.2)
DPI = 300
LABEL_FONT_SIZE = 14
TITLE_FONT_SIZE = 14
TICK_FONT_SIZE = 14
BASELINE_COLOR = "#2C3E50"

MODEL_STYLES = {
    "gpt-5": {
        "display_name": "GPT-5",
        "color": "#3498DB",
        "marker": "p",
    },
    "gpt-4.1": {
        "display_name": "GPT-4.1",
        "color": "#F39C12",
        "marker": "o",
    },
    "gpt-4o": {
        "display_name": "GPT-4o",
        "color": "#27AE60",
        "marker": "s",
    },
    "gemini-2.5-flash": {
        "display_name": "Gemini 2.5 Flash",
        "color": "#8E44AD",
        "marker": "d",
    },
    "claude-sonnet-4": {
        "display_name": "Claude Sonnet 4",
        "color": "#E74C3C",
        "marker": "^",
    },
}


def create_search_limit_plots(
    csv_files,
    welfare_type="customer",
    plot_key="Welfare",
    plot_label=None,
    hide_legend=False,
):
    """Create search limit welfare plots for each dataset."""
    for csv_file in csv_files:
        create_plot_from_csv(
            csv_file,
            welfare_type,
            plot_key,
            plot_label,
            hide_legend,
        )


def create_plot_from_csv(
    csv_file,
    welfare_type,
    plot_key,
    plot_label=None,
    hide_legend=False,
    transparent_legend=False,
):
    """Create welfare plot from a single CSV file."""
    # Convert to Path object if needed
    csv_file = Path(csv_file)

    df = pd.read_csv(csv_file)

    # Filter for the specified welfare type
    df_filtered = df[df["Welfare Type"] == welfare_type]

    if df_filtered.empty:
        print(f"No data found for welfare type '{welfare_type}' in {csv_file}")
        return

    # Group by Model and Limit to calculate means and standard errors from individual runs
    grouped = (
        df_filtered.groupby(["Model", "Limit"])[plot_key]
        .agg(["mean", "std", "count"])
        .reset_index()
    )
    print(grouped.keys())
    grouped["std_error"] = grouped["std"] / (grouped["count"] ** 0.5)

    # Print mean and std for each model and limit
    print(f"\nStatistics for {csv_file.name} ({welfare_type} {plot_key.lower()}):")
    for _, row in grouped.iterrows():
        print(
            f"Model: {row['Model']}, Limit: {row['Limit']}, "
            f"Mean: {row['mean']:.2f}, Std Dev: {row['std']:.2f}, "
            f"Std Error: {row['std_error']:.2f}, N: {int(row['count'])}"
        )

    # Add optimal welfare information (same for all rows with same limit)
    if plot_key == "Welfare":
        optimal_data = (
            df_filtered.groupby("Limit")["Welfare Optimal"].first().reset_index()
        )
        grouped = grouped.merge(optimal_data, on="Limit")

    # Set up matplotlib styling to match the reference
    plt.style.use("default")
    plt.rcParams.update(
        {
            "font.family": "serif",
        }
    )

    fig, ax = plt.subplots(figsize=FIG_SIZE)

    # Get unique models and sort search limits
    models = sorted(grouped["Model"].unique())

    # Plot line for each model
    default_styles = [
        {"color": "#606060", "marker": "^"},  # Medium-dark grey, triangle
        {"color": "#A0A0A0", "marker": "d"},  # Light grey, diamond
        {"color": "#303030", "marker": "v"},  # Very dark grey, triangle down
        {"color": "#909090", "marker": "p"},  # Light-medium grey, pentagon
    ]

    for i, model in enumerate(models):
        model_data = grouped[grouped["Model"] == model].copy()
        model_data = model_data.sort_values("Limit")

        # Get display name and style for this model
        if model in MODEL_STYLES:
            style = MODEL_STYLES[model]
            display_name = style["display_name"]
        else:
            # Use default styles cyclically for unknown models
            style = default_styles[i % len(default_styles)]
            display_name = model

        # Make error bars lighter by adjusting alpha in the color
        base_color = mcolors.to_rgba(style["color"])
        light_error_color = (*base_color[:3], 0.2)  # Same color, 40% opacity

        ax.errorbar(
            model_data["Limit"],
            model_data["mean"],
            yerr=model_data["std_error"],
            marker=style["marker"],
            linewidth=2,
            markersize=6,
            label=display_name,
            color=style["color"],
            ecolor=light_error_color,
            capsize=3,
            capthick=1,
            elinewidth=1,
        )

    # Plot optimal welfare line (assuming it's constant across limits)
    limits = sorted(grouped["Limit"].unique())

    if plot_key == "Welfare":
        optimal_value = grouped["Welfare Optimal"].iloc[0]
        ax.plot(
            limits,
            [optimal_value] * len(limits),
            color=BASELINE_COLOR,
            linestyle="--",
            linewidth=2,
            label="Optimal",
            alpha=0.8,
        )

    # Styling
    ax.set_xlabel("Search Limit", fontsize=LABEL_FONT_SIZE)
    ax.set_ylabel(f"Mean {plot_label}", fontsize=LABEL_FONT_SIZE)

    # # Center the y-axis label vertically
    # ax.yaxis.set_label_coords(-0.075, 0.4)

    # Set x-axis ticks to align precisely with data values
    ax.set_xticks(limits)

    # Add custom labels with space before "5" to prevent overlap with "3"
    tick_labels = [str(limit) if limit != 5 else " 5" for limit in limits]
    ax.set_xticklabels(tick_labels)

    ax.tick_params(axis="both", labelsize=TICK_FONT_SIZE)

    # Add legend in top left corner, positioned with coordinates
    # Reorder handles and labels to put Optimal first, then models
    handles, labels = ax.get_legend_handles_labels()

    # Find optimal index and reorder
    optimal_idx = labels.index("Optimal") if "Optimal" in labels else -1
    if optimal_idx != -1:
        # Move Optimal to front
        handles = [handles[optimal_idx]] + [
            h for i, h in enumerate(handles) if i != optimal_idx
        ]
        labels = [labels[optimal_idx]] + [
            lab for i, lab in enumerate(labels) if i != optimal_idx
        ]

    if not hide_legend:
        fig.legend(
            handles,
            labels,
            loc="upper left",
            bbox_to_anchor=(0.0, 0.98),
            ncol=3,
            frameon=True,
            facecolor="white",
            edgecolor="white",
            framealpha=0.15,
            columnspacing=1.5,
            fontsize=LABEL_FONT_SIZE,
        )

    # Remove top and right spines to match reference style
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # Set grid
    ax.set_axisbelow(True)

    plt.tight_layout(rect=[0, 0, 1, 0.82])

    # Save the plot with a descriptive name based on the CSV file
    output_name = f"{csv_file.stem}_{'_'.join(plot_key.split(' '))}.png"
    output_path = Path(output_name)
    plt.savefig(output_path, dpi=DPI, bbox_inches="tight")
    print(f"Plot saved as: {output_path}")
    plt.close()

    return output_path
