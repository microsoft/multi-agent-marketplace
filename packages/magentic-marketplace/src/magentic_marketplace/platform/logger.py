"""Marketplace logger for dual Python/database logging."""

import asyncio
import logging
import traceback
from typing import Any

from pydantic import BaseModel

from ..platform.shared.models import Log, LogLevel
from .client import MarketplaceClient


class MarketplaceLogger:
    """Logger wrapper that logs to both Python logging and the database."""

    def __init__(self, name: str, client: MarketplaceClient, flush_every: int = 100):
        """Initialize marketplace logger with name and client."""
        self.name = name
        # Set up basic logging config if none exists
        if not logging.getLogger().handlers:
            logging.basicConfig(
                level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s"
            )
        self.python_logger = logging.getLogger(name)
        self._client = client
        self._tasks: list[asyncio.Task] = []
        self._flush_every = flush_every

    def _log(
        self,
        level: LogLevel,
        message: str | None = None,
        *,
        data: dict[str, Any] | BaseModel | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        """Log to both Python logger and database."""
        if message is None and data is None:
            raise ValueError("Must provide at least one of message or data.")

        # Log to Python logging
        python_level = getattr(
            logging,
            level.upper(),
        )
        self.python_logger.log(
            python_level,
            message,
        )

        log = Log(
            level=level, name=self.name, message=message, data=data, metadata=metadata
        )

        # Log to database. Fire and forget to avoid blocking but return task in case caller wants to wait.
        loop = asyncio.get_event_loop()
        if loop.is_running():
            task = asyncio.create_task(self._log_to_db(log))
            self._tasks.append(task)
            if len(self._tasks) >= self._flush_every:
                asyncio.create_task(self.flush())
            return task
        else:
            raise RuntimeError("Cannot log to database: No running event loop.")

    async def _log_to_db(self, log: Log):
        """Async helper to log to database."""
        try:
            await self._client.logs.create(log)
        except Exception:
            # If database logging fails, log the error to Python logger only
            self.python_logger.error(
                f"Failed to log to database: {traceback.format_exc(2)}"
            )

    def debug(
        self,
        message: str | None = None,
        *,
        data: dict[str, Any] | BaseModel | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        """Log a debug message."""
        return self._log("debug", message, data=data, metadata=metadata)

    def info(
        self,
        message: str | None = None,
        *,
        data: dict[str, Any] | BaseModel | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        """Log an info message."""
        return self._log("info", message, data=data, metadata=metadata)

    def warning(
        self,
        message: str | None = None,
        *,
        data: dict[str, Any] | BaseModel | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        """Log a warning message."""
        return self._log("warning", message, data=data, metadata=metadata)

    def error(
        self,
        message: str | None = None,
        *,
        data: dict[str, Any] | BaseModel | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        """Log an error message."""
        return self._log("error", message, data=data, metadata=metadata)

    def exception(
        self,
        message: str | None = None,
        *,
        data: dict[str, Any] | BaseModel | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        """Log an error message."""
        message = ((message or "") + "\n" + traceback.format_exc(2)).strip()
        return self.error(message, data=data, metadata=metadata)

    async def flush(self):
        """Wait for any pending tasks to complete."""
        tasks = list(self._tasks)
        self._tasks.clear()
        return await asyncio.gather(*tasks, return_exceptions=True)
