"""Tests for agent registration and update logic."""

import pytest
from httpx import AsyncClient

from magentic_marketplace.marketplace.shared.models import (
    Business,
    BusinessAgentProfile,
    Customer,
    CustomerAgentProfile,
)
from magentic_marketplace.platform.shared.models import AgentRegistrationRequest


@pytest.mark.asyncio
class TestAgentRegistrationUpdate:
    """Test that registering an existing agent updates instead of creating duplicate."""

    async def test_register_same_agent_twice_updates_instead_of_creating(
        self, integration_test_setup
    ):
        """Test that registering the same agent ID twice updates the agent."""
        setup = integration_test_setup
        base_url = setup["server_url"]

        async with AsyncClient(base_url=base_url) as client:
            # Create initial customer profile
            customer_data = Customer(
                id="test-customer-123",
                name="Initial Customer Name",
                request="I want pizza",
                menu_features={"pizza": 15.0},
                amenity_features=["delivery"],
            )
            initial_customer = CustomerAgentProfile(
                id="test-customer-123",
                customer=customer_data,
            )

            # Register the agent for the first time
            register_request = AgentRegistrationRequest(agent=initial_customer)
            response1 = await client.post(
                "/agents/register", json=register_request.model_dump(mode="json")
            )
            assert response1.status_code == 200
            result1 = response1.json()
            agent_id_1 = result1["id"]
            assert agent_id_1 == "test-customer-123"

            # Verify the agent exists with initial data
            get_response1 = await client.get(f"/agents/{agent_id_1}")
            assert get_response1.status_code == 200
            agent_data_1 = get_response1.json()["agent"]
            assert agent_data_1["customer"]["name"] == "Initial Customer Name"
            assert agent_data_1["customer"]["request"] == "I want pizza"

            # Register the same agent ID again with updated data
            updated_customer_data = Customer(
                id="test-customer-123",  # Same ID
                name="Updated Customer Name",  # Different name
                request="I want sushi now",  # Different query
                menu_features={"sushi": 20.0},
                amenity_features=["dine-in"],
            )
            updated_customer = CustomerAgentProfile(
                id="test-customer-123",
                customer=updated_customer_data,
            )

            register_request2 = AgentRegistrationRequest(agent=updated_customer)
            response2 = await client.post(
                "/agents/register", json=register_request2.model_dump(mode="json")
            )
            assert response2.status_code == 200
            result2 = response2.json()
            agent_id_2 = result2["id"]
            assert agent_id_2 == "test-customer-123"  # Same ID

            # Verify the agent was updated, not duplicated
            get_response2 = await client.get(f"/agents/{agent_id_2}")
            assert get_response2.status_code == 200
            agent_data_2 = get_response2.json()["agent"]
            assert agent_data_2["customer"]["name"] == "Updated Customer Name"
            assert agent_data_2["customer"]["request"] == "I want sushi now"

            # Verify there's still only one agent with this ID
            # (not a duplicate created)
            all_agents_response = await client.get("/agents")
            assert all_agents_response.status_code == 200
            all_agents = all_agents_response.json()["items"]
            matching_agents = [a for a in all_agents if a["id"] == "test-customer-123"]
            assert len(matching_agents) == 1

    async def test_register_different_agent_types_with_same_id(
        self, integration_test_setup
    ):
        """Test that registering different agent types with same ID updates correctly."""
        setup = integration_test_setup
        base_url = setup["server_url"]

        async with AsyncClient(base_url=base_url) as client:
            # Register as a customer first
            customer_data = Customer(
                id="agent-123",
                name="Customer Agent",
                request="Looking for food",
                menu_features={"food": 10.0},
                amenity_features=[],
            )
            customer = CustomerAgentProfile(
                id="agent-123",
                customer=customer_data,
            )

            register_request1 = AgentRegistrationRequest(agent=customer)
            response1 = await client.post(
                "/agents/register", json=register_request1.model_dump(mode="json")
            )
            assert response1.status_code == 200
            assert response1.json()["id"] == "agent-123"

            # Verify it's a customer
            get_response1 = await client.get("/agents/agent-123")
            assert get_response1.status_code == 200
            agent_data_1 = get_response1.json()["agent"]
            assert "customer" in agent_data_1
            assert agent_data_1["customer"]["name"] == "Customer Agent"

            # Now register a business with the same ID
            business_data = Business(
                id="agent-123",
                name="Business Agent",
                description="Test business",
                rating=4.0,
                progenitor_customer="test",
                menu_features={"pizza": 10.0},
                amenity_features={},
                min_price_factor=0.8,
            )
            business = BusinessAgentProfile(
                id="agent-123",
                business=business_data,
            )

            register_request2 = AgentRegistrationRequest(agent=business)
            response2 = await client.post(
                "/agents/register", json=register_request2.model_dump(mode="json")
            )
            assert response2.status_code == 200
            assert response2.json()["id"] == "agent-123"

            # Verify it's now a business (updated)
            get_response2 = await client.get("/agents/agent-123")
            assert get_response2.status_code == 200
            agent_data_2 = get_response2.json()["agent"]
            assert "business" in agent_data_2
            assert agent_data_2["business"]["name"] == "Business Agent"

    async def test_register_new_agents_creates_them(self, integration_test_setup):
        """Test that registering new agents still creates them correctly."""
        setup = integration_test_setup
        base_url = setup["server_url"]

        async with AsyncClient(base_url=base_url) as client:
            # Register first agent
            customer1_data = Customer(
                id="customer-1",
                name="Customer One",
                request="Pizza",
                menu_features={"pizza": 15.0},
                amenity_features=[],
            )
            customer1 = CustomerAgentProfile(
                id="customer-1",
                customer=customer1_data,
            )

            response1 = await client.post(
                "/agents/register",
                json=AgentRegistrationRequest(agent=customer1).model_dump(mode="json"),
            )
            assert response1.status_code == 200
            assert response1.json()["id"] == "customer-1"

            # Register second agent with different ID
            customer2_data = Customer(
                id="customer-2",
                name="Customer Two",
                request="Sushi",
                menu_features={"sushi": 20.0},
                amenity_features=[],
            )
            customer2 = CustomerAgentProfile(
                id="customer-2",
                customer=customer2_data,
            )

            response2 = await client.post(
                "/agents/register",
                json=AgentRegistrationRequest(agent=customer2).model_dump(mode="json"),
            )
            assert response2.status_code == 200
            assert response2.json()["id"] == "customer-2"

            # Verify both agents exist
            all_agents_response = await client.get("/agents")
            assert all_agents_response.status_code == 200
            all_agents = all_agents_response.json()["items"]
            agent_ids = {a["id"] for a in all_agents}
            assert "customer-1" in agent_ids
            assert "customer-2" in agent_ids
