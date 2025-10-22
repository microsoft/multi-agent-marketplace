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

    async def initialize(self, database: BaseDatabaseController) -> None:
        """Initialize SimpleMarketplace-specific database indexes.

        Creates functional indexes on frequently queried JSONB paths to improve
        query performance for SendMessage action parameters.

        Args:
            database: The database controller instance

        """
        # Import here to avoid circular dependencies
        from magentic_marketplace.platform.database.postgresql.postgresql import (
            PostgreSQLDatabaseController,
        )

        # Only create indexes for PostgreSQL databases
        if isinstance(database, PostgreSQLDatabaseController):
            schema = database._schema

            # Create functional indexes for SendMessage action parameters
            # These indexes extract the JSON values and allow PostgreSQL to use
            # index scans instead of sequential scans for filtered queries
            # Composite indexes include created_at and row_index for efficient sorting
            row_index_col = database.row_index_column
            index_sql = f"""
CREATE INDEX IF NOT EXISTS actions_to_agent_id_idx
  ON {schema}.actions (
    (jsonb_path_query_first(data, '$."request"."parameters"."to_agent_id"'::jsonpath) #>> '{{}}'),
    {row_index_col} DESC
  );

CREATE INDEX IF NOT EXISTS actions_from_agent_id_idx
  ON {schema}.actions (
    (jsonb_path_query_first(data, '$."request"."parameters"."from_agent_id"'::jsonpath) #>> '{{}}'),
    {row_index_col} DESC
  );

CREATE INDEX IF NOT EXISTS actions_request_name_idx
  ON {schema}.actions (
    (jsonb_path_query_first(data, '$."request"."name"'::jsonpath) #>> '{{}}'),
    {row_index_col} DESC
  );

CREATE INDEX IF NOT EXISTS actions_fetch_messages_idx
  ON {schema}.actions (
    (jsonb_path_query_first(data, '$."request"."name"'::jsonpath) #>> '{{}}'),
    (jsonb_path_query_first(data, '$."request"."parameters"."to_agent_id"'::jsonpath) #>> '{{}}'),
    {row_index_col} DESC
  );
"""
            await database.execute(index_sql)

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
