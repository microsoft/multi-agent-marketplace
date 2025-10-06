"""Messaging actions for the simple marketplace."""

from enum import Enum
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, Field
from pydantic.type_adapter import TypeAdapter

from magentic_marketplace.platform.shared.models import BaseAction

from ..shared.models import BusinessAgentProfile, SearchConstraints


class _BaseSendMessage(BaseAction):
    """Send a message to another agent."""

    from_agent_id: str = Field(description="ID of the agent sending the message")
    to_agent_id: str = Field(description="ID of the agent to send the message to")
    created_at: AwareDatetime = Field(description="When the message was created")


class SendTextMessage(_BaseSendMessage):
    """A text message."""

    type: Literal["send_text_message"] = "send_text_message"
    content: str = Field(description="Text content of the message")


class OrderItem(BaseModel):
    """An item in an order with quantity and pricing."""

    id: str = Field(description="Menu item ID from the business")
    item_name: str = Field(description="Name of the item")
    quantity: int = Field(description="Quantity ordered", ge=1)
    unit_price: float = Field(description="Price per unit", ge=0)


class SendOrderProposal(_BaseSendMessage):
    """An order proposal message."""

    type: Literal["send_order_proposal"] = "send_order_proposal"
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


class SendPayment(_BaseSendMessage):
    """A payment message to accept an order proposal."""

    type: Literal["send_payment"] = "send_payment"
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


class SearchAlgorithm(str, Enum):
    """Available search algorithms."""

    SIMPLE = "simple"
    RNR = "rnr"
    FILTERED = "filtered"


class Search(BaseAction):
    """Search for businesses in the marketplace."""

    type: Literal["search"] = "search"
    query: str = Field(description="Search query")
    search_algorithm: SearchAlgorithm = Field(description="Search algorithm to use")
    constraints: SearchConstraints | None = Field(
        default=None, description="Search constraints"
    )
    limit: int = Field(default=10, description="Maximum number of results to return")


class SearchResponse(BaseModel):
    """Result of a business search operation."""

    businesses: list[BusinessAgentProfile]
    search_algorithm: str


SendMessageAction = SendTextMessage | SendPayment | SendOrderProposal
_SendMessageActionDiscriminated = Annotated[
    SendMessageAction,
    Field(discriminator="type"),
]

SendMessageActionAdapter: TypeAdapter[_SendMessageActionDiscriminated] = TypeAdapter(
    _SendMessageActionDiscriminated
)

# Action is a union type of the action types
Action = Annotated[
    SendMessageAction | FetchMessages | Search,
    Field(discriminator="type"),
]

# Type adapter for Action for serialization/deserialization
ActionAdapter: TypeAdapter[Action] = TypeAdapter(Action)


class FetchMessagesResponse(BaseModel):
    """Response from fetching messages."""

    messages: list[SendMessageAction] = Field(description="List of received messages")
    has_more: bool = Field(description="Whether there are more messages available")
