"""Query builders for LLM call logs."""

from magentic_marketplace.platform.database.queries.base import Query
from magentic_marketplace.platform.database.queries.logs import LogQuery, data


def all() -> LogQuery:
    """Query for all LLM call logs."""
    return data(path="type", value="llm_call", operator="=")


def by_status(status: str, operator: str = "=") -> Query:
    """Query for LLM calls with specific status (SUCCESS/ERROR)."""
    return all() & data(path="status", value=status, operator=operator)


def failed() -> Query:
    """Query for failed LLM calls."""
    return by_status("ERROR")
