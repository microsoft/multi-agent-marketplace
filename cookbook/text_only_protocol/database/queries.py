"""Database query helpers for text-only protocol.

These helpers create composable queries for filtering actions stored in the database.
They use JSONPath syntax to query nested JSON fields in the actions table.

JSONPath syntax: The path "$.request.parameters.to_agent_id" means:
  $                    - root of the JSON document
  .request             - the "request" field
  .parameters          - the "parameters" field inside request
  .to_agent_id         - the "to_agent_id" field inside parameters

Queries can be combined using the & operator to create complex filters.
Example: to_agent("bob") & from_agent("alice") & action_type("send_text_message")
"""

from typing import Any, Literal

from magentic_marketplace.platform.database.queries.base import JSONQuery
from magentic_marketplace.platform.database.queries.base import query as _query


class TextProtocolQuery(JSONQuery):
    """Query class for text protocol actions table JSON data."""

    table: Literal["actions"] = "actions"
    column: Literal["data"] = "data"


def query(*, path: str, value: Any = None, operator: str) -> TextProtocolQuery:
    """Create a query instance for text protocol actions.

    Args:
        path: JSONPath expression (e.g., "$.request.parameters.to_agent_id")
        value: Value to match against
        operator: Comparison operator (e.g., "=", ">", "<")

    Returns:
        Query object that can be combined with other queries using &
    """
    return _query(TextProtocolQuery, path=path, value=value, operator=operator)


def to_agent(agent_id: str) -> TextProtocolQuery:
    """Filter messages sent to a specific agent.

    Queries the nested JSON path: $.request.parameters.to_agent_id
    """
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
