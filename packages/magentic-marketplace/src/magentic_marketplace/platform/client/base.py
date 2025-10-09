"""Lightweight base client with core aiohttp functionality."""

import asyncio
import json
import logging
import random
import threading
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode, urljoin

import aiohttp
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Global client metrics tracking
_client_metrics = {
    "total_requests": 0,
    "total_retries": 0,
    "fatal_errors": 0,
    "successful_requests": 0,
    "retries_by_status": {},
    "retries_by_exception": {},
}

# Global metrics timer
_client_metrics_timer = None


def _dump_client_metrics_to_file(base_url: str):
    """Dump client metrics to file."""
    try:
        # Create a safe filename from base_url
        safe_url = base_url.replace("://", "_").replace("/", "_").replace(":", "_")
        metrics_file = f"client_metrics_{safe_url}.json"
        with open(metrics_file, "w") as f:
            json.dump(_client_metrics, f, indent=2)
    except Exception:
        # Silently fail to avoid issues during cleanup
        pass


def _start_client_metrics_timer(base_url: str):
    """Start a repeating timer to dump client metrics every 10 seconds."""
    global _client_metrics_timer

    # Only start one timer globally
    if _client_metrics_timer is not None:
        return

    def dump_metrics():
        _dump_client_metrics_to_file(base_url)
        # Schedule next dump
        global _client_metrics_timer
        _client_metrics_timer = threading.Timer(10.0, dump_metrics)
        _client_metrics_timer.daemon = True  # Dies when main thread dies
        _client_metrics_timer.start()

    # Start the first timer
    _client_metrics_timer = threading.Timer(10.0, dump_metrics)
    _client_metrics_timer.daemon = True
    _client_metrics_timer.start()


def _stop_client_metrics_timer():
    """Stop the client metrics timer."""
    global _client_metrics_timer
    if _client_metrics_timer is not None:
        _client_metrics_timer.cancel()
        _client_metrics_timer = None


@dataclass
class RetryConfig:
    """Configuration for HTTP request retry logic."""

    max_attempts: int | None = None
    base_delay: float = 1.0  # seconds
    max_delay: float = 30.0
    backoff_multiplier: float = 2.0
    jitter: bool = True
    jitter_size: float = 0.25
    retry_on_status: set[int] = field(default_factory=lambda: {429, 503})
    retry_on_exceptions: set[type] = field(
        default_factory=lambda: {
            TimeoutError,
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
        self._ref_count: int = 0

        # Start periodic metrics dumping
        _start_client_metrics_timer(self.base_url)

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
        """Create the aiohttp session and increment reference count."""
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        self._ref_count += 1

    async def close(self):
        """Close the aiohttp session when reference count reaches zero."""
        # Don't let ref count go below 0
        self._ref_count = max(self._ref_count - 1, 0)

        # Only actually close the session when no more references exist
        if self._ref_count == 0 and self._session:
            session = self._session
            self._session = None
            await session.close()

    def __del__(self):
        """Write metrics to file when client is destroyed."""
        # Stop the periodic timer
        _stop_client_metrics_timer()
        # Do a final dump
        _dump_client_metrics_to_file(self.base_url)

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
            # Add jitter: final delay is [100%, 125%] of the original delay
            jitter_range = delay * self.retry_config.jitter_size
            delay += random.uniform(0, jitter_range)

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

        # Track total requests
        _client_metrics["total_requests"] += 1

        url = self._build_url(path, params)

        request_headers = headers or {}

        last_exception: Exception | None = None
        attempt = 0
        while (
            self.retry_config.max_attempts is None
            or attempt < self.retry_config.max_attempts
        ):
            if attempt > 0:
                # Delay before retry
                delay = self._calculate_delay(attempt)
                logger.info(
                    f"Retrying request due to {last_exception} error (attempt {attempt + 1}/{self.retry_config.max_attempts}), "
                    f"waiting {delay:.2f}s"
                )
                await asyncio.sleep(delay)

            try:
                async with self._session.request(
                    method, url, json=json_data, headers=request_headers
                ) as response:
                    response.raise_for_status()
                    # Track successful requests
                    _client_metrics["successful_requests"] += 1
                    return await response.json()
            except aiohttp.ClientResponseError as e:
                last_exception = e
                if (
                    # Is this a retry status?
                    e.status not in self.retry_config.retry_on_status
                    # Is this a retry exception
                    and type(e) not in self.retry_config.retry_on_exceptions
                ):
                    # Not a retry status or exception, raise immediately
                    _client_metrics["fatal_errors"] += 1
                    raise

                # Track retry by status code
                status_key = str(e.status)
                _client_metrics["retries_by_status"][status_key] = (
                    _client_metrics["retries_by_status"].get(status_key, 0) + 1
                )

            except Exception as e:
                last_exception = e
                # Is this a retry exception?
                if type(e) not in self.retry_config.retry_on_exceptions:
                    # Not a retry exception, raise immediately
                    _client_metrics["fatal_errors"] += 1
                    raise

                # Track retry by exception type
                exception_key = type(e).__name__
                _client_metrics["retries_by_exception"][exception_key] = (
                    _client_metrics["retries_by_exception"].get(exception_key, 0) + 1
                )

            attempt += 1
            # Track total retries
            _client_metrics["total_retries"] += 1

        # If we make it here, retries were exceeded.
        _client_metrics["fatal_errors"] += 1
        if last_exception:
            raise last_exception
        else:
            raise RuntimeError("Maximum retries exceeded: Unknown error.")

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
