"""Abstract base class for LLM model clients."""

import asyncio
import time
from abc import ABC, abstractmethod
from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from types import TracebackType
from typing import Any, Generic, TypeVar, overload

from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from pydantic import BaseModel

from magentic_marketplace.platform.logger import MarketplaceLogger

from .config import BaseLLMConfig

TConfig = TypeVar("TConfig", bound=BaseLLMConfig)
TResponseModel = TypeVar("TResponseModel", bound=BaseModel)

AllowedChatCompletionMessageParams = (
    ChatCompletionUserMessageParam
    | ChatCompletionAssistantMessageParam
    | ChatCompletionSystemMessageParam
)


class Usage(BaseModel):
    """Usage information about a LLM completion."""

    token_count: int
    provider: str
    model: str


class LLMCallLog(BaseModel):
    """Structured log data for an LLM call."""

    type: str = "llm_call"
    success: bool
    provider: str | None
    model: str | None
    duration_ms: float
    token_count: int
    error_message: str | None
    prompt: Sequence[AllowedChatCompletionMessageParams] | str
    response: str | dict[str, Any]
    response_format: Any | None
    api_args: dict[str, Any]


class _DummySemaphore(AbstractAsyncContextManager):
    async def __aenter__(self):
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ):
        pass


class ProviderClient(ABC, Generic[TConfig]):
    """Abstract base class for LLM clients.

    All LLM clients accept OpenAI SDK arguments and convert them to the
    appropriate format for their specific provider.
    """

    def __init__(self, config: TConfig):
        """Create an instance of a ProviderClient.

        Args:
            config: The llm config model

        """
        self.config = config
        self.provider = config.provider
        self.model = config.model
        self._max_concurrency = config.max_concurrency
        self._semaphore = (
            asyncio.Semaphore(config.max_concurrency)
            if config.max_concurrency is not None
            else _DummySemaphore()
        )

    @overload
    async def _generate(
        self,
        *,
        model: str,
        messages: Sequence[AllowedChatCompletionMessageParams],
        temperature: float | None = None,
        max_tokens: int | None = None,
        reasoning_effort: str | int | None = None,
        response_format: None = None,
        **kwargs: Any,
    ) -> tuple[str, Usage]: ...

    @overload
    async def _generate(
        self,
        *,
        model: str,
        messages: Sequence[AllowedChatCompletionMessageParams],
        temperature: float | None = None,
        max_tokens: int | None = None,
        reasoning_effort: str | int | None = None,
        response_format: type[TResponseModel],
        **kwargs: Any,
    ) -> tuple[TResponseModel, Usage]: ...

    @abstractmethod
    async def _generate(
        self,
        *,
        model: str,
        messages: Sequence[AllowedChatCompletionMessageParams],
        temperature: float | None = None,
        max_tokens: int | None = None,
        reasoning_effort: str | int | None = None,
        response_format: type[TResponseModel] | None = None,
        **kwargs: Any,
    ) -> tuple[str, Usage] | tuple[TResponseModel, Usage]:
        """Generate a completion using OpenAI SDK arguments.

        Args:
            model: The model to use
            messages: List of chat messages in OpenAI format
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            reasoning_effort: Reasoning effort level for capable models
            response_format: Optional structured output schema
            **kwargs: Additional provider-specific arguments

        Returns:
            String response when response_format is None, otherwise structured BaseModel

        """
        pass

    @overload
    async def generate(
        self,
        messages: Sequence[AllowedChatCompletionMessageParams] | str,
        *,
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
        self,
        messages: Sequence[AllowedChatCompletionMessageParams] | str,
        *,
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
        self,
        messages: Sequence[AllowedChatCompletionMessageParams] | str,
        *,
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
            model: The model to use (or default if not provided)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            reasoning_effort: Reasoning effort level for capable models
            response_format: Optional structured output schema
            logger: Optional MarketplaceLogger to save LLM logs
            log_metadata: Optional metadata to include with LLM logs
            **kwargs: Additional provider-specific arguments

        Returns:
            String response when response_format is None, otherwise structured BaseModel

        """
        if isinstance(messages, str):
            messages = [ChatCompletionUserMessageParam(role="user", content=messages)]

        model = model or self.model

        if not model:
            raise ValueError("model required when self.model is not set.")

        async with self._semaphore:
            start_time = time.time()
            try:
                result = await self._generate(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    reasoning_effort=reasoning_effort,
                    response_format=response_format,
                    **kwargs,
                )

                duration_ms = (time.time() - start_time) * 1000

                # Log successful LLM call
                if logger is not None:
                    response_format_data = None
                    if response_format is not None:
                        response_format_data = response_format.model_json_schema()

                    log_data = LLMCallLog(
                        success=True,
                        provider=result[1].provider,
                        model=result[1].model,
                        duration_ms=duration_ms,
                        token_count=result[1].token_count,
                        error_message=None,
                        prompt=messages,
                        response=result[0].model_dump()
                        if isinstance(result[0], BaseModel)
                        else result[0],
                        response_format=response_format_data,
                        api_args={
                            "model": model,
                            "temperature": temperature,
                            "max_tokens": max_tokens,
                            "reasoning_effort": reasoning_effort,
                            **kwargs,
                        },
                    )

                    logger.debug(
                        "LLM call succeeded", data=log_data, metadata=log_metadata
                    )

                return result

            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000

                # Log failed LLM call
                if logger is not None:
                    response_format_data = None
                    if response_format is not None:
                        response_format_data = response_format.model_json_schema()

                    log_data = LLMCallLog(
                        success=False,
                        provider=self.provider,
                        model=model,
                        duration_ms=duration_ms,
                        token_count=0,
                        error_message=str(e),
                        prompt=messages,
                        response="",
                        response_format=response_format_data,
                        api_args={
                            "model": model,
                            "temperature": temperature,
                            "max_tokens": max_tokens,
                            "reasoning_effort": reasoning_effort,
                            **kwargs,
                        },
                    )

                    logger.debug(
                        "LLM call failed", data=log_data, metadata=log_metadata
                    )

                raise
