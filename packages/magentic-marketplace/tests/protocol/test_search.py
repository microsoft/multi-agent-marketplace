"""Integration tests for Search action."""

from typing import Any

import pytest

from magentic_marketplace.marketplace.actions import (
    Search,
    SearchAlgorithm,
    SearchResponse,
)
from magentic_marketplace.marketplace.shared.models import SearchConstraints


class TestSearch:
    """Focused test suite for Search action."""

    @pytest.mark.asyncio
    async def test_search_simple(self, test_agents_with_client: dict[str, Any]):
        """Test simple search algorithm (ignores constraints, sorts by rating)."""
        agents = test_agents_with_client
        customer = agents["customer"]
        business = agents["business"]

        search = Search(
            query="ignored",
            search_algorithm=SearchAlgorithm.SIMPLE,
            limit=50,
            constraints=None,
        )
        result = await customer.execute_action(search)

        assert result.is_error is False
        parsed_response = SearchResponse.model_validate(result.content)
        assert len(parsed_response.businesses) == 1
        assert parsed_response.businesses[0].id == business.id
        assert parsed_response.total_possible_results == 1
        assert parsed_response.total_pages == 1

    @pytest.mark.asyncio
    async def test_search_text_filtering(self, test_agents_with_client: dict[str, Any]):
        """Test filtered search with text queries (name/description matching)."""
        agents = test_agents_with_client
        customer = agents["customer"]
        business = agents["business"]

        # Test name matching
        search_name = Search(
            query="Bakery",  # Should match "Sweet Dreams Bakery"
            search_algorithm=SearchAlgorithm.FILTERED,
            limit=50,
            constraints=None,
        )
        result = await customer.execute_action(search_name)
        assert result.is_error is False
        parsed_response = SearchResponse.model_validate(result.content)
        assert len(parsed_response.businesses) == 1
        assert parsed_response.businesses[0].id == business.id

        # Test no match
        search_no_match = Search(
            query="Nonexistent",
            search_algorithm=SearchAlgorithm.FILTERED,
            limit=50,
            constraints=None,
        )
        result = await customer.execute_action(search_no_match)
        assert result.is_error is False
        parsed_response = SearchResponse.model_validate(result.content)
        assert len(parsed_response.businesses) == 0

    @pytest.mark.asyncio
    async def test_search_rating_constraints(
        self, test_agents_with_client: dict[str, Any]
    ):
        """Test filtered search with rating constraints."""
        agents = test_agents_with_client
        customer = agents["customer"]
        business = agents["business"]

        # Test rating threshold that includes business (rating 4.5)
        search_include = Search(
            query="",
            search_algorithm=SearchAlgorithm.FILTERED,
            limit=50,
            constraints=SearchConstraints(rating_threshold=4.0),
        )
        result = await customer.execute_action(search_include)
        assert result.is_error is False
        parsed_response = SearchResponse.model_validate(result.content)
        assert len(parsed_response.businesses) == 1
        assert parsed_response.businesses[0].id == business.id

        # Test rating threshold that excludes business
        search_exclude = Search(
            query="",
            search_algorithm=SearchAlgorithm.FILTERED,
            limit=50,
            constraints=SearchConstraints(rating_threshold=5.0),
        )
        result = await customer.execute_action(search_exclude)
        assert result.is_error is False
        parsed_response = SearchResponse.model_validate(result.content)
        assert len(parsed_response.businesses) == 0

    @pytest.mark.asyncio
    async def test_search_menu_constraints(
        self, test_agents_with_client: dict[str, Any]
    ):
        """Test filtered search with menu item constraints."""
        agents = test_agents_with_client
        customer = agents["customer"]
        business = agents["business"]

        # Test menu item that exists (birthday cake)
        search_include = Search(
            query="",
            search_algorithm=SearchAlgorithm.FILTERED,
            limit=50,
            constraints=SearchConstraints(menu_items=["birthday cake"]),
        )
        result = await customer.execute_action(search_include)
        assert result.is_error is False
        parsed_response = SearchResponse.model_validate(result.content)
        assert len(parsed_response.businesses) == 1
        assert parsed_response.businesses[0].id == business.id

        # Test menu item that doesn't exist (sushi)
        search_exclude = Search(
            query="",
            search_algorithm=SearchAlgorithm.FILTERED,
            limit=50,
            constraints=SearchConstraints(menu_items=["sushi"]),
        )
        result = await customer.execute_action(search_exclude)
        assert result.is_error is False
        parsed_response = SearchResponse.model_validate(result.content)
        assert len(parsed_response.businesses) == 0

    @pytest.mark.asyncio
    async def test_search_amenity_constraints(
        self, test_agents_with_client: dict[str, Any]
    ):
        """Test filtered search with amenity constraints."""
        agents = test_agents_with_client
        customer = agents["customer"]
        business = agents["business"]

        # Test amenity that exists (delivery)
        search_include = Search(
            query="",
            search_algorithm=SearchAlgorithm.FILTERED,
            limit=50,
            constraints=SearchConstraints(amenity_features=["delivery"]),
        )
        result = await customer.execute_action(search_include)
        assert result.is_error is False
        parsed_response = SearchResponse.model_validate(result.content)
        assert len(parsed_response.businesses) == 1
        assert parsed_response.businesses[0].id == business.id

        # Test amenity that doesn't exist (parking)
        search_exclude = Search(
            query="",
            search_algorithm=SearchAlgorithm.FILTERED,
            limit=50,
            constraints=SearchConstraints(amenity_features=["parking"]),
        )
        result = await customer.execute_action(search_exclude)
        assert result.is_error is False
        parsed_response = SearchResponse.model_validate(result.content)
        assert len(parsed_response.businesses) == 0

    @pytest.mark.asyncio
    async def test_search_multiple_constraints(
        self, test_agents_with_client: dict[str, Any]
    ):
        """Test filtered search with multiple combined constraints."""
        agents = test_agents_with_client
        customer = agents["customer"]
        business = agents["business"]

        # Test multiple constraints that all match
        search_all_match = Search(
            query="",
            search_algorithm=SearchAlgorithm.FILTERED,
            limit=50,
            constraints=SearchConstraints(
                rating_threshold=4.0,
                amenity_features=["delivery"],
                menu_items=["birthday cake"],
            ),
        )
        result = await customer.execute_action(search_all_match)
        assert result.is_error is False
        parsed_response = SearchResponse.model_validate(result.content)
        assert len(parsed_response.businesses) == 1
        assert parsed_response.businesses[0].id == business.id

        # Test multiple constraints where one fails
        search_one_fails = Search(
            query="",
            search_algorithm=SearchAlgorithm.FILTERED,
            limit=50,
            constraints=SearchConstraints(
                rating_threshold=4.0,
                amenity_features=["delivery"],
                menu_items=["sushi"],  # This doesn't exist
            ),
        )
        result = await customer.execute_action(search_one_fails)
        assert result.is_error is False
        parsed_response = SearchResponse.model_validate(result.content)
        assert len(parsed_response.businesses) == 0

    @pytest.mark.rnr
    @pytest.mark.asyncio
    async def test_search_rnr_basic(self, test_agents_with_client: dict[str, Any]):
        """Test RNR search algorithm with semantic ranking."""
        agents = test_agents_with_client
        customer = agents["customer"]
        business = agents["business"]

        # Test RNR search with relevant query
        search_relevant = Search(
            query="bakery birthday cake",  # Should match "Sweet Dreams Bakery" with cake description
            search_algorithm=SearchAlgorithm.RNR,
            limit=50,
            constraints=None,
        )
        result = await customer.execute_action(search_relevant)

        assert result.is_error is False
        parsed_response = SearchResponse.model_validate(result.content)
        assert len(parsed_response.businesses) == 1
        assert parsed_response.businesses[0].id == business.id
        assert parsed_response.search_algorithm == SearchAlgorithm.RNR

    @pytest.mark.rnr
    @pytest.mark.asyncio
    async def test_search_rnr_no_query(self, test_agents_with_client: dict[str, Any]):
        """Test RNR search algorithm without query (should fallback to rating sort)."""
        agents = test_agents_with_client
        customer = agents["customer"]
        business = agents["business"]

        # Test RNR search without query (empty string)
        search_no_query = Search(
            query="",
            search_algorithm=SearchAlgorithm.RNR,
            limit=50,
            constraints=None,
        )
        result = await customer.execute_action(search_no_query)

        assert result.is_error is False
        parsed_response = SearchResponse.model_validate(result.content)
        assert len(parsed_response.businesses) == 1
        assert parsed_response.businesses[0].id == business.id

    @pytest.mark.rnr
    @pytest.mark.asyncio
    async def test_search_rnr_embedding_computation(
        self, test_agents_with_client: dict[str, Any]
    ):
        """Test that RNR search computes and stores embeddings."""
        agents = test_agents_with_client
        customer = agents["customer"]

        # Run RNR search twice to test embedding caching
        search = Search(
            query="restaurant food",
            search_algorithm=SearchAlgorithm.RNR,
            limit=50,
            constraints=None,
        )

        # First search should compute embeddings
        result1 = await customer.execute_action(search)
        assert result1.is_error is False

        # Second search should use cached embeddings
        result2 = await customer.execute_action(search)
        assert result2.is_error is False

        # Results should be consistent
        response1 = SearchResponse.model_validate(result1.content)
        response2 = SearchResponse.model_validate(result2.content)
        assert len(response1.businesses) == len(response2.businesses)
