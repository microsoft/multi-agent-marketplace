"""Search utils."""

import json
import logging

from magentic_marketplace.platform.database.models import AgentRow

from ...shared.models import BusinessAgentProfile

logger = logging.getLogger(__name__)


async def convert_agent_rows_to_businesses(
    agent_rows: list[AgentRow],
) -> list[BusinessAgentProfile]:
    """Convert agent rows to BusinessAgentProfile objects."""
    businesses: list[BusinessAgentProfile] = []

    for agent_row in agent_rows:
        try:
            agent = agent_row.data
            business_agent_profile = BusinessAgentProfile.model_validate(
                agent.model_dump()
            )
            businesses.append(business_agent_profile)
        except (json.JSONDecodeError, ValueError) as e:
            # Skip invalid business data
            logger.warning(
                f"Failed to validate BusinessAgentProfile {e}", exc_info=True
            )

    return businesses
