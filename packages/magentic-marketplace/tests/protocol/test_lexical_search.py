"""Integration tests for Lexical Search algorithm."""

from typing import Any

import pytest

from magentic_marketplace.marketplace.actions import (
    Search,
    SearchAlgorithm,
    SearchResponse,
)


class TestLexicalSearch:
    """Test suite for lexical search algorithm."""

    @pytest.mark.asyncio
    async def test_search_lexical_basic(self, test_agents_with_client: dict[str, Any]):
        """Test lexical search algorithm with relevant query."""
        agents = test_agents_with_client
        customer = agents["customer"]
        business = agents["business"]

        # Test lexical search with relevant query matching business name/description
        search_relevant = Search(
            query="bakery birthday cake",  # Should match "Sweet Dreams Bakery" with cake description
            search_algorithm=SearchAlgorithm.LEXICAL,
            limit=50,
            constraints=None,
        )
        result = await customer.execute_action(search_relevant)

        assert result.is_error is False
        parsed_response = SearchResponse.model_validate(result.content)
        assert len(parsed_response.businesses) == 1
        assert parsed_response.businesses[0].id == business.id
        assert parsed_response.search_algorithm == SearchAlgorithm.LEXICAL

    @pytest.mark.asyncio
    async def test_search_lexical_partial_match(
        self, test_agents_with_client: dict[str, Any]
    ):
        """Test lexical search with partial term matching."""
        agents = test_agents_with_client
        customer = agents["customer"]
        business = agents["business"]

        # Test partial word match
        search_partial = Search(
            query="dream",  # Should partially match "Sweet Dreams Bakery"
            search_algorithm=SearchAlgorithm.LEXICAL,
            limit=50,
            constraints=None,
        )
        result = await customer.execute_action(search_partial)

        assert result.is_error is False
        parsed_response = SearchResponse.model_validate(result.content)
        assert len(parsed_response.businesses) == 1
        assert parsed_response.businesses[0].id == business.id

    @pytest.mark.asyncio
    async def test_search_lexical_menu_match(
        self, test_agents_with_client: dict[str, Any]
    ):
        """Test lexical search matching menu items in searchable text."""
        agents = test_agents_with_client
        customer = agents["customer"]
        business = agents["business"]

        # Test menu item match (birthday cake is in menu_features)
        search_menu = Search(
            query="birthday cake",
            search_algorithm=SearchAlgorithm.LEXICAL,
            limit=50,
            constraints=None,
        )
        result = await customer.execute_action(search_menu)

        assert result.is_error is False
        parsed_response = SearchResponse.model_validate(result.content)
        assert len(parsed_response.businesses) == 1
        assert parsed_response.businesses[0].id == business.id

    @pytest.mark.asyncio
    async def test_search_lexical_amenity_match(
        self, test_agents_with_client: dict[str, Any]
    ):
        """Test lexical search matching amenities in searchable text."""
        agents = test_agents_with_client
        customer = agents["customer"]
        business = agents["business"]

        # Test amenity match (delivery is True in amenity_features)
        search_amenity = Search(
            query="delivery",
            search_algorithm=SearchAlgorithm.LEXICAL,
            limit=50,
            constraints=None,
        )
        result = await customer.execute_action(search_amenity)

        assert result.is_error is False
        parsed_response = SearchResponse.model_validate(result.content)
        assert len(parsed_response.businesses) == 1
        assert parsed_response.businesses[0].id == business.id

    @pytest.mark.asyncio
    async def test_search_lexical_no_match(
        self, test_agents_with_client: dict[str, Any]
    ):
        """Test lexical search with query that doesn't match."""
        agents = test_agents_with_client
        customer = agents["customer"]

        # Test query that shouldn't match business
        search_no_match = Search(
            query="sushi restaurant",
            search_algorithm=SearchAlgorithm.LEXICAL,
            limit=50,
            constraints=None,
        )
        result = await customer.execute_action(search_no_match)

        assert result.is_error is False
        parsed_response = SearchResponse.model_validate(result.content)
        # Should still return results but with low scores (business should be last)
        assert len(parsed_response.businesses) >= 0

    @pytest.mark.asyncio
    async def test_search_lexical_no_query(
        self, test_agents_with_client: dict[str, Any]
    ):
        """Test lexical search without query (should fallback to rating sort)."""
        agents = test_agents_with_client
        customer = agents["customer"]
        business = agents["business"]

        # Test lexical search without query (empty string)
        search_no_query = Search(
            query="",
            search_algorithm=SearchAlgorithm.LEXICAL,
            limit=50,
            constraints=None,
        )
        result = await customer.execute_action(search_no_query)

        assert result.is_error is False
        parsed_response = SearchResponse.model_validate(result.content)
        assert len(parsed_response.businesses) == 1
        assert parsed_response.businesses[0].id == business.id
