"""Query builders for SendMessage actions and message types."""

from magentic_marketplace.platform.database.queries.actions import (
    ActionsQuery,
    request_name,
    request_parameters,
)
from magentic_marketplace.platform.database.queries.base import Query

from ....actions import SendMessage


def all() -> ActionsQuery:
    """Query for all SendMessage actions."""
    return request_name(value=SendMessage.get_name(), operator="=")


def from_agent(from_agent_id: str, operator: str = "=") -> Query:
    """Query for SendMessage actions from specific agent."""
    return all() & request_parameters(
        path="from_agent_id", value=from_agent_id, operator=operator
    )


def to_agent(to_agent_id: str, operator: str = "=") -> Query:
    """Query for SendMessage actions to specific agent."""
    return all() & request_parameters(
        path="to_agent_id", value=to_agent_id, operator=operator
    )


def order_proposals() -> Query:
    """Query for SendMessage actions containing OrderProposal."""
    return all() & request_parameters(
        path="message.type", value="order_proposal", operator="="
    )


def order_proposal_id(proposal_id: str, operator: str = "=") -> Query:
    """Query for OrderProposal messages by proposal ID."""
    return order_proposals() & request_parameters(
        path="message.id", value=proposal_id, operator=operator
    )
