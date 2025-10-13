"""Integration tests for TRAPI LLM client."""

import os
from unittest.mock import patch

import pytest
from azure.core.exceptions import ClientAuthenticationError
from azure.identity import AzureCliCredential
from openai.types.chat import ChatCompletionUserMessageParam
from pydantic import BaseModel

from magentic_marketplace.marketplace.llm.clients.trapi.client import (
    TrapiClient,
    TrapiConfig,
)

pytestmark = pytest.mark.skip_ci


def is_azure_cli_logged_in() -> bool:
    """Check if user is logged in via Azure CLI."""
    try:
        credential = AzureCliCredential()
        # Try to get a token for a common Azure resource
        credential.get_token("api://trapi/.default")
        return True
    except (ClientAuthenticationError, Exception):
        return False


# Skip decorator for Azure CLI authentication
skipif_no_azure_cli = pytest.mark.skipif(
    not is_azure_cli_logged_in(),
    reason="Azure CLI authentication required - run 'az login' first",
)


class ResponseModel(BaseModel):
    """Test response model for structured output."""

    answer: str
    confidence: float


class TestTrapiConfig:
    """Test TrapiConfig creation and validation."""

    def test_config_from_env(self):
        """Test creating config from environment variables."""
        env = {
            "LLM_PROVIDER": "trapi",
            "LLM_MODEL": "gpt-4o-mini",
            "LLM_TEMPERATURE": "0.1",
            "LLM_MAX_TOKENS": "100",
        }
        with patch.dict(os.environ, env, clear=True):
            config = TrapiConfig()
            assert config.provider == os.environ["LLM_PROVIDER"]
            assert config.model == os.environ["LLM_MODEL"]
            assert str(config.temperature) == os.environ["LLM_TEMPERATURE"]
            assert str(config.max_tokens) == os.environ["LLM_MAX_TOKENS"]

    def test_config_defaults(self):
        """Test config with defaults."""
        with patch.dict(os.environ, {"LLM_PROVIDER": "trapi"}, clear=True):
            config = TrapiConfig()
        assert config.provider == "trapi"
        assert config.model is None
        assert config.temperature is None
        assert config.max_tokens == 2000
        assert config.reasoning_effort == "minimal"
        assert config.max_concurrency == 64


@skipif_no_azure_cli
class TestTrapiClient:
    """Test TrapiClient functionality with real API calls."""

    @pytest.fixture
    def config(self) -> TrapiConfig:
        """Test configuration."""
        return TrapiConfig(
            provider="trapi",
            model="gpt-4o-mini",
            temperature=0.1,
            max_tokens=50,
        )

    def test_client_initialization(self, config: TrapiConfig) -> None:
        """Test client initialization."""
        client = TrapiClient(config=config)
        assert client.config == config

    def test_client_initialization_with_model_filters(
        self, config: TrapiConfig
    ) -> None:
        """Test client initialization with model include/exclude lists."""
        client = TrapiClient(
            include_models=["gpt-4o-mini"],
            exclude_models=["gpt-3.5-turbo"],
            config=config,
        )
        assert client.config == config

    @pytest.mark.asyncio
    async def test_generate_string_response(self, config: TrapiConfig):
        """Test creating a string response."""
        client = TrapiClient(config=config)
        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Say 'Hello World' and nothing else."
            )
        ]

        response, usage = await client.generate(messages)

        assert isinstance(response, str)
        assert "Hello World" in response
        assert usage.token_count > 0
        assert usage.provider == "openai"  # TRAPI uses OpenAI models
        assert "gpt" in usage.model

    @pytest.mark.asyncio
    async def test_generate_structured_response(self, config: TrapiConfig):
        """Test creating a structured response."""
        client = TrapiClient(config=config)
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

    @pytest.mark.asyncio
    async def test_generate_with_string_message(self, config: TrapiConfig):
        """Test creating response with string message input."""
        client = TrapiClient(config=config)

        response, usage = await client.generate("Say 'Test' and nothing else.")

        assert isinstance(response, str)
        assert "Test" in response
        assert usage.token_count > 0

    @pytest.mark.asyncio
    async def test_generate_with_parameters(self, config: TrapiConfig):
        """Test creating response with various parameters."""
        client = TrapiClient(config=config)
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
