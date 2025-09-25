"""Query builders for actions resource."""

from typing import Any

from ....shared.models import BaseAction
from ...queries.actions import (
    ActionsQuery,
    request_metadata,
    request_name,
    request_parameters,
    result_content,
    result_is_error,
    result_metadata,
)
from ...queries.base import Query


# Action request query builders
def action(action: type[BaseAction]) -> ActionsQuery:
    """Create query for action name."""
    return request_name(value=action.get_name(), operator="=")


def parameter(param_name: str, value: Any, operator: str = "=") -> ActionsQuery:
    """Create query for action parameter."""
    return request_parameters(path=param_name, value=value, operator=operator)


def parameters(operator: str = "=", **kwds: Any) -> Query:
    """Create query for action parameter."""
    queries = [parameter(key, value, operator) for key, value in kwds.items()]
    composite_query = None
    for query in queries:
        if composite_query is None:
            composite_query = query
        else:
            composite_query &= query

    if composite_query is None:
        raise ValueError("Must provide at least one keyword argument")

    return composite_query


def parameter_contains(param_name: str, text: str) -> ActionsQuery:
    """Find actions containing specific text in a parameter."""
    return request_parameters(path=param_name, value=f"%{text}%", operator="LIKE")


def metadata(key: str, value: Any, operator: str = "=") -> ActionsQuery:
    """Create query for action metadata."""
    return request_metadata(path=key, value=value, operator=operator)


# Action result query builders
def error_actions() -> ActionsQuery:
    """Create query for actions that resulted in errors."""
    return result_is_error(value=True, operator="=")


def success_actions() -> ActionsQuery:
    """Create query for actions that did not result in errors."""
    return result_is_error(value=False, operator="=")


def result_content_query(content: Any) -> ActionsQuery:
    """Create query for action result content."""
    return result_content(path="", value=content, operator="=")


def result_contains(text: str) -> ActionsQuery:
    """Create query for action results containing specific text."""
    return result_content(path="", value=f"%{text}%", operator="LIKE")


def action_result_metadata(key: str, value: Any) -> ActionsQuery:
    """Create query for result metadata."""
    return result_metadata(path=key, value=value, operator="=")
