"""Tests for MarketplaceClient retry behavior."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
import pytest_asyncio

from magentic_marketplace.platform.client.base import RetryConfig
from magentic_marketplace.platform.client.client import MarketplaceClient


class TestMarketplaceClientRetry:
    """Test suite for MarketplaceClient retry behavior."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create a MarketplaceClient instance with custom retry config for testing."""
        retry_config = RetryConfig(
            max_attempts=3,
            base_delay=0.01,  # Short delay for testing
            max_delay=0.1,
            backoff_multiplier=2.0,
            jitter=False,  # Disable jitter for predictable tests
            retry_on_status={429, 503},
            retry_on_exceptions=set(),  # No exception retries by default
        )
        client = MarketplaceClient("http://test.example.com", retry_config=retry_config)
        await client.connect()
        yield client
        await client.close()

    @pytest_asyncio.fixture
    async def client_with_exception_retries(self):
        """Create a MarketplaceClient instance that retries on exceptions."""
        retry_config = RetryConfig(
            max_attempts=3,
            base_delay=0.01,  # Short delay for testing
            max_delay=0.1,
            backoff_multiplier=2.0,
            jitter=False,  # Disable jitter for predictable tests
            retry_on_status={429, 503},
            retry_on_exceptions={
                aiohttp.ClientConnectionError,
                aiohttp.ServerTimeoutError,
                asyncio.TimeoutError,
            },
        )
        client = MarketplaceClient("http://test.example.com", retry_config=retry_config)
        await client.connect()
        yield client
        await client.close()

    @pytest.mark.asyncio
    async def test_retry_on_rate_limit_429(self, client):
        """Test that client retries on 429 status code."""
        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock(
            side_effect=[
                aiohttp.ClientResponseError(
                    request_info=MagicMock(),
                    history=(),
                    status=429,
                    message="Rate limited",
                ),
                aiohttp.ClientResponseError(
                    request_info=MagicMock(),
                    history=(),
                    status=429,
                    message="Rate limited",
                ),
                None,  # Success on third attempt
            ]
        )
        mock_response.json = AsyncMock(return_value={"status": "ok"})

        with patch.object(client._base_client._session, "request") as mock_request:
            mock_request.return_value.__aenter__ = AsyncMock(return_value=mock_response)

            result = await client._base_client.request("GET", "/test")

            assert result == {"status": "ok"}
            assert mock_request.call_count == 3  # Initial + 2 retries

    @pytest.mark.asyncio
    async def test_retry_on_service_unavailable_503(self, client):
        """Test that client retries on 503 status code."""
        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock(
            side_effect=[
                aiohttp.ClientResponseError(
                    request_info=MagicMock(),
                    history=(),
                    status=503,
                    message="Service unavailable",
                ),
                None,  # Success on second attempt
            ]
        )
        mock_response.json = AsyncMock(return_value={"status": "ok"})

        with patch.object(client._base_client._session, "request") as mock_request:
            mock_request.return_value.__aenter__ = AsyncMock(return_value=mock_response)

            result = await client._base_client.request("GET", "/test")

            assert result == {"status": "ok"}
            assert mock_request.call_count == 2  # Initial + 1 retry

    @pytest.mark.asyncio
    async def test_no_retry_on_connection_error_by_default(self, client):
        """Test that client does NOT retry on connection errors by default."""
        with patch.object(client._base_client._session, "request") as mock_request:
            mock_request.return_value.__aenter__ = AsyncMock(
                side_effect=aiohttp.ClientConnectionError("Connection failed")
            )

            with pytest.raises(aiohttp.ClientConnectionError) as exc_info:
                await client._base_client.request("GET", "/test")

            assert str(exc_info.value) == "Connection failed"
            assert mock_request.call_count == 1  # No retries

    @pytest.mark.asyncio
    async def test_no_retry_on_timeout_by_default(self, client):
        """Test that client does NOT retry on timeout errors by default."""
        with patch.object(client._base_client._session, "request") as mock_request:
            mock_request.return_value.__aenter__ = AsyncMock(
                side_effect=TimeoutError("Request timed out")
            )

            with pytest.raises(asyncio.TimeoutError) as exc_info:
                await client._base_client.request("GET", "/test")

            assert str(exc_info.value) == "Request timed out"
            assert mock_request.call_count == 1  # No retries

    @pytest.mark.asyncio
    async def test_no_retry_on_client_error_400(self, client):
        """Test that client does NOT retry on 400 Bad Request."""
        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock(
            side_effect=aiohttp.ClientResponseError(
                request_info=MagicMock(),
                history=(),
                status=400,
                message="Bad request",
            )
        )

        with patch.object(client._base_client._session, "request") as mock_request:
            mock_request.return_value.__aenter__ = AsyncMock(return_value=mock_response)

            with pytest.raises(aiohttp.ClientResponseError) as exc_info:
                await client._base_client.request("GET", "/test")

            assert exc_info.value.status == 400
            assert mock_request.call_count == 1  # No retries

    @pytest.mark.asyncio
    async def test_no_retry_on_unauthorized_401(self, client):
        """Test that client does NOT retry on 401 Unauthorized."""
        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock(
            side_effect=aiohttp.ClientResponseError(
                request_info=MagicMock(),
                history=(),
                status=401,
                message="Unauthorized",
            )
        )

        with patch.object(client._base_client._session, "request") as mock_request:
            mock_request.return_value.__aenter__ = AsyncMock(return_value=mock_response)

            with pytest.raises(aiohttp.ClientResponseError) as exc_info:
                await client._base_client.request("GET", "/test")

            assert exc_info.value.status == 401
            assert mock_request.call_count == 1  # No retries

    @pytest.mark.asyncio
    async def test_no_retry_on_forbidden_403(self, client):
        """Test that client does NOT retry on 403 Forbidden."""
        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock(
            side_effect=aiohttp.ClientResponseError(
                request_info=MagicMock(),
                history=(),
                status=403,
                message="Forbidden",
            )
        )

        with patch.object(client._base_client._session, "request") as mock_request:
            mock_request.return_value.__aenter__ = AsyncMock(return_value=mock_response)

            with pytest.raises(aiohttp.ClientResponseError) as exc_info:
                await client._base_client.request("GET", "/test")

            assert exc_info.value.status == 403
            assert mock_request.call_count == 1  # No retries

    @pytest.mark.asyncio
    async def test_no_retry_on_not_found_404(self, client):
        """Test that client does NOT retry on 404 Not Found."""
        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock(
            side_effect=aiohttp.ClientResponseError(
                request_info=MagicMock(),
                history=(),
                status=404,
                message="Not found",
            )
        )

        with patch.object(client._base_client._session, "request") as mock_request:
            mock_request.return_value.__aenter__ = AsyncMock(return_value=mock_response)

            with pytest.raises(aiohttp.ClientResponseError) as exc_info:
                await client._base_client.request("GET", "/test")

            assert exc_info.value.status == 404
            assert mock_request.call_count == 1  # No retries

    @pytest.mark.asyncio
    async def test_no_retry_on_value_error(self, client):
        """Test that client does NOT retry on ValueError (non-network error)."""
        with patch.object(client._base_client._session, "request") as mock_request:
            mock_request.return_value.__aenter__ = AsyncMock(
                side_effect=ValueError("Invalid input")
            )

            with pytest.raises(ValueError) as exc_info:
                await client._base_client.request("GET", "/test")

            assert str(exc_info.value) == "Invalid input"
            assert mock_request.call_count == 1  # No retries

    @pytest.mark.asyncio
    async def test_max_retry_attempts_exceeded(self, client):
        """Test that client stops retrying after max attempts."""
        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock(
            side_effect=aiohttp.ClientResponseError(
                request_info=MagicMock(),
                history=(),
                status=429,
                message="Rate limited",
            )
        )

        with patch.object(client._base_client._session, "request") as mock_request:
            mock_request.return_value.__aenter__ = AsyncMock(return_value=mock_response)

            with pytest.raises(aiohttp.ClientResponseError) as exc_info:
                await client._base_client.request("GET", "/test")

            assert exc_info.value.status == 429
            assert mock_request.call_count == 3  # Max attempts reached

    @pytest.mark.asyncio
    async def test_exponential_backoff_timing(self, client):
        """Test that retry delays follow exponential backoff pattern."""
        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock(
            side_effect=aiohttp.ClientResponseError(
                request_info=MagicMock(),
                history=(),
                status=429,
                message="Rate limited",
            )
        )

        with patch.object(client._base_client._session, "request") as mock_request:
            mock_request.return_value.__aenter__ = AsyncMock(return_value=mock_response)

            with patch("asyncio.sleep") as mock_sleep:
                mock_sleep.return_value = None

                with pytest.raises(aiohttp.ClientResponseError):
                    await client._base_client.request("GET", "/test")

                # Verify exponential backoff delays
                # With max_attempts=3, all failing: sleep occurs before retry attempts 1 and 2 (i.e., two sleep calls)
                assert mock_sleep.call_count == 2  # Two sleep calls
                delays = [call[0][0] for call in mock_sleep.call_args_list]

                # With base_delay=0.01 and multiplier=2.0:
                # First delay: 0.01 * (2.0^1) = 0.02
                # Second delay: 0.01 * (2.0^2) = 0.04
                assert abs(delays[0] - 0.02) < 0.002
                assert abs(delays[1] - 0.04) < 0.004

    @pytest.mark.asyncio
    async def test_retry_with_exception_retries_enabled(
        self, client_with_exception_retries
    ):
        """Test that client retries on exceptions when explicitly configured."""
        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = AsyncMock(return_value={"status": "ok"})

        with patch.object(
            client_with_exception_retries._base_client._session, "request"
        ) as mock_request:
            mock_request.return_value.__aenter__ = AsyncMock(
                side_effect=[
                    aiohttp.ClientConnectionError("Connection failed"),
                    TimeoutError("Request timed out"),
                    mock_response,  # Success on third attempt
                ]
            )

            result = await client_with_exception_retries._base_client.request(
                "GET", "/test"
            )

            assert result == {"status": "ok"}
            assert mock_request.call_count == 3  # Initial + 2 retries

    @pytest.mark.asyncio
    async def test_no_server_timeout_error_retry_by_default(self, client):
        """Test that client does NOT retry on ServerTimeoutError by default."""
        with patch.object(client._base_client._session, "request") as mock_request:
            mock_request.return_value.__aenter__ = AsyncMock(
                side_effect=aiohttp.ServerTimeoutError("Server timeout")
            )

            with pytest.raises(aiohttp.ServerTimeoutError) as exc_info:
                await client._base_client.request("GET", "/test")

            assert str(exc_info.value) == "Server timeout"
            assert mock_request.call_count == 1  # No retries

    @pytest.mark.asyncio
    async def test_no_retry_on_internal_server_error_500(self, client):
        """Test that client does NOT retry on 500 by default (not in retry_on_status)."""
        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock(
            side_effect=aiohttp.ClientResponseError(
                request_info=MagicMock(),
                history=(),
                status=500,
                message="Internal server error",
            )
        )

        with patch.object(client._base_client._session, "request") as mock_request:
            mock_request.return_value.__aenter__ = AsyncMock(return_value=mock_response)

            with pytest.raises(aiohttp.ClientResponseError) as exc_info:
                await client._base_client.request("GET", "/test")

            assert exc_info.value.status == 500
            assert (
                mock_request.call_count == 1
            )  # No retries since 500 not in retry_on_status
