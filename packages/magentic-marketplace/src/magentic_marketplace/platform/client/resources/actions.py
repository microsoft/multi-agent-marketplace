"""Actions resource for Magentic Marketplace API client."""

from ...shared.models import (
    ActionExecutionRequest,
    ActionExecutionResult,
    ActionProtocolResponse,
    BaseAction,
)
from ..base import BaseClient


class ActionsResource:
    """Action-related client methods."""

    def __init__(self, client: BaseClient):
        """Initialize actions resource with client."""
        self._client = client

    async def get_protocol(self) -> ActionProtocolResponse:
        """Get available action protocols."""
        response_data = await self._client.request("GET", "/actions/protocol")
        return ActionProtocolResponse.model_validate(response_data)

    async def execute(
        self,
        action: BaseAction,
    ) -> ActionExecutionResult:
        """Execute an action (automatically uses client's auth token)."""
        request = ActionExecutionRequest(
            name=action.get_name(), parameters=action.model_dump(mode="json")
        )
        response_data = await self._client.request(
            "POST", "/actions/execute", json_data=request.model_dump(mode="json")
        )
        return ActionExecutionResult.model_validate(response_data)

    async def request(self, request: ActionExecutionRequest) -> ActionExecutionResult:
        """Submit an ActionExecutionRequest directly."""
        response_data = await self._client.request(
            "POST", "/actions/execute", json_data=request.model_dump(mode="json")
        )
        return ActionExecutionResult.model_validate(response_data)
