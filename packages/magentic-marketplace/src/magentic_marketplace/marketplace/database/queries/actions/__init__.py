"""Database query builders for simple marketplace actions."""

from magentic_marketplace.platform.database.queries.base import Query

from . import fetch_messages, search, send_message


def all() -> Query:
    """Return all action rows."""
    return fetch_messages.all() | search.all() | send_message.all()


__all__ = [
    "fetch_messages",
    "search",
    "send_message",
]
