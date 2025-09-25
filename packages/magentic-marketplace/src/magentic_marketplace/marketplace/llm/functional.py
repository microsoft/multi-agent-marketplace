"""Abstract base class for LLM model clients."""

from collections.abc import Sequence
from hashlib import sha256
from typing import Annotated, Any, overload

from pydantic import Field, TypeAdapter

from magentic_marketplace.platform.logger import MarketplaceLogger

from .base import (
    AllowedChatCompletionMessageParams,
    ProviderClient,
    TResponseModel,
    Usage,
)
from .clients.anthropic import AnthropicClient, AnthropicConfig
from .clients.gemini import GeminiClient, GeminiConfig
from .clients.openai import OpenAIClient, OpenAIConfig
from .clients.trapi.client import TrapiClient, TrapiConfig
from .config import LLM_PROVIDER, BaseLLMConfig

ConcreteLLMConfigs = Annotated[
    AnthropicConfig | GeminiConfig | OpenAIConfig | TrapiConfig,
    Field(discriminator="provider"),
]
ConcreteConfigAdapter: TypeAdapter[ConcreteLLMConfigs] = TypeAdapter(ConcreteLLMConfigs)

# Global client cache to avoid creating new HTTP clients for every request
_client_cache: dict[str, ProviderClient] = {}


def _get_client_cache_key(config: BaseLLMConfig):
    client_json = config.model_dump_json(
        # Exclude parameters that don't require a new client
        exclude={
            "model",
            "reasoning_effort",
            "temperature",
            "max_tokens",
        }
    )
    return sha256(client_json.encode()).hexdigest()


@overload
async def generate(
    messages: Sequence[AllowedChatCompletionMessageParams],
    *,
    provider: LLM_PROVIDER | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    reasoning_effort: str | int | None = None,
    response_format: None = None,
    logger: MarketplaceLogger | None = None,
    log_metadata: dict[str, Any] | None = None,
    **kwargs: Any,
) -> tuple[str, Usage]: ...
@overload
async def generate(
    messages: str,
    *,
    provider: LLM_PROVIDER | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    reasoning_effort: str | int | None = None,
    response_format: None = None,
    logger: MarketplaceLogger | None = None,
    log_metadata: dict[str, Any] | None = None,
    **kwargs: Any,
) -> tuple[str, Usage]: ...


@overload
async def generate(
    messages: Sequence[AllowedChatCompletionMessageParams],
    *,
    provider: LLM_PROVIDER | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    reasoning_effort: str | int | None = None,
    response_format: type[TResponseModel],
    logger: MarketplaceLogger | None = None,
    log_metadata: dict[str, Any] | None = None,
    **kwargs: Any,
) -> tuple[TResponseModel, Usage]: ...
@overload
async def generate(
    messages: str,
    *,
    provider: LLM_PROVIDER | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    reasoning_effort: str | int | None = None,
    response_format: type[TResponseModel],
    logger: MarketplaceLogger | None = None,
    log_metadata: dict[str, Any] | None = None,
    **kwargs: Any,
) -> tuple[TResponseModel, Usage]: ...


async def generate(
    messages: Sequence[AllowedChatCompletionMessageParams] | str,
    *,
    provider: LLM_PROVIDER | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    reasoning_effort: str | int | None = None,
    response_format: type[TResponseModel] | None = None,
    logger: MarketplaceLogger | None = None,
    log_metadata: dict[str, Any] | None = None,
    **kwargs: Any,
) -> tuple[str, Usage] | tuple[TResponseModel, Usage]:
    """Generate a completion using OpenAI SDK arguments.

    Args:
        messages: List of chat messages in OpenAI format
        provider: The LLM provider.
        model: The model to use (or default if not provided)
        temperature: Sampling temperature
        max_tokens: Maximum tokens to generate
        reasoning_effort: Reasoning effort level for capable models
        response_format: Optional structured output schema
        logger: Optional MarketplaceLogger for logging LLM calls
        log_metadata: Optional metadata to include with LLM logs
        **kwargs: Additional provider-specific arguments

    Returns:
        String response when response_format is None, otherwise structured BaseModel

    """
    config_kwargs = {
        "provider": provider,
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "reasoning_effort": reasoning_effort,
    }
    config_kwargs = {k: v for k, v in config_kwargs.items() if v is not None}
    config = ConcreteConfigAdapter.validate_python(config_kwargs)

    cache_key = _get_client_cache_key(config)

    # Get or create client from cache
    if cache_key not in _client_cache:
        match config.provider:
            case "anthropic":
                _client_cache[cache_key] = AnthropicClient(config)
            case "openai":
                _client_cache[cache_key] = OpenAIClient(config)
            case "trapi":
                _client_cache[cache_key] = TrapiClient(config)
            case "gemini":
                _client_cache[cache_key] = GeminiClient(config)
            case _:
                raise ValueError(f"Unsupported provider: {config.provider}")

    client = _client_cache[cache_key]

    return await client.generate(
        messages=messages,
        response_format=response_format,
        logger=logger,
        log_metadata=log_metadata,
        **config.model_dump(exclude={"provider"}),
        **kwargs,
    )


def clear_client_cache() -> None:
    """Clear the global client cache. Useful for testing or changing configurations."""
    global _client_cache
    _client_cache.clear()
