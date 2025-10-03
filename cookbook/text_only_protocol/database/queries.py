"""Database query helpers for text-only protocol."""

from typing import Any, Literal

from magentic_marketplace.platform.database.queries.base import JSONQuery
from magentic_marketplace.platform.database.queries.base import query as _query


class TextProtocolQuery(JSONQuery):
    """Query class for text protocol actions table JSON data."""

    table: Literal["actions"] = "actions"
    column: Literal["data"] = "data"


def query(*, path: str, value: Any = None, operator: str) -> TextProtocolQuery:
    """Create a query instance for text protocol actions."""
    return _query(TextProtocolQuery, path=path, value=value, operator=operator)


def to_agent(agent_id: str) -> TextProtocolQuery:
    """Filter messages sent to a specific agent."""
    return query(
        path="$.request.parameters.to_agent_id",
        value=agent_id,
        operator="=",
    )


def from_agent(agent_id: str) -> TextProtocolQuery:
    """Filter messages sent from a specific agent."""
    return query(
        path="$.request.parameters.from_agent_id",
        value=agent_id,
        operator="=",
    )


def action_type(action_type_name: str) -> TextProtocolQuery:
    """Filter by action type."""
    return query(
        path="$.request.parameters.type",
        value=action_type_name,
        operator="=",
    )
