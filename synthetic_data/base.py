"""Base types for the synthetic customer and business generation."""

from pydantic import BaseModel


class ItemFeature(BaseModel):
    """Menu item feature with name and price distribution parameters."""

    name: str
    mean_price: float
    price_stddev: float


class Customer(BaseModel):
    """Customer with required menu items and amenities."""

    id: str
    name: str
    request: str
    menu_features: dict[str, float]  # item name -> requested price
    amenity_features: list[str]


class Business(BaseModel):
    """Business with menu items and amenities."""

    id: str
    name: str
    description: str
    rating: float
    progenitor_customer: str
    menu_features: dict[str, float]  # item name -> price
    amenity_features: dict[str, bool]  # amenity name -> available
    min_price_factor: float
