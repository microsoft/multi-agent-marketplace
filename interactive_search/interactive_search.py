"""A simple interactive search client for the agentic-economics marketplace."""

import argparse
import asyncio

from search_launcher import SearchMarketLauncher


async def main(
    data_dir: str,
    postgres_host: str,
    postgres_port: int,
    postgres_password: str,
    search_algorithm: str = "lexical",
) -> None:
    """Run a simple interactive search client for the agentic-economics marketplace."""
    search_launcher = SearchMarketLauncher(
        data_dir=data_dir,
        postgres_host=postgres_host,
        postgres_port=postgres_port,
        postgres_password=postgres_password,
        search_algorithm=search_algorithm,
    )

    async with search_launcher.start() as _:
        # Start interactive search loop
        await search_launcher.interactive_search()

        # Shutdown
        await search_launcher.stop()


if __name__ == "__main__":
    # Add argument parsing for data dir using argparse
    parser = argparse.ArgumentParser(
        description="Interactive search client for the multi-agent-marketplace"
    )
    parser.add_argument(
        "--data-dir", help="Path to the dataset directory", required=True
    )
    parser.add_argument(
        "--search-algorithm",
        default="lexical",
        help="Search algorithm to use (default: lexical)",
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
            args.search_algorithm,
        )
    )
