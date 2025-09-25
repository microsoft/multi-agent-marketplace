"""Query builders for logs resource."""

from ...queries.base import query
from ...queries.logs import LogQuery


def message_contains(text: str) -> LogQuery:
    """Create query for log messages containing specific text."""
    return query(LogQuery, path="$.message", value=f"%{text}%", operator="LIKE")


# Composite helper functions
def error_logs() -> LogQuery:
    """Find error-level log entries."""
    return query(LogQuery, path="$.level", value="error", operator="=")


def warning_logs() -> LogQuery:
    """Find warning-level log entries."""
    return query(LogQuery, path="$.level", value="warning", operator="=")


def info_logs() -> LogQuery:
    """Find info-level log entries."""
    return query(LogQuery, path="$.level", value="info", operator="=")


def debug_logs() -> LogQuery:
    """Find debug-level log entries."""
    return query(LogQuery, path="$.level", value="debug", operator="=")
