"""ID generation service for creating unique agent IDs."""

import asyncio
import re

from ...database.base import AgentTableController


class DatabaseIdGenerationService:
    """Database-backed ID generation service with internal state tracking."""

    def __init__(self):
        """Initialize the service."""
        # Track the last suffix used for each base_id
        self._last_suffix: dict[str, int] = {}
        # Use a lock per base_id to prevent race conditions
        self._locks: dict[str, asyncio.Lock] = {}
        self._locks_lock = asyncio.Lock()

    async def _get_lock(self, base_id: str) -> asyncio.Lock:
        """Get or create a lock for the given base_id."""
        async with self._locks_lock:
            if base_id not in self._locks:
                self._locks[base_id] = asyncio.Lock()
            return self._locks[base_id]

    async def generate_unique_agent_id(
        self,
        base_id: str,
        agent_controller: AgentTableController,
        max_retries: int = 10,
    ) -> str:
        """Generate a unique agent ID by adding a suffix to the base ID.

        This method maintains internal state to track the last suffix used for each base_id,
        making it efficient and thread-safe for concurrent requests.

        Args:
            base_id: The base agent ID (e.g., "Agent")
            agent_controller: The AgentTableController from the database
            max_retries: Maximum number of attempts to generate a unique ID (Default: 10)

        Returns:
            A unique agent ID with suffix (e.g., "Agent-0", "Agent-1000", etc.)

        Raises:
            RuntimeError: If unable to generate a unique ID after retries

        """
        # Get a lock specific to this base_id to prevent race conditions
        lock = await self._get_lock(base_id)

        async def find_last_suffix():
            matching_ids = await agent_controller.find_agents_by_id_pattern(base_id)

            # Pattern to match base_id followed by dash and number: base_id-\d+
            pattern = re.compile(rf"^{re.escape(base_id)}-(\d+)$")

            # Find the highest existing suffix number
            max_suffix = -1
            for agent_id in matching_ids:
                match = pattern.match(agent_id)
                if match:
                    suffix = int(match.group(1))
                    max_suffix = max(max_suffix, suffix)

            # Set the last suffix to the highest found (or -1 if none found)
            self._last_suffix[base_id] = max_suffix

        async with lock:
            # Retry logic in case of concurrent creation by external processes
            for attempt in range(max_retries):
                # Find all existing agent IDs that contain the base_id
                await find_last_suffix()

                # Get the next suffix by incrementing our internal counter
                next_suffix = self._last_suffix[base_id] + 1
                candidate_id = f"{base_id}-{next_suffix}"

                # Double-check that this ID doesn't exist (in case another process created it)
                existing_agent = await agent_controller.get_by_id(candidate_id)
                if existing_agent is None:
                    # Success! Update our internal state and return the ID
                    self._last_suffix[base_id] = next_suffix
                    return candidate_id

                await asyncio.sleep(1 + attempt / 1000)

            # If we still can't generate a unique ID, something is very wrong
            raise RuntimeError(
                f"Failed to generate unique ID for base_id '{base_id}' after {max_retries} retries and rescan"
            )
