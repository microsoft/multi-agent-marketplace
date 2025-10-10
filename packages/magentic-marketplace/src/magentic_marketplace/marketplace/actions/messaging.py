"""Messaging actions for the simple marketplace."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field
from pydantic.type_adapter import TypeAdapter


class OrderItem(BaseModel):
    """An item in an order with quantity and pricing."""

    id: str = Field(description="Menu item ID from the business")
    item_name: str = Field(description="Name of the item")
    quantity: int = Field(description="Quantity ordered", ge=1)
    unit_price: float = Field(description="Price per unit", ge=0)


class TextMessage(BaseModel):
    """A text message."""

    type: Literal["text"] = "text"
    content: str = Field(description="Text content of the message")


class OrderProposal(BaseModel):
    """Order proposal details sent by service agents to customers."""

    type: Literal["order_proposal"] = "order_proposal"
    id: str = Field(description="The unique id of this proposal", min_length=1)
    items: list[OrderItem] = Field(
        min_length=1,
        description="Required; the list of OrderItem objects with item_name, quantity, and unit_price",
    )
    total_price: float = Field(description="Required; total price for the entire order")
    special_instructions: str | None = Field(
        default=None, description="Optional; any special requests or notes"
    )
    estimated_delivery: str | None = Field(
        default=None, description="Optional; estimated delivery time"
    )
    expiry_time: str | None = Field(
        default=None, description="Optional; when this proposal expires"
    )


class Payment(BaseModel):
    """A payment message to accept an order proposal."""

    type: Literal["payment"] = "payment"
    proposal_message_id: str = Field(
        description="ID of the message containing the order proposal to accept"
    )
    payment_method: str | None = Field(
        default=None,
        description="Payment method to use (e.g., 'credit_card', 'cash', 'digital_wallet')",
    )
    delivery_address: str | None = Field(
        default=None, description="Delivery address if different from customer profile"
    )
    payment_message: str | None = Field(
        default=None, description="Additional message to include with the payment"
    )


# Message is a union type of the message types
Message = Annotated[TextMessage | OrderProposal | Payment, Field(discriminator="type")]

# Type adapter for Message for serialization/deserialization
MessageAdapter: TypeAdapter[Message] = TypeAdapter(Message)
