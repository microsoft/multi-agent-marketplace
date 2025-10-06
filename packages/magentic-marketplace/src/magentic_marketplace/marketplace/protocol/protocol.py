"""Simple marketplace protocol implementation."""

from magentic_marketplace.platform.database.base import BaseDatabaseController
from magentic_marketplace.platform.protocol.base import BaseMarketplaceProtocol
from magentic_marketplace.platform.shared.models import (
    ActionExecutionRequest,
    ActionExecutionResult,
    AgentProfile,
)

from ..actions import (
    ActionAdapter,
    FetchMessages,
    Search,
    SendMessage,
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
        return [SendMessage, FetchMessages, Search]

    async def execute_action(
        self,
        *,
        agent: AgentProfile,
        action: ActionExecutionRequest,
        database: BaseDatabaseController,
    ) -> ActionExecutionResult:
        """Execute an action."""
        parsed_action = ActionAdapter.validate_python(action.parameters)

        if isinstance(parsed_action, SendMessage):
            return await execute_send_message(parsed_action, database)

        elif isinstance(parsed_action, FetchMessages):
            return await execute_fetch_messages(parsed_action, agent, database)

        elif isinstance(parsed_action, Search):
            return await execute_search(
                search=parsed_action, agent=agent, database=database
            )
        else:
            raise ValueError(f"Unknown action type: {parsed_action.type}")
