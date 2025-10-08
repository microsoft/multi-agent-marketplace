"""Search action implementation for the simple marketplace."""

import logging

from magentic_marketplace.platform.database.base import BaseDatabaseController
from magentic_marketplace.platform.shared.models import ActionExecutionResult

from ...actions import Search, SearchAlgorithm
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
        search: The search action containing query parameters.
        agent: The agent executing the search. Required for the optimal search algorithm; optional for others.
        database: Database controller for accessing data.

    Returns:
        ActionExecutionResult with the action result

    """
    # Execute the appropriate search algorithm
    logger.info(f'Search: "{search.query}", {search.search_algorithm}')
    if search.search_algorithm == SearchAlgorithm.FILTERED:
        response = await execute_filtered_search(search, database)
    elif search.search_algorithm == SearchAlgorithm.RNR:
        response = await execute_rnr_search(search, database)
    elif search.search_algorithm == SearchAlgorithm.LEXICAL:
        response = await execute_lexical_search(search, database)
    elif search.search_algorithm == SearchAlgorithm.OPTIMAL:
        if agent is None:
            raise ValueError("agent is required to perform optimal search")
        # Parse agent as CustomerAgentProfile to extract customer
        customer_agent = CustomerAgentProfile.model_validate(agent.model_dump())
        response = await execute_optimal_search(
            search=search, customer=customer_agent.customer, database=database
        )
    elif search.search_algorithm == SearchAlgorithm.SIMPLE:
        response = await execute_simple_search(search, database)
    else:
        raise ValueError(f"Unknown search algorithm: {search.search_algorithm}")

    logger.debug(f"SearchResponse: {response.model_dump_json(indent=2)}")

    return ActionExecutionResult(content=response.model_dump(mode="json"))
