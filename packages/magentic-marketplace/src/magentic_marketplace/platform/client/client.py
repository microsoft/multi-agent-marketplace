"""Main MarketplaceClient with modular resource access."""

from typing import Any

from .base import BaseClient, RetryConfig
from .resources import ActionsResource, AgentsResource, LogsResource

# Cache for reusing BaseClient instances across MarketplaceClients
_base_client_cache: dict[str, BaseClient] = {}


def _get_or_create_base_client(
    base_url: str,
    timeout: float | None = 60.0,
    retry_config: RetryConfig | None = None,
) -> BaseClient:
    """Get cached BaseClient or create new one.

    Args:
        base_url: The base URL for the client
        timeout: Request timeout in seconds
        retry_config: Optional retry configuration

    Returns:
        BaseClient: Cached or newly created BaseClient instance

    """
    # Create cache key from parameters using identity of retry_config
    cache_key = (
        f"{base_url}:{timeout}:{id(retry_config) if retry_config else 'default'}"
    )

    if cache_key not in _base_client_cache:
        _base_client_cache[cache_key] = BaseClient(base_url, timeout, retry_config)

    return _base_client_cache[cache_key]


class MarketplaceClient:
    """Main client for the Magentic Marketplace API with modular resource access.

    Usage:
        async with MarketplaceClient("http://localhost:8000") as client:
            agent = await client.agents.get("agent_id")
            result = await client.actions.execute(action)
            log = await client.logs.create("info", {"message": "test"})
            from ..logger import MarketplaceLogger
            logger = MarketplaceLogger(__name__, client)
            logger.info("This logs to both Python logging and database")
    """

    def __init__(
        self,
        base_url: str,
        timeout: float | None = 60.0,
        retry_config: RetryConfig | None = None,
    ):
        """Initialize marketplace client with resource modules and cached base client."""
        # Use cached BaseClient instance
        self._base_client = _get_or_create_base_client(base_url, timeout, retry_config)
        self._agent_id: str | None = None

        # Initialize resource modules with base client
        self.agents = AgentsResource(self._base_client)
        self.actions = ActionsResource(self._base_client)
        self.logs = LogsResource(self._base_client)

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
        """Connect the underlying base client (increments reference count)."""
        await self._base_client.connect()

    async def close(self):
        """Close the underlying base client (decrements reference count)."""
        await self._base_client.close()

    def set_agent_id(self, agent_id: str) -> None:
        """Set the agent ID for requests on all resources.

        Args:
            agent_id: The agent ID to use

        """
        self._agent_id = agent_id
        self.agents.set_agent_id(agent_id)
        self.actions.set_agent_id(agent_id)
        self.logs.set_agent_id(agent_id)

    @property
    def agent_id(self) -> str | None:
        """Get the current agent ID from agents resource.

        Returns:
            str | None: The agent ID or None if not set

        """
        return self.agents.agent_id

    async def health_check(self) -> dict[str, Any]:
        """Check server health.

        Returns:
            dict: Health check response

        """
        return await self._base_client.request("GET", "/health")
