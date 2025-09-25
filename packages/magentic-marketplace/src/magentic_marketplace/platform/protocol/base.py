"""Behavior protocol interface for agent actions."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from ..database.base import BaseDatabaseController
from ..shared.models import (
    ActionExecutionRequest,
    ActionExecutionResult,
    ActionProtocol,
    AgentProfile,
    BaseAction,
)


class BaseMarketplaceProtocol(ABC):
    """Abstract interface for defining agent behavior protocols."""

    @abstractmethod
    def get_actions(self) -> Sequence[ActionProtocol | type[BaseAction]]:
        """Get available actions for this protocol."""
        ...

    @abstractmethod
    async def execute_action(
        self,
        *,
        agent: AgentProfile,
        action: ActionExecutionRequest,
        database: BaseDatabaseController,
    ) -> ActionExecutionResult:
        """Execute a specific action with the given name and parameters."""
        ...
