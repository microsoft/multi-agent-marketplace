"""Base resource class with auth token handling."""

from typing import Any

from ..base import BaseClient


class BaseResource:
    """Base class for API resources with auth token support."""

    def __init__(self, base_client: BaseClient):
        """Initialize resource with base client.

        Args:
            base_client: The BaseClient instance for making HTTP requests

        """
        self._base_client = base_client
        self._auth_token: str | None = None

    def set_token(self, token: str) -> None:
        """Set the authentication token for requests.

        Args:
            token: The auth token to use

        """
        self._auth_token = token

    @property
    def auth_token(self) -> str | None:
        """Get the current authentication token.

        Returns:
            str | None: The auth token or None if not set

        """
        return self._auth_token

    async def request(
        self,
        method: str,
        path: str,
        params: Any = None,
        json_data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request with automatic auth token injection.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API endpoint path
            params: Optional query parameters
            json_data: Optional JSON body
            headers: Optional additional headers

        Returns:
            dict: Parsed JSON response

        """
        # Add auth token to headers if set
        request_headers = headers or {}
        if self._auth_token:
            request_headers["Authorization"] = f"Bearer {self._auth_token}"

        return await self._base_client.request(
            method, path, params, json_data, request_headers
        )
