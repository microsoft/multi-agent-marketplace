"""Optimal search implementation for the simple marketplace."""

import logging
import math

from magentic_marketplace.platform.database.base import BaseDatabaseController
from magentic_marketplace.platform.database.queries.agents import query as agent_query

from ...actions import Search, SearchResponse
from ...shared.models import Business, BusinessAgentProfile, Customer
from .utils import convert_agent_rows_to_businesses

logger = logging.getLogger(__name__)


def is_subset(customer: Customer, business: Business) -> bool:
    """Check if what the customer wants is completely available in the menu.

    This is used to implement optimal search - it only returns True for businesses
    that can completely fulfill the customer's order.

    Args:
        customer: Customer with desired menu items
        business: Business with available menu items

    Returns:
        True if business has all items customer wants, False otherwise

    """
    # Customer's desired menu items
    customer_items = set(customer.menu_features.keys())

    # Business's available menu items
    business_items = set(business.menu_features.keys())

    # Check if customer items is a subset of business items
    return customer_items.issubset(business_items)


async def execute_optimal_search(
    *,
    search: Search,
    customer: Customer,
    database: BaseDatabaseController,
) -> SearchResponse:
    """Execute optimal search that only returns businesses that can completely fulfill customer's order.

    This search algorithm filters businesses to only include those that have ALL
    the menu items the customer wants. This ensures the customer can get everything
    they need from a single business.

    Args:
        search: The search action containing query parameters
        customer: The customer profile with menu preferences
        database: Database controller for accessing data

    Returns:
        List of businesses that can completely fulfill the customer's order

    """
    # Get all business agents
    business_filter = agent_query(path="$.business", value=None, operator="!=")
    all_agent_rows = await database.agents.find(business_filter)

    # Convert to BusinessAgentProfile objects
    all_businesses = await convert_agent_rows_to_businesses(all_agent_rows)

    # Filter businesses using subset check - only keep businesses that have
    # all the menu items the customer wants
    filtered_businesses: list[BusinessAgentProfile] = []
    for business_profile in all_businesses:
        if is_subset(customer, business_profile.business):
            filtered_businesses.append(business_profile)

    # Sort by rating (descending) for consistent ordering
    filtered_businesses.sort(key=lambda b: b.business.rating, reverse=True)

    total_possible_results = len(filtered_businesses)
    paginated_businesses = filtered_businesses
    total_pages = 1

    if search.limit and search.limit > 0:
        start = (search.page - 1) * search.limit
        end = start + search.limit
        paginated_businesses = filtered_businesses[start:end]
        total_pages = math.ceil(len(filtered_businesses) / search.limit)

    return SearchResponse(
        businesses=paginated_businesses,
        search_algorithm=search.search_algorithm,
        total_possible_results=total_possible_results,
        total_pages=total_pages,
    )
