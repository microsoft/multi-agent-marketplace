"""FetchMessages action implementation for the simple marketplace."""

from magentic_marketplace.platform.database.base import BaseDatabaseController
from magentic_marketplace.platform.database.models import ActionRow
from magentic_marketplace.platform.database.queries.base import (
    RangeQueryParams,
)
from magentic_marketplace.platform.shared.models import (
    ActionExecutionResult,
    AgentProfile,
)

from ..actions import FetchMessages, FetchMessagesResponse, ReceivedMessage
from ..actions.messaging import MessageAdapter
from ..database import queries


async def execute_fetch_messages(
    fetch_messages: FetchMessages,
    agent: AgentProfile,
    database: BaseDatabaseController,
) -> ActionExecutionResult:
    """Execute a fetch messages action.

    This function implements the message fetching functionality that was previously
    handled by the /assistant/receive and /service/receive routes in platform.py.

    Args:
        fetch_messages: The fetch messages action containing query parameters
        agent: The agent fetching messages
        database: Database controller for accessing data

    Returns:
        ActionExecutionResult containing the fetched messages

    """
    messages, has_more = await _fetch_messages_from_database(
        fetch_messages, agent, database
    )

    response = FetchMessagesResponse(
        messages=messages,
        has_more=has_more,
    )

    return ActionExecutionResult(content=response.model_dump(mode="json"))


async def _fetch_messages_from_database(
    fetch_messages: FetchMessages,
    agent: AgentProfile,
    database: BaseDatabaseController,
) -> tuple[list[ReceivedMessage], bool]:
    """Fetch messages from the actions table using efficient database queries.

    Args:
        fetch_messages: The fetch messages action containing query parameters
        agent: The agent making the request
        database: Database controller

    Returns:
        List of ReceivedMessage objects

    """
    # Build query to filter SendMessage actions for this recipient
    from magentic_marketplace.platform.database.queries.base import Query

    query: Query = queries.actions.send_message.to_agent(agent.id)

    # Add sender filter if specified
    if fetch_messages.from_agent_id is not None:
        query &= queries.actions.send_message.from_agent(fetch_messages.from_agent_id)

    # Setup query parameters with pagination and index filtering
    limit = (
        fetch_messages.limit + 1 if fetch_messages.limit else None
    )  # +1 to check for has_more
    query_params = RangeQueryParams(
        offset=fetch_messages.offset or 0,
        limit=limit,
        after=fetch_messages.after,
        after_index=fetch_messages.after_index,
    )

    # Execute the query
    action_rows = await database.actions.find(query, query_params)

    # Convert to ReceivedMessage objects
    received_messages: list[ReceivedMessage] = []
    for action_row in action_rows:
        received_message = _convert_action_to_received_message(action_row)
        if received_message:
            received_messages.append(received_message)

    has_more = False
    if (
        fetch_messages.limit is not None
        and len(received_messages) > fetch_messages.limit
    ):
        received_messages = received_messages[: fetch_messages.limit - 1]
        has_more = True

    return received_messages, has_more


def _convert_action_to_received_message(
    action_row: ActionRow,
) -> ReceivedMessage | None:
    """Convert ActionRow to ReceivedMessage format.

    Args:
        action_row: ActionRow from database

    Returns:
        ReceivedMessage object or None if conversion fails

    """
    params = action_row.data.request.parameters
    message_data = params.get("message", {})
    message = MessageAdapter.validate_python(message_data)

    if action_row.index is None:
        raise ValueError(
            "action_row.index must not be None, i.e. it must be returned from a database operation."
        )

    return ReceivedMessage(
        from_agent_id=params["from_agent_id"],
        to_agent_id=params["to_agent_id"],
        created_at=action_row.created_at,
        message=message,
        index=action_row.index,
    )
