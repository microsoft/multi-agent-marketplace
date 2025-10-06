"""Search action implementation for the simple marketplace."""

import logging

from magentic_marketplace.platform.database.base import BaseDatabaseController
from magentic_marketplace.platform.shared.models import ActionExecutionResult

from ...actions import Search, SearchAlgorithm, SearchResponse
from ...shared.models import AgentProfile, CustomerAgentProfile
from .filtered import execute_filtered_search
from .lexical import execute_lexical_search
from .optimal import execute_optimal_search
from .rnr import execute_rnr_search
from .simple import execute_simple_search

logger = logging.getLogger(__name__)


async def execute_search(
    *,
    search: Search,
    agent: AgentProfile | None,
    database: BaseDatabaseController,
) -> ActionExecutionResult:
    """Execute a search action to find businesses in the marketplace.

    This function implements the business search functionality using the database
    controller's proper abstractions instead of raw SQL queries.

    Args:
        search: The search action containing query parameters
        customer: The customer executing the search (needed for optimal search, None for other algorithms)
        database: Database controller for accessing data
        agent: Optional. The agent calling this search method. Required for some search algorithms e.g. optimal.

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
        elif search.search_algorithm == SearchAlgorithm.OPTIMAL:
            if agent is None:
                raise ValueError("agent is required to perform optimal search")
            # Parse agent as CustomerAgentProfile to extract customer
            customer_agent = CustomerAgentProfile.model_validate(agent.model_dump())
            businesses = await execute_optimal_search(
                search=search, customer=customer_agent.customer, database=database
            )
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
