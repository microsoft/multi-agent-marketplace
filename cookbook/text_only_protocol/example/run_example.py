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

from cookbook.text_only_protocol.example.agents import (
    ConversationAgent,
    GreeterAgent,
    ReaderAgent,
)
from cookbook.text_only_protocol.protocol import TextOnlyProtocol


async def run_greeter_reader_example():
    """Run example with one agent sending messages and another receiving."""
    print("\n" + "=" * 60)
    print("EXAMPLE 1: One-Way Messaging")
    print("=" * 60)
    print("Alice (greeter) will send 3 messages to Bob (reader)")
    print("Bob will check for messages every second")
    print("-" * 60 + "\n")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_file:
        db_path = temp_file.name

    def database_factory():
        return create_sqlite_database(db_path)

    launcher = MarketplaceLauncher(
        protocol=TextOnlyProtocol(),
        database_factory=database_factory,
        server_log_level="warning",
    )

    async with launcher:
        # Note: Agent IDs may be modified by the server during registration
        # Use the registered profile IDs for communication
        alice_profile = AgentProfile(id="alice", metadata={})
        bob_profile = AgentProfile(id="bob", metadata={})

        # Create reader first (will be registered first)
        reader = ReaderAgent(
            profile=bob_profile,
            server_url=launcher.server_url,
            check_interval=1.0,
        )

        # Create greeter that will send to bob
        # The target ID will be resolved after registration
        greeter = GreeterAgent(
            profile=alice_profile,
            server_url=launcher.server_url,
            target_agent_id=bob_profile.id,  # Will use bob's actual registered ID
            message_count=3,
        )

        async with AgentLauncher(launcher.server_url) as agent_launcher:
            try:
                # Run both agents as primary so they both register concurrently
                await agent_launcher.run_agents_with_dependencies(
                    primary_agents=[reader, greeter],  # Reader first to register
                    dependent_agents=[],
                )
            except KeyboardInterrupt:
                print("\nExample interrupted by user")

    print("\n" + "-" * 60)
    print("Example 1 complete! All messages delivered successfully.")
    print("=" * 60)

    try:
        import os

        os.unlink(db_path)
    except Exception:
        pass


async def run_conversation_example():
    """Run example with two agents having a conversation."""
    print("\n" + "=" * 60)
    print("EXAMPLE 2: Two-Way Conversation")
    print("=" * 60)
    print("Alice will start the conversation")
    print("Bob will respond to each message")
    print("Each agent will send up to 3 messages")
    print("-" * 60 + "\n")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_file:
        db_path = temp_file.name

    def database_factory():
        return create_sqlite_database(db_path)

    launcher = MarketplaceLauncher(
        protocol=TextOnlyProtocol(),
        database_factory=database_factory,
        server_log_level="warning",
    )

    async with launcher:
        alice_profile = AgentProfile(id="alice", metadata={})
        bob_profile = AgentProfile(id="bob", metadata={})

        alice = ConversationAgent(
            profile=alice_profile,
            server_url=launcher.server_url,
            peer_agent_id="bob",
            initial_message="Hi Bob, how are you?",
        )

        bob = ConversationAgent(
            profile=bob_profile,
            server_url=launcher.server_url,
            peer_agent_id="alice",
        )

        async with AgentLauncher(launcher.server_url) as agent_launcher:
            try:
                await agent_launcher.run_agents_with_dependencies(
                    primary_agents=[alice, bob],
                    dependent_agents=[],
                )
            except KeyboardInterrupt:
                print("\nExample interrupted by user")

    print("\n" + "-" * 60)
    print("Example 2 complete! Conversation finished.")
    print("=" * 60)

    try:
        import os

        os.unlink(db_path)
    except Exception:
        pass


async def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("TEXT-ONLY PROTOCOL DEMONSTRATION")
    print("=" * 60)
    print("This demo shows agents communicating using a minimal protocol")
    print("with just two actions: SendTextMessage and CheckMessages")
    print("=" * 60)

    await run_greeter_reader_example()

    await asyncio.sleep(1)

    await run_conversation_example()

    print("\n" + "=" * 60)
    print("ALL EXAMPLES COMPLETE")
    print("=" * 60)
    print("You've seen:")
    print("  1. One-way messaging (greeter -> reader)")
    print("  2. Two-way conversation (alice <-> bob)")
    print("\nNext steps: Check the code in example/agents.py to see how")
    print("these agents work, or run the tests with:")
    print("  uv run pytest cookbook/text_only_protocol/tests/ -v")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
