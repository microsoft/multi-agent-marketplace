#!/usr/bin/env python3
"""Analyze competitive description marketing experiment results.

This script processes all database files in the results directory and extracts:
- Model (AI model used)
- Condition (marketing strategy type)
- Run ID
- Business name
- Number of payments received

Usage:
    python analyze_results.py [results_directory]

Example:
    python analyze_results.py paper_experiments/results

"""

import argparse
import csv
import os
import sqlite3
from pathlib import Path


def parse_filename(filename):
    """Parse experiment details from database filename.

    Expected format: condition_model_runX.db
    Example: contractors_authority_gpt-4.1_run1.db
            contractors_authority_qwen3_4b_run1.db

    Returns: (condition, model, run_id) or None if invalid format
    """
    if not filename.endswith(".db"):
        return None

    # Remove .db extension
    name = filename.replace(".db", "")

    # Find run part at the end
    if "_run" not in name:
        return None

    # Split at last occurrence of _run
    parts = name.rsplit("_run", 1)
    if len(parts) != 2:
        return None

    run_id = parts[1]
    rest = parts[0]

    # Known model patterns - check for multi-part model names
    known_models = [
        "claude-sonnet-4-5",
        "gpt_oss_20b",
        "qwen3_4b",
        "qwen3_14b",
        "gpt-4o",
        "gpt-4.1",
        "gemini-2.5-flash",
    ]

    model = None
    condition = None

    for known_model in known_models:
        # Normalize the comparison (handle both - and _)
        normalized_known = known_model.replace("-", "_").replace(".", "_")
        if rest.endswith("_" + normalized_known):
            model = normalized_known
            condition = rest[: -len("_" + normalized_known)]
            break

    # Fallback to old logic if no known model matched
    if model is None:
        last_underscore = rest.rfind("_")
        if last_underscore == -1:
            return None
        condition = rest[:last_underscore]
        model = rest[last_underscore + 1 :]

    return condition, model, run_id


def get_businesses(conn):
    """Extract all business names from the agents table."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT json_extract(data, '$.business.name')
        FROM agents
        WHERE json_extract(data, '$.metadata.type') = 'business'
    """)
    return [row[0] for row in cursor.fetchall()]


def get_payment_counts(conn):
    """Count payments received by each business."""
    cursor = conn.cursor()

    # Find all payment messages
    cursor.execute("""
        SELECT json_extract(data, '$.request.parameters.to_agent_id') as to_agent_id
        FROM actions
        WHERE json_extract(data, '$.request.parameters.message.type') = 'payment'
    """)

    payment_counts = {}
    for row in cursor.fetchall():
        to_agent_id = row[0]
        if to_agent_id:
            # Extract business name from agent_id (format: business_XXXX-X)
            # Need to look up the business name from agents table
            cursor.execute(
                """
                SELECT json_extract(data, '$.business.name')
                FROM agents
                WHERE id = ?
            """,
                (to_agent_id,),
            )
            result = cursor.fetchone()
            if result and result[0]:
                business_name = result[0]
                payment_counts[business_name] = payment_counts.get(business_name, 0) + 1

    return payment_counts


def main():
    """Extract data from experiment databases and generate CSV summary."""
    parser = argparse.ArgumentParser(
        description="Analyze competitive description marketing experiment results."
    )
    parser.add_argument(
        "results_dir",
        type=str,
        nargs="?",
        default="paper_experiments/competitive/results",
        help="Directory containing the experiment database files",
    )
    args = parser.parse_args()
    results_dir = Path(args.results_dir)

    if not results_dir.exists():
        print(f"Error: Directory not found: {results_dir}")
        return

    csv_data = []
    model_data = {}

    print("Processing experiment databases...\n")

    for filename in sorted(os.listdir(results_dir)):
        if not filename.endswith(".db"):
            continue

        parsed = parse_filename(filename)
        if not parsed:
            print(f"Skipping {filename} - unexpected format")
            continue

        condition, model, run_id = parsed
        db_path = results_dir / filename

        print(f"Processing {filename}...")
        print(f"  Condition: {condition}")
        print(f"  Model: {model}")
        print(f"  Run: {run_id}")

        conn = sqlite3.connect(db_path)

        # Get all businesses
        businesses = get_businesses(conn)
        print(f"  Businesses: {len(businesses)}")

        # Get payment counts
        payment_counts = get_payment_counts(conn)
        print(f"  Total payments: {sum(payment_counts.values())}")

        # Create rows for all businesses
        for business in businesses:
            payments = payment_counts.get(business, 0)
            row = {
                "model": model,
                "condition": condition,
                "run_id": run_id,
                "business_name": business,
                "payments_received": payments,
            }
            csv_data.append(row)

            if model not in model_data:
                model_data[model] = []
            model_data[model].append(row)

        conn.close()
        print()

    if not csv_data:
        print("No data found!")
        return

    # Write combined CSV
    combined_output = results_dir / "competitive_description_results_all_models.csv"
    with open(combined_output, "w", newline="") as f:
        fieldnames = [
            "model",
            "condition",
            "run_id",
            "business_name",
            "payments_received",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_data)

    print(f"Combined data exported to: {combined_output}")
    print(f"Total rows: {len(csv_data)}\n")

    # Write model-specific CSVs
    for model, data in model_data.items():
        clean_model = model.replace("-", "_").replace(".", "_")
        model_output = (
            results_dir / f"competitive_description_results_{clean_model}.csv"
        )

        with open(model_output, "w", newline="") as f:
            fieldnames = [
                "model",
                "condition",
                "run_id",
                "business_name",
                "payments_received",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)

        print(f"Model-specific data: {model_output}")
        print(f"  Rows: {len(data)}")

    # Display summary
    print("\nSUMMARY:")
    print(
        f"Total experiments: {len({(r['model'], r['condition'], r['run_id']) for r in csv_data})}"
    )
    print(f"Models: {', '.join(sorted({r['model'] for r in csv_data}))}")
    print(f"Conditions: {', '.join(sorted({r['condition'] for r in csv_data}))}")


if __name__ == "__main__":
    main()
