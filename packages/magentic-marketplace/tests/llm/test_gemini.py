"""Integration tests for Gemini LLM client."""

import os
from unittest.mock import patch

import pytest
from openai.types.chat import ChatCompletionUserMessageParam
from pydantic import BaseModel

from magentic_marketplace.marketplace.llm.clients.gemini import (
    GeminiClient,
    GeminiConfig,
)


class ResponseModel(BaseModel):
    """Test response model for structured output."""

    answer: str
    confidence: float


class TestGeminiConfig:
    """Test GeminiConfig creation and validation."""

    def test_config_from_env(self):
        """Test creating config from environment variables."""
        env = {
            "LLM_PROVIDER": "gemini",
            "GEMINI_API_KEY": "test",
            "LLM_MODEL": "gemini-2.5-flash",
            "LLM_TEMPERATURE": "0.7",
            "LLM_MAX_TOKENS": "1000",
            "LLM_REASONING_EFFORT": "100",
        }
        with patch.dict(os.environ, env, clear=True):
            config = GeminiConfig()
            assert config.provider == os.environ["LLM_PROVIDER"]
            assert config.api_key == os.environ["GEMINI_API_KEY"]
            assert config.model == os.environ["LLM_MODEL"]
            assert str(config.temperature) == os.environ["LLM_TEMPERATURE"]
            assert str(config.max_tokens) == os.environ["LLM_MAX_TOKENS"]
            assert str(config.reasoning_effort) == os.environ["LLM_REASONING_EFFORT"]

    def test_config_defaults(self):
        """Test config with defaults."""
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test"}, clear=True):
            config = GeminiConfig(provider="gemini")
            assert config.provider == "gemini"
            assert config.api_key == os.environ["GEMINI_API_KEY"]
            assert config.model is None
            assert config.temperature == 0
            assert config.max_tokens == 2000
            assert config.reasoning_effort == "minimal"


@pytest.mark.skipif(
    not os.environ.get("GEMINI_API_KEY"), reason="GEMINI_API_KEY not set"
)
class TestGeminiClient:
    """Test GeminiClient functionality with real API calls."""

    @pytest.fixture
    def config(self) -> GeminiConfig:
        """Test configuration."""
        return GeminiConfig(
            provider="gemini",
            model="gemini-2.5-flash",
            temperature=0.1,
            max_tokens=50,
        )

    def test_client_initialization(self, config: GeminiConfig) -> None:
        """Test client initialization."""
        client = GeminiClient(config)
        assert client.config == config

    def test_client_initialization_no_api_key(self):
        """Test client initialization fails without API key."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError):
                GeminiConfig(provider="gemini")

    @pytest.mark.asyncio
    async def test_generate_string_response(self, config: GeminiConfig):
        """Test creating a string response."""
        client = GeminiClient(config)
        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Say 'Hello World' and nothing else."
            )
        ]

        response, usage = await client.generate(messages)

        assert isinstance(response, str)
        assert "Hello World" in response
        assert usage.provider == "gemini"
        assert "gemini" in usage.model

    @pytest.mark.asyncio
    async def test_generate_structured_response(self, config: GeminiConfig):
        """Test creating a structured response."""
        client = GeminiClient(config)
        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Respond with JSON: answer=42, confidence=0.95"
            )
        ]

        response, usage = await client.generate(messages, response_format=ResponseModel)

        assert isinstance(response, ResponseModel)
        assert response.answer == "42"
        assert response.confidence == 0.95
        assert usage.provider == "gemini"

    @pytest.mark.asyncio
    async def test_generate_with_string_message(self, config: GeminiConfig):
        """Test creating response with string message input."""
        client = GeminiClient(config)

        response, _ = await client.generate("Say 'Test' and nothing else.")

        assert isinstance(response, str)
        assert "Test" in response

    @pytest.mark.asyncio
    async def test_generate_with_parameters(self, config: GeminiConfig):
        """Test creating response with various parameters."""
        client = GeminiClient(config)
        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Say 'OK' and nothing else."
            )
        ]

        response, _ = await client.generate(messages, temperature=0.1)

        assert isinstance(response, str)
        assert "OK" in response
