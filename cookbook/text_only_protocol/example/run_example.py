#!/usr/bin/env python3
"""Run example agents using the text-only protocol."""

import asyncio
import tempfile

from cookbook.text_only_protocol.example.agents import (
    ConversationAgent,
    GreeterAgent,
    ReaderAgent,
)
from cookbook.text_only_protocol.protocol import TextOnlyProtocol
from magentic_marketplace.platform.database.sqlite import create_sqlite_database
from magentic_marketplace.platform.launcher import AgentLauncher, MarketplaceLauncher
from magentic_marketplace.platform.shared.models import AgentProfile


async def run_greeter_reader_example():
    """Run example with one agent sending messages and another receiving."""
    print("=" * 60)
    print("Text-Only Protocol Example: Greeter and Reader")
    print("=" * 60)

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

        greeter = GreeterAgent(
            profile=alice_profile,
            server_url=launcher.server_url,
            target_agent_id="bob",
            message_count=3,
        )

        reader = ReaderAgent(
            profile=bob_profile,
            server_url=launcher.server_url,
            check_interval=1.0,
        )

        async with AgentLauncher(launcher.server_url) as agent_launcher:
            try:
                await agent_launcher.run_agents_with_dependencies(
                    primary_agents=[greeter],
                    dependent_agents=[reader],
                )
            except KeyboardInterrupt:
                print("\nExample interrupted by user")

    print("\nExample completed!")

    try:
        import os

        os.unlink(db_path)
    except Exception:
        pass


async def run_conversation_example():
    """Run example with two agents having a conversation."""
    print("=" * 60)
    print("Text-Only Protocol Example: Conversation")
    print("=" * 60)

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

    print("\nExample completed!")

    try:
        import os

        os.unlink(db_path)
    except Exception:
        pass


async def main():
    """Run all examples."""
    print("\nRunning Greeter/Reader Example...\n")
    await run_greeter_reader_example()

    await asyncio.sleep(2)

    print("\n\nRunning Conversation Example...\n")
    await run_conversation_example()


if __name__ == "__main__":
    asyncio.run(main())
