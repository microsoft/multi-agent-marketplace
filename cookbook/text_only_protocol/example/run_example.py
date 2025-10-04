#!/usr/bin/env python3
"""Run example agents using the text-only protocol.

This example shows a Writer agent sending text from a PDF to a Proofreader agent,
who corrects errors and explains the changes.
"""

import argparse
import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from magentic_marketplace.platform.database.sqlite import create_sqlite_database
from magentic_marketplace.platform.launcher import AgentLauncher, MarketplaceLauncher
from magentic_marketplace.platform.shared.models import AgentProfile

from cookbook.text_only_protocol.example.agents import ProofreaderAgent, WriterAgent
from cookbook.text_only_protocol.protocol import TextOnlyProtocol


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text content from a PDF file using markitdown.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        Extracted text content

    """
    try:
        from markitdown import MarkItDown

        md = MarkItDown()
        result = md.convert(pdf_path)
        return result.text_content
    except ImportError:
        print("Error: markitdown not installed. Install with: uv sync --extra cookbook")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading PDF: {e}")
        sys.exit(1)


async def main():
    """Run writer and proofreader agents with PDF input."""
    parser = argparse.ArgumentParser(
        description="Proofread a PDF document using the text-only protocol"
    )
    parser.add_argument("pdf_path", help="Path to PDF file to proofread")
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        print(f"Error: PDF file not found: {pdf_path}")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("TEXT-ONLY PROTOCOL: MULTI-AGENT MARKETPLACE")
    print("=" * 70)
    print(f"Document: {pdf_path.name}")
    print("\nLEARNING OBJECTIVE:")
    print("  See how 2 actions (SendTextMessage + CheckMessages) enable a")
    print("  complete marketplace with bidding, selection, and task execution.")
    print("\nMARKETPLACE FLOW:")
    print("  Phase 1: Broadcast (1→Many)  - Request quotes from all vendors")
    print("  Phase 2: Collect (Many→1)    - Gather bids, select winner")
    print("  Phase 3: Assign (1→1)        - Send work to chosen vendor")
    print("  Phase 4: Complete (1→1)      - Receive finished work")
    print("-" * 70 + "\n")

    print(f"Extracting text from {pdf_path.name}...")
    text = extract_text_from_pdf(str(pdf_path))
    print(f"Extracted {len(text)} characters\n")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_file:
        db_path = temp_file.name

    launcher = MarketplaceLauncher(
        protocol=TextOnlyProtocol(),
        database_factory=lambda: create_sqlite_database(db_path),
        server_log_level="warning",
    )

    async with launcher:
        # Create three proofreaders with different LLMs
        proofreader_gpt4o = ProofreaderAgent(
            profile=AgentProfile(id="proofreader-gpt4o", metadata={}),
            server_url=launcher.server_url,
            llm_provider="openai",
            llm_model="gpt-4o",
        )

        proofreader_gpt4mini = ProofreaderAgent(
            profile=AgentProfile(id="proofreader-gpt4mini", metadata={}),
            server_url=launcher.server_url,
            llm_provider="openai",
            llm_model="gpt-4o-mini",
        )

        proofreader_gemini = ProofreaderAgent(
            profile=AgentProfile(id="proofreader-gemini", metadata={}),
            server_url=launcher.server_url,
            llm_provider="gemini",
            llm_model="gemini-2.0-flash-exp",
        )

        # Writer uses GPT-4o to request quotes and select best proofreader
        writer = WriterAgent(
            profile=AgentProfile(id="writer", metadata={}),
            server_url=launcher.server_url,
            proofreader_ids=["proofreader-gpt4o", "proofreader-gpt4mini", "proofreader-gemini"],
            text_to_proofread=text,
            llm_provider="openai",
            llm_model="gpt-4o",
        )

        async with AgentLauncher(launcher.server_url) as agent_launcher:
            try:
                await asyncio.wait_for(
                    agent_launcher.run_agents_with_dependencies(
                        primary_agents=[writer, proofreader_gpt4o, proofreader_gpt4mini, proofreader_gemini],
                        dependent_agents=[],
                    ),
                    timeout=60.0
                )
            except asyncio.TimeoutError:
                print("\nExample completed (timeout)")
            except KeyboardInterrupt:
                print("\nExample interrupted")

    print("\n" + "=" * 70)
    print("KEY TAKEAWAYS")
    print("=" * 70)
    print("\n1. MINIMAL ACTIONS, MAXIMUM FLEXIBILITY:")
    print("   - Only 2 actions needed: SendTextMessage + CheckMessages")
    print("   - Same actions work for quotes, tasks, and results")
    print("   - No special 'bid' or 'contract' actions required")
    print("\n2. PROTOCOL HANDLES INFRASTRUCTURE:")
    print("   - Auto-persistence: All messages saved to database")
    print("   - Auto-routing: Messages delivered to correct agents")
    print("   - Simple queries: CheckMessages() retrieves all relevant messages")
    print("\n3. LLMS ENABLE NATURAL NEGOTIATION:")
    print("   - Agents interpret message intent (quote vs task)")
    print("   - Decision making (select best quote) uses LLM reasoning")
    print("   - No hardcoded message formats or rigid protocols")
    print("\nNext: Read example/agents.py to see the implementation")
    print("=" * 70 + "\n")

    try:
        import os

        os.unlink(db_path)
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
