"""MarketplaceServer - FastAPI Server for the Magentic Marketplace API.

This module provides a MarketplaceServer class that subclasses FastAPI and accepts
async context manager factory functions for dependency injection.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request

from ..database.base import BaseDatabaseController
from ..protocol.base import BaseMarketplaceProtocol
from .auth import AuthService


class MarketplaceServer(FastAPI):
    """FastAPI server for the Magentic Marketplace API with hybrid dependency injection.

    This server accepts a factory function for DatabaseController (for proper resource management)
    and a BaseMarketplaceProtocol instance, managing their lifecycle and making them available through app.state.
    """

    def __init__(
        self,
        database_factory: Callable[
            [], AbstractAsyncContextManager[BaseDatabaseController]
        ],
        protocol: BaseMarketplaceProtocol,
        **kwargs: Any,
    ):
        """Initialize the MarketplaceServer.

        Args:
            database_factory: Factory function that returns an async context manager for DatabaseController
            protocol: The behavior protocol instance
            **kwargs: Additional arguments passed to FastAPI constructor

        """
        # Store factory function and protocol instance
        self._database_factory = database_factory
        self._behavior_protocol = protocol

        # Create lifespan manager
        @asynccontextmanager
        async def lifespan(app: FastAPI) -> AsyncIterator[None]:
            # Startup: create and enter database context manager
            database_cm = self._database_factory()
            database_controller = await database_cm.__aenter__()

            # Initialize protocol-specific resources (e.g., indexes)
            await self._behavior_protocol.initialize(database_controller)

            # Create auth service with database controller
            auth_service = AuthService(database_controller)

            # Store instances and context manager for cleanup
            app.state.database_controller = database_controller
            app.state.behavior_protocol = self._behavior_protocol
            app.state.auth_service = auth_service
            app.state._database_cm = database_cm

            try:
                yield
            finally:
                # Shutdown: properly exit database context manager
                try:
                    await app.state._database_cm.__aexit__(None, None, None)
                except Exception:
                    pass  # Log error in real implementation

        # Set default title if not provided
        if "title" not in kwargs:
            kwargs["title"] = "Magentic Marketplace API"

        # Set lifespan
        kwargs["lifespan"] = lifespan

        # Initialize FastAPI
        super().__init__(**kwargs)

        # Include all route modules
        from .routes import actions, agents, health, logs

        self.include_router(agents.router)
        self.include_router(actions.router)
        self.include_router(logs.router)
        self.include_router(health.router)

    def serve(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        log_level: str = "info",
        **kwargs: Any,
    ) -> None:
        """Start the server synchronously using uvicorn.

        Args:
            host: Host to bind to
            port: Port to bind to
            log_level: Log level for uvicorn
            **kwargs: Additional arguments passed to uvicorn.run()

        """
        try:
            import uvicorn
        except ImportError as e:
            raise ImportError(
                "uvicorn is required for serve() method. Install with: pip install uvicorn"
            ) from e

        uvicorn.run(
            self, host=host, port=port, log_level=log_level, workers=1, **kwargs
        )

    async def serve_async(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        log_level: str = "info",
        **kwargs: Any,
    ) -> None:
        """Start the server asynchronously using uvicorn.

        Args:
            host: Host to bind to
            port: Port to bind to
            log_level: Log level for uvicorn
            **kwargs: Additional arguments passed to uvicorn.Config()

        """
        try:
            import uvicorn
        except ImportError as e:
            raise ImportError(
                "uvicorn is required for serve_async() method. Install with: pip install uvicorn"
            ) from e

        config = uvicorn.Config(
            self,
            host=host,
            port=port,
            log_level=log_level,
            timeout_keep_alive=60,
            workers=1,
            **kwargs,
        )
        server = uvicorn.Server(config)
        await server.serve()

    def create_server_task(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        log_level: str = "info",
        **kwargs: Any,
    ) -> tuple["asyncio.Task[None]", Callable[[], None]]:
        """Create a server task with a shutdown function for graceful termination.

        Args:
            host: Host to bind to
            port: Port to bind to
            log_level: Log level for uvicorn
            **kwargs: Additional arguments passed to uvicorn.Config()

        Returns:
            Tuple of (server_task, shutdown_function)

        """
        try:
            import uvicorn
        except ImportError as e:
            raise ImportError(
                "uvicorn is required for create_server_with_shutdown() method. Install with: pip install uvicorn"
            ) from e

        config = uvicorn.Config(
            self,
            host=host,
            port=port,
            log_level=log_level,
            timeout_keep_alive=60,
            workers=1,
            **kwargs,
        )
        server = uvicorn.Server(config)

        server_task = asyncio.create_task(server.serve())

        def shutdown():
            server.should_exit = True

        return server_task, shutdown


# Reusable dependency functions that grab from app.state
def get_database(request: Request) -> BaseDatabaseController:
    """Get the database controller from app state."""
    return request.app.state.database_controller


def get_protocol(request: Request) -> BaseMarketplaceProtocol:
    """Get the behavior protocol from app state."""
    return request.app.state.behavior_protocol


def get_auth_service(request: Request) -> AuthService:
    """Get the auth service from app state."""
    return request.app.state.auth_service
