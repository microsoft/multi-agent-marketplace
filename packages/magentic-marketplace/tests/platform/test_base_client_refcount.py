"""Tests for BaseClient reference counting behavior."""

import pytest
import pytest_asyncio

from magentic_marketplace.platform.client.base import BaseClient, RetryConfig
from magentic_marketplace.platform.client.client import (
    MarketplaceClient,
    _base_client_cache,
)


class TestBaseClientReferenceCount:
    """Test suite for BaseClient reference counting."""

    @pytest_asyncio.fixture
    async def base_client(self):
        """Create a BaseClient instance for testing."""
        client = BaseClient("http://test.example.com")
        yield client
        # Cleanup: force close if still open
        if client._session:
            await client._session.close()
            client._session = None

    @pytest.mark.asyncio
    async def test_initial_ref_count_is_zero(self, base_client):
        """Test that a new BaseClient starts with ref count of 0."""
        assert base_client._ref_count == 0
        assert base_client._session is None

    @pytest.mark.asyncio
    async def test_connect_increments_ref_count(self, base_client):
        """Test that connect increments the reference count."""
        assert base_client._ref_count == 0

        await base_client.connect()
        assert base_client._ref_count == 1

        await base_client.close()

    @pytest.mark.asyncio
    async def test_connect_creates_session_on_first_call(self, base_client):
        """Test that connect creates a session only on the first call."""
        assert base_client._session is None

        await base_client.connect()
        assert base_client._session is not None
        first_session = base_client._session

        # Second connect should reuse the same session
        await base_client.connect()
        assert base_client._session is first_session

        await base_client.close()
        await base_client.close()

    @pytest.mark.asyncio
    async def test_multiple_connects_increment_ref_count(self, base_client):
        """Test that multiple connects increment ref count correctly."""
        await base_client.connect()
        assert base_client._ref_count == 1

        await base_client.connect()
        assert base_client._ref_count == 2

        await base_client.connect()
        assert base_client._ref_count == 3

        # Cleanup
        await base_client.close()
        await base_client.close()
        await base_client.close()

    @pytest.mark.asyncio
    async def test_close_decrements_ref_count(self, base_client):
        """Test that close decrements the reference count."""
        await base_client.connect()
        await base_client.connect()
        assert base_client._ref_count == 2

        await base_client.close()
        assert base_client._ref_count == 1

        await base_client.close()
        assert base_client._ref_count == 0

    @pytest.mark.asyncio
    async def test_session_closes_only_when_ref_count_reaches_zero(self, base_client):
        """Test that session only closes when ref count reaches 0."""
        await base_client.connect()
        await base_client.connect()
        await base_client.connect()

        session = base_client._session
        assert session is not None
        assert base_client._ref_count == 3

        # First close: ref count 3 -> 2, session should remain open
        await base_client.close()
        assert base_client._ref_count == 2
        assert base_client._session is session
        assert not session.closed

        # Second close: ref count 2 -> 1, session should remain open
        await base_client.close()
        assert base_client._ref_count == 1
        assert base_client._session is session
        assert not session.closed

        # Third close: ref count 1 -> 0, session should close
        await base_client.close()
        assert base_client._ref_count == 0
        assert base_client._session is None
        assert session.closed

    @pytest.mark.asyncio
    async def test_ref_count_does_not_go_below_zero(self, base_client):
        """Test that ref count never goes below zero."""
        # Close without connect should not make ref count negative
        await base_client.close()
        assert base_client._ref_count == 0

        await base_client.close()
        assert base_client._ref_count == 0

        # Connect and then close multiple times
        await base_client.connect()
        assert base_client._ref_count == 1

        await base_client.close()
        assert base_client._ref_count == 0

        await base_client.close()
        assert base_client._ref_count == 0

    @pytest.mark.asyncio
    async def test_context_manager_manages_ref_count(self, base_client):
        """Test that context manager properly manages ref count."""
        assert base_client._ref_count == 0

        async with base_client:
            assert base_client._ref_count == 1
            assert base_client._session is not None

        assert base_client._ref_count == 0
        assert base_client._session is None

    @pytest.mark.asyncio
    async def test_nested_context_managers(self, base_client):
        """Test that nested context managers work correctly with ref counting."""
        assert base_client._ref_count == 0

        async with base_client:
            assert base_client._ref_count == 1
            session1 = base_client._session
            assert session1 is not None

            async with base_client:
                assert base_client._ref_count == 2
                # Should be the same session
                assert base_client._session is session1

            # After inner context exits
            assert base_client._ref_count == 1
            assert base_client._session is session1
            assert not session1.closed

        # After outer context exits
        assert base_client._ref_count == 0
        assert base_client._session is None
        assert session1.closed

    @pytest.mark.asyncio
    async def test_reconnect_after_full_close(self, base_client):
        """Test that we can reconnect after fully closing."""
        # First session
        await base_client.connect()
        first_session = base_client._session
        await base_client.close()

        assert base_client._ref_count == 0
        assert base_client._session is None
        assert first_session.closed

        # Reconnect creates new session
        await base_client.connect()
        second_session = base_client._session

        assert base_client._ref_count == 1
        assert second_session is not None
        assert second_session is not first_session
        assert not second_session.closed

        await base_client.close()


class TestMarketplaceClientSharedBaseClient:
    """Test suite for MarketplaceClient sharing BaseClient instances."""

    def teardown_method(self):
        """Clear the base client cache after each test."""
        _base_client_cache.clear()

    @pytest.mark.asyncio
    async def test_multiple_marketplace_clients_share_base_client(self):
        """Test that multiple MarketplaceClients with same URL share BaseClient."""
        client1 = MarketplaceClient("http://test.example.com")
        client2 = MarketplaceClient("http://test.example.com")

        # Should share the same BaseClient instance
        assert client1._base_client is client2._base_client

    @pytest.mark.asyncio
    async def test_different_urls_get_different_base_clients(self):
        """Test that different URLs get different BaseClient instances."""
        client1 = MarketplaceClient("http://test1.example.com")
        client2 = MarketplaceClient("http://test2.example.com")

        # Should NOT share the same BaseClient instance
        assert client1._base_client is not client2._base_client

    @pytest.mark.asyncio
    async def test_different_retry_configs_get_different_base_clients(self):
        """Test that different retry configs get different BaseClient instances."""
        retry_config1 = RetryConfig(max_attempts=3)
        retry_config2 = RetryConfig(max_attempts=5)

        client1 = MarketplaceClient(
            "http://test.example.com", retry_config=retry_config1
        )
        client2 = MarketplaceClient(
            "http://test.example.com", retry_config=retry_config2
        )

        # Should NOT share the same BaseClient (different retry configs)
        assert client1._base_client is not client2._base_client

    @pytest.mark.asyncio
    async def test_shared_base_client_ref_counting(self):
        """Test that shared BaseClient properly manages ref count."""
        client1 = MarketplaceClient("http://test.example.com")
        client2 = MarketplaceClient("http://test.example.com")

        base_client = client1._base_client
        assert base_client is client2._base_client

        # Initially ref count should be 0
        assert base_client._ref_count == 0

        # Connect both clients
        await client1.connect()
        assert base_client._ref_count == 1

        await client2.connect()
        assert base_client._ref_count == 2

        # Session should be shared
        assert base_client._session is not None
        session = base_client._session

        # Close first client
        await client1.close()
        assert base_client._ref_count == 1
        assert base_client._session is session
        assert not session.closed

        # Close second client - should actually close session
        await client2.close()
        assert base_client._ref_count == 0
        assert base_client._session is None
        assert session.closed

    @pytest.mark.asyncio
    async def test_marketplace_client_context_manager_with_shared_base(self):
        """Test context managers work correctly with shared BaseClient."""
        client1 = MarketplaceClient("http://test.example.com")
        client2 = MarketplaceClient("http://test.example.com")

        base_client = client1._base_client

        async with client1:
            assert base_client._ref_count == 1
            session = base_client._session
            assert session is not None

            async with client2:
                assert base_client._ref_count == 2
                assert base_client._session is session

            # After client2 exits
            assert base_client._ref_count == 1
            assert base_client._session is session
            assert not session.closed

        # After client1 exits
        assert base_client._ref_count == 0
        assert base_client._session is None
        assert session.closed

    @pytest.mark.asyncio
    async def test_interleaved_connect_close_with_shared_base(self):
        """Test interleaved connect/close calls with shared BaseClient."""
        client1 = MarketplaceClient("http://test.example.com")
        client2 = MarketplaceClient("http://test.example.com")
        client3 = MarketplaceClient("http://test.example.com")

        base_client = client1._base_client

        await client1.connect()  # ref=1
        await client2.connect()  # ref=2
        await client1.connect()  # ref=3 (client1 connects again)
        assert base_client._ref_count == 3

        await client3.connect()  # ref=4
        assert base_client._ref_count == 4
        session = base_client._session
        assert session is not None

        await client1.close()  # ref=3
        await client2.close()  # ref=2
        assert base_client._ref_count == 2
        assert base_client._session is session

        await client1.close()  # ref=1 (client1 had 2 connects)
        assert base_client._ref_count == 1
        assert base_client._session is session

        await client3.close()  # ref=0 - session should close
        assert base_client._ref_count == 0
        assert base_client._session is None
        assert session.closed
