"""RNR (Retrieve and Rerank) search implementation for the simple marketplace."""

import logging
import math

from magentic_marketplace.platform.database.base import BaseDatabaseController
from magentic_marketplace.platform.database.models import AgentRow
from magentic_marketplace.platform.database.queries.agents import query as agent_query
from magentic_marketplace.platform.database.queries.base import RangeQueryParams

from ...actions import Search, SearchResponse
from .utils import convert_agent_rows_to_businesses

logger = logging.getLogger(__name__)


async def execute_rnr_search(
    search: Search,
    database: BaseDatabaseController,
) -> SearchResponse:
    """Execute RNR search algorithm using retrieve and rerank."""
    # Delay import to avoid slow torch import times if not using it
    from .rnr_algo import RetrieveAndRerank

    # Initialize the RNR system
    rnr = RetrieveAndRerank()

    # Get all business agents (with larger limit for RNR processing)
    business_filter = agent_query(path="$.business", value=None, operator="!=")

    # First, get agents that need embeddings computed
    all_agent_rows = await database.agents.find(business_filter, RangeQueryParams())

    # Compute embeddings for agents that don't have them
    agents_without_embeddings = [
        row for row in all_agent_rows if row.agent_embedding is None
    ]

    embedding_data: list[tuple[str, bytes]] = []
    if agents_without_embeddings:
        logger.info(
            f"Computing embeddings for {len(agents_without_embeddings)} agents without embeddings"
        )

        # Compute embeddings for these agents
        embedding_data = rnr.compute_business_embeddings_as_bytes(
            agents_without_embeddings
        )

        # Update the database with new embeddings
        for agent_id, embedding_bytes in embedding_data:
            await database.agents.update(agent_id, {"agent_embedding": embedding_bytes})

    # Now get all agents with embeddings for ranking
    agents_with_embeddings: list[AgentRow] = []
    for row in all_agent_rows:
        if row.agent_embedding is not None:
            agents_with_embeddings.append(row)
        else:
            # Check if we just computed embedding for this agent
            for agent_id, embedding_bytes in embedding_data:
                if agent_id == row.id:
                    # Create a new AgentRow with the embedding
                    row_with_embedding = row.model_copy()
                    row_with_embedding.agent_embedding = embedding_bytes
                    agents_with_embeddings.append(row_with_embedding)
                    break

    if not agents_with_embeddings:
        logger.warning("No agents with embeddings found")
        return SearchResponse(
            businesses=[],
            search_algorithm=search.search_algorithm,
            total_possible_results=0,
            total_pages=0,
        )

    # Use RNR to rank the results
    if search.query:
        ranked_agent_rows = rnr.rank_search_results(
            search.query, search.constraints, agents_with_embeddings
        )
    else:
        # If no query, just sort by rating
        ranked_agent_rows = sorted(
            agents_with_embeddings,
            key=lambda row: _get_business_rating(row),
            reverse=True,
        )

    # Convert to BusinessAgentProfile objects and apply limit
    businesses = await convert_agent_rows_to_businesses(ranked_agent_rows)
    total_pages = (
        math.ceil(len(businesses) / search.limit)
        if search.limit and search.limit > 0
        else 1
    )
    return SearchResponse(
        businesses=businesses,
        search_algorithm=search.search_algorithm,
        total_possible_results=len(businesses),
        total_pages=total_pages,
    )


def _get_business_rating(agent_row: AgentRow) -> float:
    """Extract business rating from agent row, with fallback."""
    try:
        business_data = getattr(agent_row.data, "business", None)
        if business_data and "rating" in business_data:
            return float(business_data["rating"])
    except (ValueError, TypeError):
        pass
    return 0.0
