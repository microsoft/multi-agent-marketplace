"""Query builders for FetchMessages actions."""

from magentic_marketplace.platform.database.queries.actions import (
    ActionsQuery,
    request_name,
)

from ....actions import FetchMessages


def all() -> ActionsQuery:
    """Query for all FetchMessages actions."""
    return request_name(value=FetchMessages.get_name(), operator="=")
