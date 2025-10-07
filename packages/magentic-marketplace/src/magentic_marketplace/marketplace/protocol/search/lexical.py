"""Lexical search implementation for the simple marketplace."""

import logging

from magentic_marketplace.platform.database.base import BaseDatabaseController
from magentic_marketplace.platform.database.queries.agents import query as agent_query
from magentic_marketplace.platform.database.queries.base import RangeQueryParams

from ...actions import Search
from ...shared.models import BusinessAgentProfile
from .utils import convert_agent_rows_to_businesses

logger = logging.getLogger(__name__)


async def execute_lexical_search(
    search: Search,
    database: BaseDatabaseController,
) -> list[BusinessAgentProfile]:
    """Execute lexical search using shingle overlap ranking."""

    # Get all business agents
    business_filter = agent_query(path="$.business", value=None, operator="!=")
    all_agent_rows = await database.agents.find(business_filter, RangeQueryParams())

    # Convert to BusinessAgentProfile objects
    businesses = await convert_agent_rows_to_businesses(all_agent_rows)

    # Rating rank before lexical rank to help with:
    # 1. Tie breaking in lexical search
    # 2. Handle sort in no-query case
    businesses = sorted(
        businesses,
        key=lambda b: b.business.rating,
        reverse=True,
    )

    # Rank by lexical similarity if query provided
    if search.query:
        from .lexical_algo import lexical_rank

        businesses = lexical_rank(search.query, businesses)

    # Apply limit
    return businesses[: search.limit] if search.limit else businesses
