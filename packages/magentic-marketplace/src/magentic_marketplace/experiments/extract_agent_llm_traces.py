#!/usr/bin/env python3
"""CLI script to extract LLM logs by agent and save prompts to markdown files."""

import json
from collections import defaultdict
from pathlib import Path

from pydantic import TypeAdapter

from magentic_marketplace.marketplace.actions import ActionAdapter, SendMessage
from magentic_marketplace.marketplace.actions.messaging import Payment
from magentic_marketplace.marketplace.database.queries.logs import llm_call
from magentic_marketplace.marketplace.llm.base import LLMCallLog
from magentic_marketplace.marketplace.shared.models import (
    BusinessAgentProfile,
    CustomerAgentProfile,
    MarketplaceAgentProfileAdapter,
)
from magentic_marketplace.platform.database import connect_to_postgresql_database
from magentic_marketplace.platform.database.base import (
    BaseDatabaseController,
    RangeQueryParams,
)
from magentic_marketplace.platform.database.sqlite.sqlite import (
    SQLiteDatabaseController,
)
from magentic_marketplace.platform.shared.models import ActionExecutionRequest

AgentProfileAdapter: TypeAdapter[BusinessAgentProfile | CustomerAgentProfile] = (
    TypeAdapter(BusinessAgentProfile | CustomerAgentProfile)
)


async def get_last_llm_log_for_agent(
    db_controller: BaseDatabaseController, agent_id: str
) -> tuple[LLMCallLog, str] | None:
    """Get the last LLM log for a specific agent with timestamp.

    Args:
        db_controller: Database controller
        agent_id: The agent ID

    Returns:
        Tuple of (LLMCallLog, timestamp) for the most recent log, or None if not found

    """
    # Query for all LLM logs
    query = llm_call.all()
    params = RangeQueryParams()
    logs = await db_controller.logs.find(query, params)

    if not logs:
        return None

    # Filter logs by agent_id and find the most recent
    agent_logs = []
    for log_row in logs:
        log = log_row.data
        log_agent_id = (log.metadata or {}).get("agent_id", None)

        if log_agent_id == agent_id:
            try:
                llm_call_log = LLMCallLog.model_validate(log.data)
                timestamp = log_row.created_at.isoformat()
                agent_logs.append((log_row.index, llm_call_log, timestamp))  # type: ignore[attr-defined]
            except Exception as e:
                print(f"Warning: Could not parse LLM call log: {e}")
                continue

    if not agent_logs:
        return None

    # Sort by index and return the most recent (log, timestamp)
    agent_logs.sort(key=lambda x: x[0])
    return (agent_logs[-1][1], agent_logs[-1][2])


async def get_business_customer_pairs(
    db_controller: BaseDatabaseController,
) -> dict[str, set[str]]:
    """Get all business-customer pairs that have messages.

    Args:
        db_controller: Database controller

    Returns:
        Dictionary mapping business_id -> set of customer_ids they messaged

    """
    actions = await db_controller.actions.get_all()
    business_customer_pairs: dict[str, set[str]] = defaultdict(set)

    for action_row in actions:
        action_request: ActionExecutionRequest = action_row.data.request
        agent_id = action_row.data.agent_id

        # Parse the action
        action = ActionAdapter.validate_python(action_request.parameters)

        # Process SendMessage actions from businesses to customers
        if isinstance(action, SendMessage):
            if (
                "business" in agent_id.lower()
                and "customer" in action.to_agent_id.lower()
            ):
                business_customer_pairs[action.from_agent_id].add(action.to_agent_id)

    return business_customer_pairs


async def get_customer_business_payments(
    db_controller: BaseDatabaseController,
) -> dict[tuple[str, str], list[Payment]]:
    """Get all payments from customers to businesses.

    Args:
        db_controller: Database controller

    Returns:
        Dictionary mapping (customer_id, business_id) -> list of Payment messages

    """
    actions = await db_controller.actions.get_all()
    payments: dict[tuple[str, str], list[Payment]] = defaultdict(list)

    for action_row in actions:
        action_request: ActionExecutionRequest = action_row.data.request
        agent_id = action_row.data.agent_id

        # Parse the action
        action = ActionAdapter.validate_python(action_request.parameters)

        # Process SendMessage actions from customers to businesses with Payment messages
        if isinstance(action, SendMessage):
            if (
                "customer" in agent_id.lower()
                and "business" in action.to_agent_id.lower()
            ):
                # Check if the message is a Payment
                if isinstance(action.message, Payment):
                    payments[(action.from_agent_id, action.to_agent_id)].append(
                        action.message
                    )

    return payments


async def extract_agent_llm_traces(
    db_controller: BaseDatabaseController, db_name: str
) -> None:
    """Extract LLM logs by agent and save to markdown files.

    Creates:
    - 1 markdown file per customer containing their latest LLM log
    - 1 markdown file per business-customer conversation (from business perspective)

    Args:
        db_controller: Database controller
        db_name: Database name for output directory

    """
    # Load all agents
    agents = await db_controller.agents.get_all()

    customer_agents: dict[str, CustomerAgentProfile] = {}
    business_agents: dict[str, BusinessAgentProfile] = {}

    for agent_row in agents:
        agent_data = agent_row.data
        agent = MarketplaceAgentProfileAdapter.validate_python(agent_data.model_dump())

        if isinstance(agent, CustomerAgentProfile):
            customer_agents[agent.id] = agent
        elif isinstance(agent, BusinessAgentProfile):
            business_agents[agent.id] = agent

    print(
        f"Found {len(customer_agents)} customers and {len(business_agents)} businesses"
    )

    # Create output directory
    output_dir = Path(f"{db_name}-agent-llm-traces")
    output_dir.mkdir(exist_ok=True)

    # Create subdirectories
    customer_dir = output_dir / "customers"
    business_customer_dir = output_dir / "business-customer-conversations"
    customer_dir.mkdir(exist_ok=True)
    business_customer_dir.mkdir(exist_ok=True)

    # Extract customer logs
    print("\nExtracting customer LLM logs...")
    for customer_id, customer_profile in customer_agents.items():
        llm_log_result = await get_last_llm_log_for_agent(db_controller, customer_id)

        if llm_log_result is None:
            print(f"  No LLM logs found for customer: {customer_id}")
            continue

        llm_log, llm_timestamp = llm_log_result

        # Create markdown content
        markdown_content = create_markdown_content(
            customer_id, llm_log, customer_profile, llm_timestamp
        )

        # Save to markdown file
        safe_customer_id = customer_id.replace("/", "_").replace("\\", "_")
        output_file = customer_dir / f"{safe_customer_id}.md"

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        print(f"  Saved LLM log for customer '{customer_id}' to {output_file}")

    # Get business-customer pairs and payments
    print("\nExtracting business-customer conversation LLM logs...")
    business_customer_pairs = await get_business_customer_pairs(db_controller)
    customer_business_payments = await get_customer_business_payments(db_controller)

    # Track files with payments
    files_with_payments: list[str] = []

    for business_id, customer_ids in business_customer_pairs.items():
        business_profile = business_agents.get(business_id)

        # Create subdirectory for this business
        safe_business_id = business_id.replace("/", "_").replace("\\", "_")
        business_dir = business_customer_dir / safe_business_id
        business_dir.mkdir(exist_ok=True)

        for customer_id in customer_ids:
            llm_log_result = await get_last_llm_log_for_agent(
                db_controller, business_id
            )

            if llm_log_result is None:
                print(f"  No LLM logs found for business: {business_id}")
                continue

            llm_log, llm_timestamp = llm_log_result

            # Create markdown content with business-customer context
            customer_profile = customer_agents.get(customer_id)
            markdown_content = create_business_customer_markdown(
                business_id,
                customer_id,
                llm_log,
                business_profile,
                customer_profile,
                llm_timestamp,
            )

            # Save to markdown file in business subdirectory
            safe_customer_id = customer_id.replace("/", "_").replace("\\", "_")
            output_file = business_dir / f"{safe_business_id}_to_{safe_customer_id}.md"

            with open(output_file, "w", encoding="utf-8") as f:
                f.write(markdown_content)

            # Check if this conversation has payments
            if (customer_id, business_id) in customer_business_payments:
                # Store relative path from output_dir
                relative_path = output_file.relative_to(output_dir)
                files_with_payments.append(str(relative_path))

            print(
                f"  Saved business-customer log for '{business_id}' -> '{customer_id}' to {output_file}"
            )

    # Write the list of files with payments to a text file
    if files_with_payments:
        payments_list_file = output_dir / "conversations_with_payments.txt"
        with open(payments_list_file, "w", encoding="utf-8") as f:
            f.write("\n".join(sorted(files_with_payments)))
        print(
            f"\nCreated list of {len(files_with_payments)} conversations with payments: {payments_list_file}"
        )

    print(f"\nAll agent LLM traces saved to: {output_dir}")


def create_markdown_content(
    agent_id: str,
    llm_call_log: LLMCallLog,
    agent_profile: BusinessAgentProfile | CustomerAgentProfile | None,
    llm_timestamp: str,
) -> str:
    """Create markdown content for a customer's LLM log.

    Args:
        agent_id: The agent identifier
        llm_call_log: The structured LLM call log data
        agent_profile: The AgentProfile from the agents table
        llm_timestamp: Timestamp of the LLM log

    Returns:
        Formatted markdown string

    """
    lines = [
        f"# Customer: {agent_id}",
        "",
        f"Latest LLM log timestamp: {llm_timestamp}",
        "",
    ]

    # Add CustomerProfile if available
    if agent_profile and isinstance(agent_profile, CustomerAgentProfile):
        lines.extend(
            [
                "## Customer Profile",
                "",
                "| Field | Value |",
                "|-------|-------|",
                f"| ID | {agent_profile.id} |",
                f"| Name | {agent_profile.customer.name} |",
                f"| Request | {agent_profile.customer.request} |",
            ]
        )

        # Add menu features (requested items)
        if agent_profile.customer.menu_features:
            lines.extend(
                [
                    "",
                    "### Requested Menu Items",
                    "",
                    "| Item | Requested Price |",
                    "|------|----------------|",
                ]
            )
            for item, price in agent_profile.customer.menu_features.items():
                lines.append(f"| {item} | ${price} |")

        # Add amenity features (required amenities)
        if agent_profile.customer.amenity_features:
            lines.extend(
                [
                    "",
                    "### Required Amenities",
                    "",
                ]
            )
            amenities_str = ", ".join(agent_profile.customer.amenity_features)
            lines.append(f"Required: {amenities_str}")

        lines.extend(["", ""])

    # Add LLM call metadata
    lines.extend(
        [
            "## LLM Call Metadata",
            "",
            "| Field | Value |",
            "|-------|-------|",
            f"| Success | {llm_call_log.success} |",
        ]
    )

    if llm_call_log.model:
        lines.append(f"| Model | {llm_call_log.model} |")
    if llm_call_log.provider:
        lines.append(f"| Provider | {llm_call_log.provider} |")
    lines.append(f"| Duration | {llm_call_log.duration_ms}ms |")
    lines.append(f"| Token Count | {llm_call_log.token_count} |")
    if llm_call_log.error_message:
        lines.append(f"| Error Message | {llm_call_log.error_message} |")

    lines.extend(["", "## Prompt", ""])

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
                "## Response Format",
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


def create_business_customer_markdown(
    business_id: str,
    customer_id: str,
    llm_call_log: LLMCallLog,
    business_profile: BusinessAgentProfile | None,
    customer_profile: CustomerAgentProfile | None,
    llm_timestamp: str,
) -> str:
    """Create markdown content for a business-customer conversation.

    Args:
        business_id: The business agent identifier
        customer_id: The customer agent identifier
        llm_call_log: The structured LLM call log data from the business
        business_profile: The business AgentProfile
        customer_profile: The customer AgentProfile
        llm_timestamp: Timestamp of the LLM log

    Returns:
        Formatted markdown string

    """
    lines = [
        "# Business-Customer Conversation",
        "",
        f"Business: {business_id}",
        f"Customer: {customer_id}",
        "",
        f"Latest business LLM log timestamp: {llm_timestamp}",
        "",
    ]

    # Add BusinessProfile if available
    if business_profile:
        business = business_profile.business
        lines.extend(
            [
                "## Business Profile",
                "",
                "| Field | Value |",
                "|-------|-------|",
                f"| ID | {business_profile.id} |",
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

        lines.extend(["", ""])

    # Add CustomerProfile if available
    if customer_profile:
        customer = customer_profile.customer
        lines.extend(
            [
                "## Customer Profile",
                "",
                "| Field | Value |",
                "|-------|-------|",
                f"| ID | {customer_profile.id} |",
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

        lines.extend(["", ""])

    # Add LLM call metadata
    lines.extend(
        [
            "## Business LLM Call Metadata",
            "",
            "| Field | Value |",
            "|-------|-------|",
            f"| Success | {llm_call_log.success} |",
        ]
    )

    if llm_call_log.model:
        lines.append(f"| Model | {llm_call_log.model} |")
    if llm_call_log.provider:
        lines.append(f"| Provider | {llm_call_log.provider} |")
    lines.append(f"| Duration | {llm_call_log.duration_ms}ms |")
    lines.append(f"| Token Count | {llm_call_log.token_count} |")
    if llm_call_log.error_message:
        lines.append(f"| Error Message | {llm_call_log.error_message} |")

    lines.extend(["", "## Business Prompt", ""])

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
                "## Response Format",
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
            "## Business LLM Response",
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


async def run_extract_traces(db_path_or_schema: str, db_type: str = "postgres") -> None:
    """Run LLM trace extraction on the database.

    Args:
        db_path_or_schema: Path to SQLite database file or Postgres schema name
        db_type: Type of database ("sqlite" or "postgres")

    """
    if db_type == "sqlite":
        if not Path(db_path_or_schema).exists():
            raise FileNotFoundError(
                f"SQLite database file {db_path_or_schema} not found"
            )

        db_name = Path(db_path_or_schema).stem

        db_controller = SQLiteDatabaseController(db_path_or_schema)
        await db_controller.initialize()

        await extract_agent_llm_traces(db_controller, db_name)
    elif db_type == "postgres":
        async with connect_to_postgresql_database(
            schema=db_path_or_schema,
            host="localhost",
            port=5432,
            password="postgres",
            mode="existing",
        ) as db_controller:
            await extract_agent_llm_traces(db_controller, db_path_or_schema)
    else:
        raise ValueError(
            f"Unsupported database type: {db_type}. Must be 'sqlite' or 'postgres'."
        )
