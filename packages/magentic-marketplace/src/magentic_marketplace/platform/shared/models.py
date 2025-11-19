"""Shared data models for the marketplace."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SerializeAsAny


# Core domain models
class AgentProfile(BaseModel):
    """Agent model representing a marketplace participant."""

    model_config = ConfigDict(extra="allow")

    id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActionProtocol(BaseModel):
    """Action protocol model for API responses."""

    name: str
    description: str
    parameters: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)


class BaseAction(BaseModel):
    """Base class for marketplace actions."""

    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def get_name(cls):
        """Get the name of this action."""
        return cls.__name__

    @classmethod
    def get_description(cls):
        """Get the description of this action."""
        return cls.__doc__ or ""

    @classmethod
    def get_parameters(cls):
        """Get the parameters (JSON schema) of this action."""
        return cls.model_json_schema()

    @classmethod
    def to_protocol(cls) -> ActionProtocol:
        """Get the ActionProtocol for this action using class name and docstring as action name and description, and BaseModel JSON Schema as parameters."""
        return ActionProtocol(
            name=cls.get_name(),
            description=cls.get_description(),
            parameters=cls.get_parameters(),
            metadata={"source": "BaseAction"},
        )


class ActionExecutionRequest(BaseModel):
    """A request to execute an action."""

    name: str
    parameters: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActionExecutionResult(BaseModel):
    """The result of executing an action."""

    content: Any
    is_error: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


LogLevel = Literal["debug", "info", "warning", "error"]


class Log(BaseModel):
    """Log model representing a log entry."""

    model_config = ConfigDict(extra="allow")

    level: LogLevel
    name: str
    message: str | None = None
    data: dict[str, Any] | SerializeAsAny[BaseModel] | None = None
    metadata: dict[str, Any] | None = None


# Base Request/Response models for API
class BaseRequest(BaseModel):
    """Base class for all API requests."""

    pass


class BaseResponse(BaseModel):
    """Base class for all API responses."""

    error: str | None = None


class ListRequest(BaseRequest):
    """Base class for list requests with pagination support."""

    offset: int = 0
    limit: int | None = None


class ListResponse(BaseResponse):
    """Base class for list responses with pagination metadata."""

    total: int | None = None
    offset: int
    limit: int | None
    has_more: bool | None = None


# Agent-related Request/Response models
class AgentRegistrationRequest(BaseRequest):
    """Request model for agent registration using Agent type."""

    agent: SerializeAsAny[AgentProfile]


class AgentRegistrationResponse(BaseResponse):
    """Response model for agent registration."""

    id: str


class AgentListResponse(ListResponse):
    """Response model for agent list endpoints."""

    items: list[SerializeAsAny[AgentProfile]]


class AgentGetResponse(BaseResponse):
    """Response model for getting a single agent."""

    agent: SerializeAsAny[AgentProfile]


# Action-related Request/Response models
class ActionProtocolResponse(BaseResponse):
    """Response model for action protocol endpoint."""

    actions: list[ActionProtocol]


# Log-related Request/Response models
class LogCreateRequest(BaseRequest):
    """Request model for creating log records."""

    log: Log


class LogListResponse(ListResponse):
    """Response model for log list endpoints."""

    items: list[Log]
