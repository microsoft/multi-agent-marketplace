"""Unit tests for OpenAI LLM client retry logic."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai.types.chat import ChatCompletionUserMessageParam
from pydantic import BaseModel

from magentic_marketplace.marketplace.llm.clients.openai import (
    OpenAIClient,
    OpenAIConfig,
)


class TestResponseModel(BaseModel):
    """Test response model for structured output."""

    answer: str
    confidence: float


class TestOpenAIRetryLogic:
    """Test suite for OpenAI client retry logic in _generate_struct."""

    @pytest.fixture
    def config(self) -> OpenAIConfig:
        """Test configuration with mocked API key."""
        return OpenAIConfig(
            provider="openai",
            api_key="test-api-key",
            model="gpt-4o-mini",
            temperature=0.1,
            max_tokens=50,
        )

    @pytest.fixture
    def mock_client(self, config: OpenAIConfig):
        """Create an OpenAI client with mocked internal client."""
        with patch("openai.AsyncOpenAI"):
            client = OpenAIClient(config)
            client.client = MagicMock()
            client.client.chat = MagicMock()
            client.client.chat.completions = MagicMock()
            yield client

    def _create_tool_call_response(
        self, tool_arguments: str, tool_id: str = "call_123", tokens: int = 100
    ):
        """Helper to create a mock completion response with tool call."""
        tool_call = MagicMock()
        tool_call.id = tool_id
        tool_call.type = "function"
        tool_call.function = MagicMock()
        tool_call.function.name = "GenerateTestResponseModel"
        tool_call.function.arguments = tool_arguments

        message = MagicMock()
        message.tool_calls = [tool_call]

        choice = MagicMock()
        choice.message = message

        completion = MagicMock()
        completion.choices = [choice]
        completion.usage = MagicMock()
        completion.usage.total_tokens = tokens

        return completion

    def _create_empty_response(self):
        """Helper to create a mock response with no choices."""
        completion = MagicMock()
        completion.choices = []
        return completion

    @pytest.mark.asyncio
    async def test_retry_on_validation_error_then_success(self, mock_client: OpenAIClient):
        """Test that client retries on validation error and succeeds on second attempt."""
        # First response: invalid JSON missing 'confidence' field
        first_response = self._create_tool_call_response(
            '{"answer": "42"}', tokens=100
        )

        # Second response: valid JSON
        second_response = self._create_tool_call_response(
            '{"answer": "42", "confidence": 0.95}', tokens=150
        )

        mock_client.client.chat.completions.create = AsyncMock(
            side_effect=[first_response, second_response]
        )

        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Answer with structured response"
            )
        ]

        result = await mock_client._generate_struct(
            model="gpt-4o-mini",
            messages=messages,
            response_format=TestResponseModel,
        )

        assert isinstance(result, TestResponseModel)
        assert result.answer == "42"
        assert result.confidence == 0.95
        assert mock_client.client.chat.completions.create.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_json_decode_error_then_success(self, mock_client: OpenAIClient):
        """Test that client retries on JSON decode error and succeeds on second attempt."""
        # First response: malformed JSON
        first_response = self._create_tool_call_response(
            '{"answer": "42", invalid json}', tokens=100
        )

        # Second response: valid JSON
        second_response = self._create_tool_call_response(
            '{"answer": "42", "confidence": 0.95}', tokens=150
        )

        mock_client.client.chat.completions.create = AsyncMock(
            side_effect=[first_response, second_response]
        )

        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Answer with structured response"
            )
        ]

        result = await mock_client._generate_struct(
            model="gpt-4o-mini",
            messages=messages,
            response_format=TestResponseModel,
        )

        assert isinstance(result, TestResponseModel)
        assert result.answer == "42"
        assert result.confidence == 0.95
        assert mock_client.client.chat.completions.create.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_wrong_type_then_success(self, mock_client: OpenAIClient):
        """Test that client retries when field has wrong type and succeeds on second attempt."""
        # First response: wrong type for answer (number instead of string)
        first_response = self._create_tool_call_response(
            '{"answer": 42, "confidence": 0.95}', tokens=100
        )

        # Second response: correct types
        second_response = self._create_tool_call_response(
            '{"answer": "42", "confidence": 0.95}', tokens=150
        )

        mock_client.client.chat.completions.create = AsyncMock(
            side_effect=[first_response, second_response]
        )

        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Answer with structured response"
            )
        ]

        result = await mock_client._generate_struct(
            model="gpt-4o-mini",
            messages=messages,
            response_format=TestResponseModel,
        )

        assert isinstance(result, TestResponseModel)
        assert result.answer == "42"
        assert result.confidence == 0.95
        assert mock_client.client.chat.completions.create.call_count == 2

    @pytest.mark.asyncio
    async def test_exhausted_retries_validation_errors(self, mock_client: OpenAIClient):
        """Test that client raises exception after exhausting all retries."""
        # All three responses: invalid JSON missing 'confidence' field
        invalid_response = self._create_tool_call_response(
            '{"answer": "42"}', tokens=100
        )

        mock_client.client.chat.completions.create = AsyncMock(
            side_effect=[invalid_response, invalid_response, invalid_response]
        )

        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Answer with structured response"
            )
        ]

        with pytest.raises(Exception) as exc_info:
            await mock_client._generate_struct(
                model="gpt-4o-mini",
                messages=messages,
                response_format=TestResponseModel,
            )

        assert "Failed to _generate_struct: Exceeded maximum retries" in str(exc_info.value)
        assert "Inner exceptions:" in str(exc_info.value)
        assert mock_client.client.chat.completions.create.call_count == 3

    @pytest.mark.asyncio
    async def test_exhausted_retries_json_errors(self, mock_client: OpenAIClient):
        """Test that client raises exception when JSON is malformed on all attempts."""
        # All three responses: malformed JSON
        malformed_response = self._create_tool_call_response(
            '{"answer": "42", invalid}', tokens=100
        )

        mock_client.client.chat.completions.create = AsyncMock(
            side_effect=[malformed_response, malformed_response, malformed_response]
        )

        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Answer with structured response"
            )
        ]

        with pytest.raises(Exception) as exc_info:
            await mock_client._generate_struct(
                model="gpt-4o-mini",
                messages=messages,
                response_format=TestResponseModel,
            )

        assert "Failed to _generate_struct: Exceeded maximum retries" in str(exc_info.value)
        assert mock_client.client.chat.completions.create.call_count == 3

    @pytest.mark.asyncio
    async def test_conversation_context_updated_on_retry(self, mock_client: OpenAIClient):
        """Test that conversation context is updated with error messages on retry."""
        # First response: validation error
        first_response = self._create_tool_call_response(
            '{"answer": "42"}', tokens=100
        )

        # Second response: valid JSON
        second_response = self._create_tool_call_response(
            '{"answer": "42", "confidence": 0.95}', tokens=150
        )

        # Track the calls to verify conversation context
        call_args_list = []

        async def track_calls(**kwargs):
            call_args_list.append(kwargs)
            if len(call_args_list) == 1:
                return first_response
            return second_response

        mock_client.client.chat.completions.create = AsyncMock(side_effect=track_calls)

        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Answer with structured response"
            )
        ]

        await mock_client._generate_struct(
            model="gpt-4o-mini",
            messages=messages,
            response_format=TestResponseModel,
        )

        # Verify that the second call has more messages
        assert len(call_args_list) == 2
        first_call_messages = call_args_list[0]["messages"]
        second_call_messages = call_args_list[1]["messages"]

        # Second call should have more messages (original + assistant tool call + tool response)
        assert len(second_call_messages) > len(first_call_messages)

        # Verify the last message is a tool message with error context
        last_message = second_call_messages[-1]
        assert last_message["role"] == "tool"
        assert "Error parsing tool" in last_message["content"]

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self, mock_client: OpenAIClient):
        """Test that no retry occurs when first attempt succeeds."""
        # Valid response on first attempt
        response = self._create_tool_call_response(
            '{"answer": "42", "confidence": 0.95}', tokens=150
        )

        mock_client.client.chat.completions.create = AsyncMock(return_value=response)

        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Answer with structured response"
            )
        ]

        result = await mock_client._generate_struct(
            model="gpt-4o-mini",
            messages=messages,
            response_format=TestResponseModel,
        )

        assert isinstance(result, TestResponseModel)
        assert result.answer == "42"
        assert result.confidence == 0.95
        # Should only call once when successful on first attempt
        assert mock_client.client.chat.completions.create.call_count == 1

    @pytest.mark.asyncio
    async def test_tool_call_id_preserved_in_retry(self, mock_client: OpenAIClient):
        """Test that tool call ID is properly preserved in retry context."""
        # First response: validation error
        tool_id = "call_abc123"
        first_response = self._create_tool_call_response(
            '{"answer": "42"}', tool_id=tool_id, tokens=100
        )

        # Second response: valid JSON
        second_response = self._create_tool_call_response(
            '{"answer": "42", "confidence": 0.95}', tokens=150
        )

        # Track the calls to verify tool call ID
        call_args_list = []

        async def track_calls(**kwargs):
            call_args_list.append(kwargs)
            if len(call_args_list) == 1:
                return first_response
            return second_response

        mock_client.client.chat.completions.create = AsyncMock(side_effect=track_calls)

        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Answer with structured response"
            )
        ]

        await mock_client._generate_struct(
            model="gpt-4o-mini",
            messages=messages,
            response_format=TestResponseModel,
        )

        # Verify the tool response message includes the correct tool_call_id
        assert len(call_args_list) == 2
        second_call_messages = call_args_list[1]["messages"]

        # Find the tool response message
        tool_message = None
        for msg in second_call_messages:
            if msg.get("role") == "tool":
                tool_message = msg
                break

        assert tool_message is not None
        assert tool_message["tool_call_id"] == tool_id

    @pytest.mark.asyncio
    async def test_raises_value_error_on_empty_choices(self, mock_client: OpenAIClient):
        """Test that proper error is raised when choices is empty."""
        # Response with no choices
        empty_response = self._create_empty_response()

        mock_client.client.chat.completions.create = AsyncMock(return_value=empty_response)

        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Answer with structured response"
            )
        ]

        with pytest.raises(ValueError) as exc_info:
            await mock_client._generate_struct(
                model="gpt-4o-mini",
                messages=messages,
                response_format=TestResponseModel,
            )

        assert "choices was empty" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_multiple_retry_cycles(self, mock_client: OpenAIClient):
        """Test retry behavior across multiple attempts with different errors."""
        # First response: JSON decode error
        first_response = self._create_tool_call_response(
            '{"answer": invalid}', tokens=100
        )

        # Second response: validation error (missing field)
        second_response = self._create_tool_call_response(
            '{"answer": "42"}', tokens=120
        )

        # Third response: valid JSON
        third_response = self._create_tool_call_response(
            '{"answer": "42", "confidence": 0.95}', tokens=150
        )

        mock_client.client.chat.completions.create = AsyncMock(
            side_effect=[first_response, second_response, third_response]
        )

        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Answer with structured response"
            )
        ]

        result = await mock_client._generate_struct(
            model="gpt-4o-mini",
            messages=messages,
            response_format=TestResponseModel,
        )

        assert isinstance(result, TestResponseModel)
        assert result.answer == "42"
        assert result.confidence == 0.95
        assert mock_client.client.chat.completions.create.call_count == 3
