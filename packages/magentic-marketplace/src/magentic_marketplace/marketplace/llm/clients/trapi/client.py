"""TRAPI model client implementation."""

import logging
import threading
from collections.abc import Sequence
from hashlib import sha256
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

    _client_cache: dict[str, "TrapiClient"] = {}  # pyright: ignore[reportIncompatibleVariableOverride]
    _cache_lock = threading.Lock()

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

        ProviderClient.__init__(self, config)

        self.config = config
        self.client = Trapi(
            include_models=include_models,
            exclude_models=exclude_models,
            **kwargs,
        )
        logger.debug(f"Initialized TrapiClient with provider: {config.provider}")

    @staticmethod
    def _get_cache_key(  # pyright: ignore[reportIncompatibleMethodOverride]
        config: TrapiConfig,
        include_models: Sequence[str] | None = None,
        exclude_models: Sequence[str] | None = None,
        **kwargs: Any,
    ) -> str:
        """Generate cache key for a config."""
        # Create a dictionary with all cache-relevant parameters
        cache_params = {
            "config": config.model_dump_json(include={"provider"}),
            "include_models": list(include_models) if include_models else None,
            "exclude_models": list(exclude_models) if exclude_models else None,
            "kwargs": kwargs,
        }
        # Convert to JSON and hash
        import json

        cache_json = json.dumps(cache_params, sort_keys=True)
        return sha256(cache_json.encode()).hexdigest()

    @staticmethod
    def from_cache(  # pyright: ignore[reportIncompatibleMethodOverride]
        config: TrapiConfig,
        *,
        include_models: Sequence[str] | None = None,
        exclude_models: Sequence[str] | None = None,
        **kwargs: Any,
    ) -> "TrapiClient":
        """Get or create client from cache."""
        cache_key = TrapiClient._get_cache_key(
            config, include_models, exclude_models, **kwargs
        )
        with TrapiClient._cache_lock:
            if cache_key not in TrapiClient._client_cache:
                TrapiClient._client_cache[cache_key] = TrapiClient(
                    config,
                    include_models=include_models,
                    exclude_models=exclude_models,
                    **kwargs,
                )
            return TrapiClient._client_cache[cache_key]
