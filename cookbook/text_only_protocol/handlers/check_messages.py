"""Handler for CheckMessages action."""

from magentic_marketplace.platform.database.base import BaseDatabaseController
from magentic_marketplace.platform.database.models import ActionRow
from magentic_marketplace.platform.database.queries.base import RangeQueryParams
from magentic_marketplace.platform.shared.models import (
    ActionExecutionResult,
    AgentProfile,
)

from ..actions import CheckMessages, CheckMessagesResponse, ReceivedTextMessage
from ..database import queries


async def execute_check_messages(
    action: CheckMessages,
    agent: AgentProfile,
    database: BaseDatabaseController,
) -> ActionExecutionResult:
    """Execute a check messages action.

    Args:
        action: The check messages action containing query parameters
        agent: The agent checking messages
        database: Database controller for accessing data

    Returns:
        ActionExecutionResult containing the fetched messages

    """
    try:
        messages, has_more = await _fetch_messages_from_database(
            action, agent, database
        )

        response = CheckMessagesResponse(
            messages=messages,
            has_more=has_more,
        )

        return ActionExecutionResult(content=response.model_dump(mode="json"))

    except Exception as e:
        return ActionExecutionResult(
            content={"error": str(e)},
            is_error=True,
        )


async def _fetch_messages_from_database(
    action: CheckMessages,
    agent: AgentProfile,
    database: BaseDatabaseController,
) -> tuple[list[ReceivedTextMessage], bool]:
    """Fetch messages from the actions table using database queries.

    Args:
        action: The check messages action containing query parameters
        agent: The agent making the request
        database: Database controller

    Returns:
        Tuple of (list of ReceivedTextMessage objects, has_more flag)

    """
    # Build query to filter SendTextMessage actions for this recipient
    query = queries.to_agent(agent.id) & queries.action_type("send_text_message")

    # Setup query parameters with pagination
    limit = action.limit + 1 if action.limit else None
    query_params = RangeQueryParams(
        offset=action.offset or 0,
        limit=limit,
    )

    # Execute the query
    action_rows = await database.actions.find(query, query_params)

    # Convert to ReceivedTextMessage objects
    received_messages: list[ReceivedTextMessage] = []
    for action_row in action_rows:
        received_message = _convert_action_to_received_message(action_row)
        if received_message:
            received_messages.append(received_message)

    # Check if there are more messages
    has_more = False
    if action.limit is not None and len(received_messages) > action.limit:
        received_messages = received_messages[: action.limit]
        has_more = True

    return received_messages, has_more


def _convert_action_to_received_message(
    action_row: ActionRow,
) -> ReceivedTextMessage | None:
    """Convert ActionRow to ReceivedTextMessage format.

    Args:
        action_row: ActionRow from database

    Returns:
        ReceivedTextMessage object or None if conversion fails

    """
    params = action_row.data.request.parameters

    return ReceivedTextMessage(
        from_agent_id=params["from_agent_id"],
        to_agent_id=params["to_agent_id"],
        created_at=action_row.created_at,
        message=params["message"],
    )
