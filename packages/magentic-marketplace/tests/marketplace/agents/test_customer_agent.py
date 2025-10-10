"""Tests for the SimpleMarketplace's CustomerAgent."""

import asyncio
import unittest.mock

import pytest

from magentic_marketplace.marketplace.agents.customer import (
    CustomerAction,
    CustomerAgent,
)
from magentic_marketplace.marketplace.llm.clients.openai import OpenAIConfig
from magentic_marketplace.marketplace.shared.models import Customer


@pytest.fixture
def customer():
    """Return a Customer profile for building Customer agents."""
    return Customer(
        id="test-customer-001",
        name="Test Customer",
        request="Looking for test items",
        menu_features={"item": 10.0},
        amenity_features=["delivery"],
    )


@pytest.fixture
def search_businesses_action():
    """Return a CustomerAction representing the search_businesses."""
    return CustomerAction(
        action_type="search_businesses",
        reason="test",
        search_query="test",
        search_page=1,
    )


@pytest.fixture
def llm_config():
    """Return a dummy OpenAIConfig with 'none' api_key."""
    return OpenAIConfig(
        provider="openai",
        model="gpt-4.1-mini",
        api_key="none",
    )


@pytest.mark.asyncio
async def test_max_steps_1(
    integration_test_setup,
    customer: Customer,
    llm_config: OpenAIConfig,
    search_businesses_action: CustomerAction,
):
    """Tests that a CustomerAgent successfully shuts down after a single action."""
    agent = CustomerAgent(
        llm_config=llm_config,
        customer=customer,
        base_url=integration_test_setup["server_url"],
        polling_interval=0.1,
        max_steps=1,
    )

    # Mock the agent's _generate_customer_action method to return a search_businesses action to avoid hitting LLM calls
    with unittest.mock.patch.object(
        agent, "_generate_customer_action", return_value=search_businesses_action
    ):
        # Wait for up to 60 seconds
        await asyncio.wait_for(agent.run(), 60)
        assert agent.will_shutdown is True
        assert agent.conversation_step == 1


@pytest.mark.asyncio
async def test_max_steps_none(
    integration_test_setup,
    customer: Customer,
    llm_config: OpenAIConfig,
    search_businesses_action: CustomerAction,
):
    """Tests that a customer never (i.e. not within 60 seconds) shuts down when max_steps is None."""
    agent = CustomerAgent(
        llm_config=llm_config,
        customer=customer,
        base_url=integration_test_setup["server_url"],
        polling_interval=0.1,
        max_steps=None,
    )
    # Mock the agent's _generate_customer_action method to return a search_businesses action to avoid hitting LLM calls
    with unittest.mock.patch.object(
        agent, "_generate_customer_action", return_value=search_businesses_action
    ):
        try:
            await asyncio.wait_for(agent.run(), 60)
        except TimeoutError:
            assert agent.will_shutdown is False


@pytest.mark.asyncio
async def test_max_steps_default(customer: Customer, llm_config: OpenAIConfig):
    """Tests that the default value for max_steps is None."""
    agent = CustomerAgent(
        llm_config=llm_config,
        customer=customer,
        base_url="http://dummy.com",
        polling_interval=0.1,
    )

    assert agent._max_steps is None
