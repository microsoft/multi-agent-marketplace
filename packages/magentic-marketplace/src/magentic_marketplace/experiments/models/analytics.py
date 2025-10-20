"""Pydantic models for analytics results."""

from typing import Literal

from pydantic import BaseModel


class CustomerSummary(BaseModel):
    """Summary statistics for a single customer."""

    customer_id: str
    customer_name: str
    messages_sent: int
    proposals_received: int
    payments_made: int
    searches_made: int
    utility: float
    needs_met: bool


class BusinessSummary(BaseModel):
    """Summary statistics for a single business."""

    business_id: str
    business_name: str
    messages_sent: int
    proposals_sent: int
    utility: float


class TransactionSummary(BaseModel):
    """Summary of transaction-related statistics."""

    order_proposals_created: int
    payments_made: int
    average_proposal_value: float | None = None
    average_paid_order_value: float | None = None
    total_invalid_proposals: int
    invalid_proposals_purchased: int


class AnalyticsResults(BaseModel):
    """Comprehensive analytics results for marketplace simulation."""

    # Basic simulation overview
    total_customers: int
    total_businesses: int
    total_actions_executed: int
    total_messages_sent: int

    # Action and message breakdowns
    action_breakdown: dict[str, int]
    message_type_breakdown: dict[str, int]

    # Transaction summary
    transaction_summary: TransactionSummary

    # Customer and business summaries
    customer_summaries: list[CustomerSummary]
    business_summaries: list[BusinessSummary]

    # LLM metrics
    llm_providers: list[str]
    llm_models: list[str]
    total_llm_calls: int
    failed_llm_calls: int

    # Final summary metrics
    customers_who_made_purchases: int
    customers_with_needs_met: int
    total_marketplace_customer_utility: float
    average_utility_per_active_customer: float | None = None
    purchase_completion_rate: float


class _BaseOrderProposalError(BaseModel):
    proposal_id: str
    business_agent_id: str
    customer_agent_id: str


class InvalidBusiness(_BaseOrderProposalError):
    """The OrderProposal was from a nonexistent business."""

    type: Literal["invalid_business"] = "invalid_business"

    @property
    def sort_key(self):
        """Return a key to sort errors of the same type."""
        return self.business_agent_id


class InvalidCustomer(_BaseOrderProposalError):
    """The OrderProposal was sent to a nonexistent customer."""

    type: Literal["invalid_customer"] = "invalid_customer"

    @property
    def sort_key(self):
        """Return a key to sort errors of the same type."""
        return self.customer_agent_id


class InvalidMenuItem(_BaseOrderProposalError):
    """The OrderProposal contained a menu item that was not actually on the menu."""

    type: Literal["invalid_menu_item"] = "invalid_menu_item"
    proposed_menu_item: str
    closest_menu_item: str
    closest_menu_item_distance: int

    @property
    def sort_key(self):
        """Return a key to sort errors of the same type."""
        return self.closest_menu_item_distance


class InvalidMenuItemPrice(_BaseOrderProposalError):
    """The OrderProposal reported a price that does not actually match the menu price."""

    type: Literal["invalid_menu_item_price"] = "invalid_menu_item_price"
    menu_item: str
    proposed_price: float
    actual_price: float

    @property
    def sort_key(self):
        """Return a key to sort errors of the same type."""
        return abs(self.actual_price - self.proposed_price)


class InvalidTotalPrice(_BaseOrderProposalError):
    """The OrderProposal's total_price does not equal the sum of the item prices."""

    type: Literal["invalid_total_price"] = "invalid_total_price"
    proposed_total_price: float
    calculated_total_price: float

    @property
    def sort_key(self):
        """Return a key to sort errors of the same type."""
        return abs(self.calculated_total_price - self.proposed_total_price)


OrderProposalError = (
    InvalidBusiness
    | InvalidCustomer
    | InvalidMenuItem
    | InvalidMenuItemPrice
    | InvalidTotalPrice
)
