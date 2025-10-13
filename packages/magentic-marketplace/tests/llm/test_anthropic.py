"""Integration tests for Anthropic LLM client."""

import os
from unittest.mock import AsyncMock, patch

import pytest
from openai.types.chat import ChatCompletionUserMessageParam
from pydantic import BaseModel

from magentic_marketplace.marketplace.llm.clients.anthropic import (
    AnthropicClient,
    AnthropicConfig,
)

pytestmark = pytest.mark.skip_ci


class ResponseModel(BaseModel):
    """Test response model for structured output."""

    answer: str
    confidence: float


class TestAnthropicConfig:
    """Test AnthropicConfig creation and validation."""

    def test_config_from_env(self):
        """Test creating config from environment variables."""
        env = {
            "LLM_PROVIDER": "anthropic",
            "ANTHROPIC_API_KEY": "test",
            "LLM_MODEL": "claude-sonnet-4-20250514",
            "LLM_TEMPERATURE": "0.1",
            "LLM_MAX_TOKENS": "100",
        }
        with patch.dict(os.environ, env, clear=True):
            config = AnthropicConfig()
            assert config.provider == os.environ["LLM_PROVIDER"]
            assert config.api_key == os.environ["ANTHROPIC_API_KEY"]
            assert config.model == os.environ["LLM_MODEL"]
            assert str(config.temperature) == os.environ["LLM_TEMPERATURE"]
            assert str(config.max_tokens) == os.environ["LLM_MAX_TOKENS"]

    def test_config_defaults(self):
        """Test config with defaults."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}, clear=True):
            config = AnthropicConfig(provider="anthropic")
            assert config.provider == "anthropic"
            assert config.api_key == os.environ["ANTHROPIC_API_KEY"]
            assert config.model is None
            assert config.temperature is None
            assert config.max_tokens == 2000
            assert config.reasoning_effort == "minimal"
            assert config.max_concurrency == 64


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set"
)
class TestAnthropicClient:
    """Test AnthropicClient functionality with real API calls."""

    @pytest.fixture
    def config(self) -> AnthropicConfig:
        """Test configuration."""
        return AnthropicConfig(
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            temperature=0.1,
            max_tokens=50,
        )

    def test_client_initialization(self, config: AnthropicConfig) -> None:
        """Test client initialization."""
        client = AnthropicClient(config)
        assert client.config == config

    def test_client_initialization_no_api_key(self):
        """Test client initialization fails without API key."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError):
                AnthropicConfig(provider="anthropic")

    @pytest.mark.asyncio
    async def test_generate_string_response(self, config: AnthropicConfig):
        """Test creating a string response."""
        client = AnthropicClient(config)
        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Say 'Hello World' and nothing else."
            )
        ]

        response, usage = await client.generate(messages)

        assert isinstance(response, str)
        assert "Hello World" in response
        assert usage.token_count > 0
        assert usage.provider == "anthropic"
        assert "claude" in usage.model

    @pytest.mark.asyncio
    async def test_generate_structured_response(self, config: AnthropicConfig):
        """Test creating a structured response."""
        client = AnthropicClient(config)
        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Respond with JSON: answer=42, confidence=0.95"
            )
        ]

        response, usage = await client.generate(messages, response_format=ResponseModel)

        assert isinstance(response, ResponseModel)
        assert response.answer == "42"
        assert response.confidence == 0.95
        assert usage.token_count > 0
        assert usage.provider == "anthropic"

    @pytest.mark.asyncio
    async def test_generate_with_string_message(self, config: AnthropicConfig):
        """Test creating response with string message input."""
        client = AnthropicClient(config)

        response, usage = await client.generate("Say 'Test' and nothing else.")

        assert isinstance(response, str)
        assert "Test" in response
        assert usage.token_count > 0

    @pytest.mark.asyncio
    async def test_generate_with_parameters(self, config: AnthropicConfig):
        """Test creating response with various parameters."""
        client = AnthropicClient(config)
        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Say 'OK' and nothing else."
            )
        ]

        response, usage = await client.generate(
            messages, temperature=0.1, max_tokens=10
        )

        assert isinstance(response, str)
        assert "OK" in response
        assert usage.token_count > 0

    @pytest.mark.asyncio
    async def test_temperature_not_sent_when_none(self):
        """Test that temperature is not sent to API when unset (None)."""
        import anthropic.types

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=True):
            config = AnthropicConfig(provider="anthropic", api_key="test-key")
            client = AnthropicClient(config)

            # Create a proper Message response
            mock_message = anthropic.types.Message(
                id="test-id",
                type="message",
                role="assistant",
                content=[anthropic.types.TextBlock(type="text", text="Test response")],
                model="claude-sonnet-4-20250514",
                usage=anthropic.types.Usage(input_tokens=5, output_tokens=5),
            )

            # Capture the request body
            captured_request_body = {}

            async def mock_post(
                _path,
                *,
                cast_to=None,
                body=None,
                options=None,
                stream=None,
                stream_cls=None,
            ):
                # Capture the body being sent
                if body:
                    captured_request_body.update(body)
                return mock_message

            # Mock the client's post method
            client.client.post = AsyncMock(side_effect=mock_post)

            messages = [
                ChatCompletionUserMessageParam(role="user", content="Test message")
            ]

            # Call generate without explicitly setting temperature
            await client.generate(messages, model="claude-sonnet-4-20250514")

            # Verify the post method was called
            assert client.client.post.called

            # Check that temperature was not included in the request body
            assert "temperature" not in captured_request_body, (
                f"Temperature should not be in API request body when it's None. Body: {captured_request_body}"
            )
