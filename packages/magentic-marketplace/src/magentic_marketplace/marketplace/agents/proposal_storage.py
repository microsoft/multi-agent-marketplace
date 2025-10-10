"""Shared proposal storage for both business and customer agents."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from ..actions import OrderProposal


class ProposalInfo(BaseModel):
    """Information about a single proposal."""

    sender_id: str = Field(description="ID of the business that sent the proposal")
    created_at: str = Field(description="When the proposal was created (ISO format)")
    total_price: float = Field(description="Total price of the proposal")
    item_count: int = Field(description="Number of items in the proposal")


class ProposalSummary(BaseModel):
    """Summary of all received proposals."""

    total_proposals: int = Field(description="Total number of proposals received")
    proposals: list[ProposalInfo] = Field(description="List of proposal details")


class StoredOrderProposal(BaseModel):
    """A stored proposal with metadata that works for both business and customer perspectives."""

    business_id: str = Field(
        description="ID of the business (sender for customers, self for businesses)"
    )
    customer_id: str = Field(
        description="ID of the customer (recipient for businesses, self for customers)"
    )
    created_at: AwareDatetime = Field(
        description="When the proposal was created/received"
    )
    proposal: OrderProposal = Field(description="The actual order proposal")
    status: Literal["pending", "accepted", "rejected", "expired"] = Field(
        default="pending", description="Current status of the proposal"
    )
    notes: str | None = Field(
        default=None, description="Additional notes about the proposal"
    )

    @property
    def proposal_id(self) -> str:
        """Get the proposal ID from the OrderProposal."""
        return self.proposal.id

    def is_expired(self) -> bool:
        """Check if the proposal has expired."""
        return False
        # TODO: Revisit this once we are confident in LLM expiry_time generation.
        if self.proposal.expiry_time is None:
            return False
        return datetime.now(UTC) >= self.proposal.expiry_time

    def get_display_name_for_business(self) -> str:
        """Get a display name from business perspective."""
        items_summary = f"{len(self.proposal.items)} item(s)"
        return f"Proposal to {self.customer_id}: {items_summary} - ${self.proposal.total_price}"

    def get_display_name_for_customer(self) -> str:
        """Get a display name from customer perspective."""
        items_summary = f"{len(self.proposal.items)} item(s)"
        return f"Proposal from {self.business_id}: {items_summary} - ${self.proposal.total_price}"


class OrderProposalStorage(BaseModel):
    """Unified storage for order proposals that works for both business and customer agents."""

    proposals: dict[str, StoredOrderProposal] = Field(
        default_factory=dict, description="Stored proposals by ID"
    )
    customer_proposal_counts: dict[str, int] = Field(
        default_factory=dict,
        description="Count of proposals sent to each customer (business perspective)",
    )

    def add_proposal(
        self, proposal: OrderProposal, business_id: str, customer_id: str
    ) -> str:
        """Add a new proposal to storage.

        Args:
            proposal: The order proposal
            business_id: ID of the business
            customer_id: ID of the customer

        Returns:
            The proposal ID from the OrderProposal

        """
        stored_proposal = StoredOrderProposal(
            business_id=business_id,
            customer_id=customer_id,
            created_at=datetime.now(UTC),
            proposal=proposal,
        )
        self.proposals[proposal.id] = stored_proposal
        return proposal.id

    def get_proposal(self, proposal_id: str) -> StoredOrderProposal | None:
        """Get a proposal by ID."""
        return self.proposals.get(proposal_id)

    def get_proposals_by_customer(self, customer_id: str) -> list[StoredOrderProposal]:
        """Get all proposals for a specific customer."""
        return [
            proposal
            for proposal in self.proposals.values()
            if proposal.customer_id == customer_id
        ]

    def get_proposals_by_business(self, business_id: str) -> list[StoredOrderProposal]:
        """Get all proposals from a specific business."""
        return [
            proposal
            for proposal in self.proposals.values()
            if proposal.business_id == business_id
        ]

    def get_pending_proposals(self) -> list[StoredOrderProposal]:
        """Get all pending proposals (not expired, accepted, or rejected)."""
        return [
            proposal
            for proposal in self.proposals.values()
            if proposal.status == "pending" and not proposal.is_expired()
        ]

    def update_proposal_status(
        self,
        proposal_id: str,
        status: Literal["pending", "accepted", "rejected", "expired"],
    ) -> bool:
        """Update the status of a proposal.

        Args:
            proposal_id: ID of the proposal to update
            status: New status

        Returns:
            True if the proposal was found and updated, False otherwise

        """
        proposal = self.proposals.get(proposal_id)
        if proposal is None:
            return False
        proposal.status = status
        return True

    def count_proposals(self) -> int:
        """Get the total number of proposals."""
        return len(self.proposals)

    def count_pending_proposals(self) -> int:
        """Get the number of pending proposals."""
        return len(self.get_pending_proposals())

    def cleanup_expired_proposals(self) -> int:
        """Mark expired proposals as expired and return count."""
        expired_count = 0
        for proposal in self.proposals.values():
            if proposal.status == "pending" and proposal.is_expired():
                proposal.status = "expired"
                expired_count += 1
        return expired_count

    def get_proposal_summary(self) -> ProposalSummary:
        """Get a summary of all proposals."""
        proposal_infos = [
            ProposalInfo(
                sender_id=proposal.business_id,
                created_at=proposal.created_at.isoformat(),
                total_price=proposal.proposal.total_price,
                item_count=len(proposal.proposal.items),
            )
            for proposal in self.proposals.values()
        ]
        return ProposalSummary(
            total_proposals=len(proposal_infos),
            proposals=proposal_infos,
        )

    def get_proposal_ids_by_status(
        self, status: Literal["pending", "accepted", "rejected", "expired"]
    ) -> list[str]:
        """Get proposal IDs filtered by status."""
        return [
            proposal_id
            for proposal_id, proposal in self.proposals.items()
            if proposal.status == status
        ]
