"""Lightweight base client with core aiohttp functionality."""

import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode, urljoin

import aiohttp
from pydantic import BaseModel

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """Configuration for HTTP request retry logic."""

    max_attempts: int = 10
    base_delay: float = 1.0  # seconds
    max_delay: float = 30.0
    backoff_multiplier: float = 2.0
    jitter: bool = True
    jitter_size: float = 0.25
    retry_on_status: set[int] = field(default_factory=lambda: {429})
    retry_on_exceptions: set[type] = field(
        default_factory=lambda: {
            aiohttp.ClientConnectionError,
            aiohttp.ServerTimeoutError,
            aiohttp.ClientResponseError,
            asyncio.TimeoutError,
        }
    )


class ClientError(Exception):
    """Base exception for client errors."""

    pass


class HTTPError(ClientError):
    """HTTP error from server."""

    def __init__(self, status: int, message: str):
        """Initialize HTTP error with status and message."""
        self.status = status
        self.message = message
        super().__init__(f"HTTP {status}: {message}")


class BaseClient:
    """Lightweight base client with core HTTP functionality."""

    def __init__(
        self,
        base_url: str,
        timeout: float | None = 60.0,
        retry_config: RetryConfig | None = None,
    ):
        """Initialize base client with URL, timeout, and retry configuration."""
        self.base_url = base_url.rstrip("/")
        self.timeout = aiohttp.ClientTimeout(total=timeout) if timeout else None
        self.retry_config = retry_config or RetryConfig()
        self._session: aiohttp.ClientSession | None = None
        self._auth_token: str | None = None

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit."""
        await self.close()

    async def connect(self):
        """Create the aiohttp session."""
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        else:
            raise RuntimeError("Attempting to reconnect to existing ClientSession.")

    async def close(self):
        """Close the aiohttp session."""
        if self._session:
            await self._session.close()
        else:
            raise RuntimeError("Attempting to close unconnected ClientSession.")

    def _build_url(self, path: str, params: BaseModel | None = None) -> str:
        """Build a complete URL with query parameters."""
        url = urljoin(self.base_url, path.lstrip("/"))
        if params:
            # Convert BaseModel to dict and filter out None values
            params_dict = params.model_dump(mode="json", exclude_none=True)
            # Convert datetime objects to ISO format
            filtered_params: dict[str, str] = {}
            for k, v in params_dict.items():
                filtered_params[k] = v
            if filtered_params:
                url += "?" + urlencode(filtered_params)
        return url

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for exponential backoff with optional jitter."""
        delay = self.retry_config.base_delay * (
            self.retry_config.backoff_multiplier**attempt
        )
        delay = min(delay, self.retry_config.max_delay)

        if self.retry_config.jitter:
            # Add jitter: ±25% of the delay
            jitter_range = delay * self.retry_config.jitter_size
            delay += random.uniform(-jitter_range, jitter_range)

        return max(0, delay)

    async def _request(
        self,
        method: str,
        path: str,
        params: BaseModel | None = None,
        json_data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request with retry logic and return parsed JSON response."""
        if not self._session:
            raise ClientError(
                "Client is not connected. You must call connect before request."
            )

        url = self._build_url(path, params)

        # Add auth header if token is set
        request_headers = headers or {}
        if self._auth_token:
            request_headers["Authorization"] = f"Bearer {self._auth_token}"

        last_exception: Exception | None = None

        for attempt in range(self.retry_config.max_attempts):
            try:
                async with self._session.request(
                    method, url, json=json_data, headers=request_headers
                ) as response:
                    response.raise_for_status()
                    return await response.json()
            except aiohttp.ClientResponseError as e:
                last_exception = e
                if (
                    # Is this a retry status?
                    e.status not in self.retry_config.retry_on_status
                    # Is this a retry exception
                    and type(e) not in self.retry_config.retry_on_exceptions
                ):
                    # Not a retry status or exception, raise
                    raise
            except Exception as e:
                last_exception = e
                # Is this a retry exception?
                if type(e) not in self.retry_config.retry_on_exceptions:
                    # Not a retry exception, raise
                    raise

            # Delay before retry
            delay = self._calculate_delay(attempt)
            logger.info(
                f"Retrying request after {last_exception} error (attempt {attempt + 1}/{self.retry_config.max_attempts}), "
                f"waiting {delay:.2f}s"
            )
            await asyncio.sleep(delay)

        # If we make it here, retries were exceeded.
        if last_exception:
            raise last_exception
        else:
            raise RuntimeError("Maximum retries exceeded: Unknown error.")

    def set_token(self, token: str) -> None:
        """Set the authentication token for requests."""
        self._auth_token = token

    @property
    def auth_token(self) -> str | None:
        """Get the current authentication token."""
        return self._auth_token

    async def request(
        self,
        method: str,
        path: str,
        params: BaseModel | None = None,
        json_data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Public method for making HTTP requests."""
        return await self._request(method, path, params, json_data, headers)
