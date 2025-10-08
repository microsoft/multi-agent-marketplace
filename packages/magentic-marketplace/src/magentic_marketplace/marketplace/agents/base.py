"""Base agent functionality for the simple marketplace."""

from datetime import UTC, datetime
from typing import Any, TypeVar

from pydantic import BaseModel

from magentic_marketplace.platform.agent.base import BaseAgent, TProfile

from ..actions import (
    FetchMessages,
    FetchMessagesResponse,
    Message,
    SendMessage,
)
from ..llm import generate
from ..llm.config import BaseLLMConfig

TResponseFormat = TypeVar("TResponseFormat", bound=BaseModel)


class LLMCallMetadata(BaseModel):
    """Metadata returned from LLM calls for logging purposes."""

    duration_ms: float
    token_count: int
    provider: str
    model: str


class AgentLogData(BaseModel):
    """Structured log data for agent activities."""

    agent_class: str
    agent_id: str
    additional_data: dict[str, Any] = {}


class BaseSimpleMarketplaceAgent(BaseAgent[TProfile]):
    """Base class for simple marketplace agents with common functionality."""

    def __init__(
        self, profile: TProfile, base_url: str, llm_config: BaseLLMConfig | None = None
    ):
        """Initialize the simple marketplace agent."""
        super().__init__(profile, base_url)
        self.last_fetch_index: int | None = None
        self.llm_config = llm_config or BaseLLMConfig()
        self._seen_message_indexes: set[int] = set()

    async def send_message(self, to_agent_id: str, message: Message):
        """Send a message to another agent.

        Args:
            to_agent_id: ID of the agent to send the message to
            message: The message to send

        Returns:
            Result of the action execution

        """
        action = SendMessage(
            from_agent_id=self.id,
            to_agent_id=to_agent_id,
            created_at=datetime.now(UTC),
            message=message,
        )

        self.logger.info(
            f"Sending {message.type} message to {to_agent_id}",
            data=action,
        )

        result = await self.execute_action(action)

        return result

    async def fetch_messages(
        self,
    ) -> FetchMessagesResponse:
        """Fetch messages received by this agent.

        Args:
            from_agent_id: Filter by sender agent ID
            limit: Maximum number of messages to retrieve
            offset: Number of messages to skip for pagination
            after_index: Only return messages with index greater than this

        Returns:
            Response containing the fetched messages

        """
        action = FetchMessages()

        result = await self.execute_action(action)

        # Check if the action failed
        if result.is_error:
            # Return empty response on error to avoid breaking the agent loop
            self.logger.warning(f"Failed to fetch messages: {result.content}")
            return FetchMessagesResponse(messages=[], has_more=False)

        response = FetchMessagesResponse.model_validate(result.content)

        new_messages = []
        for message in response.messages:
            if message.index not in self._seen_message_indexes:
                new_messages.append(message)
                self._seen_message_indexes.add(message.index)

                if (
                    self.last_fetch_index is None
                    or message.index > self.last_fetch_index
                ):
                    self.last_fetch_index = message.index

        return response.model_copy(update={"messages": new_messages})

    async def generate(self, prompt: str, **kwargs: Any) -> tuple[str, Any]:
        """Generate LLM response with automatic logging.

        Args:
            prompt: The prompt to send to the LLM
            **kwargs: Additional arguments passed to generate

        Returns:
            Tuple of (response_text, call_metadata)

        """
        # Use llm_config if provided, otherwise use kwargs directly
        kwargs = {**self.llm_config.model_dump(), **kwargs}
        response, usage = await generate(
            prompt, logger=self.logger, log_metadata={"agent_id": self.id}, **kwargs
        )

        # Create metadata for compatibility
        call_metadata = LLMCallMetadata(
            duration_ms=0,  # This will be logged internally by generate function
            token_count=usage.token_count,
            provider=usage.provider,
            model=usage.model,
        )

        return response, call_metadata

    async def generate_struct(
        self, prompt: str, response_format: type[TResponseFormat], **kwargs: Any
    ):
        """Generate LLM structured response with automatic logging.

        Args:
            prompt: The prompt to send to the LLM
            response_format: The Pydantic model class for structured response
            **kwargs: Additional arguments passed to generate_struct

        Returns:
            Tuple of (structured_response, call_metadata)

        """
        # Use llm_config if provided, otherwise use kwargs directly
        kwargs = {
            **self.llm_config.model_dump(),
            **kwargs,
        }
        response, usage = await generate(
            prompt,
            response_format=response_format,
            logger=self.logger,
            log_metadata={"agent_id": self.id},
            **kwargs,
        )

        # Create metadata for compatibility
        call_metadata = LLMCallMetadata(
            duration_ms=0,  # This will be logged internally by generate function
            token_count=usage.token_count,
            provider=usage.provider,
            model=usage.model,
        )

        return response, call_metadata
