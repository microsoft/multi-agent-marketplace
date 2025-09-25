"""Simple search implementation for the simple marketplace."""

from magentic_marketplace.platform.database.base import BaseDatabaseController
from magentic_marketplace.platform.database.queries.agents import query as agent_query
from magentic_marketplace.platform.database.queries.base import RangeQueryParams

from ...actions import Search
from ...shared.models import BusinessAgentProfile
from .utils import convert_agent_rows_to_businesses


async def execute_simple_search(
    search: Search, database: BaseDatabaseController
) -> list[BusinessAgentProfile]:
    """Execute simple search returning top-rated businesses."""
    # Create query to find agents with business metadata
    business_filter = agent_query(path="$.business", value=None, operator="!=")

    # Use database controller to find matching agents
    params = RangeQueryParams(limit=search.limit)
    agent_rows = await database.agents.find(business_filter, params)
    # Convert to business agents and sort by rating
    businesses = await convert_agent_rows_to_businesses(agent_rows)
    businesses.sort(key=lambda b: b.business.rating, reverse=True)

    return businesses[: search.limit]
