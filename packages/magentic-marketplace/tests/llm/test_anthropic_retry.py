"""Unit tests for Anthropic LLM client retry logic."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai.types.chat import ChatCompletionUserMessageParam
from pydantic import BaseModel

from magentic_marketplace.marketplace.llm.clients.anthropic import (
    AnthropicClient,
    AnthropicConfig,
)


class TestResponseModel(BaseModel):
    """Test response model for structured output."""

    answer: str
    confidence: float


class TestAnthropicRetryLogic:
    """Test suite for Anthropic client retry logic in _generate_structured."""

    @pytest.fixture
    def config(self) -> AnthropicConfig:
        """Test configuration with mocked API key."""
        return AnthropicConfig(
            provider="anthropic",
            api_key="test-api-key",
            model="claude-sonnet-4-20250514",
            temperature=0.1,
            max_tokens=50,
        )

    @pytest.fixture
    def mock_client(self, config: AnthropicConfig):
        """Create an Anthropic client with mocked internal client."""
        with patch("anthropic.AsyncAnthropic"):
            client = AnthropicClient(config)
            client.client = MagicMock()
            client.client.messages = MagicMock()
            yield client

    def _create_tool_use_response(self, tool_input: dict, tokens: int = 100):
        """Helper to create a mock response with tool use."""
        tool_use_block = MagicMock()
        tool_use_block.type = "tool_use"
        tool_use_block.input = tool_input

        response = MagicMock()
        response.content = [tool_use_block]
        response.usage = MagicMock()
        response.usage.input_tokens = tokens // 2
        response.usage.output_tokens = tokens // 2
        return response

    def _create_text_only_response(self, text: str, tokens: int = 100):
        """Helper to create a mock response with text only (no tool use)."""
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = text

        response = MagicMock()
        response.content = [text_block]
        response.usage = MagicMock()
        response.usage.input_tokens = tokens // 2
        response.usage.output_tokens = tokens // 2
        return response

    @pytest.mark.asyncio
    async def test_retry_on_validation_error_then_success(self, mock_client: AnthropicClient):
        """Test that client retries on validation error and succeeds on second attempt."""
        # First response: invalid data that will cause validation error
        first_response = self._create_tool_use_response({"answer": "42"}, tokens=100)

        # Second response: valid data
        second_response = self._create_tool_use_response(
            {"answer": "42", "confidence": 0.95}, tokens=150
        )

        mock_client.client.messages.create = AsyncMock(
            side_effect=[first_response, second_response]
        )

        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Answer with structured response"
            )
        ]

        # Convert messages to Anthropic format
        anthropic_messages, system_prompt = mock_client._convert_messages(messages)

        result, usage = await mock_client._generate_structured(
            model="claude-sonnet-4-20250514",
            response_format=TestResponseModel,
            messages=anthropic_messages,
            max_tokens=50,
        )

        assert isinstance(result, TestResponseModel)
        assert result.answer == "42"
        assert result.confidence == 0.95
        assert usage.provider == "anthropic"
        assert mock_client.client.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_no_tool_use_then_success(self, mock_client: AnthropicClient):
        """Test that client retries when no tool use found and succeeds on second attempt."""
        # First response: text only, no tool use
        first_response = self._create_text_only_response("I'll help with that", tokens=50)

        # Second response: valid tool use
        second_response = self._create_tool_use_response(
            {"answer": "42", "confidence": 0.95}, tokens=150
        )

        mock_client.client.messages.create = AsyncMock(
            side_effect=[first_response, second_response]
        )

        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Answer with structured response"
            )
        ]

        anthropic_messages, system_prompt = mock_client._convert_messages(messages)

        result, usage = await mock_client._generate_structured(
            model="claude-sonnet-4-20250514",
            response_format=TestResponseModel,
            messages=anthropic_messages,
            max_tokens=50,
        )

        assert isinstance(result, TestResponseModel)
        assert result.answer == "42"
        assert result.confidence == 0.95
        assert mock_client.client.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_json_decode_error_then_success(self, mock_client: AnthropicClient):
        """Test that client retries on JSON decode error and succeeds on second attempt."""
        # First response: tool use with invalid input that can't be validated
        first_response = self._create_tool_use_response(
            {"answer": 12345},  # Wrong type, will cause validation error
            tokens=100
        )

        # Second response: valid data
        second_response = self._create_tool_use_response(
            {"answer": "42", "confidence": 0.95}, tokens=150
        )

        mock_client.client.messages.create = AsyncMock(
            side_effect=[first_response, second_response]
        )

        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Answer with structured response"
            )
        ]

        anthropic_messages, system_prompt = mock_client._convert_messages(messages)

        result, usage = await mock_client._generate_structured(
            model="claude-sonnet-4-20250514",
            response_format=TestResponseModel,
            messages=anthropic_messages,
            max_tokens=50,
        )

        assert isinstance(result, TestResponseModel)
        assert result.answer == "42"
        assert result.confidence == 0.95
        assert mock_client.client.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_api_exception_then_success(self, mock_client: AnthropicClient):
        """Test that client retries on API exception and succeeds on second attempt."""
        # First call: API error
        api_error = Exception("API temporarily unavailable")

        # Second response: valid data
        second_response = self._create_tool_use_response(
            {"answer": "42", "confidence": 0.95}, tokens=150
        )

        mock_client.client.messages.create = AsyncMock(
            side_effect=[api_error, second_response]
        )

        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Answer with structured response"
            )
        ]

        anthropic_messages, system_prompt = mock_client._convert_messages(messages)

        result, usage = await mock_client._generate_structured(
            model="claude-sonnet-4-20250514",
            response_format=TestResponseModel,
            messages=anthropic_messages,
            max_tokens=50,
        )

        assert isinstance(result, TestResponseModel)
        assert result.answer == "42"
        assert result.confidence == 0.95
        assert mock_client.client.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_exhausted_retries_validation_errors(self, mock_client: AnthropicClient):
        """Test that client raises exception after exhausting all retries."""
        # All three responses: invalid data
        invalid_response = self._create_tool_use_response({"answer": "42"}, tokens=100)

        mock_client.client.messages.create = AsyncMock(
            side_effect=[invalid_response, invalid_response, invalid_response]
        )

        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Answer with structured response"
            )
        ]

        anthropic_messages, system_prompt = mock_client._convert_messages(messages)

        with pytest.raises(Exception) as exc_info:
            await mock_client._generate_structured(
                model="claude-sonnet-4-20250514",
                response_format=TestResponseModel,
                messages=anthropic_messages,
                max_tokens=50,
            )

        assert "Failed to _generate_structured: Exceeded maximum retries" in str(exc_info.value)
        assert "Inner exceptions:" in str(exc_info.value)
        assert mock_client.client.messages.create.call_count == 3

    @pytest.mark.asyncio
    async def test_exhausted_retries_no_tool_use(self, mock_client: AnthropicClient):
        """Test that client raises exception when no tool use on all attempts."""
        # All three responses: text only, no tool use
        no_tool_response = self._create_text_only_response("I'll help with that", tokens=50)

        mock_client.client.messages.create = AsyncMock(
            side_effect=[no_tool_response, no_tool_response, no_tool_response]
        )

        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Answer with structured response"
            )
        ]

        anthropic_messages, system_prompt = mock_client._convert_messages(messages)

        with pytest.raises(Exception) as exc_info:
            await mock_client._generate_structured(
                model="claude-sonnet-4-20250514",
                response_format=TestResponseModel,
                messages=anthropic_messages,
                max_tokens=50,
            )

        assert "Failed to _generate_structured: Exceeded maximum retries" in str(exc_info.value)
        assert "No tool use found" in str(exc_info.value)
        assert mock_client.client.messages.create.call_count == 3

    @pytest.mark.asyncio
    async def test_conversation_context_updated_on_retry(self, mock_client: AnthropicClient):
        """Test that conversation context is updated with error messages on retry."""
        # First response: validation error
        first_response = self._create_tool_use_response({"answer": "42"}, tokens=100)

        # Second response: valid data
        second_response = self._create_tool_use_response(
            {"answer": "42", "confidence": 0.95}, tokens=150
        )

        # Track the calls to verify conversation context
        call_args_list = []

        async def track_calls(**kwargs):
            call_args_list.append(kwargs)
            if len(call_args_list) == 1:
                return first_response
            return second_response

        mock_client.client.messages.create = AsyncMock(side_effect=track_calls)

        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Answer with structured response"
            )
        ]

        anthropic_messages, system_prompt = mock_client._convert_messages(messages)

        await mock_client._generate_structured(
            model="claude-sonnet-4-20250514",
            response_format=TestResponseModel,
            messages=anthropic_messages,
            max_tokens=50,
        )

        # Verify that the second call has more messages (original + assistant + error)
        assert len(call_args_list) == 2
        first_call_messages = call_args_list[0]["messages"]
        second_call_messages = call_args_list[1]["messages"]

        # Second call should have more messages (original + assistant response + user error)
        assert len(second_call_messages) > len(first_call_messages)

        # Verify the last message is a user message with error context
        last_message = second_call_messages[-1]
        assert last_message["role"] == "user"

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self, mock_client: AnthropicClient):
        """Test that no retry occurs when first attempt succeeds."""
        # Valid response on first attempt
        response = self._create_tool_use_response(
            {"answer": "42", "confidence": 0.95}, tokens=150
        )

        mock_client.client.messages.create = AsyncMock(return_value=response)

        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Answer with structured response"
            )
        ]

        anthropic_messages, system_prompt = mock_client._convert_messages(messages)

        result, usage = await mock_client._generate_structured(
            model="claude-sonnet-4-20250514",
            response_format=TestResponseModel,
            messages=anthropic_messages,
            max_tokens=50,
        )

        assert isinstance(result, TestResponseModel)
        assert result.answer == "42"
        assert result.confidence == 0.95
        # Should only call once when successful on first attempt
        assert mock_client.client.messages.create.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_preserves_system_and_temperature(self, mock_client: AnthropicClient):
        """Test that retry attempts preserve system prompt and temperature settings."""
        # First response: validation error
        first_response = self._create_tool_use_response({"answer": "42"}, tokens=100)

        # Second response: valid data
        second_response = self._create_tool_use_response(
            {"answer": "42", "confidence": 0.95}, tokens=150
        )

        # Track the calls to verify parameters
        call_args_list = []

        async def track_calls(**kwargs):
            call_args_list.append(kwargs)
            if len(call_args_list) == 1:
                return first_response
            return second_response

        mock_client.client.messages.create = AsyncMock(side_effect=track_calls)

        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Answer with structured response"
            )
        ]

        anthropic_messages, system_prompt = mock_client._convert_messages(messages)

        await mock_client._generate_structured(
            model="claude-sonnet-4-20250514",
            response_format=TestResponseModel,
            messages=anthropic_messages,
            max_tokens=50,
            temperature=0.7,
            system="You are a helpful assistant",
        )

        # Verify that both calls have the same temperature and system prompt
        assert len(call_args_list) == 2
        assert call_args_list[0]["temperature"] == 0.7
        assert call_args_list[1]["temperature"] == 0.7
        assert call_args_list[0]["system"] == "You are a helpful assistant"
        assert call_args_list[1]["system"] == "You are a helpful assistant"
