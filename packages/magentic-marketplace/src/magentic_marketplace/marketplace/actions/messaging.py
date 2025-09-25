"""Messaging actions for the simple marketplace."""

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, Field
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
    """An order proposal message."""

    type: Literal["order_proposal"] = "order_proposal"
    id: str = Field(description="The unique id of this proposal", min_length=1)
    items: list[OrderItem] = Field(
        description="List of items in the proposal", min_length=1
    )
    total_price: float = Field(description="Total price for the entire order", ge=0)
    special_instructions: str | None = Field(
        default=None, description="Special instructions or notes for the order"
    )
    estimated_delivery: str | None = Field(
        default=None,
        description="Estimated delivery time (e.g., '30 minutes', 'Tomorrow at 2pm')",
    )
    expiry_time: AwareDatetime | None = Field(
        default=None, description="When this proposal expires. Timezone is required."
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
