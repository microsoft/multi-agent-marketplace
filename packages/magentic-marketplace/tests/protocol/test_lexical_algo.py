"""Unit tests for lexical ranking algorithm."""

import pytest

from magentic_marketplace.marketplace.protocol.search.lexical_algo import (
    lexical_rank,
    shingle_overlap_score,
)
from magentic_marketplace.marketplace.shared.models import (
    Business,
    BusinessAgentProfile,
)


class TestShingleOverlapScore:
    """Test suite for shingle overlap scoring."""

    def test_exact_match(self):
        """Test exact string match gives high score."""
        score = shingle_overlap_score("bakery", "bakery")
        assert score == 1.0

    def test_partial_match(self):
        """Test partial match gives score between 0 and 1."""
        score = shingle_overlap_score("sweet dreams bakery", "sweet dreams")
        assert 0.0 < score < 1.0

    def test_no_match(self):
        """Test no match gives score of 0."""
        score = shingle_overlap_score("sushi", "bakery")
        assert score == 0.0

    def test_case_insensitive(self):
        """Test that scoring is case insensitive."""
        score1 = shingle_overlap_score("Bakery", "bakery")
        score2 = shingle_overlap_score("bakery", "bakery")
        assert score1 == score2 == 1.0


class TestBusinessSearchableText:
    """Test suite for Business.get_searchable_text() method."""

    @pytest.fixture
    def sample_business(self) -> Business:
        """Create a sample business for testing."""
        return Business(
            id="test_bakery",
            name="Sweet Dreams Bakery",
            description="Artisan bakery with custom cakes",
            rating=4.5,
            progenitor_customer="customer_000",
            menu_features={
                "birthday cake": 58.0,
                "cupcake": 5.0,
            },
            amenity_features={
                "delivery": True,
                "parking": False,
                "wifi": True,
            },
            min_price_factor=0.8,
        )

    def test_default_searchable_text(self, sample_business: Business):
        """Test default searchable text includes name, description, and menu items."""
        text = sample_business.get_searchable_text()

        # Should include name and description
        assert "Sweet Dreams Bakery" in text
        assert "Artisan bakery with custom cakes" in text

        # Should include menu item names
        assert "birthday cake" in text
        assert "cupcake" in text

        # Should NOT include prices (default index_menu_prices=False)
        assert "58.0" not in text
        assert "5.0" not in text

        # Should NOT include amenities (default index_amenities=False)
        assert "delivery" not in text
        assert "wifi" not in text

    def test_searchable_text_without_name(self, sample_business: Business):
        """Test searchable text excludes name when index_name=False."""
        text = sample_business.get_searchable_text(index_name=False)

        # Should NOT include name
        assert "Sweet Dreams Bakery" not in text

        # Should still include description and menu items
        assert "Artisan bakery with custom cakes" in text
        assert "birthday cake" in text

    def test_searchable_text_with_menu_prices(self, sample_business: Business):
        """Test searchable text includes prices when index_menu_prices=True."""
        text = sample_business.get_searchable_text(index_menu_prices=True)

        # Should include menu item names and prices
        assert "birthday cake" in text
        assert "58.0" in text
        assert "cupcake" in text
        assert "5.0" in text

    def test_searchable_text_with_amenities(self, sample_business: Business):
        """Test searchable text includes amenities when index_amenities=True."""
        text = sample_business.get_searchable_text(index_amenities=True)

        # Should include amenities that are True
        assert "delivery" in text
        assert "wifi" in text

        # Should NOT include amenities that are False
        assert "parking" not in text


class TestLexicalRank:
    """Test suite for lexical ranking function."""

    @pytest.fixture
    def sample_businesses(self) -> list[BusinessAgentProfile]:
        """Create sample businesses for ranking tests."""
        bakery = Business(
            id="bakery_1",
            name="Sweet Dreams Bakery",
            description="Artisan bakery specializing in custom cakes",
            rating=4.5,
            progenitor_customer="customer_000",
            menu_features={"birthday cake": 58.0, "cupcake": 5.0},
            amenity_features={"delivery": True, "wifi": True, "parking": False},
            min_price_factor=0.8,
        )

        restaurant = Business(
            id="restaurant_1",
            name="Sushi Paradise",
            description="Japanese restaurant with fresh sushi",
            rating=4.8,
            progenitor_customer="customer_001",
            menu_features={"sushi roll": 12.0, "ramen": 15.0},
            amenity_features={"delivery": True, "wifi": False, "parking": True},
            min_price_factor=0.9,
        )

        cafe = Business(
            id="cafe_1",
            name="Dream Coffee",
            description="Cozy cafe with artisan coffee",
            rating=4.2,
            progenitor_customer="customer_002",
            menu_features={"latte": 5.0, "croissant": 4.0},
            amenity_features={"delivery": False, "wifi": True, "parking": False},
            min_price_factor=0.7,
        )

        return [
            BusinessAgentProfile.from_business(bakery),
            BusinessAgentProfile.from_business(restaurant),
            BusinessAgentProfile.from_business(cafe),
        ]

    def test_rank_by_name_match(self, sample_businesses: list[BusinessAgentProfile]):
        """Test ranking prioritizes name matches."""
        ranked = lexical_rank("bakery", sample_businesses)

        # "Sweet Dreams Bakery" should rank first
        assert ranked[0].id == "bakery_1"

    def test_rank_by_description_match(
        self, sample_businesses: list[BusinessAgentProfile]
    ):
        """Test ranking by description content."""
        ranked = lexical_rank("sushi", sample_businesses)

        # "Sushi Paradise" should rank first
        assert ranked[0].id == "restaurant_1"

    def test_rank_by_menu_item_match(
        self, sample_businesses: list[BusinessAgentProfile]
    ):
        """Test ranking by menu items."""
        ranked = lexical_rank("birthday cake", sample_businesses)

        # Bakery with birthday cake should rank first
        assert ranked[0].id == "bakery_1"

    def test_rank_without_name_indexing(
        self, sample_businesses: list[BusinessAgentProfile]
    ):
        """Test ranking with index_name=False."""
        # Query for "bakery" which appears in the name
        ranked = lexical_rank("bakery", sample_businesses, index_name=False)

        # With name excluded, "bakery" appears in description of bakery_1
        # but scores should be different than with name included
        # The exact ranking depends on description matches
        assert len(ranked) == 3  # All businesses should be in results

    def test_rank_with_amenity_indexing(
        self, sample_businesses: list[BusinessAgentProfile]
    ):
        """Test ranking with amenities included in searchable text."""
        ranked = lexical_rank("delivery", sample_businesses, index_amenities=True)

        # Both bakery and restaurant have delivery, so they should rank higher
        # than cafe which doesn't have delivery
        top_two_ids = {ranked[0].id, ranked[1].id}
        assert "bakery_1" in top_two_ids
        assert "restaurant_1" in top_two_ids
        assert ranked[2].id == "cafe_1"

    def test_rank_with_menu_prices(self, sample_businesses: list[BusinessAgentProfile]):
        """Test ranking with menu prices included."""
        # Search for a specific price
        ranked = lexical_rank("58", sample_businesses, index_menu_prices=True)

        # Bakery with birthday cake at 58.0 should rank first
        assert ranked[0].id == "bakery_1"

    def test_rank_partial_word_match(
        self, sample_businesses: list[BusinessAgentProfile]
    ):
        """Test ranking with partial word matches."""
        ranked = lexical_rank("dream", sample_businesses)

        # Both "Sweet Dreams Bakery" and "Dream Coffee" contain "dream"
        # They should rank higher than "Sushi Paradise"
        assert ranked[2].id == "restaurant_1"
