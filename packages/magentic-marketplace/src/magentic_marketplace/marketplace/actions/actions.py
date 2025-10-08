"""Messaging actions for the simple marketplace."""

from enum import Enum
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, Field
from pydantic.type_adapter import TypeAdapter

from magentic_marketplace.platform.shared.models import BaseAction

from ..shared.models import BusinessAgentProfile, SearchConstraints
from .messaging import Message


class SendMessage(BaseAction):
    """Send a message to another agent."""

    type: Literal["send_message"] = "send_message"
    from_agent_id: str = Field(description="ID of the agent sending the message")
    to_agent_id: str = Field(description="ID of the agent to send the message to")
    created_at: AwareDatetime = Field(description="When the message was created")
    message: Message = Field(description="The message to send")


class FetchMessages(BaseAction):
    """Get messages received by this agent."""

    type: Literal["fetch_messages"] = "fetch_messages"
    from_agent_id: str | None = Field(
        default=None, description="Filter by sender agent ID"
    )
    limit: int | None = Field(
        default=None, description="Maximum number of messages to retrieve"
    )
    offset: int | None = Field(
        default=None, description="Number of messages to skip for pagination"
    )
    after: AwareDatetime | None = Field(
        default=None, description="Only return messages sent after this timestamp"
    )
    after_index: int | None = Field(
        default=None, description="Only return messages with index greater than this"
    )


class ReceivedMessage(BaseModel):
    """A message as received by an agent with metadata."""

    from_agent_id: str = Field(description="ID of the agent who sent the message")
    to_agent_id: str = Field(description="ID of the agent who received the message")
    created_at: AwareDatetime = Field(description="When the message was created")
    message: Message = Field(description="The actual message content")
    index: int = Field(description="The row index of the message")


class FetchMessagesResponse(BaseModel):
    """Response from fetching messages."""

    messages: list[ReceivedMessage] = Field(description="List of received messages")
    has_more: bool = Field(description="Whether there are more messages available")


class SearchAlgorithm(str, Enum):
    """Available search algorithms."""

    SIMPLE = "simple"
    RNR = "rnr"
    FILTERED = "filtered"
    LEXICAL = "lexical"
    OPTIMAL = "optimal"


class Search(BaseAction):
    """Search for businesses in the marketplace."""

    type: Literal["search"] = "search"
    query: str = Field(description="Search query")
    search_algorithm: SearchAlgorithm = Field(description="Search algorithm to use")
    constraints: SearchConstraints | None = Field(
        default=None, description="Search constraints"
    )
    limit: int = Field(default=10, description="Maximum number of results to return")
    page: int = Field(default=1, description="Page number for pagination")


class SearchResponse(BaseModel):
    """Result of a business search operation."""

    businesses: list[BusinessAgentProfile]
    search_algorithm: str
    total_possible_results: int | None = Field(
        default=None, description="Total number of possible results"
    )
    total_pages: int | None = Field(
        default=None, description="Total number of pages available"
    )


# Action is a union type of the action types
Action = Annotated[SendMessage | FetchMessages | Search, Field(discriminator="type")]

# Type adapter for Action for serialization/deserialization
ActionAdapter: TypeAdapter[Action] = TypeAdapter(Action)
