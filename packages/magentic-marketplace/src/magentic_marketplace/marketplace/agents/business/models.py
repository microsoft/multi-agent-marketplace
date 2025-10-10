"""Data models for the business agent."""

from typing import Literal

from pydantic import BaseModel, Field

from ...actions import OrderProposal, TextMessage


class ServiceTextMessageRequest(TextMessage):
    """Request for sending a text service message."""

    to_customer_id: str = Field(
        description="The id of the customer this message should be sent to."
    )


class ServiceOrderProposalMessageRequest(OrderProposal):
    """Request for sending an order proposal message."""

    to_customer_id: str = Field(
        description="The id of the customer this message should be sent to."
    )


class BusinessAction(BaseModel):
    """Actions the service agent can take."""

    action_type: Literal["text", "order_proposal"] = Field(
        description="Type of action to take"
    )

    text_message: ServiceTextMessageRequest | None = None
    order_proposal_message: ServiceOrderProposalMessageRequest | None = None


class BusinessSummary(BaseModel):
    """Summary of business operations."""

    business_id: str = Field(description="Business ID")
    business_name: str = Field(description="Business name")
    description: str = Field(description="Business description")
    rating: float = Field(description="Business rating")
    menu_items: int = Field(description="Number of menu items available")
    amenities: int = Field(description="Number of amenities offered")
    pending_proposals: int = Field(description="Number of pending proposals")
    confirmed_orders: int = Field(description="Number of confirmed orders")
    delivery_available: bool = Field(description="Whether delivery is available")
