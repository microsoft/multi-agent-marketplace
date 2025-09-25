"""TRAPI model client implementation."""

import logging
from collections.abc import Sequence
from typing import Any, Literal, TypeVar

from pydantic import BaseModel

from ...base import ProviderClient
from ...config import BaseLLMConfig, EnvField
from ..openai import OpenAIClient
from ._trapi import Trapi

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class TrapiConfig(BaseLLMConfig):
    """Configuration for TRAPI provider."""

    provider: Literal["trapi"] = EnvField("LLM_PROVIDER", default="trapi")  # pyright: ignore[reportIncompatibleVariableOverride]


class TrapiClient(OpenAIClient):
    """TRAPI model client that uses the Microsoft Research TRAPI service."""

    def __init__(
        self,
        config: TrapiConfig | None = None,
        *,
        include_models: Sequence[str] | None = None,
        exclude_models: Sequence[str] | None = None,
        **kwargs: Any,
    ):
        """Initialize TRAPI client.

        Args:
            include_models: List of models to include. If None, includes all available.
            exclude_models: List of models to exclude.
            config: Optional LLM configuration. If None, creates one from environment.
            **kwargs: Additional arguments passed to Trapi constructor.

        """
        # Load configuration from environment if not provided
        if config is None:
            config = TrapiConfig()
            logger.debug("Created TrapiConfig from environment variables")
        else:
            config = TrapiConfig.model_validate(config)

        ProviderClient.__init__(self, model=config.model, provider=config.provider)

        self.config = config
        self.client = Trapi(
            include_models=include_models,
            exclude_models=exclude_models,
            **kwargs,
        )
        logger.debug(f"Initialized TrapiClient with provider: {config.provider}")
