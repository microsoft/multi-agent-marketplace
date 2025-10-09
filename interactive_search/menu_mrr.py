"""Run search queries based on menu items and evaluate using Mean Reciprocal Rank (MRR)."""

import argparse
import asyncio
import random
from pathlib import Path

from magentic_marketplace.experiments.utils.yaml_loader import load_businesses_from_yaml
from magentic_marketplace.marketplace.shared.models import BusinessAgentProfile
from search_launcher import SearchMarketLauncher


def has_items(items: list[str], business: BusinessAgentProfile) -> bool:
    """Check if the business has all the specified menu items."""
    menu_items = business.business.menu_features.keys()
    for item in items:
        if item not in menu_items:
            return False
    return True


async def main(
    data_dir: str,
    postgres_host: str,
    postgres_port: int,
    postgres_password: str,
    order_size: int = 1,
):
    """Evaluate search functionality using Mean Reciprocal Rank (MRR) based on menu items."""
    # Start the search market server before running this script
    search_launcher = SearchMarketLauncher(
        data_dir=data_dir,
        postgres_host=postgres_host,
        postgres_port=postgres_port,
        postgres_password=postgres_password,
    )
    async with search_launcher.start() as _:
        reciprocal_ranks: list[float] = []
        businesses_dir = Path(args.data_dir) / "businesses"

        businesses = load_businesses_from_yaml(businesses_dir)

        for business in businesses:
            menu_items = list(business.menu_features.keys())
            sampled_items = random.sample(menu_items, min(order_size, len(menu_items)))

            query = " ".join(sampled_items)
            print(f"Searching for: {query}")
            results = await search_launcher.search(query=query)

            found = False
            rank = 0
            for rank in range(len(results)):
                result = results[rank]
                if has_items(sampled_items, result):
                    print(
                        f"Found matching business at rank {rank + 1}: {result.business.name}"
                    )
                    found = True
                    break
            if found:
                reciprocal_ranks.append(1 / (rank + 1))
            else:
                print(f"No matching business found in top {len(results)} results.")
                reciprocal_ranks.append(1 / (len(results) + 1))
            print()

        print("--- Evaluation Complete ---")
        print(
            f"Mean Reciprocal Rank (MRR): {sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else 0:.4f}"
        )

        # Shutdown
        print("Shutting down...")
        await search_launcher.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Compute Mean Reciprocal Rank (MRR) for search queries based on menu items"
    )
    parser.add_argument(
        "--data-dir", help="Path to the dataset directory", required=True
    )
    parser.add_argument(
        "--postgres-host",
        default="localhost",
        help="PostgreSQL host (default: localhost)",
    )

    parser.add_argument(
        "--postgres-port",
        type=int,
        default=5432,
        help="PostgreSQL port (default: 5432)",
    )

    parser.add_argument(
        "--postgres-password",
        default="postgres",
        help="PostgreSQL password (default: postgres)",
    )

    args = parser.parse_args()

    asyncio.run(
        main(
            args.data_dir,
            args.postgres_host,
            args.postgres_port,
            args.postgres_password,
        )
    )
