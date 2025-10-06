"""Search action implementation for the simple marketplace."""

import logging

from magentic_marketplace.platform.database.base import BaseDatabaseController
from magentic_marketplace.platform.shared.models import ActionExecutionResult

from ...actions import Search, SearchAlgorithm, SearchResponse
from .filtered import execute_filtered_search
from .lexical import execute_lexical_search
from .rnr import execute_rnr_search
from .simple import execute_simple_search

logger = logging.getLogger(__name__)


async def execute_search(
    search: Search,
    database: BaseDatabaseController,
) -> ActionExecutionResult:
    """Execute a search action to find businesses in the marketplace.

    This function implements the business search functionality using the database
    controller's proper abstractions instead of raw SQL queries.

    Args:
        search: The search action containing query parameters
        database: Database controller for accessing data

    Returns:
        ActionExecutionResult with the action result

    """
    try:
        # Execute the appropriate search algorithm
        if search.search_algorithm == SearchAlgorithm.FILTERED:
            businesses = await execute_filtered_search(search, database)
        elif search.search_algorithm == SearchAlgorithm.RNR:
            businesses = await execute_rnr_search(search, database)
        elif search.search_algorithm == SearchAlgorithm.LEXICAL:
            businesses = await execute_lexical_search(search, database)
        elif search.search_algorithm == SearchAlgorithm.SIMPLE:
            businesses = await execute_simple_search(search, database)
        else:
            raise ValueError(f"Unknown search algorithm: {search.search_algorithm}")

        # Create response
        response = SearchResponse(
            businesses=businesses,
            search_algorithm=search.search_algorithm,
        )

        logger.debug(f"SearchResponse: {response.model_dump_json(indent=2)}")

        return ActionExecutionResult(content=response.model_dump(mode="json"))
    except Exception as e:
        return ActionExecutionResult(
            content={"error": str(e)},
            is_error=True,
        )
