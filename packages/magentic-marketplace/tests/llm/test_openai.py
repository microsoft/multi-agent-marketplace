"""Integration tests for OpenAI LLM client."""

import os
from unittest.mock import AsyncMock, patch

import pytest
from openai.types.chat import ChatCompletionUserMessageParam
from pydantic import BaseModel

from magentic_marketplace.marketplace.llm.clients.openai import (
    OpenAIClient,
    OpenAIConfig,
)

pytestmark = pytest.mark.skip_ci


class ResponseModel(BaseModel):
    """Test response model for structured output."""

    answer: str
    confidence: float


class TestOpenAIConfig:
    """Test OpenAIConfig creation and validation."""

    def test_config_from_env(self):
        """Test creating config from environment variables."""
        env = {
            "LLM_PROVIDER": "openai",
            "OPENAI_API_KEY": "test",
            "LLM_MODEL": "gpt-4o-mini",
            "LLM_TEMPERATURE": "0.1",
            "LLM_MAX_TOKENS": "100",
        }
        with patch.dict(os.environ, env, clear=True):
            config = OpenAIConfig()
            assert config.provider == os.environ["LLM_PROVIDER"]
            assert config.api_key == os.environ["OPENAI_API_KEY"]
            assert config.model == os.environ["LLM_MODEL"]
            assert str(config.temperature) == os.environ["LLM_TEMPERATURE"]
            assert str(config.max_tokens) == os.environ["LLM_MAX_TOKENS"]

    def test_config_defaults(self):
        """Test config with defaults."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}, clear=True):
            config = OpenAIConfig(api_key=os.environ["OPENAI_API_KEY"])
            assert config.provider == "openai"
            assert config.api_key == os.environ["OPENAI_API_KEY"]
            assert config.model is None
            assert config.temperature is None
            assert config.max_tokens == 2000
            assert config.reasoning_effort == "minimal"
            assert config.max_concurrency == 64
            assert config.base_url is None


@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set"
)
class TestOpenAIClient:
    """Test OpenAIClient functionality with real API calls."""

    @pytest.fixture
    def config(self) -> OpenAIConfig:
        """Test configuration."""
        return OpenAIConfig(
            provider="openai",
            api_key=os.environ["OPENAI_API_KEY"],
            model="gpt-4o-mini",
            temperature=0.1,
            max_tokens=50,
        )

    def test_client_initialization(self, config: OpenAIConfig) -> None:
        """Test client initialization."""
        client = OpenAIClient(config)
        assert client.config == config

    def test_client_initialization_no_api_key(self):
        """Test client initialization fails without API key."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError):
                OpenAIClient()

    @pytest.mark.asyncio
    async def test_generate_string_response(self, config: OpenAIConfig) -> None:
        """Test creating a string response."""
        client = OpenAIClient(config)
        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Say 'Hello World' and nothing else."
            )
        ]

        response, usage = await client.generate(messages)

        assert isinstance(response, str)
        assert "Hello World" in response
        assert usage.token_count > 0
        assert usage.provider == "openai"
        assert "gpt" in usage.model

    @pytest.mark.asyncio
    async def test_generate_structured_response(self, config: OpenAIConfig) -> None:
        """Test creating a structured response."""
        client = OpenAIClient(config)
        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Answer '42' with confidence 0.95"
            )
        ]

        response, usage = await client.generate(messages, response_format=ResponseModel)

        assert isinstance(response, ResponseModel)
        assert response.answer == "42"
        assert response.confidence == 0.95
        assert usage.token_count > 0
        assert usage.provider == "openai"

    @pytest.mark.asyncio
    async def test_generate_with_string_message(self, config: OpenAIConfig) -> None:
        """Test creating response with string message input."""
        client = OpenAIClient(config)

        response, usage = await client.generate("Say 'Test' and nothing else.")

        assert isinstance(response, str)
        assert "Test" in response
        assert usage.token_count > 0

    @pytest.mark.asyncio
    async def test_generate_with_parameters(self, config: OpenAIConfig) -> None:
        """Test creating response with various parameters."""
        client = OpenAIClient(config)
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
        """Test that temperature is not sent to API when unset."""
        from openai.types.chat import ChatCompletion
        from openai.types.chat.chat_completion import Choice
        from openai.types.chat.chat_completion_message import ChatCompletionMessage
        from openai.types.completion_usage import CompletionUsage

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True):
            config = OpenAIConfig(api_key="test-key")
            client = OpenAIClient(config)

            # Create a proper ChatCompletion response
            mock_completion = ChatCompletion(
                id="test-id",
                object="chat.completion",
                created=1234567890,
                model="gpt-4o-mini",
                choices=[
                    Choice(
                        index=0,
                        message=ChatCompletionMessage(
                            role="assistant", content="Test response"
                        ),
                        finish_reason="stop",
                    )
                ],
                usage=CompletionUsage(
                    prompt_tokens=5, completion_tokens=5, total_tokens=10
                ),
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
                return mock_completion

            # Mock the client's post method
            client.client.post = AsyncMock(side_effect=mock_post)

            messages = [
                ChatCompletionUserMessageParam(role="user", content="Test message")
            ]

            # Call generate without explicitly setting temperature
            await client.generate(messages, model="gpt-4o-mini")

            # Verify the post method was called
            assert client.client.post.called

            # Check that temperature was not included in the request body
            assert "temperature" not in captured_request_body, (
                f"Temperature should not be in API request body when it's None. Body: {captured_request_body}"
            )
