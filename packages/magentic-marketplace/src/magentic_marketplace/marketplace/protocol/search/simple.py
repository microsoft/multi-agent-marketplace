"""Simple search implementation for the simple marketplace."""

import logging
import math

from magentic_marketplace.platform.database.base import BaseDatabaseController
from magentic_marketplace.platform.database.queries.agents import query as agent_query
from magentic_marketplace.platform.database.queries.base import RangeQueryParams

from ...actions import Search, SearchResponse
from .utils import convert_agent_rows_to_businesses

logger = logging.getLogger(__name__)


async def execute_simple_search(
    search: Search, database: BaseDatabaseController
) -> SearchResponse:
    """Execute simple search returning top-rated businesses."""
    # Create query to find agents with business metadata
    business_filter = agent_query(path="$.business", value=None, operator="!=")

    # Use database controller to find matching agents
    params = RangeQueryParams()
    agent_rows = await database.agents.find(business_filter, params)
    # Convert to business agents and sort by rating
    businesses = await convert_agent_rows_to_businesses(agent_rows)
    businesses.sort(key=lambda b: b.business.rating, reverse=True)

    total_possible_results = len(businesses)
    paginated_businesses = businesses
    total_pages = 1

    if search.limit and search.limit > 0:
        start = (search.page - 1) * search.limit
        end = start + search.limit
        paginated_businesses = businesses[start:end]
        total_pages = math.ceil(len(businesses) / search.limit)

    return SearchResponse(
        businesses=paginated_businesses,
        search_algorithm=search.search_algorithm,
        total_possible_results=total_possible_results,
        total_pages=total_pages,
    )
