"""Simple marketplace protocol implementation."""

from typing import get_args

from magentic_marketplace.platform.database.base import BaseDatabaseController
from magentic_marketplace.platform.protocol.base import BaseMarketplaceProtocol
from magentic_marketplace.platform.shared.models import (
    ActionExecutionRequest,
    ActionExecutionResult,
    AgentProfile,
)

from ..actions import (
    Action,
    ActionAdapter,
    FetchMessages,
    Search,
    SendMessageAction,
)
from .fetch_messages import execute_fetch_messages
from .search import execute_search
from .send_message import execute_send_message


class SimpleMarketplaceProtocol(BaseMarketplaceProtocol):
    """Marketplace protocol."""

    def __init__(self):
        """Initialize the marketplace protocol."""

    def get_actions(self):
        """Define available actions in the marketplace."""
        return list(get_args(Action))

    async def execute_action(
        self,
        *,
        agent: AgentProfile,
        action: ActionExecutionRequest,
        database: BaseDatabaseController,
    ) -> ActionExecutionResult:
        """Execute an action."""
        parsed_action = ActionAdapter.validate_python(action.parameters)

        if isinstance(parsed_action, SendMessageAction):
            return await execute_send_message(parsed_action, database)

        elif isinstance(parsed_action, FetchMessages):
            return await execute_fetch_messages(parsed_action, agent, database)

        elif isinstance(parsed_action, Search):  # pyright: ignore[reportUnnecessaryIsInstance]
            return await execute_search(parsed_action, database)
        else:
            raise ValueError(f"Unknown action type: {parsed_action.type}")
