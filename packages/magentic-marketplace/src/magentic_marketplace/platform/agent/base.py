"""Base class for marketplace agents."""

import asyncio
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from ..client import MarketplaceClient
from ..logger import MarketplaceLogger
from ..shared.models import AgentProfile, BaseAction

# Generic TypeVar bound to AgentProfile
TProfile = TypeVar("TProfile", bound=AgentProfile)


class BaseAgent(Generic[TProfile], ABC):  # noqa: UP046
    """Abstract base class for marketplace agents."""

    def __init__(self, profile: TProfile, base_url: str):
        """Initialize agent with profile and server URL."""
        self.profile: TProfile = profile
        self._base_url = base_url
        self._client = MarketplaceClient(base_url)
        self._logger = MarketplaceLogger(self.id, self._client)
        self.will_shutdown: bool = False

    @property
    def id(self) -> str:
        """Get agent ID from profile."""
        return self.profile.id

    @property
    def client(self):
        """Get the marketplace client."""
        return self._client

    @property
    def logger(self):
        """Get the MarketplaceLogger for this client."""
        return self._logger

    async def get_protocol(self):
        """Get the marketplace protocol information, e.g. allowed actions.

        Returns:
            The protocol information from the marketplace.

        """
        return await self.client.actions.get_protocol()

    async def execute_action(self, action: BaseAction):
        """Execute an action through the marketplace.

        Arguments:
            action: The action to execute in the marketplace.

        Returns:
            The result of the action execution.

        """
        return await self.client.actions.execute(action)

    async def on_started(self):
        """Handle agent startup.

        Override this method to implement custom startup logic.
        """
        pass

    async def on_will_stop(self):
        """Handle agent pre-shutdown.

        Override this method to implement custom pre-shutdown logic.
        """
        pass

    async def on_stopped(self):
        """Handle agent cleanup.

        Override this method to implement custom cleanup logic.
        """
        pass

    def shutdown(self):
        """Signal the agent to shutdown gracefully."""
        self.will_shutdown = True

    @abstractmethod
    async def step(self):
        """Implement one step of agent logic.

        This method should perform one iteration of the agent's main loop.
        Return True to continue running, False to stop.
        """
        pass

    async def run(self):
        """Run the agent. Handles registration and calls step() in a loop within client context."""
        await self._client.connect()
        try:
            response = await self._client.agents.register(self.profile)

            # Update our profile ID to match the database-generated ID
            self.profile.id = response.id
            self._client.set_agent_id(self.profile.id)

            # Call startup hook
            await self.on_started()

            # Main agent loop
            while not self.will_shutdown:
                try:
                    await self.step()
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    # Log error but continue running unless shutdown is requested
                    self.logger.error(f"Error in agent step: {e}")
                    if self.will_shutdown:
                        break
                    await asyncio.sleep(1)  # Brief pause before retrying

        finally:
            # Call shutdown hooks
            await self.on_will_stop()
            await self.on_stopped()
            await self.logger.flush()
            await self._client.close()

    def __repr__(self) -> str:
        """Return string representation of the agent."""
        return f"{self.__class__.__name__}(id='{self.id}')"
