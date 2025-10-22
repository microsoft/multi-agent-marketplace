"""Configuration management for LLM providers and API settings.

This module provides configuration classes and utilities for managing environment
variables and settings across different LLM providers including OpenAI, Azure OpenAI,
Gemini, and Anthropic.
"""

import logging
import os
from typing import Any, Literal, TypeVar, get_args

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

LLM_PROVIDER = Literal["openai", "gemini", "anthropic"]
ALLOWED_LLM_PROVIDERS = get_args(LLM_PROVIDER)
# Exclude these fields when dumping for concrete client completions
EXCLUDE_FIELDS = {"provider", "max_concurrency", "base_url"}

TField = TypeVar("TField")


def EnvField(*env_vars: str, default: TField | None = None, **kwargs: Any) -> TField:  # noqa: UP047
    """Create a Field that gets its default value from an environment variable."""

    def get_env_value():
        for env_var in env_vars:
            value = os.getenv(env_var)
            if value is not None:
                return value
        logger.debug(
            f"No environment variable found among: {env_vars}, using default value: {default}"
        )
        return default

    return Field(default_factory=get_env_value, validate_default=True, **kwargs)  # pyright: ignore[reportReturnType] # Following the note from pydantic's Field, this is to trick the type checkers, actual return type is FieldInfo


class BaseLLMConfig(BaseModel):
    """Base configuration for LLM providers."""

    provider: LLM_PROVIDER = EnvField("LLM_PROVIDER", "API_PROVIDER")
    model: str | None = EnvField(
        "LLM_MODEL", "AME_MODEL", "AZURE_OPENAI_DEPLOYMENT_NAME", default=None
    )
    reasoning_effort: Literal["minimal", "low", "medium", "high"] | int = EnvField(
        "LLM_REASONING_EFFORT", "REASONING_EFFORT", default="minimal"
    )
    temperature: float | None = EnvField("LLM_TEMPERATURE", default=None)
    max_tokens: int = EnvField("LLM_MAX_TOKENS", default=2000)
    max_concurrency: int = EnvField("LLM_MAX_CONCURRENCY", default=64)
