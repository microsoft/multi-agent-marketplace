"""Data models for the customer agent."""

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from ...shared.models import SearchConstraints


class CustomerAction(BaseModel):
    """Actions the Assistant can take."""

    action_type: Literal[
        "search_businesses", "send_messages", "check_messages", "end_transaction"
    ] = Field(description="Type of action to take")
    reason: str = Field(description="Reason for taking this action")

    # Search-specific fields
    search_query: str | None = Field(
        None,
        description="Search query for businesses. Required when action_type is 'search_businesses'",
    )
    search_constraints: SearchConstraints | None = Field(
        None,
        description="Search constraints. Optional when action_type is 'search_businesses'.",
    )

    # Send messages-specific fields
    target_business_ids: list[str] | None = Field(
        None,
        description="Business IDs to send messages to. Required when action_type is 'send_messages'.",
    )
    message_content: str | None = Field(
        None,
        description="Content of text message to send. Required when action_type is 'send_messages'.",
    )

    # Payment-specific fields
    proposal_to_accept: str | None = Field(
        None,
        description="Proposal ID to accept with payment. Required when action_type is 'end_transaction'.",
    )

    @model_validator(mode="after")
    def validate_model(self):
        """Validate the BaseModel structure."""
        if self.action_type == "search_businesses":
            if not self.search_query and not self.search_constraints:
                raise ValueError(
                    "At least one of search_query or search_constraints is required when action_type is search_businesses"
                )
        elif self.action_type == "send_messages":
            if not self.target_business_ids:
                raise ValueError(
                    "target_business_ids must contain at least one element when action_type is send_messages"
                )
            if not self.message_content:
                raise ValueError(
                    "message_content must not be empty when action_type is send_messages"
                )
        elif self.action_type == "end_transaction":
            if not self.proposal_to_accept:
                raise ValueError(
                    "proposal_to_accept must not be empty when action_type is end_transaction"
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
