"""Integration tests for OpenAI LLM client."""

import os
from unittest.mock import patch

import pytest
from openai.types.chat import ChatCompletionUserMessageParam
from pydantic import BaseModel

from magentic_marketplace.marketplace.llm.clients.openai import (
    OpenAIClient,
    OpenAIConfig,
)


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
            assert config.temperature == 0.0
            assert config.max_tokens == 2000
            assert config.reasoning_effort == "minimal"


@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set"
)
class TestOpenAIClient:
    """Test OpenAIClient functionality with real API calls."""

    @pytest.fixture
    def config(self) -> OpenAIConfig:
        """Test configuration."""
        return OpenAIConfig(
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
