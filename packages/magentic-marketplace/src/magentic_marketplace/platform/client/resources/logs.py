"""Logs resource for Magentic Marketplace API client."""

from ...shared.models import (
    BaseResponse,
    ListRequest,
    Log,
    LogCreateRequest,
    LogListResponse,
)
from ..base import BaseClient


class LogsResource:
    """Log-related client methods."""

    def __init__(self, client: BaseClient):
        """Initialize logs resource with client."""
        self._client = client

    async def create(
        self,
        log: Log,
    ) -> Log:
        """Create a log record."""
        request = LogCreateRequest(log=log)
        response_data = await self._client.request(
            "POST", "/logs/create", json_data=request.model_dump(mode="json")
        )
        response = BaseResponse.model_validate(response_data)
        if response.error:
            raise Exception(f"Failed to create log: {response.error}")
        return log

    async def list(
        self,
        offset: int = 0,
        limit: int | None = None,
    ) -> LogListResponse:
        """Get log records with optional filtering."""
        params = ListRequest(offset=offset, limit=limit)
        response_data = await self._client.request("GET", "/logs", params=params)
        return LogListResponse.model_validate(response_data)
