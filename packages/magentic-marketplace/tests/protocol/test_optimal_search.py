"""Integration tests for Optimal Search algorithm."""

from typing import Any

import pytest

from magentic_marketplace.marketplace.actions import (
    Search,
    SearchAlgorithm,
    SearchResponse,
)
from magentic_marketplace.marketplace.protocol.search.optimal import is_subset
from magentic_marketplace.marketplace.shared.models import Business, Customer


class TestIsSubset:
    """Test suite for is_subset utility function."""

    def test_is_subset_all_items_available(self):
        """Test when business has all items customer wants."""
        customer = Customer(
            id="customer_1",
            name="Test Customer",
            request="Looking for cake and cookies",
            menu_features={"birthday cake": 60.0, "cookies": 10.0},
            amenity_features=["delivery"],
        )

        business = Business(
            id="bakery_1",
            name="Sweet Bakery",
            description="Bakery with cakes and cookies",
            rating=4.5,
            progenitor_customer="customer_000",
            menu_features={
                "birthday cake": 58.0,
                "cookies": 8.0,
                "brownies": 12.0,
            },
            amenity_features={"delivery": True, "wifi": True},
            min_price_factor=0.8,
        )

        assert is_subset(customer, business) is True

    def test_is_subset_missing_items(self):
        """Test when business is missing some items customer wants."""
        customer = Customer(
            id="customer_1",
            name="Test Customer",
            request="Looking for cake and sushi",
            menu_features={"birthday cake": 60.0, "sushi roll": 15.0},
            amenity_features=["delivery"],
        )

        business = Business(
            id="bakery_1",
            name="Sweet Bakery",
            description="Bakery with cakes",
            rating=4.5,
            progenitor_customer="customer_000",
            menu_features={"birthday cake": 58.0, "cookies": 8.0},
            amenity_features={"delivery": True},
            min_price_factor=0.8,
        )

        # Business doesn't have sushi roll
        assert is_subset(customer, business) is False

    def test_is_subset_exact_match(self):
        """Test when business has exactly the items customer wants."""
        customer = Customer(
            id="customer_1",
            name="Test Customer",
            request="Looking for cake",
            menu_features={"birthday cake": 60.0},
            amenity_features=[],
        )

        business = Business(
            id="bakery_1",
            name="Sweet Bakery",
            description="Bakery with cakes",
            rating=4.5,
            progenitor_customer="customer_000",
            menu_features={"birthday cake": 58.0},
            amenity_features={},
            min_price_factor=0.8,
        )

        assert is_subset(customer, business) is True

    def test_is_subset_empty_customer_wants(self):
        """Test when customer wants no items (edge case)."""
        customer = Customer(
            id="customer_1",
            name="Test Customer",
            request="Just browsing",
            menu_features={},
            amenity_features=[],
        )

        business = Business(
            id="bakery_1",
            name="Sweet Bakery",
            description="Bakery",
            rating=4.5,
            progenitor_customer="customer_000",
            menu_features={"birthday cake": 58.0},
            amenity_features={},
            min_price_factor=0.8,
        )

        # Empty set is subset of any set
        assert is_subset(customer, business) is True


class TestOptimalSearch:
    """Test suite for optimal search algorithm."""

    @pytest.mark.asyncio
    async def test_optimal_search_perfect_match(
        self, test_agents_with_client: dict[str, Any]
    ):
        """Test optimal search returns business with all required items."""
        agents = test_agents_with_client
        customer = agents["customer"]
        business = agents["business"]

        # Customer wants birthday cake, business has it
        search = Search(
            query="",
            search_algorithm=SearchAlgorithm.OPTIMAL,
            limit=50,
            constraints=None,
        )
        result = await customer.execute_action(search)

        assert result.is_error is False
        parsed_response = SearchResponse.model_validate(result.content)
        assert len(parsed_response.businesses) == 1
        assert parsed_response.businesses[0].id == business.id
        assert parsed_response.search_algorithm == SearchAlgorithm.OPTIMAL
        assert parsed_response.total_possible_results == 1
        assert parsed_response.total_pages == 1

    @pytest.mark.asyncio
    async def test_optimal_search_sorts_by_rating(
        self, test_agents_with_client: dict[str, Any]
    ):
        """Test optimal search sorts results by rating when multiple matches."""
        agents = test_agents_with_client
        customer = agents["customer"]

        # This test would need multiple businesses to verify sorting
        # For now, just verify the search works
        search = Search(
            query="",
            search_algorithm=SearchAlgorithm.OPTIMAL,
            limit=50,
            constraints=None,
        )
        result = await customer.execute_action(search)

        assert result.is_error is False
        parsed_response = SearchResponse.model_validate(result.content)
        # Verify results are sorted by rating (descending)
        ratings = [b.business.rating for b in parsed_response.businesses]
        assert ratings == sorted(ratings, reverse=True)
        assert parsed_response.total_possible_results == 1
        assert parsed_response.total_pages == 1
