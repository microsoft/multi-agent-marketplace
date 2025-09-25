#!/usr/bin/env python3
"""CLI script to extract LLM logs by agent and save prompts to markdown files."""

import argparse
import asyncio
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from pydantic import AwareDatetime, BaseModel, TypeAdapter

from magentic_marketplace.marketplace.database.queries.logs import llm_call
from magentic_marketplace.marketplace.llm.base import LLMCallLog
from magentic_marketplace.marketplace.shared.models import (
    BusinessAgentProfile,
    CustomerAgentProfile,
)
from magentic_marketplace.platform.database.base import RangeQueryParams
from magentic_marketplace.platform.database.sqlite.sqlite import (
    SQLiteDatabaseController,
)

AgentProfileAdapter: TypeAdapter[BusinessAgentProfile | CustomerAgentProfile] = (
    TypeAdapter(BusinessAgentProfile | CustomerAgentProfile)
)


class AgentLogEntry(BaseModel):
    """Structured type for agent log entries."""

    timestamp: AwareDatetime
    log_id: str
    llm_call_log: LLMCallLog
    full_content: dict[str, Any]


async def extract_agent_llm_traces(db_path: str) -> None:
    """Extract LLM logs grouped by agent ID and save most recent prompts to markdown files.

    Args:
        db_path: Path to the SQLite database file

    """
    # Initialize database controller
    controller = SQLiteDatabaseController(db_path)
    await controller.initialize()

    # Query for all LLM logs
    query = llm_call.all()
    params = RangeQueryParams()
    logs = await controller.logs.find(query, params)

    if not logs:
        print("No LLM logs found in the database.")
        return

    print(f"Found {len(logs)} LLM logs in total.")

    # Group logs by agent ID
    agent_logs: dict[str, list[AgentLogEntry]] = defaultdict(list)

    for log_row in logs:
        log = log_row.data

        # Parse the log data as LLMCallLog for type safety
        try:
            llm_call_log = LLMCallLog.model_validate(log.data)
        except Exception as e:
            print(f"Warning: Could not parse LLM call log: {e}")
            continue

        # Extract agent_id from the log name field (this should be the logger name)
        agent_id = (log.metadata or {}).get("agent_id", None)

        if not agent_id:
            print("Warning: No agent_id metadata.")
            continue

        # Create full content dict from log fields
        full_content = {
            "logger": log.name,
            "message": log.message,
            "level": log.level,
            "metadata": log.metadata,
            "data": log.data,
        }

        if agent_id:
            agent_logs[agent_id].append(
                AgentLogEntry(
                    timestamp=log_row.created_at,
                    log_id=log_row.id,
                    llm_call_log=llm_call_log,  # Structured LLM call data
                    full_content=full_content,  # This includes logger, message, etc.
                )
            )

    if not agent_logs:
        print("No agent IDs found in LLM logs. Logs might be structured differently.")
        return

    print(f"Found logs for {len(agent_logs)} agents.")

    # Create output directory next to database
    db_path_obj = Path(db_path)
    db_name = db_path_obj.stem
    output_dir = db_path_obj.parent / f"{db_name}-agent-prompts"
    output_dir.mkdir(exist_ok=True)

    # Process each agent's logs
    for agent_id, logs_list in agent_logs.items():

        def get_prompt_length(log_entry: AgentLogEntry) -> int:
            """Calculate prompt length for a log entry."""
            llm_log: LLMCallLog = log_entry.llm_call_log
            if isinstance(llm_log.prompt, str):
                return len(llm_log.prompt)
            else:
                # For message sequences, count total content length
                total_length = 0
                for message in llm_log.prompt:
                    total_length += len(str(message.get("content", "")))
                return total_length

        def get_interaction_score(log_entry: AgentLogEntry) -> int:
            """Count occurrences of business interaction keywords."""
            llm_log: LLMCallLog = log_entry.llm_call_log
            prompt_text = ""

            if isinstance(llm_log.prompt, str):
                prompt_text = llm_log.prompt
            else:
                # For message sequences, concatenate all content
                content_parts: list[str] = []
                for message in llm_log.prompt:
                    content_parts.append(str(message.get("content", "")))
                prompt_text = " ".join(content_parts)

            # Count occurrences of interaction keywords (including quotes)
            text_count = prompt_text.count('"text"')
            proposal_count = prompt_text.count('"order_proposal"')
            payment_count = prompt_text.count('"payment"')

            return text_count + proposal_count + payment_count

        # Determine selection strategy based on agent type
        if "business" in agent_id.lower():
            # For business agents, use interaction score
            def selection_key(log_entry: AgentLogEntry) -> tuple[int, Any]:
                score = get_interaction_score(log_entry)
                timestamp = log_entry.timestamp
                return (
                    score,
                    timestamp,
                )  # Primary: interaction score, Secondary: timestamp

            selected_log = max(logs_list, key=selection_key)
            selection_criteria = "Most business interactions"

            print(f"\nAgent '{agent_id}' - {len(logs_list)} logs:")
            for log_entry in logs_list:
                length = get_prompt_length(log_entry)
                score = get_interaction_score(log_entry)
                timestamp = log_entry.timestamp
                marker = "🏪 [SELECTED]" if log_entry is selected_log else "  "
                print(
                    f"  {marker} {length:5d} chars, {score:2d} interactions - {timestamp}"
                )
        else:
            # For other agents, use most recent
            logs_list.sort(key=lambda x: x.timestamp)
            selected_log = logs_list[-1]
            selection_criteria = "Most recent"

            print(f"\nAgent '{agent_id}' - {len(logs_list)} logs:")
            for log_entry in logs_list:
                length = get_prompt_length(log_entry)
                timestamp = log_entry.timestamp
                marker = "📝 [SELECTED]" if log_entry is selected_log else "  "
                print(f"  {marker} {length:5d} chars - {timestamp}")

        llm_call_log: LLMCallLog = selected_log.llm_call_log

        # Extract prompt information (no longer needed since we have structured data)
        # prompt_data = extract_prompt_info(log_content)

        # Fetch AgentProfile from the agents table
        # Note: agent_id from logs might be "customer_0001" but agents table uses "customer_0001-0"
        agent_profile: CustomerAgentProfile | BusinessAgentProfile | None = None
        try:
            # Try the agent_id as-is first
            agent_row = await controller.agents.get_by_id(agent_id)
            if not agent_row:
                # Try with "-0" suffix
                agent_row = await controller.agents.get_by_id(f"{agent_id}-0")
            if agent_row:
                agent_profile = AgentProfileAdapter.validate_python(
                    agent_row.data.model_dump()
                )
        except Exception as e:
            print(f"Warning: Could not fetch agent profile for '{agent_id}': {e}")

        # Create markdown content
        markdown_content = create_markdown_content(
            agent_id, llm_call_log, len(logs_list), agent_profile, selection_criteria
        )

        # Save to markdown file
        safe_agent_id = agent_id.replace("/", "_").replace("\\", "_")
        output_file = output_dir / f"{safe_agent_id}.md"

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        prompt_length = get_prompt_length(selected_log)
        score_text = ""
        if "business" in agent_id.lower():
            score = get_interaction_score(selected_log)
            score_text = f", {score} interactions"

        print(
            f"Saved selected prompt ({prompt_length} chars{score_text}) for agent '{agent_id}' to {output_file}"
        )

    print(f"\nAll agent prompts saved to: {output_dir}")


def create_markdown_content(
    agent_id: str,
    llm_call_log: LLMCallLog,
    total_logs: int,
    agent_profile: BusinessAgentProfile | CustomerAgentProfile | None = None,
    selection_criteria: str = "Most recent",
) -> str:
    """Create markdown content for an agent's prompt information.

    Args:
        agent_id: The agent identifier
        llm_call_log: The structured LLM call log data
        total_logs: Total number of logs for this agent
        agent_profile: The AgentProfile from the agents table
        selection_criteria: Criteria to select best log for each agent

    Returns:
        Formatted markdown string

    """
    lines = [
        f"# Agent: {agent_id}",
        "",
    ]

    # Add AgentProfile at the very top if available
    if agent_profile:
        lines.extend(
            [
                "## AgentProfile",
                "",
            ]
        )

        # Basic info table
        lines.extend(
            [
                "| Field | Value |",
                "|-------|-------|",
                f"| ID | {agent_profile.id} |",
            ]
        )

        # Add business-specific formatting
        if isinstance(agent_profile, BusinessAgentProfile):
            business = agent_profile.business
            lines.extend(
                [
                    "| Type | Business |",
                    f"| Name | {business.name} |",
                    f"| Rating | {business.rating} |",
                    f"| Description | {business.description} |",
                    "",
                    "### Menu Items",
                    "",
                    "| Item | Price |",
                    "|------|-------|",
                ]
            )

            for item, price in business.menu_features.items():
                lines.append(f"| {item} | ${price} |")

            lines.extend(
                [
                    "",
                    "### Amenities",
                    "",
                    "| Amenity | Available |",
                    "|---------|-----------|",
                ]
            )

            for amenity, available in business.amenity_features.items():
                status = "✓" if available else "✗"
                lines.append(f"| {amenity} | {status} |")

        # Add customer-specific formatting
        elif isinstance(agent_profile, CustomerAgentProfile):  # pyright: ignore[reportUnnecessaryIsInstance]
            customer = agent_profile.customer
            lines.extend(
                [
                    "| Type | Customer |",
                    f"| Name | {customer.name} |",
                    f"| Request | {customer.request} |",
                ]
            )

            # Add menu features (requested items)
            if customer.menu_features:
                lines.extend(
                    [
                        "",
                        "### Requested Menu Items",
                        "",
                        "| Item | Requested Price |",
                        "|------|----------------|",
                    ]
                )
                for item, price in customer.menu_features.items():
                    lines.append(f"| {item} | ${price} |")

            # Add amenity features (required amenities)
            if customer.amenity_features:
                lines.extend(
                    [
                        "",
                        "### Required Amenities",
                        "",
                    ]
                )
                amenities_str = ", ".join(customer.amenity_features)
                lines.append(f"Required: {amenities_str}")

        # If neither business nor customer, show generic format
        else:
            lines.append("| Type | Unknown |")

        lines.extend(["", ""])

    # Add metadata table using structured LLMCallLog (longest prompt)
    lines.extend(
        [
            "| Field | Value |",
            "|-------|-------|",
            f"| Total LLM Logs | {total_logs} |",
            f"| Success | {llm_call_log.success} |",
            f"| Selection Criteria | {selection_criteria} |",
        ]
    )

    # Add LLM call metadata from structured log
    if llm_call_log.model:
        lines.append(f"| Model | {llm_call_log.model} |")
    if llm_call_log.provider:
        lines.append(f"| Provider | {llm_call_log.provider} |")
    lines.append(f"| Duration | {llm_call_log.duration_ms}ms |")
    lines.append(f"| Token Count | {llm_call_log.token_count} |")
    if llm_call_log.error_message:
        lines.append(f"| Error Message | {llm_call_log.error_message} |")

    lines.extend(["", "## prompt", ""])

    # Handle prompt field which can be a sequence of messages or a string
    if isinstance(llm_call_log.prompt, str):
        lines.append(llm_call_log.prompt)
    else:
        # Handle sequence of chat messages - format with role prefixes
        for message in llm_call_log.prompt:
            role = message.get("role", "unknown")
            content = str(message.get("content", ""))
            lines.append(f"<|{role}|>")
            lines.append(content)
            lines.append("")  # Add blank line between messages

    # Add response_format section if available
    if llm_call_log.response_format:
        lines.extend(
            [
                "",
                "## response_format",
                "",
                "```json",
                json.dumps(llm_call_log.response_format, indent=2),
                "```",
            ]
        )

    # Add LLM response output at the bottom
    lines.extend(
        [
            "",
            "## LLM Response",
            "",
        ]
    )

    # Handle response field which can be a string or BaseModel
    if isinstance(llm_call_log.response, str):
        lines.extend(
            [
                "```",
                llm_call_log.response,
                "```",
            ]
        )
    else:
        # Handle BaseModel response
        lines.extend(
            [
                "```json",
                json.dumps(llm_call_log.response, indent=2),
                "```",
            ]
        )

    return "\n".join(lines)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Extract LLM logs grouped by agent ID and save most recent prompts to markdown files"
    )
    parser.add_argument("database_path", help="Path to the SQLite database file")

    args = parser.parse_args()

    # Validate database path
    if not os.path.exists(args.database_path):
        print(f"Error: Database file '{args.database_path}' does not exist.")
        return 1

    try:
        asyncio.run(extract_agent_llm_traces(args.database_path))
        return 0
    except Exception as e:
        print(f"Error processing database: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
