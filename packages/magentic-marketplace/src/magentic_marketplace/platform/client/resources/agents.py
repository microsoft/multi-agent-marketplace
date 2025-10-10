"""Agents resource for Magentic Marketplace API client."""

from ...shared.models import (
    AgentGetResponse,
    AgentListResponse,
    AgentProfile,
    AgentRegistrationRequest,
    AgentRegistrationResponse,
    ListRequest,
)
from .base import BaseResource


class AgentsResource(BaseResource):
    """Agent-related client methods."""

    async def register(self, agent: AgentProfile) -> AgentRegistrationResponse:
        """Register a new agent and return both agent and auth token."""
        request = AgentRegistrationRequest(agent=agent)
        response_data = await self.request(
            "POST", "/agents/register", json_data=request.model_dump(mode="json")
        )
        return AgentRegistrationResponse.model_validate(response_data)

    async def list(
        self, offset: int = 0, limit: int | None = None
    ) -> AgentListResponse:
        """Get all agents with pagination."""
        params = ListRequest(offset=offset, limit=limit)
        response_data = await self.request("GET", "/agents", params=params)
        return AgentListResponse.model_validate(response_data)

    async def get(self, agent_id: str) -> AgentProfile:
        """Get a specific agent by ID."""
        response_data = await self.request("GET", f"/agents/{agent_id}")
        response = AgentGetResponse.model_validate(response_data)
        return response.agent
