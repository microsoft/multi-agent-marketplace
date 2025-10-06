"""Query builders for SendMessageAction actions and message types."""

from typing import get_args

from magentic_marketplace.marketplace.actions.actions import SendOrderProposal
from magentic_marketplace.platform.database.queries.actions import (
    request_action,
    request_parameters,
)
from magentic_marketplace.platform.database.queries.base import Query
from magentic_marketplace.platform.shared.models import BaseAction

from ....actions import SendMessageAction


def all() -> Query:
    """Query for all SendMessageAction actions."""
    query: Query | None = None
    actions: tuple[type[BaseAction]] = get_args(SendMessageAction)
    for action_type in actions:
        action_query = request_action(action=action_type, operator="=")
        if query is None:
            query = action_query
        else:
            query |= action_query

    if query is None:
        raise RuntimeError(
            "CRITICAL: Failed to create query for all SendMessageAction types."
        )

    return query


def from_agent(from_agent_id: str, operator: str = "=") -> Query:
    """Query for SendMessageAction actions from specific agent."""
    return all() & request_parameters(
        path="from_agent_id", value=from_agent_id, operator=operator
    )


def to_agent(to_agent_id: str, operator: str = "=") -> Query:
    """Query for SendMessageAction actions to specific agent."""
    return all() & request_parameters(
        path="to_agent_id", value=to_agent_id, operator=operator
    )


def order_proposals() -> Query:
    """Query for SendMessageAction actions containing OrderProposal."""
    return request_action(action=SendOrderProposal, operator="=")


def order_proposal_id(proposal_id: str, operator: str = "=") -> Query:
    """Query for OrderProposal messages by proposal ID."""
    return order_proposals() & request_parameters(
        path="id", value=proposal_id, operator=operator
    )
