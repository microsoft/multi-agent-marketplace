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
    print("TEXT-ONLY PROTOCOL: MULTI-LLM PDF PROOFREADING")
    print("=" * 70)
    print(f"PDF: {pdf_path.name}")
    print("\nWriter agent will:")
    print("  1. Extract text from PDF")
    print("  2. Send text to 3 proofreaders using SendTextMessage")
    print("\nProofreader agents will (in parallel):")
    print("  - gpt-4o: Receive text, proofread with GPT-4o, send corrections")
    print("  - gpt-4o-mini: Receive text, proofread with GPT-4o-mini, send corrections")
    print("  - gemini-2.0-flash-exp: Receive text, proofread with Gemini, send corrections")
    print("\nWriter agent will:")
    print("  3. Collect all corrections using CheckMessages")
    print("  4. Display results from each LLM")
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

        # Writer sends to all three proofreaders
        writer = WriterAgent(
            profile=AgentProfile(id="writer", metadata={}),
            server_url=launcher.server_url,
            proofreader_ids=["proofreader-gpt4o", "proofreader-gpt4mini", "proofreader-gemini"],
            text_to_proofread=text,
        )

        async with AgentLauncher(launcher.server_url) as agent_launcher:
            try:
                await agent_launcher.run_agents_with_dependencies(
                    primary_agents=[writer, proofreader_gpt4o, proofreader_gpt4mini, proofreader_gemini],
                    dependent_agents=[],
                )
            except KeyboardInterrupt:
                print("\nExample interrupted")

    print("\n" + "-" * 70)
    print("Example complete!")
    print("\nWhat happened:")
    print("  - Writer sent PDF text to 3 different LLM-powered proofreaders")
    print("  - Each proofreader processed the text in parallel")
    print("  - Writer collected all 3 corrections via CheckMessages")
    print("\nNext steps:")
    print("  - Check example/agents.py to see WriterAgent and ProofreaderAgent")
    print("  - Run tests: uv run pytest cookbook/text_only_protocol/tests/ -v")
    print("=" * 70 + "\n")

    try:
        import os

        os.unlink(db_path)
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
