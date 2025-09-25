"""Query helpers for actions table operations."""

from typing import Any, Literal

from .base import JSONQuery
from .base import query as _query


class ActionsQuery(JSONQuery):
    """Query class for actions table JSON data."""

    table: Literal["actions"] = "actions"
    column: Literal["data"] = "data"


def query(*, path: str, value: Any = None, operator: str) -> ActionsQuery:
    """Create a query instance for actions table."""
    return _query(ActionsQuery, path=path, value=value, operator=operator)


# Agent ID query helper
def agent_id(*, value: Any = None, operator: str) -> ActionsQuery:
    """Query actions by agent_id field."""
    return query(path="$.agent_id", value=value, operator=operator)


# Request field query helpers
def request_name(*, value: Any = None, operator: str) -> ActionsQuery:
    """Query actions by request name field."""
    return query(path="$.request.name", value=value, operator=operator)


def request_parameters(*, path: str, value: Any = None, operator: str) -> ActionsQuery:
    """Query actions by request parameters field with path."""
    return query(path=f"$.request.parameters.{path}", value=value, operator=operator)


def request_metadata(*, path: str, value: Any = None, operator: str) -> ActionsQuery:
    """Query actions by request metadata field with path."""
    return query(path=f"$.request.metadata.{path}", value=value, operator=operator)


# Result field query helpers
def result_content(*, path: str, value: Any = None, operator: str) -> ActionsQuery:
    """Query actions by result content field with path."""
    return query(path=f"$.result.content.{path}", value=value, operator=operator)


def result_is_error(*, value: Any = None, operator: str) -> ActionsQuery:
    """Query actions by result is_error field."""
    return query(path="$.result.is_error", value=value, operator=operator)


def result_metadata(*, path: str, value: Any = None, operator: str) -> ActionsQuery:
    """Query actions by result metadata field with path."""
    return query(path=f"$.result.metadata.{path}", value=value, operator=operator)
