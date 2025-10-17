"""FastAPI server for marketplace analytics and visualization."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ..experiments.run_analytics import MarketplaceAnalytics
from ..marketplace.actions import ActionAdapter, Search, SendMessage
from ..marketplace.shared.models import (
    BusinessAgentProfile,
    CustomerAgentProfile,
    MarketplaceAgentProfileAdapter,
)
from ..platform.database import (
    connect_to_postgresql_database,
    connect_to_sqlite_database,
)
from ..platform.database.base import BaseDatabaseController

# Global database controller (set during lifespan)
_db_controller: BaseDatabaseController | None = None


async def _load_customers():
    """Load all customer agents from the database."""
    if _db_controller is None:
        raise RuntimeError("Database controller not initialized")

    agent_rows = await _db_controller.agents.get_all()
    customers = []

    for agent_row in agent_rows:
        agent = MarketplaceAgentProfileAdapter.validate_python(
            agent_row.data.model_dump()
        )

        if isinstance(agent, CustomerAgentProfile):
            customer_data = agent.customer
            customer = {
                "id": agent.id,
                "name": customer_data.name,
                "user_request": customer_data.request,
                "menu_features": customer_data.menu_features,
                "amenity_features": customer_data.amenity_features,
            }
            customers.append(customer)

    return customers


async def _load_businesses():
    """Load all business agents from the database."""
    if _db_controller is None:
        raise RuntimeError("Database controller not initialized")

    agent_rows = await _db_controller.agents.get_all()
    businesses = []

    for agent_row in agent_rows:
        agent = MarketplaceAgentProfileAdapter.validate_python(
            agent_row.data.model_dump()
        )

        if isinstance(agent, BusinessAgentProfile):
            business_data = agent.business
            business = {
                "id": agent.id,
                "name": business_data.name,
                "rating": business_data.rating,
                "price_min": min(business_data.menu_features.values())
                if business_data.menu_features
                else 0,
                "price_max": max(business_data.menu_features.values())
                if business_data.menu_features
                else 0,
                "description": business_data.description,
                "menu_features": business_data.menu_features,
                "amenity_features": business_data.amenity_features,
            }
            businesses.append(business)

    return businesses


async def _load_messages():
    """Load all messages from actions in the database."""
    if _db_controller is None:
        raise RuntimeError("Database controller not initialized")

    action_rows = await _db_controller.actions.get_all()
    messages = []

    for action_row in action_rows:
        action_request = action_row.data.request
        action_result = action_row.data.result

        if action_result.is_error:
            continue

        try:
            action = ActionAdapter.validate_python(action_request.parameters)

            if isinstance(action, SendMessage):
                message_content = action.message
                content_dict = message_content.model_dump(mode="json")

                if message_content.type == "text" and "content" in content_dict:
                    content_value = content_dict["content"]
                else:
                    content_value = content_dict

                message = {
                    "id": action_row.id,
                    "to_agent": action.to_agent_id,
                    "from_agent": action.from_agent_id,
                    "type": message_content.type,
                    "content": content_value,
                    "created_at": action.created_at.isoformat(),
                }
                messages.append(message)
            elif isinstance(action, Search):
                # Extract business IDs from search results
                result_content = action_result.content
                business_ids = []
                if result_content and "businesses" in result_content:
                    business_ids = [
                        b.get("id") for b in result_content["businesses"] if "id" in b
                    ]

                # Create search result message
                search_content = {
                    "type": "search",
                    "query": action.query,
                    "business_ids": business_ids,
                    "total_results": len(business_ids),
                }

                message = {
                    "id": action_row.id,
                    "from_agent": action_row.data.agent_id,
                    "to_agent": None,  # Search doesn't have a specific recipient
                    "type": "search",
                    "content": search_content,
                    "created_at": action_row.created_at.isoformat(),
                    "business_ids": business_ids,  # Store for thread matching
                }
                messages.append(message)
        except Exception as e:
            print(f"Warning: Failed to parse action {action_row.id}: {e}")
            continue

    return messages


def _create_message_threads(customers, businesses, messages):
    """Create message threads from customers, businesses, and messages.

    Returns:
        tuple: (threads_dict, threads_with_payments_set) where:
            - threads_dict: dict of thread_key -> thread data
            - threads_with_payments_set: set of thread_keys that have payments

    """
    threads = {}
    threads_with_payments = set()
    customer_by_agent_id = {c["id"]: c for c in customers}
    business_by_agent_id = {b["id"]: b for b in businesses}

    for message in messages:
        from_agent = message["from_agent"]
        to_agent = message.get("to_agent")

        # Handle search messages specially - they create threads with all matched businesses
        if message["type"] == "search" and "business_ids" in message:
            customer = customer_by_agent_id.get(from_agent)
            if customer:
                for business_id in message["business_ids"]:
                    business = business_by_agent_id.get(business_id)
                    if business:
                        thread_key = f"{customer['id']}-{business_id}"

                        if thread_key not in threads:
                            threads[thread_key] = {
                                "participants": {
                                    "customer": customer,
                                    "business": business,
                                },
                                "messages": [],
                                "lastMessageTime": message["created_at"],
                                "utility": 0,  # Default utility
                            }

                        # Add search message to each relevant thread
                        thread_message = message.copy()
                        thread_message.pop(
                            "business_ids", None
                        )  # Remove internal field
                        threads[thread_key]["messages"].append(thread_message)
                        threads[thread_key]["lastMessageTime"] = message["created_at"]
        else:
            # Handle regular messages (SendMessage)
            customer = customer_by_agent_id.get(from_agent) or customer_by_agent_id.get(
                to_agent
            )
            business = business_by_agent_id.get(from_agent) or business_by_agent_id.get(
                to_agent
            )

            if customer and business:
                customer_id = customer["id"]
                business_id = business["id"]
                thread_key = f"{customer_id}-{business_id}"

                if thread_key not in threads:
                    threads[thread_key] = {
                        "participants": {"customer": customer, "business": business},
                        "messages": [],
                        "lastMessageTime": message["created_at"],
                        "utility": 0,  # Default utility
                    }

                threads[thread_key]["messages"].append(message)
                threads[thread_key]["lastMessageTime"] = message["created_at"]

                # Track threads with payments (customer sending payment to business)
                if message["type"] == "payment" and from_agent == customer_id:
                    threads_with_payments.add(thread_key)

    return threads, threads_with_payments


def create_analytics_app(
    database_name: str,
    db_type: str = "postgres",
    postgres_host: str = "localhost",
    postgres_port: int = 5432,
    postgres_password: str = "postgres",
) -> FastAPI:
    """Create FastAPI app for analytics with database connection.

    Args:
        database_name: PostgreSQL schema name or path to SQLite database file
        db_type: Type of database ("sqlite" or "postgres")
        postgres_host: PostgreSQL host (only used if db_type is "postgres")
        postgres_port: PostgreSQL port (only used if db_type is "postgres")
        postgres_password: PostgreSQL password (only used if db_type is "postgres")

    Returns:
        Configured FastAPI application

    """

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        """Manage database connection lifecycle."""
        global _db_controller

        if db_type == "sqlite":
            print("Connecting to SQLite database...", flush=True)
            print(f"Database path: {database_name}", flush=True)

            async with connect_to_sqlite_database(database_path=database_name) as db:
                _db_controller = db
                print("Database connection established", flush=True)
                print("UI API ready", flush=True)
                yield

            print("Database connection closed", flush=True)
        elif db_type == "postgres":
            print("Connecting to PostgreSQL database...", flush=True)
            print(f"Host: {postgres_host}:{postgres_port}", flush=True)
            print(f"Schema: {database_name}", flush=True)

            async with connect_to_postgresql_database(
                schema=database_name,
                host=postgres_host,
                port=postgres_port,
                password=postgres_password,
                mode="existing",
            ) as db:
                _db_controller = db
                print("Database connection established", flush=True)
                print("UI API ready", flush=True)
                yield

            print("Database connection closed", flush=True)
        else:
            raise ValueError(
                f"Unsupported database type: {db_type}. Must be 'sqlite' or 'postgres'."
            )

    app = FastAPI(
        title="Marketplace UI API",
        version="2.0.0",
        description="UI API for marketplace simulation data",
        lifespan=lifespan,
    )

    # Enable CORS for frontend access
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routes (all under /api prefix)
    @app.get("/api")
    def api_index():
        """Get basic info about the API."""
        return {
            "name": "Marketplace UI API",
            "version": "2.0.0",
            "database": "SQLite" if db_type == "sqlite" else "PostgreSQL",
            "endpoints": [
                "/api/customers",
                "/api/businesses",
                "/api/marketplace-data",
                "/api/health",
            ],
        }

    @app.get("/api/customers")
    async def get_customers():
        """Get all customers."""
        try:
            return await _load_customers()
        except Exception as e:
            print(f"Error: {e}")
            return {"error": "Unable to load customers"}

    @app.get("/api/businesses")
    async def get_businesses():
        """Get all businesses."""
        try:
            return await _load_businesses()
        except Exception as e:
            print(f"Error: {e}")
            return {"error": "Unable to load businesses"}

    @app.get("/api/marketplace-data")
    async def get_marketplace_data():
        """Get messages, message threads, and analytics."""
        try:
            customers = await _load_customers()
            businesses = await _load_businesses()
            messages = await _load_messages()
            threads_dict, threads_with_payments = _create_message_threads(
                customers, businesses, messages
            )

            # Calculate analytics
            if _db_controller is None:
                raise RuntimeError("Database controller not initialized")
            analytics = MarketplaceAnalytics(_db_controller)
            await analytics.load_data()
            await analytics.analyze_actions()
            analytics_results = analytics.collect_analytics_results()

            for thread_key in threads_with_payments:
                thread = threads_dict[thread_key]
                customer_id = thread["participants"]["customer"]["id"]
                business_id = thread["participants"]["business"]["id"]

                # Calculate utility for this specific conversation
                conversation_utility = analytics.calculate_conversation_utility(
                    customer_id, business_id
                )
                thread["utility"] = conversation_utility

            # Convert to list and sort by lastMessageTime
            message_threads = list(threads_dict.values())
            message_threads.sort(key=lambda x: x["lastMessageTime"], reverse=True)

            # Build customer analytics dict
            customer_analytics = {}
            for customer_summary in analytics_results.customer_summaries:
                customer_analytics[customer_summary.customer_id] = {
                    "utility": customer_summary.utility,
                    "payments_made": customer_summary.payments_made,
                    "proposals_received": customer_summary.proposals_received,
                }

            # Build business analytics dict
            business_analytics = {}
            for business_summary in analytics_results.business_summaries:
                # Count payments received for this business
                payments_received = 0
                for customer_payments in analytics.customer_payments.values():
                    for payment in customer_payments:
                        business_id = analytics._find_business_for_proposal(
                            payment.proposal_message_id
                        )
                        if business_id == business_summary.business_id:
                            payments_received += 1

                business_analytics[business_summary.business_id] = {
                    "utility": business_summary.utility,
                    "proposals_sent": business_summary.proposals_sent,
                    "payments_received": payments_received,
                }

            # Marketplace summary
            marketplace_summary = {
                "total_utility": analytics_results.total_marketplace_customer_utility,
                "total_payments": analytics_results.transaction_summary.payments_made,
                "total_proposals": analytics_results.transaction_summary.order_proposals_created,
            }

            return {
                "messages": messages,
                "messageThreads": message_threads,
                "analytics": {
                    "customer_analytics": customer_analytics,
                    "business_analytics": business_analytics,
                    "marketplace_summary": marketplace_summary,
                },
            }
        except Exception as e:
            print(f"Error: {e}")
            return {"error": "Unable to load messages"}

    @app.get("/api/health")
    def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "timestamp": datetime.now(UTC).isoformat(),
            "database": "connected" if _db_controller else "disconnected",
        }

    # Mount static files at root (for UI)
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app


def run_ui_server(
    database_name: str,
    db_type: str = "postgres",
    postgres_host: str = "localhost",
    postgres_port: int = 5432,
    postgres_password: str = "postgres",
    ui_port: int = 5000,
    ui_host: str = "localhost",
):
    """Run the UI server.

    Args:
        database_name: PostgreSQL schema name or path to SQLite database file
        db_type: Type of database ("sqlite" or "postgres")
        postgres_host: PostgreSQL host (only used if db_type is "postgres")
        postgres_port: PostgreSQL port (only used if db_type is "postgres")
        postgres_password: PostgreSQL password (only used if db_type is "postgres")
        ui_port: Port for UI server
        ui_host: Host for UI server

    """
    import uvicorn

    print("Starting Marketplace UI Server...", flush=True)
    if db_type == "sqlite":
        print(f"Database: {database_name}", flush=True)
    else:
        print(f"Schema: {database_name}", flush=True)
    print(f"Server will be available at: http://{ui_host}:{ui_port}", flush=True)

    app = create_analytics_app(
        database_name=database_name,
        db_type=db_type,
        postgres_host=postgres_host,
        postgres_port=postgres_port,
        postgres_password=postgres_password,
    )

    uvicorn.run(
        app,
        host=ui_host,
        port=ui_port,
        log_level="info",
    )
