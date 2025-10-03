#!/usr/bin/env python3
"""Run example agents using the text-only protocol."""

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from magentic_marketplace.platform.database.sqlite import create_sqlite_database
from magentic_marketplace.platform.launcher import AgentLauncher, MarketplaceLauncher
from magentic_marketplace.platform.shared.models import AgentProfile

from cookbook.text_only_protocol.example.agents import ChatAgent
from cookbook.text_only_protocol.protocol import TextOnlyProtocol


async def main():
    """Show two agents exchanging messages."""
    print("\n" + "=" * 60)
    print("TEXT-ONLY PROTOCOL EXAMPLE")
    print("=" * 60)
    print("Alice and Bob will exchange messages using two actions:")
    print("  - SendTextMessage: Send a message to another agent")
    print("  - CheckMessages: Retrieve messages sent to this agent")
    print("-" * 60 + "\n")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_file:
        db_path = temp_file.name

    launcher = MarketplaceLauncher(
        protocol=TextOnlyProtocol(),
        database_factory=lambda: create_sqlite_database(db_path),
        server_log_level="warning",
    )

    async with launcher:
        alice = ChatAgent(
            profile=AgentProfile(id="alice", metadata={}),
            server_url=launcher.server_url,
            peer_id="bob",
            messages_to_send=2,
            send_first=True,
        )

        bob = ChatAgent(
            profile=AgentProfile(id="bob", metadata={}),
            server_url=launcher.server_url,
            peer_id="alice",
            messages_to_send=2,
        )

        async with AgentLauncher(launcher.server_url) as agent_launcher:
            try:
                await agent_launcher.run_agents_with_dependencies(
                    primary_agents=[alice, bob],
                    dependent_agents=[],
                )
            except KeyboardInterrupt:
                print("\nExample interrupted")

    print("\n" + "-" * 60)
    print("Example complete!")
    print("\nNext steps:")
    print("  - Check example/agents.py to see the ChatAgent implementation")
    print("  - Run tests: uv run pytest cookbook/text_only_protocol/tests/ -v")
    print("=" * 60 + "\n")

    try:
        import os

        os.unlink(db_path)
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
