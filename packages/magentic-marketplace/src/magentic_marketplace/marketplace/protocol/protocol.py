"""Simple marketplace protocol implementation."""

from collections import defaultdict

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
from .fetch_messages import FetchMessagesPersistence, execute_fetch_messages
from .search import execute_search
from .send_message import execute_send_message


class SimpleMarketplaceProtocol(BaseMarketplaceProtocol):
    """Marketplace protocol."""

    def __init__(
        self,
        fetch_messages_persistence: FetchMessagesPersistence = FetchMessagesPersistence.ALL,
    ):
        """Initialize the marketplace protocol.

        Args:
            fetch_messages_persistence: Controls which FetchMessages actions are persisted to database.
                - ALL (default): Save all FetchMessages actions
                - NON_EMPTY: Save only FetchMessages that returned messages
                - NONE: Don't save any FetchMessages actions

        """
        self.fetch_messages_persistence = fetch_messages_persistence
        # Track how many messages were fetched by an agent in the last count, use it to determine if "new" messages were provided or not
        self._to_agent_id_last_fetch_messages_count: dict[str, int] = defaultdict(int)

    def get_actions(self):
        """Define available actions in the marketplace."""
        return [SendMessage, FetchMessages, Search]

    async def execute_action(
        self,
        *,
        agent: AgentProfile,
        action: ActionExecutionRequest,
        database: BaseDatabaseController,
    ) -> tuple[ActionExecutionResult, bool]:
        """Execute an action.

        Returns:
            A tuple of (ActionExecutionResult, bool) where:
                - ActionExecutionResult contains the action execution result
                - bool indicates whether the action should be persisted to the database

        """
        parsed_action = ActionAdapter.validate_python(action.parameters)

        if isinstance(parsed_action, SendMessage):
            return await execute_send_message(parsed_action, database), True

        elif isinstance(parsed_action, FetchMessages):
            return await execute_fetch_messages(
                parsed_action,
                agent,
                database,
                self._to_agent_id_last_fetch_messages_count,
                self.fetch_messages_persistence,
            )

        elif isinstance(parsed_action, Search):
            return await execute_search(
                search=parsed_action, agent=agent, database=database
            ), True
        else:
            raise ValueError(f"Unknown action type: {parsed_action.type}")
