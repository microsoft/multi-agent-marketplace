"""Postgres utils."""

from typing import Any

import ftfy


def fix_json_for_postgres(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively apply ftfy.fix_text() to all string values in a dict.

    This fixes invalid Unicode sequences (like null bytes) that PostgreSQL
    cannot handle in TEXT/JSONB columns.

    Args:
        data: Dictionary that may contain strings with invalid unicode

    Returns:
        Dictionary with all strings fixed

    """

    def fix_value(value: Any) -> Any:
        if isinstance(value, str):
            fixed = ftfy.fix_text(value)
            return fixed
        elif isinstance(value, dict):
            return {k: fix_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [fix_value(item) for item in value]
        elif isinstance(value, tuple):
            return tuple(fix_value(item) for item in value)
        else:
            return value

    return fix_value(data)
