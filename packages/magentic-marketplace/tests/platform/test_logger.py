"""Tests for MarketplaceLogger."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from magentic_marketplace.platform.client import MarketplaceClient
from magentic_marketplace.platform.logger import MarketplaceLogger


@pytest_asyncio.fixture
async def mock_client():
    """Create a mock MarketplaceClient for testing."""
    client = MagicMock(spec=MarketplaceClient)
    client.closed = False
    client.logs = MagicMock()
    client.logs.create = AsyncMock()
    return client


@pytest_asyncio.fixture
async def logger(mock_client):
    """Create a MarketplaceLogger with a mock client."""
    return MarketplaceLogger("test-logger", mock_client)


class TestMarketplaceLogger:
    """Tests for MarketplaceLogger."""

    @pytest.mark.asyncio
    async def test_debug(self, logger, mock_client):
        """Test debug logging."""
        logger.debug("debug message")
        await logger.flush()
        assert mock_client.logs.create.call_count == 1

    @pytest.mark.asyncio
    async def test_info(self, logger, mock_client):
        """Test info logging."""
        logger.info("info message")
        await logger.flush()
        assert mock_client.logs.create.call_count == 1

    @pytest.mark.asyncio
    async def test_warning(self, logger, mock_client):
        """Test warning logging."""
        logger.warning("warning message")
        await logger.flush()
        assert mock_client.logs.create.call_count == 1

    @pytest.mark.asyncio
    async def test_error(self, logger, mock_client):
        """Test error logging."""
        logger.error("error message")
        await logger.flush()
        assert mock_client.logs.create.call_count == 1

    @pytest.mark.asyncio
    async def test_flush_returns_zero_for_no_tasks(self, logger):
        """Test that flush returns empty list when no tasks are pending."""
        results = await logger.flush()
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_flush_returns_count_below_flush_every(self, mock_client):
        """Test that flush returns correct count for tasks below flush_every threshold."""
        logger = MarketplaceLogger("test-logger", mock_client, flush_every=10)

        # Log fewer than flush_every
        logger.info("message 1")
        logger.info("message 2")
        logger.info("message 3")

        results = await logger.flush()
        assert len(results) == 3
        assert mock_client.logs.create.call_count == 3

    @pytest.mark.asyncio
    async def test_flush_returns_count_above_flush_every(self, mock_client):
        """Test that flush returns correct count for tasks above flush_every threshold."""
        flush_every = 2
        logger = MarketplaceLogger("test-logger", mock_client, flush_every=flush_every)

        # Log more than flush_every (will trigger auto-flush)
        n = 5
        for i in range(n):
            logger.info(f"message {i}")

        # Wait for auto-flushes
        await asyncio.sleep(0.1)

        # Flush any remaining
        await logger.flush()

        # Total logged should be 5
        assert mock_client.logs.create.call_count == n

    @pytest.mark.asyncio
    async def test_flush_with_task_errors(self, mock_client):
        """Test that flush completes successfully even when tasks fail (errors caught internally)."""
        # Make some tasks fail
        mock_client.logs.create.side_effect = [
            None,  # First succeeds
            Exception("Database error"),  # Second fails
            None,  # Third succeeds
        ]

        logger = MarketplaceLogger("test-logger", mock_client)

        logger.info("message 1")
        logger.info("message 2")
        logger.info("message 3")

        # Flush completes successfully because _log_to_db catches exceptions
        results = await logger.flush()

        # All tasks completed (some with errors caught internally)
        assert len(results) == 3
        assert mock_client.logs.create.call_count == 3
