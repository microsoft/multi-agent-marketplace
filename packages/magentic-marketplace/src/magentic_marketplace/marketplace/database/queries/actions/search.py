"""Query builders for Search actions."""

from magentic_marketplace.platform.database.queries.actions import (
    ActionsQuery,
    request_name,
    result_is_error,
)
from magentic_marketplace.platform.database.queries.base import Query

from ....actions import Search


def all() -> ActionsQuery:
    """Query for all Search actions."""
    return request_name(value=Search.get_name(), operator="=")


def successful() -> Query:
    """Query for successful Search actions."""
    return all() & result_is_error(value=False, operator="=")
