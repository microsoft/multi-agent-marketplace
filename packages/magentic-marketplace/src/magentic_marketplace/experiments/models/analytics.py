"""Pydantic models for analytics results."""

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

    # Final summary metrics
    customers_who_made_purchases: int
    customers_with_needs_met: int
    total_marketplace_customer_utility: float
    average_utility_per_active_customer: float | None = None
    purchase_completion_rate: float
