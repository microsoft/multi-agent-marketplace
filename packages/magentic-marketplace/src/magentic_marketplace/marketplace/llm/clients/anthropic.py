"""Anthropic model client implementation."""

import threading
from collections.abc import Sequence
from hashlib import sha256
from typing import Any, Literal, cast, overload

import anthropic
import anthropic.types

from ..base import (
    AllowedChatCompletionMessageParams,
    ProviderClient,
    TResponseModel,
    Usage,
)
from ..config import BaseLLMConfig, EnvField


class AnthropicConfig(BaseLLMConfig):
    """Configuration for Anthropic provider."""

    provider: Literal["anthropic"] = EnvField("LLM_PROVIDER", default="anthropic")  # pyright: ignore[reportIncompatibleVariableOverride]
    api_key: str = EnvField("ANTHROPIC_API_KEY", exclude=True)


class AnthropicClient(ProviderClient[AnthropicConfig]):
    """Anthropic model client that accepts OpenAI SDK arguments."""

    _client_cache: dict[str, "AnthropicClient"] = {}
    _cache_lock = threading.Lock()

    def __init__(self, config: AnthropicConfig | None = None):
        """Initialize Anthropic client.

        Args:
            config: Anthropic configuration. If None, creates from environment.

        """
        if config is None:
            config = AnthropicConfig()
        else:
            config = AnthropicConfig.model_validate(config)

        super().__init__(config)

        self.config = config
        if not self.config.api_key:
            raise ValueError(
                "Anthropic API key not found. Set ANTHROPIC_API_KEY environment variable "
                "or pass api_key in config."
            )
        self.client = anthropic.AsyncAnthropic(api_key=self.config.api_key)

    @staticmethod
    def _get_cache_key(config: AnthropicConfig) -> str:
        """Generate cache key for a config."""
        config_json = config.model_dump_json(include={"api_key", "provider"})
        return sha256(config_json.encode()).hexdigest()

    @staticmethod
    def from_cache(config: AnthropicConfig) -> "AnthropicClient":
        """Get or create client from cache."""
        cache_key = AnthropicClient._get_cache_key(config)
        with AnthropicClient._cache_lock:
            if cache_key not in AnthropicClient._client_cache:
                AnthropicClient._client_cache[cache_key] = AnthropicClient(config)
            return AnthropicClient._client_cache[cache_key]

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
        """Generate completion using Anthropic API."""
        # Convert OpenAI messages to Anthropic format
        anthropic_messages, system_prompt = self._convert_messages(messages)

        # Build base arguments
        args: dict[str, Any] = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens or 2000,
        }

        # Add system prompt if we have system messages
        if system_prompt:
            args["system"] = system_prompt

        # Handle reasoning effort -> thinking config
        thinking_config = None
        if reasoning_effort is not None:
            if reasoning_effort == "minimal":
                reasoning_effort = 0

            if isinstance(reasoning_effort, str):
                reasoning_effort = 0  # Fallback for unsupported string values

            if reasoning_effort == 0:
                thinking_config = anthropic.types.ThinkingConfigDisabledParam(
                    type="disabled"
                )
            else:
                # Temperature not supported for thinking mode
                temperature = None
                thinking_config = anthropic.types.ThinkingConfigEnabledParam(
                    type="enabled", budget_tokens=reasoning_effort
                )

        if thinking_config:
            args["thinking"] = thinking_config

        if temperature is not None:
            args["temperature"] = temperature

        # Add any additional kwargs
        args.update(kwargs)

        # Handle structured output via tool calling
        if response_format is not None:
            return await self._generate_structured(args, response_format, model)
        else:
            # Regular completion
            response = await self.client.messages.create(**args, stream=False)

            # Create usage object
            usage = Usage(
                token_count=response.usage.input_tokens + response.usage.output_tokens
                if response.usage
                else 0,
                provider="anthropic",
                model=model,
            )

            # Collect all text content
            content = ""
            for block in response.content:
                if block.type == "text":
                    content += block.text

            return content, usage

    def _convert_messages(
        self, messages: Sequence[AllowedChatCompletionMessageParams]
    ) -> tuple[list[anthropic.types.MessageParam], str | None]:
        """Convert OpenAI messages to Anthropic format.

        Returns:
            A tuple of (messages, system_prompt) where messages is the list of
            MessageParam objects and system_prompt is the concatenated system messages
            or None if there are no system messages.

        """
        anthropic_messages: list[anthropic.types.MessageParam] = []
        system_messages: list[str] = []

        for message in messages:
            role = message.get("role")
            content = message.get("content")

            if not content:
                continue

            # Collect system messages separately
            if role == "system":
                if isinstance(content, str):
                    system_messages.append(content)
                elif isinstance(content, list):
                    # Handle multi-part content (text only for now)
                    text_parts: list[str] = []
                    for part in content:
                        if part.get("type", None) == "text":
                            text = part.get("text", "")
                            text_parts.append(text)
                    if text_parts:
                        system_messages.append("\n".join(text_parts))
            elif role in ("user", "assistant"):
                # Handle different content formats
                if isinstance(content, str):
                    anthropic_messages.append(
                        anthropic.types.MessageParam(role=role, content=content)
                    )
                elif isinstance(content, list):
                    # Handle multi-part content (text only for now)
                    text_content: list[str] = []
                    for part in content:
                        if part.get("type", None) == "text":
                            text = part.get("text", "")
                            text_content.append(text)

                    if text_content:
                        anthropic_messages.append(
                            anthropic.types.MessageParam(
                                role=role,
                                content="\n".join(text_content),
                            )
                        )

        # Concatenate system messages or return None
        system_prompt = "\n\n".join(system_messages) if system_messages else None

        return anthropic_messages, system_prompt

    async def _generate_structured(
        self,
        base_args: dict[str, Any],
        response_format: type[TResponseModel],
        model: str,
    ) -> tuple[TResponseModel, Usage]:
        """Generate structured output using tool calling."""
        # Create tool for the response format
        tool = anthropic.types.ToolParam(
            name=f"generate{response_format.__name__}",
            description=f"Generate a {response_format.__name__} object.",
            input_schema=response_format.model_json_schema(),
        )

        tool_choice = anthropic.types.ToolChoiceToolParam(
            name=tool["name"], type="tool", disable_parallel_tool_use=True
        )

        # Update args for tool use
        args = base_args.copy()
        args["tools"] = [tool]
        args["tool_choice"] = tool_choice

        # Thinking not allowed when forcing tool use
        if "thinking" in args:
            args["thinking"] = anthropic.types.ThinkingConfigDisabledParam(
                type="disabled"
            )

        # Track exception messages for final error
        exceptions: list[str] = []

        # Make up to 3 attempts
        for attempt in range(3):
            try:
                response = await self.client.messages.create(**args, stream=False)

                # Find tool use block
                for block in response.content:
                    if block.type == "tool_use":
                        usage = Usage(
                            token_count=response.usage.input_tokens
                            + response.usage.output_tokens
                            if response.usage
                            else 0,
                            provider="anthropic",
                            model=model,
                        )

                        try:
                            validated_response = response_format.model_validate(
                                block.input
                            )
                            return validated_response, usage
                        except Exception as e:
                            import traceback

                            tb_str = traceback.format_exc()
                            error_message = f"Error parsing tool response: {e}\nTraceback:\n{tb_str}"
                            exceptions.append(error_message)

                            # Add error to conversation for retry
                            if attempt < 2:
                                current_messages = cast(
                                    list[anthropic.types.MessageParam], args["messages"]
                                )
                                current_messages.append(
                                    anthropic.types.MessageParam(
                                        role="assistant",
                                        content=response.content,
                                    )
                                )
                                current_messages.append(
                                    anthropic.types.MessageParam(
                                        role="user",
                                        content=error_message,
                                    )
                                )
                            break

                # No tool use found, add to conversation for retry
                else:
                    error_message = (
                        f"No tool use found in response on attempt {attempt + 1}"
                    )
                    exceptions.append(error_message)

                    if attempt < 2:
                        # Get current messages and add assistant response
                        current_messages = cast(
                            list[anthropic.types.MessageParam], args["messages"]
                        )
                        current_messages.append(
                            anthropic.types.MessageParam(
                                role="assistant",
                                content=response.content,
                            )
                        )
                        current_messages.append(
                            anthropic.types.MessageParam(
                                role="user",
                                content="Please use the required tool to format your response.",
                            )
                        )

            except Exception as e:
                import traceback

                tb_str = traceback.format_exc()
                error_message = f"API call failed on attempt {attempt + 1}: {e}\nTraceback:\n{tb_str}"
                exceptions.append(error_message)

                if attempt < 2:
                    # Add error to conversation for retry
                    current_messages = cast(
                        list[anthropic.types.MessageParam], args["messages"]
                    )
                    current_messages.append(
                        anthropic.types.MessageParam(
                            role="user",
                            content=error_message,
                        )
                    )
                else:
                    break

        raise Exception(
            "Failed to _generate_structured: Exceeded maximum retries. Inner exceptions: "
            + " -> ".join(exceptions)
        )
