"""Text-only marketplace protocol implementation.

This minimal protocol demonstrates the core structure needed for any marketplace
protocol: defining actions and routing them to handlers.
"""

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
        """Return list of actions agents can perform.

        The platform uses this to validate agent requests and generate
        documentation. Each action class defines its parameters and types.
        """
        return [SendTextMessage, CheckMessages]

    async def execute_action(
        self,
        *,
        agent: AgentProfile,
        action: ActionExecutionRequest,
        database: BaseDatabaseController,
    ) -> ActionExecutionResult:
        """Route an action to its handler.

        The platform calls this method when an agent performs an action.
        This method:
        1. Checks the action type
        2. Validates parameters using the action model
        3. Calls the appropriate handler function
        4. Returns the result

        Args:
            agent: The agent executing the action
            action: Raw action request from agent
            database: Database for reading/writing data

        Returns:
            Result of the action (success or error)

        """
        action_type = action.parameters.get("type")

        if action_type == "send_text_message":
            # Validate and parse the action parameters
            parsed_action = SendTextMessage.model_validate(action.parameters)
            # Call the handler that implements the business logic
            return await execute_send_text_message(parsed_action, database)

        elif action_type == "check_messages":
            parsed_action = CheckMessages.model_validate(action.parameters)
            return await execute_check_messages(parsed_action, agent, database)

        else:
            # Unknown action type - return error
            return ActionExecutionResult(
                content={"error": f"Unknown action type: {action_type}"},
                is_error=True,
            )
