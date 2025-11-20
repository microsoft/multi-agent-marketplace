"""Base resource class with agent ID handling."""

from typing import Any

from ..base import BaseClient


class BaseResource:
    """Base class for API resources with agent ID support."""

    def __init__(self, base_client: BaseClient):
        """Initialize resource with base client.

        Args:
            base_client: The BaseClient instance for making HTTP requests

        """
        self._base_client = base_client
        self._agent_id: str | None = None

    def set_agent_id(self, agent_id: str) -> None:
        """Set the agent ID for requests.

        Args:
            agent_id: The agent ID to use

        """
        self._agent_id = agent_id

    @property
    def agent_id(self) -> str | None:
        """Get the current agent ID.

        Returns:
            str | None: The agent ID or None if not set

        """
        return self._agent_id

    async def request(
        self,
        method: str,
        path: str,
        params: Any = None,
        json_data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request with automatic agent ID injection.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API endpoint path
            params: Optional query parameters
            json_data: Optional JSON body
            headers: Optional additional headers

        Returns:
            dict: Parsed JSON response

        """
        # Add agent ID to headers if set
        request_headers = headers or {}
        if self._agent_id:
            request_headers["X-Agent-Id"] = self._agent_id

        return await self._base_client.request(
            method, path, params, json_data, request_headers
        )
