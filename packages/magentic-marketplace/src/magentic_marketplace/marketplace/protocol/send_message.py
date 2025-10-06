"""SendMessage action implementation for the simple marketplace."""

import logging
import traceback

from magentic_marketplace.platform.database.base import (
    BaseDatabaseController,
    DatabaseTooBusyError,
    RangeQueryParams,
)
from magentic_marketplace.platform.shared.models import (
    ActionExecutionResult,
)

from ..actions import SendMessageAction, SendOrderProposal, SendPayment
from ..database import queries

logger = logging.getLogger(__name__)


async def execute_send_message(
    send_message: SendMessageAction,
    database: BaseDatabaseController,
) -> ActionExecutionResult:
    """Execute a send message action.

    This function implements the message sending functionality that was previously
    handled by the /assistant/send and /service/send routes in platform.py.

    Args:
        send_message: The parsed send message action containing message data
        database: Database controller for accessing data

    Returns:
        ActionExecutionResult indicating success or failure

    """
    try:
        # Validate the target agent exists
        target_agent = await database.agents.get_by_id(send_message.to_agent_id)
        if target_agent is None:
            return ActionExecutionResult(
                content={"error": f"to_agent_id {send_message.to_agent_id} not found"},
                is_error=True,
            )

        # Validate message content
        validation_error = await _validate_message_content(send_message, database)
        if validation_error:
            return ActionExecutionResult(
                content=validation_error,
                is_error=True,
            )

        # Create the action result for the successful send
        action_result = ActionExecutionResult(
            content=send_message.model_dump(mode="json"),
            is_error=False,
            metadata={"status": "sent"},
        )

        return action_result

    except DatabaseTooBusyError:
        # Let DatabaseTooBusyError bubble up so server converts it to HTTP 429
        raise
    except Exception:
        return ActionExecutionResult(
            content={"error": f"Failed to send message: {traceback.format_exc()}"},
            is_error=True,
        )


async def _validate_message_content(
    send_message: SendMessageAction,
    database: BaseDatabaseController,
) -> dict[str, str] | None:
    """Validate message content based on message type.

    Args:
        send_message: The message to validate
        database: Database controller

    Returns:
        Error dict with error_type and message, or None if valid

    """
    # For payment messages, validate proposal_id exists
    if isinstance(send_message, SendPayment):
        proposal_id = send_message.proposal_message_id
        try:
            # Find the order proposal we're trying to pay for
            query = (
                queries.actions.send_message.from_agent(send_message.to_agent_id)
                & queries.actions.send_message.order_proposals()
                & queries.actions.send_message.order_proposal_id(proposal_id)
            )
            action_rows = await database.actions.find(query, RangeQueryParams())
            order_proposals: list[SendOrderProposal] = []
            for row in action_rows:
                try:
                    action = SendOrderProposal.model_validate(
                        row.data.request.parameters
                    )
                    logger.warning("Ignoring OrderProposal expiry time!")
                    order_proposals.append(action)
                    # TODO: Get LLMs to generate a decent expiry time, then bring this back:
                    # if (
                    #     action.message.expiry_time
                    #     and action.message.expiry_time
                    #     < datetime.now(action.message.expiry_time.tzinfo)
                    # ):
                    #     logger.warning("Skipping expired order proposal")
                    # else:
                    #     order_proposals.append(action.message)
                except Exception as e:
                    logger.warning(
                        f"OrderProposal query returned non OrderProposal action: {e}",
                        exc_info=True,
                    )

            if order_proposals:
                logger.info(
                    f"Found {len(order_proposals)} matching unexpired proposals for payment",
                    {
                        "order_proposals": [
                            p.model_dump(mode="json") for p in order_proposals
                        ]
                    },
                )
                # There is at least one unexpired proposal for that id
                return None
            else:
                logger.warning(
                    f"No unexpired order proposals found with id {proposal_id}",
                )
                return {
                    "error_type": "invalid_proposal",
                    "message": f"No unexpired order proposals found with id {proposal_id}",
                }

        except Exception as e:
            return {
                "error_type": "database_error",
                "message": f"Failed to validate proposal: {str(e)}",
            }

    return None
