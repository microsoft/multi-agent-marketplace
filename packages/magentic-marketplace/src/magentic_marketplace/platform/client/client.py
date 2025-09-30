"""Main MarketplaceClient with modular resource access."""

from typing import Any

from .base import BaseClient, RetryConfig
from .resources import ActionsResource, AgentsResource, LogsResource


class MarketplaceClient(BaseClient):
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
        """Initialize marketplace client with resource modules."""
        super().__init__(base_url, timeout, retry_config=retry_config)

        # Initialize resource modules
        self.agents = AgentsResource(self)
        self.actions = ActionsResource(self)
        self.logs = LogsResource(self)

    async def health_check(self) -> dict[str, Any]:
        """Check server health."""
        return await self.request("GET", "/health")
