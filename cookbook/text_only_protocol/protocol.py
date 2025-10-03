"""Text-only marketplace protocol implementation."""

from magentic_marketplace.platform.database.base import BaseDatabaseController
from magentic_marketplace.platform.protocol.base import BaseMarketplaceProtocol
from magentic_marketplace.platform.shared.models import (
    ActionExecutionRequest,
    ActionExecutionResult,
    AgentProfile,
)

from .actions import CheckMessages, SendTextMessage
from .handlers.check_messages import execute_check_messages
from .handlers.send_message import execute_send_text_message


class TextOnlyProtocol(BaseMarketplaceProtocol):
    """Simple text-only marketplace protocol.

    This protocol supports only two actions:
    - SendTextMessage: Send a text message to another agent
    - CheckMessages: Retrieve text messages received by an agent

    """

    def __init__(self):
        """Initialize the text-only protocol."""

    def get_actions(self):
        """Define available actions in the marketplace."""
        return [SendTextMessage, CheckMessages]

    async def execute_action(
        self,
        *,
        agent: AgentProfile,
        action: ActionExecutionRequest,
        database: BaseDatabaseController,
    ) -> ActionExecutionResult:
        """Execute an action.

        Args:
            agent: The agent executing the action
            action: The action execution request
            database: Database controller for accessing data

        Returns:
            ActionExecutionResult containing the result of the action

        """
        action_type = action.parameters.get("type")

        if action_type == "send_text_message":
            parsed_action = SendTextMessage.model_validate(action.parameters)
            return await execute_send_text_message(parsed_action, database)

        elif action_type == "check_messages":
            parsed_action = CheckMessages.model_validate(action.parameters)
            return await execute_check_messages(parsed_action, agent, database)

        else:
            return ActionExecutionResult(
                content={"error": f"Unknown action type: {action_type}"},
                is_error=True,
            )
