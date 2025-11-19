"""Simple authentication service for agent ID validation."""

from ...database.base import BaseDatabaseController


class AuthService:
    """Database-backed authentication service for agents."""

    def __init__(self, db_controller: BaseDatabaseController):
        """Initialize authentication service with database controller.

        Args:
            db_controller: Database controller for agent validation

        """
        self._db = db_controller

    async def validate_agent_id(self, agent_id: str) -> bool:
        """Validate that an agent_id exists in the database.

        Args:
            agent_id: The agent ID to validate

        Returns:
            True if agent exists, False otherwise

        """
        # Check if the agent exists in the database
        agent = await self._db.agents.get_by_id(agent_id)
        return agent is not None
