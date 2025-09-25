"""Query builders for agents resource."""

from typing import Any

from ...queries.agents import AgentsQuery, id, metadata


def name(agent_name: str) -> AgentsQuery:
    """Create query for agent name."""
    return id(value=agent_name, operator="=")


def name_contains(text: str) -> AgentsQuery:
    """Create query for agent names containing specific text."""
    return id(value=f"%{text}%", operator="LIKE")


def agent_metadata(key: str, value: Any) -> AgentsQuery:
    """Create query for agent metadata."""
    return metadata(path=key, value=value, operator="=")
