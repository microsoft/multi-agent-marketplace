"""Pydantic models for analytics results."""

from pydantic import BaseModel


class CustomerSummary(BaseModel):
    """Summary statistics for a single customer."""

    customer_id: str
    customer_name: str
    messages_sent: int
    proposals_received: int
    proposals_in_last_llm_call: list[str]
    """The OrderProposal ids that were in the final LLM call made by this customer.
    i.e. how many of the received proposals did the customer actually see."""
    payments_made: int
    searches_made: int
    utility: float
    optimal_utility: float
    utility_gap: float
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


class SuboptimalCustomersSummary(BaseModel):
    """Summary of customers that achieved suboptimal utility.

    Breaks down the suboptimal utility gaps into categories {needs_met, needs_not_met} x {saw_all_proposals, missing_some_proposals}

    Useful for identifying whether the LLM just did a bad job of picking the right proposal, or acted too fast and never saw the right proposal.

    needs_met_utility_gap = needs_met_all_proposals_utility_gap + needs_met_missing_proposals_utility_gap
    needs_not_met_utility_gap = needs_not_met_all_proposals_utility_gap + needs_not_met_missing_proposals_utility_gap
    total_utility_gap = needs_not_met_utility_gap + needs_met_utility_gap

    """

    total_suboptimal_customers: int
    needs_met: list[CustomerSummary]
    needs_met_utility_gap: float
    needs_met_all_proposals_utility_gap: float
    needs_met_missing_proposals_utility_gap: float
    needs_not_met: list[CustomerSummary]
    needs_not_met_utility_gap: float
    needs_not_met_all_proposals_utility_gap: float
    needs_not_met_missing_proposals_utility_gap: float
    total_utility_gap: float


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

    # Behavior summary
    businesses_who_sent_proposals: int
    customers_who_did_not_see_all_proposals: int
    """The number of customers who did not include all received proposals in their final LLM call."""
    suboptimal_customers_summary: SuboptimalCustomersSummary

    # Final summary metrics
    customers_who_made_purchases: int
    customers_with_needs_met: int
    total_marketplace_customer_utility: float
    optimal_marketplace_customer_utility: float
    average_utility_per_active_customer: float | None = None
    purchase_completion_rate: float
