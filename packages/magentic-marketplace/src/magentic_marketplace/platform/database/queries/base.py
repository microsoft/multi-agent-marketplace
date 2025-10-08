"""Base classes and utility functions for database query operations."""

from functools import partial
from typing import Any, Literal, TypeVar

from pydantic import BaseModel
from pydantic.types import AwareDatetime


class QueryParams(BaseModel):
    """Query parameters for database operations."""

    offset: int = 0
    limit: int | None = None


class RangeQueryParams(QueryParams):
    """Query parameters with date range filtering."""

    after: AwareDatetime | None = None
    before: AwareDatetime | None = None
    before_index: int | None = None
    after_index: int | None = None


Operator = (
    Literal["=", "!=", ">", ">=", "<", "<=", "in", "not in", "like", "not like"] | str
)


class Query(BaseModel):
    """Base class of all queries, provides & and | operators."""

    def __and__(self, other: "Query") -> "AndQuery":
        """Override bitwise & operator to create AndQuery."""
        return AndQuery(left=self, right=other)

    def __or__(self, other: "Query") -> "OrQuery":
        """Override bitwise | operator to create OrQuery."""
        return OrQuery(left=self, right=other)


class JSONQuery(Query):
    """Base class of all database queries."""

    path: str
    value: Any = None
    operator: Operator


class AndQuery(Query):
    """AND of two JSON queries."""

    left: "Query"
    right: "Query"


class OrQuery(Query):
    """OR of two JSON queries."""

    left: "Query"
    right: "Query"


T = TypeVar("T", bound=JSONQuery)


def query(
    query_class: type[T],
    *,
    path: str,
    value: Any = None,
    operator: str,
) -> T:
    """Create a query instance for the given query class.

    Args:
        query_class (type[T]): The class type to instantiate for the query
        path (str): The field path to query against
        value (Any, optional): The value to search for in the specified path. Defaults to None.
        operator (str): The comparison operator to use
    Returns:
        T: An instance of the specified query class with the provided parameters

    """
    return query_class(
        path=path,
        value=value,
        operator=operator,
    )


def query_path(query_class: type[T], path: str):
    """Create a query function bound to a specific path."""
    return partial(query, query_class, path=path)


def query_path_prefix(query_class: type[T], prefix: str):
    """Create a query function bound to a path prefix."""

    def wrapper(
        *,
        path: str,
        value: str,
        operator: str = "=",
    ) -> T:
        return query(
            query_class,
            path=f"{prefix}.{path}",
            value=value,
            operator=operator,
        )

    return wrapper
