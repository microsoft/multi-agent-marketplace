"""Database models for marketplace entities."""

from typing import Generic, TypeVar

from pydantic import AwareDatetime, BaseModel

from ..shared.models import (
    ActionExecutionRequest,
    ActionExecutionResult,
    AgentProfile,
    Log,
)

T = TypeVar("T")


class Row(BaseModel, Generic[T]):
    """Base database row model with generic data field."""

    id: str
    created_at: AwareDatetime
    data: T
    index: int | None = None


class AgentRow(Row[AgentProfile]):
    """Database Agent model that wraps the Agent with DB fields."""

    agent_embedding: bytes | None = None


class ActionRowData(BaseModel):
    """Data container for action request and result."""

    agent_id: str
    request: ActionExecutionRequest
    result: ActionExecutionResult


class ActionRow(Row[ActionRowData]):
    """Database Action model that wraps the Action with DB fields."""


class LogRow(Row[Log]):
    """Database model for log records that wraps the Log with DB fields."""
