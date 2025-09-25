"""Simple authentication service for agent tokens."""

import asyncio
import uuid


class AuthService:
    """Simple token-based authentication service for agents."""

    def __init__(self):
        """Initialize authentication service with empty token storage."""
        # In-memory token storage (agent_id -> token)
        self._agent_tokens: dict[str, str] = {}
        # Reverse lookup (token -> agent_id)
        self._token_to_agent: dict[str, str] = {}
        # Async lock for thread-safe operations
        self._lock = asyncio.Lock()

    async def generate_token(self, agent_id: str) -> str:
        """Generate a new token for an agent."""
        async with self._lock:
            # Generate a UUID token
            token = str(uuid.uuid4())

            # Store the mapping
            self._agent_tokens[agent_id] = token
            self._token_to_agent[token] = agent_id

            return token

    async def validate_token(self, token: str) -> str | None:
        """Validate a token and return the associated agent_id if valid."""
        async with self._lock:
            return self._token_to_agent.get(token)

    async def get_agent_token(self, agent_id: str) -> str | None:
        """Get the current token for an agent."""
        async with self._lock:
            return self._agent_tokens.get(agent_id)

    async def revoke_token(self, agent_id: str) -> bool:
        """Revoke a token for an agent."""
        async with self._lock:
            token = self._agent_tokens.pop(agent_id, None)
            if token:
                self._token_to_agent.pop(token, None)
                return True
            return False
