"""Unit tests for Gemini LLM client retry logic."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai.types.chat import ChatCompletionUserMessageParam
from pydantic import BaseModel

from magentic_marketplace.marketplace.llm.clients.gemini import (
    GeminiClient,
    GeminiConfig,
)


class TestResponseModel(BaseModel):
    """Test response model for structured output."""

    answer: str
    confidence: float


class TestGeminiRetryLogic:
    """Test suite for Gemini client retry logic in _generate_struct."""

    @pytest.fixture
    def config(self) -> GeminiConfig:
        """Test configuration with mocked API key."""
        return GeminiConfig(
            provider="gemini",
            api_key="test-api-key",
            model="gemini-2.5-flash",
            temperature=0.1,
            max_tokens=50,
        )

    @pytest.fixture
    def mock_client(self, config: GeminiConfig):
        """Create a Gemini client with mocked internal client."""
        with patch("google.genai.Client"):
            client = GeminiClient(config)
            client.client = MagicMock()
            client.client.aio = MagicMock()
            client.client.aio.models = MagicMock()
            yield client

    @pytest.mark.asyncio
    async def test_retry_on_validation_error_then_success(self, mock_client: GeminiClient):
        """Test that client retries on validation error and succeeds on second attempt."""
        # First response: invalid data that will cause validation error
        first_response = MagicMock()
        first_response.parsed = None
        first_response.text = '{"answer": "42"}'  # Missing 'confidence' field
        first_response.usage_metadata = MagicMock()
        first_response.usage_metadata.total_token_count = 100

        # Second response: valid data
        second_response = MagicMock()
        second_response.parsed = {"answer": "42", "confidence": 0.95}
        second_response.text = None
        second_response.usage_metadata = MagicMock()
        second_response.usage_metadata.total_token_count = 150

        mock_client.client.aio.models.generate_content = AsyncMock(
            side_effect=[first_response, second_response]
        )

        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Answer with structured response"
            )
        ]

        result, usage = await mock_client._generate_struct(
            model="gemini-2.5-flash",
            messages=messages,
            response_format=TestResponseModel,
        )

        assert isinstance(result, TestResponseModel)
        assert result.answer == "42"
        assert result.confidence == 0.95
        assert usage.provider == "gemini"
        assert mock_client.client.aio.models.generate_content.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_json_decode_error_then_success(self, mock_client: GeminiClient):
        """Test that client retries on JSON decode error and succeeds on second attempt."""
        # First response: malformed JSON
        first_response = MagicMock()
        first_response.parsed = None
        first_response.text = '{"answer": "42", invalid json}'
        first_response.usage_metadata = MagicMock()
        first_response.usage_metadata.total_token_count = 100

        # Second response: valid data
        second_response = MagicMock()
        second_response.parsed = {"answer": "42", "confidence": 0.95}
        second_response.text = None
        second_response.usage_metadata = MagicMock()
        second_response.usage_metadata.total_token_count = 150

        mock_client.client.aio.models.generate_content = AsyncMock(
            side_effect=[first_response, second_response]
        )

        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Answer with structured response"
            )
        ]

        result, usage = await mock_client._generate_struct(
            model="gemini-2.5-flash",
            messages=messages,
            response_format=TestResponseModel,
        )

        assert isinstance(result, TestResponseModel)
        assert result.answer == "42"
        assert result.confidence == 0.95
        assert mock_client.client.aio.models.generate_content.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_no_response_content_then_success(self, mock_client: GeminiClient):
        """Test that client retries when no response content and succeeds on second attempt."""
        # First response: no content
        first_response = MagicMock()
        first_response.parsed = None
        first_response.text = None
        first_response.usage_metadata = MagicMock()
        first_response.usage_metadata.total_token_count = 50

        # Second response: valid data
        second_response = MagicMock()
        second_response.parsed = {"answer": "42", "confidence": 0.95}
        second_response.text = None
        second_response.usage_metadata = MagicMock()
        second_response.usage_metadata.total_token_count = 150

        mock_client.client.aio.models.generate_content = AsyncMock(
            side_effect=[first_response, second_response]
        )

        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Answer with structured response"
            )
        ]

        result, _ = await mock_client._generate_struct(
            model="gemini-2.5-flash",
            messages=messages,
            response_format=TestResponseModel,
        )

        assert isinstance(result, TestResponseModel)
        assert result.answer == "42"
        assert result.confidence == 0.95
        assert mock_client.client.aio.models.generate_content.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_api_exception_then_success(self, mock_client: GeminiClient):
        """Test that client retries on API exception and succeeds on second attempt."""
        # First call: API error
        api_error = Exception("API temporarily unavailable")

        # Second response: valid data
        second_response = MagicMock()
        second_response.parsed = {"answer": "42", "confidence": 0.95}
        second_response.text = None
        second_response.usage_metadata = MagicMock()
        second_response.usage_metadata.total_token_count = 150

        mock_client.client.aio.models.generate_content = AsyncMock(
            side_effect=[api_error, second_response]
        )

        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Answer with structured response"
            )
        ]

        result, _ = await mock_client._generate_struct(
            model="gemini-2.5-flash",
            messages=messages,
            response_format=TestResponseModel,
        )

        assert isinstance(result, TestResponseModel)
        assert result.answer == "42"
        assert result.confidence == 0.95
        assert mock_client.client.aio.models.generate_content.call_count == 2

    @pytest.mark.asyncio
    async def test_exhausted_retries_validation_errors(self, mock_client: GeminiClient):
        """Test that client raises exception after exhausting all retries."""
        # All three responses: invalid data
        invalid_response = MagicMock()
        invalid_response.parsed = None
        invalid_response.text = '{"answer": "42"}'  # Missing 'confidence' field
        invalid_response.usage_metadata = MagicMock()
        invalid_response.usage_metadata.total_token_count = 100

        mock_client.client.aio.models.generate_content = AsyncMock(
            side_effect=[invalid_response, invalid_response, invalid_response]
        )

        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Answer with structured response"
            )
        ]

        with pytest.raises(Exception) as exc_info:
            await mock_client._generate_struct(
                model="gemini-2.5-flash",
                messages=messages,
                response_format=TestResponseModel,
            )

        assert "Failed to _generate_struct: Exceeded maximum retries" in str(exc_info.value)
        assert "Inner exceptions:" in str(exc_info.value)
        assert mock_client.client.aio.models.generate_content.call_count == 3

    @pytest.mark.asyncio
    async def test_exhausted_retries_no_content(self, mock_client: GeminiClient):
        """Test that client raises exception when no content on all attempts."""
        # All three responses: no content
        no_content_response = MagicMock()
        no_content_response.parsed = None
        no_content_response.text = None
        no_content_response.usage_metadata = MagicMock()
        no_content_response.usage_metadata.total_token_count = 50

        mock_client.client.aio.models.generate_content = AsyncMock(
            side_effect=[no_content_response, no_content_response, no_content_response]
        )

        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Answer with structured response"
            )
        ]

        with pytest.raises(Exception) as exc_info:
            await mock_client._generate_struct(
                model="gemini-2.5-flash",
                messages=messages,
                response_format=TestResponseModel,
            )

        assert "Failed to _generate_struct: Exceeded maximum retries" in str(exc_info.value)
        assert "No response content available" in str(exc_info.value)
        assert mock_client.client.aio.models.generate_content.call_count == 3

    @pytest.mark.asyncio
    async def test_conversation_context_updated_on_retry(self, mock_client: GeminiClient):
        """Test that conversation context is updated with error messages on retry."""
        # First response: validation error
        first_response = MagicMock()
        first_response.parsed = None
        first_response.text = '{"answer": "42"}'  # Missing 'confidence' field
        first_response.usage_metadata = MagicMock()
        first_response.usage_metadata.total_token_count = 100

        # Second response: valid data
        second_response = MagicMock()
        second_response.parsed = {"answer": "42", "confidence": 0.95}
        second_response.text = None
        second_response.usage_metadata = MagicMock()
        second_response.usage_metadata.total_token_count = 150

        # Track the calls to verify conversation context
        call_args_list = []

        async def track_calls(**kwargs):
            call_args_list.append(kwargs)
            if len(call_args_list) == 1:
                return first_response
            return second_response

        mock_client.client.aio.models.generate_content = AsyncMock(side_effect=track_calls)

        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Answer with structured response"
            )
        ]

        await mock_client._generate_struct(
            model="gemini-2.5-flash",
            messages=messages,
            response_format=TestResponseModel,
        )

        # Verify that the second call has more messages (original + error context)
        assert len(call_args_list) == 2
        first_call_contents = call_args_list[0]["contents"]
        second_call_contents = call_args_list[1]["contents"]

        # Second call should have more content items (original + model response + error)
        assert len(second_call_contents) > len(first_call_contents)

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self, mock_client: GeminiClient):
        """Test that no retry occurs when first attempt succeeds."""
        # Valid response on first attempt
        response = MagicMock()
        response.parsed = {"answer": "42", "confidence": 0.95}
        response.text = None
        response.usage_metadata = MagicMock()
        response.usage_metadata.total_token_count = 150

        mock_client.client.aio.models.generate_content = AsyncMock(return_value=response)

        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Answer with structured response"
            )
        ]

        result, _ = await mock_client._generate_struct(
            model="gemini-2.5-flash",
            messages=messages,
            response_format=TestResponseModel,
        )

        assert isinstance(result, TestResponseModel)
        assert result.answer == "42"
        assert result.confidence == 0.95
        # Should only call once when successful on first attempt
        assert mock_client.client.aio.models.generate_content.call_count == 1
