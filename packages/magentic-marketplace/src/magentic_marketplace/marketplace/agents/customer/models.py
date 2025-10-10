"""Data models for the customer agent."""

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from magentic_marketplace.platform.shared.models import ActionExecutionResult

from ...actions.actions import FetchMessagesResponse, SearchResponse
from ...actions.messaging import Payment, TextMessage


@dataclass
class CustomerSendMessageResults:
    """Internal dataclass for storing the results of sending messages in CustomerAction format."""

    text_message_results: list[tuple[bool, str]] = field(default_factory=list)
    pay_message_results: list[tuple[bool, str]] = field(default_factory=list)


class AssistantTextMessageRequest(TextMessage):
    """Request for sending a text message."""

    to_business_id: str = Field(
        description="The id of the business this message should be sent to."
    )


class AssistantPayMessageRequest(Payment):
    """Request for sending a payment message to accept an order proposal."""

    to_business_id: str = Field(
        description="The id of the business this message should be sent to."
    )


class Messages(BaseModel):
    """Messages to be sent to services.

    Use text messages for general inquiries and pay messages to accept order proposals.
    """

    text_messages: list[AssistantTextMessageRequest]
    pay_messages: list[AssistantPayMessageRequest]


class CustomerAction(BaseModel):
    """Actions the Assistant can take.

    Use:
        - search_businesses to search for businesses.
        - send_messages to send messages to some businesses.
        - check_messages to check for new responses from businesses.
        - end_transaction if you have paid for an order or received confirmation.

    Do not end if you haven't completed a purchase transaction.
    """

    action_type: Literal[
        "search_businesses", "send_messages", "check_messages", "end_transaction"
    ] = Field(description="Type of action to take")
    reason: str = Field(description="Reason for taking this action")

    # Search-specific fields
    search_query: str | None = Field(
        default=None,
        description="Search query for businesses.",
    )
    search_page: int = Field(
        default=1,
        description="Page number to retrieve for the search results (default: 1)",
    )

    messages: Messages | None = Field(
        default=None,
        description="Messages container with text and pay message lists",
    )

    @model_validator(mode="after")
    def validate_model(self):
        """Validate the BaseModel structure."""
        if self.action_type == "search_businesses":
            if not self.search_query:
                raise ValueError(
                    "search_query is required when action_type is search_businesses"
                )
        elif self.action_type == "send_messages":
            if not self.messages:
                raise ValueError(
                    "messages must have at least one element when action_type is send_messages"
                )

        return self


class CustomerSummary(BaseModel):
    """Summary of customer transactions and activity."""

    customer_id: str = Field(description="Customer ID")
    customer_name: str = Field(description="Customer name")
    request: str = Field(description="Original customer request")
    profile: dict[str, Any] = Field(description="Full customer profile data")
    proposals_received: int = Field(description="Number of proposals received")
    transactions_completed: int = Field(description="Number of completed transactions")
    completed_proposal_ids: list[str] = Field(description="IDs of completed proposals")


CustomerActionResult = (
    ActionExecutionResult
    | SearchResponse
    | CustomerSendMessageResults
    | FetchMessagesResponse
)
