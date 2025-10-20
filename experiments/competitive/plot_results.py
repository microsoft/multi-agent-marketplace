#!/usr/bin/env python3
"""Create plots for competitive description marketing experiments (separate by experiment type)."""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import t

# Read data
results_dir = Path("paper_experiments/competitive/results")
df = pd.read_csv(results_dir / "competitive_description_results_all_models.csv")

# Separate experiments by type
df["exp_type"] = df["condition"].apply(
    lambda x: "mexican" if "mexican" in x else "contractors"
)

# Get experiment type from command line or default to both
exp_types_to_plot = ["mexican", "contractors"]
if len(sys.argv) > 1:
    exp_type_arg = sys.argv[1].lower()
    if exp_type_arg in ["mexican", "contractors"]:
        exp_types_to_plot = [exp_type_arg]

# Configuration
configs = {
    "mexican": {
        "treatment": "Poblano Palate",
        "title": "Mexican Restaurant Marketing",
        "strategies": [
            "mexican_control",
            "mexican_authority",
            "mexican_social_proof",
            "mexican_loss_aversion",
            "mexican_prompt_injection_basic",
            "mexican_prompt_injection_strong",
        ],
    },
    "contractors": {
        "treatment": "Summit Residential Services",
        "title": "Contractors Marketing",
        "strategies": [
            "contractors_control",
            "contractors_authority",
            "contractors_social_proof",
            "contractors_loss_aversion",
            "contractors_prompt_injection_basic",
            "contractors_prompt_injection_strong",
        ],
    },
}

strategy_labels = {
    "mexican_control": "Control",
    "mexican_authority": "Authority",
    "mexican_social_proof": "Social Proof",
    "mexican_loss_aversion": "Loss Aversion",
    "mexican_prompt_injection_basic": "Prompt Inj.\n(Basic)",
    "mexican_prompt_injection_strong": "Prompt Inj.\n(Strong)",
    "contractors_control": "Control",
    "contractors_authority": "Authority",
    "contractors_social_proof": "Social Proof",
    "contractors_loss_aversion": "Loss Aversion",
    "contractors_prompt_injection_basic": "Prompt Inj.\n(Basic)",
    "contractors_prompt_injection_strong": "Prompt Inj.\n(Strong)",
}

# Plot each experiment type and model
for exp_type in exp_types_to_plot:
    exp_df = df[df["exp_type"] == exp_type]
    config = configs[exp_type]

    for model in exp_df["model"].unique():
        model_df = exp_df[exp_df["model"] == model].copy()
        clean_model = model.replace("-", "_").replace(".", "_")

        # Get businesses
        businesses = sorted(model_df["business_name"].unique())
        if config["treatment"] in businesses:
            businesses.remove(config["treatment"])
            businesses.insert(0, config["treatment"])

        # Calculate stats
        stats = (
            model_df.groupby(["condition", "business_name"])["payments_received"]
            .agg(["mean", "std", "count"])
            .reset_index()
        )
        strategies = [
            s for s in config["strategies"] if s in model_df["condition"].values
        ]

        # Setup plot
        plt.figure(figsize=(10, 6))
        ax = plt.gca()
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        # Plot bars
        x = np.arange(len(strategies))
        width = 0.8 / len(businesses)

        for i, biz in enumerate(businesses):
            means, cis = [], []
            for strat in strategies:
                row = stats[
                    (stats["condition"] == strat) & (stats["business_name"] == biz)
                ]
                if not row.empty:
                    mean_val = float(row["mean"].iloc[0])
                    std_val = float(row["std"].iloc[0])
                    n = float(row["count"].iloc[0])
                    ci = (t.ppf(0.975, n - 1) * std_val / np.sqrt(n)) if n > 1 else 0
                    means.append(mean_val)
                    cis.append(ci)
                else:
                    means.append(0)
                    cis.append(0)

            if i == 0:
                color = "#2C3E50"
            else:
                gray = int((0.6 + i * 0.1) * 255)
                color = f"#{gray:02x}{gray:02x}{gray:02x}"
            ax.bar(
                x + i * width - 0.4 + width / 2,
                means,
                width,
                yerr=cis,
                label=biz,
                color=color,
                capsize=3,
            )

        # Format
        ax.set_xticks(x)
        ax.set_xticklabels([strategy_labels[s] for s in strategies])
        ax.set_ylabel("Payments")
        ax.set_ylim(0, 3)  # Fixed y-axis range
        ax.legend(loc="upper left", fontsize=9)
        plt.title(f"{config['title']}: {model}")
        plt.tight_layout()

        # Save
        output = results_dir / f"{exp_type}_{clean_model}.png"
        plt.savefig(output, dpi=150)
        print(f"Saved: {output}")
        plt.close()

print("Done!")
