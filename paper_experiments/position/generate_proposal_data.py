#!/usr/bin/env python3
# type: ignore
"""Generate customer proposal bias data for position bias experiment.

For each customer, we analyze which proposal (ranked by arrival time) they accepted.
This helps identify if customers show bias toward earlier proposals.
"""

import csv
import os
import sqlite3
from typing import TypedDict


class CustomerChoice(TypedDict):
    """Structure of each customer choice record."""

    model: str
    condition: str
    run_id: str
    customer_name: str
    chosen_proposal_rank: int
    total_proposals_received: int


def analyze_database(db_path: str) -> list[CustomerChoice]:
    """Analyze a single database file and extract customer choices."""
    choices: list[CustomerChoice] = []

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all order proposals ranked by creation time
    cursor.execute("""
    SELECT
        json_extract(data, '$.agent_id') as from_business,
        json_extract(data, '$.request.parameters.to_agent_id') as to_customer,
        json_extract(data, '$.request.parameters.message.id') as proposal_id,
        created_at
    FROM actions
    WHERE json_extract(data, '$.request.name') = 'SendMessage'
        AND json_extract(data, '$.request.parameters.message.type') = 'order_proposal'
    ORDER BY created_at
    """)

    proposals = cursor.fetchall()

    # Get the payment to find which proposal was accepted
    cursor.execute("""
    SELECT
        json_extract(data, '$.agent_id') as from_customer,
        json_extract(data, '$.request.parameters.message.proposal_message_id') as paid_proposal_id
    FROM actions
    WHERE json_extract(data, '$.request.name') = 'SendMessage'
        AND json_extract(data, '$.request.parameters.message.type') = 'payment'
    LIMIT 1
    """)

    payment_result = cursor.fetchone()

    if payment_result and proposals:
        paid_proposal_id = payment_result[1]
        total_proposals = len(proposals)

        # Find which rank the paid proposal has
        for rank, (from_business, to_customer, proposal_id, created_at) in enumerate(proposals, start=1):
            if proposal_id == paid_proposal_id:
                choices.append(
                    CustomerChoice(
                        model="",
                        condition="",
                        run_id="",
                        customer_name="customer_0001",
                        chosen_proposal_rank=rank,
                        total_proposals_received=total_proposals,
                    )
                )
                break

    conn.close()
    return choices


def main() -> None:
    """Extract customer proposal choice data from all experiment databases."""
    results_dir = "paper_experiments/position/results"
    output_csv = "paper_experiments/position/customer_proposal_choices.csv"

    all_choices: list[CustomerChoice] = []

    if not os.path.exists(results_dir):
        print(f"Results directory '{results_dir}' not found. Run experiments first.")
        return

    print("Processing position bias experiment databases...")

    # Process each database file
    for filename in sorted(os.listdir(results_dir)):
        if filename.endswith(".db") and not filename.endswith(("-shm", "-wal")):
            # Parse filename: position_business_0001_first_gemini-2.5-flash_run1.db
            name = filename.replace("position_", "").replace(".db", "")

            if "_run" not in name:
                continue

            parts = name.rsplit("_run", 1)
            run_id = parts[1]
            rest = parts[0]

            # Split by underscore from the right to find model
            parts2 = rest.rsplit("_", 1)
            if len(parts2) < 2:
                continue

            model = parts2[1]
            condition = parts2[0]

            db_path = os.path.join(results_dir, filename)
            print(f"Processing {filename}...")

            # Analyze this database
            choices = analyze_database(db_path)

            # Fill in model, condition and run_id
            for choice in choices:
                choice["model"] = model
                choice["condition"] = condition
                choice["run_id"] = run_id

            all_choices.extend(choices)

            print(f"  Found {len(choices)} customer purchases")

    # Write customer proposal choices
    with open(output_csv, "w", newline="") as f:
        fieldnames = [
            "model",
            "condition",
            "run_id",
            "customer_name",
            "chosen_proposal_rank",
            "total_proposals_received",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_choices)

    print(f"\nProposal data exported to: {output_csv}")
    print(f"Total customer purchases: {len(all_choices)}")

    # Show summary statistics
    rank_counts = {1: 0, 2: 0, 3: 0}

    for choice in all_choices:
        rank = choice["chosen_proposal_rank"]
        if rank in rank_counts:
            rank_counts[rank] += 1

    total = len(all_choices)
    if total > 0:
        print("\nPROPOSAL RANK SUMMARY:")
        print(
            f"1st proposal chosen: {rank_counts[1]} ({rank_counts[1] / total * 100:.1f}%)"
        )
        print(
            f"2nd proposal chosen: {rank_counts[2]} ({rank_counts[2] / total * 100:.1f}%)"
        )
        print(
            f"3rd proposal chosen: {rank_counts[3]} ({rank_counts[3] / total * 100:.1f}%)"
        )


if __name__ == "__main__":
    main()
