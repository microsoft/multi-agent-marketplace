#!/usr/bin/env python3
# type: ignore
"""Generate CSV data from position bias experiment results."""

import csv
import os
import sqlite3


def get_payment_data(db_path: str):
    """Get payment recipient from a database file."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Find payment action
        cursor.execute("""
            SELECT json_extract(data, '$.request.parameters.to_agent_id') as to_agent_id
            FROM actions
            WHERE json_extract(data, '$.request.parameters.message.type') = 'payment'
            LIMIT 1
        """)

        result = cursor.fetchone()

        if result and result[0]:
            to_agent_id = result[0]

            # Get business name from agents table
            cursor.execute(
                """
                SELECT json_extract(data, '$.business.name')
                FROM agents
                WHERE id = ?
            """,
                (to_agent_id,),
            )

            business_result = cursor.fetchone()
            conn.close()

            if business_result and business_result[0]:
                business_name = business_result[0]
                # Extract business number from agent_id (format: business_0001-0)
                business_id = to_agent_id.split("-")[0].replace("business_", "")
                return business_id, business_name

        conn.close()
        return None, None

    except Exception as e:
        print(f"Error reading {db_path}: {e}")
        return None, None


def main():
    """Generate CSV with position bias experiment results."""
    results_dir = "paper_experiments/position/results"

    if not os.path.exists(results_dir):
        print(f"Results directory '{results_dir}' not found.")
        return

    # Collect all results
    all_results = []

    # Process each database file
    for filename in sorted(os.listdir(results_dir)):
        if not filename.endswith(".db") or filename.endswith(("-shm", "-wal")):
            continue

        # Parse filename: position_business_0001_first_gemini-2.5-flash_run1.db
        # Remove prefix and .db
        name = filename.replace("position_", "").replace(".db", "")

        # Find run part at the end
        if "_run" not in name:
            continue

        parts = name.rsplit("_run", 1)
        run_number = parts[1]
        rest = parts[0]

        # rest is now: business_0001_first_gemini-2.5-flash or contractors_first_gemini-2.5-flash
        # Split by underscore from the right to find model
        # Handle multi-part model names like qwen3_4b
        known_models = [
            "claude_sonnet_4_5",
            "gpt_oss_20b",
            "qwen3_4b",
            "gpt_4o",
            "gpt_4_1",
            "gemini_2_5_flash",
        ]

        model = None
        condition_and_position = None

        for known_model in known_models:
            if rest.endswith("_" + known_model):
                model = known_model
                condition_and_position = rest[: -len("_" + known_model)]
                break

        if not model:
            # Fallback to simple split for unknown models
            parts2 = rest.rsplit("_", 1)
            if len(parts2) < 2:
                continue
            model = parts2[1]
            condition_and_position = parts2[0]

        # Extract position (last part)
        position_parts = condition_and_position.rsplit("_", 1)
        if len(position_parts) < 2:
            continue

        position = position_parts[1]  # first, second, third
        condition = condition_and_position  # full condition name

        db_path = os.path.join(results_dir, filename)
        business_id, business_name = get_payment_data(db_path)

        if business_id and business_name:
            # Determine restaurant order based on condition and business_id
            # business_0001 is Summit Residential Services
            # For first: business_0001 should be 1st (rating 1.0)
            # For second: business_0002 1st (rating 1.0), business_0001 2nd
            # For third: business_0002 1st (rating 1.0), business_0003 2nd, business_0001 3rd

            if position == "first":
                order_map = {"0001": 1, "0002": 2, "0003": 3}
            elif position == "second":
                order_map = {"0002": 1, "0001": 2, "0003": 3}
            elif position == "third":
                order_map = {"0002": 1, "0003": 2, "0001": 3}
            else:
                order_map = {}

            restaurant_order = order_map.get(business_id, None)

            all_results.append(
                {
                    "model": model,
                    "condition": condition,
                    "position": position,
                    "run": run_number,
                    "winner_id": business_id,
                    "winner_name": business_name,
                    "restaurant_order": restaurant_order,
                }
            )

    if not all_results:
        print("No data found!")
        return

    # Group results by model
    model_data = {}
    for result in all_results:
        model = result["model"]
        if model not in model_data:
            model_data[model] = []
        model_data[model].append(result)

    fieldnames = [
        "model",
        "condition",
        "position",
        "run",
        "winner_id",
        "winner_name",
        "restaurant_order",
    ]

    # Write combined CSV
    combined_csv = os.path.join(results_dir, "position_bias_results_all_models.csv")
    with open(combined_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_results)

    print(f"Combined data exported to: {combined_csv}")
    print(f"Total rows: {len(all_results)}\n")

    # Write model-specific CSVs
    for model, data in model_data.items():
        model_csv = os.path.join(results_dir, f"position_bias_results_{model}.csv")
        with open(model_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)

        print(f"Model-specific data: {model_csv}")
        print(f"  Rows: {len(data)}")

    # Generate summary statistics by model
    models = list({r["model"] for r in all_results})
    print("\n=== SUMMARY STATISTICS BY MODEL ===")
    for model in sorted(models):
        print(f"\n=== {model.upper()} ===")
        model_results = [r for r in all_results if r["model"] == model]

        for position in ["first", "second", "third"]:
            position_results = [r for r in model_results if r["position"] == position]
            if position_results:
                total = len(position_results)

                # Count wins by restaurant order
                order_wins = {1: 0, 2: 0, 3: 0}
                for r in position_results:
                    if r["restaurant_order"]:
                        order_wins[r["restaurant_order"]] += 1

                print(f"\n{position.capitalize()} Position ({total} runs):")
                print(
                    f"  Restaurant Order 1: {order_wins[1]}/{total} ({order_wins[1] / total * 100:.1f}%)"
                )
                print(
                    f"  Restaurant Order 2: {order_wins[2]}/{total} ({order_wins[2] / total * 100:.1f}%)"
                )
                print(
                    f"  Restaurant Order 3: {order_wins[3]}/{total} ({order_wins[3] / total * 100:.1f}%)"
                )


if __name__ == "__main__":
    main()
