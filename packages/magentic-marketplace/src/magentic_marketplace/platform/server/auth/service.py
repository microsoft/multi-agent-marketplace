"""Simple authentication service for agent tokens."""

import uuid

from ...database.base import BaseDatabaseController


class AuthService:
    """Database-backed token-based authentication service for agents."""

    def __init__(self, db_controller: BaseDatabaseController):
        """Initialize authentication service with database controller.

        Args:
            db_controller: Database controller for persistent token storage

        """
        self._db = db_controller

    async def generate_token(self, agent_id: str) -> str:
        """Generate a new token for an agent and store it in the database.

        Args:
            agent_id: The ID of the agent to generate a token for

        Returns:
            The generated token string

        """
        # Generate a UUID token
        token = str(uuid.uuid4())

        # Update the agent's auth_token in the database
        await self._db.agents.update(agent_id, {"auth_token": token})

        return token

    async def validate_token(self, token: str) -> str | None:
        """Validate a token and return the associated agent_id if valid.

        Args:
            token: The token to validate

        Returns:
            The agent_id if token is valid, None otherwise

        """
        # Query the database for an agent with this token
        agent = await self._db.agents.get_agent_by_token(token)
        return agent.id if agent else None

    async def get_agent_token(self, agent_id: str) -> str | None:
        """Get the current token for an agent from the database.

        Args:
            agent_id: The ID of the agent to get the token for

        Returns:
            The agent's token if it exists, None otherwise

        """
        # Get the agent from the database
        agent = await self._db.agents.get_by_id(agent_id)
        return agent.auth_token if agent else None

    async def revoke_token(self, agent_id: str) -> bool:
        """Revoke a token for an agent by setting it to NULL in the database.

        Args:
            agent_id: The ID of the agent to revoke the token for

        Returns:
            True if token was revoked, False if agent not found

        """
        # Set the agent's auth_token to NULL in the database
        result = await self._db.agents.update(agent_id, {"auth_token": None})
        return result is not None
