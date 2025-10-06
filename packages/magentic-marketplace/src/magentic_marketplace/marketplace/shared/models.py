"""Shared models for the simple marketplace."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

from magentic_marketplace.platform.shared.models import AgentProfile


class Customer(BaseModel):
    """Customer with required menu items and amenities."""

    type: Literal["customer"] = "customer"

    id: str = Field(description="Customer ID")
    name: str = Field(description="Customer name")
    request: str = Field(description="Customer request/inquiry")
    menu_features: dict[str, float] = Field(
        description="Menu item name -> requested price"
    )
    amenity_features: list[str] = Field(description="Required amenities")


class Business(BaseModel):
    """Business with menu items and amenities."""

    type: Literal["business"] = "business"

    id: str = Field(description="Business ID")
    name: str = Field(description="Business name")
    description: str = Field(description="Business description")
    rating: float = Field(description="Business rating")
    progenitor_customer: str = Field(
        description="ID of customer that inspired this business"
    )
    menu_features: dict[str, float] = Field(description="Menu item name -> price")
    amenity_features: dict[str, bool] = Field(description="Amenity name -> available")
    min_price_factor: float = Field(description="Minimum price factor for pricing")

    def get_searchable_text(
        self,
        index_name: bool = True,
        index_menu_prices: bool = False,
        index_amenities: bool = False,
    ) -> str:
        """Format the business metadata for ranking.

        Args:
            business (BusinessMetadata): The business metadata to format.
            index_name (bool): Whether to include the business name in the formatted output.
            index_menu_prices (bool): Whether to include menu item prices in the formatted output.
            index_amenities (bool): Whether to include amenities in the formatted output.

        Returns:
            str: The formatted business metadata.

        """
        if index_name:
            formatted_business = (self.name).strip() + ", "
        else:
            formatted_business = ""

        formatted_business += self.description.strip() + ", "

        # Add in menu item descriptors
        for item_name, item_price in self.menu_features.items():
            if index_menu_prices:
                formatted_business += f"({item_name.strip()}: {item_price}), "
            else:
                formatted_business += f"{item_name.strip()}, "

        if index_amenities:
            # Add in amenities
            for feature, value in self.amenity_features.items():
                if value:
                    formatted_business += f"{feature.strip()}, "

        return formatted_business


MarketplaceParticipantType = Annotated[Customer | Business, Field(discriminator="type")]
MarketplaceParticipantAdapter: TypeAdapter[MarketplaceParticipantType] = TypeAdapter(
    MarketplaceParticipantType
)


class BusinessAgentProfile(AgentProfile):
    """Profile data for business agents."""

    business: Business

    @classmethod
    def from_business(cls, business: Business, metadata: dict[str, Any] | None = None):
        """Create BusinessAgentProfile from Business data."""
        final_metadata = metadata or {}
        final_metadata["type"] = "business"
        return cls(id=business.id, business=business, metadata=final_metadata)


class CustomerAgentProfile(AgentProfile):
    """Profile data for customer agents."""

    customer: Customer

    @classmethod
    def from_customer(cls, customer: Customer, metadata: dict[str, Any] | None = None):
        """Create CustomerAgentProfile from Customer data."""
        final_metadata = metadata or {}
        final_metadata["type"] = "customer"
        return cls(id=customer.id, customer=customer, metadata=final_metadata)


MarketplaceAgentProfileType = BusinessAgentProfile | CustomerAgentProfile
MarketplaceAgentProfileAdapter: TypeAdapter[MarketplaceAgentProfileType] = TypeAdapter(
    MarketplaceAgentProfileType
)


class SearchConstraints(BaseModel):
    """Constraints for business search queries."""

    rating_threshold: float | None = Field(
        default=None,
        description="Minimum rating threshold",
    )
    amenity_features: list[str] | None = Field(
        default=None,
        description="Required amenity_features",
    )
    menu_items: list[str] | None = Field(
        default=None,
        description="Required menu_features",
    )
