"""Query helpers for logs table operations."""

from typing import Any, Literal

from .base import JSONQuery
from .base import query as _query


class LogQuery(JSONQuery):
    """Query class for logs table JSON data."""

    table: Literal["logs"] = "logs"
    column: Literal["data"] = "data"


def query(*, path: str, value: Any = None, operator: str) -> LogQuery:
    """Create a query instance for logs table."""
    return _query(LogQuery, path=path, value=value, operator=operator)


# Log field query helpers
def level(*, value: Any = None, operator: str) -> LogQuery:
    """Query logs by level field."""
    return query(path="$.level", value=value, operator=operator)


def name(*, value: Any = None, operator: str) -> LogQuery:
    """Query logs by name field."""
    return query(path="$.name", value=value, operator=operator)


def message(*, value: Any = None, operator: str) -> LogQuery:
    """Query logs by message field."""
    return query(path="$.message", value=value, operator=operator)


def data(*, path: str, value: Any = None, operator: str) -> LogQuery:
    """Query logs by data field with path."""
    return query(path=f"$.data.{path}", value=value, operator=operator)


def metadata(*, path: str, value: Any = None, operator: str) -> LogQuery:
    """Query logs by metadata field with path."""
    return query(path=f"$.metadata.{path}", value=value, operator=operator)
