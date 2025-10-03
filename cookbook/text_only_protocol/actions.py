"""Actions for text-only marketplace protocol."""

from typing import Literal

from magentic_marketplace.platform.shared.models import BaseAction
from pydantic import AwareDatetime, BaseModel, Field

from .messaging import TextMessage


class SendTextMessage(BaseAction):
    """Send a text message to another agent."""

    type: Literal["send_text_message"] = "send_text_message"
    from_agent_id: str = Field(description="ID of the agent sending the message")
    to_agent_id: str = Field(description="ID of the agent receiving the message")
    created_at: AwareDatetime = Field(description="When the message was created")
    message: TextMessage = Field(description="The text message to send")


class CheckMessages(BaseAction):
    """Check text messages received by this agent."""

    type: Literal["check_messages"] = "check_messages"
    limit: int | None = Field(
        default=None, description="Maximum number of messages to retrieve"
    )
    offset: int | None = Field(
        default=None, description="Number of messages to skip for pagination"
    )


class ReceivedTextMessage(BaseModel):
    """A text message as received by an agent with metadata."""

    from_agent_id: str = Field(description="ID of the agent who sent the message")
    to_agent_id: str = Field(description="ID of the agent who received the message")
    created_at: AwareDatetime = Field(description="When the message was created")
    message: TextMessage = Field(description="The actual message content")


class CheckMessagesResponse(BaseModel):
    """Response from checking messages."""

    messages: list[ReceivedTextMessage] = Field(description="List of received messages")
    has_more: bool = Field(description="Whether there are more messages available")
