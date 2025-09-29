"""Integration tests for LLM functional interface."""

import os

import pytest
from openai.types.chat import ChatCompletionUserMessageParam
from pydantic import BaseModel

from magentic_marketplace.marketplace.llm import functional

pytestmark = pytest.mark.skip_ci


class ResponseModel(BaseModel):
    """Test response model for structured output."""

    answer: str
    confidence: float


class TestFunctionalInterface:
    """Test the functional interface for LLM clients."""

    @pytest.mark.skipif(
        not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set"
    )
    @pytest.mark.asyncio
    async def test_generate_with_anthropic_provider(self):
        """Test functional generate with Anthropic provider."""
        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Say 'Hello World' and nothing else."
            )
        ]
        response, usage = await functional.generate(
            messages,
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            temperature=0.1,
            max_tokens=50,
        )

        assert isinstance(response, str)
        assert "Hello World" in response
        assert usage.provider == "anthropic"

    @pytest.mark.skipif(
        not os.environ.get("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set"
    )
    @pytest.mark.asyncio
    async def test_generate_with_openai_provider(self):
        """Test functional generate with OpenAI provider."""
        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Say 'Hello World' and nothing else."
            )
        ]
        response, usage = await functional.generate(
            messages,
            provider="openai",
            model="gpt-4o-mini",
            temperature=0.1,
            max_tokens=50,
        )

        assert isinstance(response, str)
        assert "Hello World" in response
        assert usage.provider == "openai"

    @pytest.mark.skipif(
        not os.environ.get("GEMINI_API_KEY"), reason="GEMINI_API_KEY not set"
    )
    @pytest.mark.asyncio
    async def test_generate_with_gemini_provider(self):
        """Test functional generate with Gemini provider."""
        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Say 'Hello World' and nothing else."
            )
        ]
        response, usage = await functional.generate(
            messages,
            provider="gemini",
            model="gemini-2.5-flash",
            temperature=0.1,
            max_tokens=50,
        )

        assert isinstance(response, str)
        assert "Hello World" in response
        assert usage.provider == "gemini"

    @pytest.mark.asyncio
    async def test_generate_with_unsupported_provider(self):
        """Test functional generate with unsupported provider."""
        messages = [ChatCompletionUserMessageParam(role="user", content="Hello")]

        with pytest.raises(ValueError):
            await functional.generate(messages, provider="invalid")  # type: ignore

    @pytest.mark.skipif(
        not os.environ.get("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set"
    )
    @pytest.mark.asyncio
    async def test_generate_with_string_message(self):
        """Test functional generate with string message."""
        response, usage = await functional.generate(
            "Say 'Test' and nothing else.",
            provider="openai",
            model="gpt-4o-mini",
            max_tokens=20,
        )

        assert isinstance(response, str)
        assert "Test" in response
        assert usage.token_count > 0

    @pytest.mark.skipif(
        not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set"
    )
    @pytest.mark.asyncio
    async def test_generate_with_structured_output(self):
        """Test functional generate with structured output."""
        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Respond with JSON: answer=42, confidence=0.95"
            )
        ]
        response, usage = await functional.generate(
            messages,
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            response_format=ResponseModel,
            max_tokens=100,
        )

        assert isinstance(response, ResponseModel)
        assert response.answer == "42"
        assert response.confidence == 0.95
        assert usage.token_count > 0

    @pytest.mark.skipif(
        not os.environ.get("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set"
    )
    @pytest.mark.asyncio
    async def test_generate_with_all_parameters(self):
        """Test functional generate with all possible parameters."""
        messages = [
            ChatCompletionUserMessageParam(
                role="user", content="Say 'Complete' and nothing else."
            )
        ]
        response, usage = await functional.generate(
            messages,
            provider="openai",
            model="gpt-4o-mini",
            temperature=0.1,
            max_tokens=20,
            reasoning_effort="minimal",
        )

        assert isinstance(response, str)
        assert "Complete" in response
        assert usage.token_count > 0
