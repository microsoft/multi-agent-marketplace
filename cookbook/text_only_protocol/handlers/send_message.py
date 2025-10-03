"""Handler for SendTextMessage action."""

from magentic_marketplace.platform.database.base import (
    BaseDatabaseController,
    DatabaseTooBusyError,
)
from magentic_marketplace.platform.shared.models import ActionExecutionResult

from ..actions import SendTextMessage


async def execute_send_text_message(
    action: SendTextMessage,
    database: BaseDatabaseController,
) -> ActionExecutionResult:
    """Execute a send text message action.

    Args:
        action: The parsed send text message action
        database: Database controller for accessing data

    Returns:
        ActionExecutionResult indicating success or failure

    """
    try:
        # Validate the target agent exists
        target_agent = await database.agents.get_by_id(action.to_agent_id)
        if target_agent is None:
            return ActionExecutionResult(
                content={"error": f"Agent {action.to_agent_id} not found"},
                is_error=True,
            )

        # Return success - message is auto-persisted by platform
        return ActionExecutionResult(
            content=action.model_dump(mode="json"),
            is_error=False,
            metadata={"status": "sent"},
        )

    except DatabaseTooBusyError:
        # Let DatabaseTooBusyError bubble up so server converts it to HTTP 429
        raise
    except Exception as e:
        return ActionExecutionResult(
            content={"error": f"Failed to send message: {str(e)}"},
            is_error=True,
        )
