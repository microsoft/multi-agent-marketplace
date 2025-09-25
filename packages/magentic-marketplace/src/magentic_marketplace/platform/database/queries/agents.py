"""Query helpers for agents table operations."""

from typing import Any, Literal

from .base import JSONQuery
from .base import query as _query


class AgentsQuery(JSONQuery):
    """Query class for agents table JSON data."""

    table: Literal["agents"] = "agents"
    column: Literal["data"] = "data"


def query(*, path: str, value: Any = None, operator: str) -> AgentsQuery:
    """Create a query instance for agents table."""
    return _query(AgentsQuery, path=path, value=value, operator=operator)


# Agent field query helpers
def id(*, value: Any = None, operator: str) -> AgentsQuery:
    """Query agents by id field."""
    return query(path="$.id", value=value, operator=operator)


def metadata(*, path: str, value: Any = None, operator: str) -> AgentsQuery:
    """Query agents by metadata field with path."""
    return query(path=f"$.metadata.{path}", value=value, operator=operator)
