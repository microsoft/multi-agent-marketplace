"""Filtered search implementation for the simple marketplace."""

import math

from magentic_marketplace.platform.database.base import BaseDatabaseController
from magentic_marketplace.platform.database.queries.agents import (
    query as agent_query,
)
from magentic_marketplace.platform.database.queries.base import (
    Query,
    RangeQueryParams,
)

from ...actions import Search, SearchResponse
from ...shared.models import SearchConstraints
from .utils import convert_agent_rows_to_businesses


async def execute_filtered_search(
    search: Search,
    database: BaseDatabaseController,
) -> SearchResponse:
    """Execute filtered search using constraints and text matching."""
    # Start with base business filter
    query = agent_query(path="$.business", value=None, operator="!=")

    # Add text search filters
    if search.query:
        name_query = agent_query(
            path="$.business.name", value=search.query, operator="like"
        )
        desc_query = agent_query(
            path="$.business.description", value=search.query, operator="like"
        )
        text_query = name_query | desc_query
        query = query & text_query

    # Add constraint filters
    if search.constraints:
        query = _add_constraint_query(query, search.constraints)

    # Execute query without limiting so we can compute total counts
    params = RangeQueryParams()
    agent_rows = await database.agents.find(query, params)

    # Convert and sort results
    businesses = await convert_agent_rows_to_businesses(agent_rows)
    businesses.sort(key=lambda b: b.business.rating, reverse=True)

    total_possible_results = len(businesses)
    paginated_businesses = businesses
    total_pages = 1

    if search.limit and search.limit > 0:
        start = (search.page - 1) * search.limit
        end = start + search.limit
        paginated_businesses = businesses[start:end]
        total_pages = math.ceil(total_possible_results / search.limit)

    return SearchResponse(
        businesses=paginated_businesses,
        search_algorithm=search.search_algorithm,
        total_possible_results=total_possible_results,
        total_pages=total_pages,
    )


def _add_constraint_query(input_query: Query, constraints: SearchConstraints) -> Query:
    """Build a query object from search constraints."""
    # Rating threshold filter
    if constraints.rating_threshold is not None:
        rating_query = agent_query(
            path="$.business.rating",
            value=constraints.rating_threshold,
            operator=">=",
        )
        input_query &= rating_query

    # Amenity features filter
    if constraints.amenity_features:
        for amenity in constraints.amenity_features:
            amenity_query = agent_query(
                path=f"$.business.amenity_features.{amenity}",
                value=True,
                operator="=",
            )
            input_query &= amenity_query

    # Menu items filter
    if constraints.menu_items:
        for menu_item in constraints.menu_items:
            menu_query = agent_query(
                path=f"$.business.menu_features.{menu_item}",
                value=None,
                operator="!=",
            )
            input_query &= menu_query

    return input_query
