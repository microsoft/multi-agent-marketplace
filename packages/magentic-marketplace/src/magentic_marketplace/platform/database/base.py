"""Base database classes and interfaces for the marketplace."""

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from .models import ActionRow, AgentRow, LogRow
from .queries import Query, RangeQueryParams

TableEntryType = TypeVar("TableEntryType")


class DatabaseTooBusyError(Exception):
    """Raised when database is too busy to handle requests (connection pool exhausted, timeouts, etc)."""

    def __init__(self, message: str = "Database is too busy to handle the request"):
        """Initialize the DatabaseTooBusyError with a message."""
        self.message = message
        super().__init__(self.message)


class TableController(ABC, Generic[TableEntryType]):  # noqa: UP046
    """Abstract base class for table-specific CRUD operations.

    This generic interface defines the contract for controllers managing
    database tables, providing asynchronous methods for Create, Read, Update,
    and Delete (CRUD) operations. It is parameterized by:

        - TableEntryType: The type representing a row or entry in the table.

    Subclasses should implement these methods for specific tables/entities.
    """

    @abstractmethod
    async def create(self, item: TableEntryType) -> TableEntryType:
        """Create a new item in the Table."""
        pass

    @abstractmethod
    async def create_many(
        self, items: list[TableEntryType], batch_size: int = 1000
    ) -> None:
        """Create multiple items efficiently in batches.

        Args:
            items: List of items to create
            batch_size: Number of items to insert per batch (default: 1000)

        """
        pass

    @abstractmethod
    async def get_by_id(self, item_id: str) -> TableEntryType | None:
        """Retrieve an item by its ID."""
        pass

    @abstractmethod
    async def get_all(
        self, params: RangeQueryParams | None = None, batch_size: int = 1000
    ) -> list[TableEntryType]:
        """Retrieve all items with optional pagination, fetching in batches.

        Args:
            params: Range query parameters for filtering
            batch_size: Number of rows to fetch per batch (default: 1000)

        Returns:
            List of all matching items

        """
        pass

    @abstractmethod
    async def find(
        self, query: Query, params: RangeQueryParams | None = None
    ) -> list[TableEntryType]:
        """Find items matching query with range parameters."""
        pass

    @abstractmethod
    async def update(
        self, item_id: str, updates: dict[str, Any]
    ) -> TableEntryType | None:
        """Update an item by ID with the given field updates."""
        pass

    @abstractmethod
    async def delete(self, item_id: str) -> bool:
        """Delete an item by ID. Returns True if deleted, False if not found."""
        pass

    @abstractmethod
    async def count(self) -> int:
        """Get the total count of items."""
        pass


class AgentTableController(
    TableController[AgentRow],
):
    """Abstract controller for Agent operations."""


class ActionTableController(
    TableController[ActionRow],
):
    """Abstract controller for Action operations."""


class LogTableController(
    TableController[LogRow],
):
    """Abstract controller for Log operations."""


class BaseDatabaseController(ABC):
    """database controller that owns all entity controllers."""

    @property
    @abstractmethod
    def agents(self) -> AgentTableController:
        """Get the agent controller."""
        pass

    @property
    @abstractmethod
    def actions(self) -> ActionTableController:
        """Get the Action controller."""
        pass

    @property
    @abstractmethod
    def logs(self) -> LogTableController:
        """Get the log record controller."""
        pass

    @property
    @abstractmethod
    def row_index_column(self) -> str:
        """Get the name of the row index column for this database."""
        pass

    @abstractmethod
    async def execute(self, command: Any) -> Any:
        """Execute an arbitrary database command."""
        pass
