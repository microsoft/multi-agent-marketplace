"""Postgres utils."""

from typing import Any

import ftfy


def fix_json_for_postgres(value: Any) -> Any:
    """Recursively apply ftfy.fix_text() to all string values in a dict.

    This fixes invalid Unicode sequences (like null bytes) that PostgreSQL
    cannot handle in TEXT/JSONB columns.

    Args:
        value: json dict, string, or array that may contain strings with invalid unicode

    Returns:
        value with all strings fixed

    """
    if isinstance(value, str):
        fixed = ftfy.fix_text(value)
        return fixed
    elif isinstance(value, dict):
        return {k: fix_json_for_postgres(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [fix_json_for_postgres(item) for item in value]
    elif isinstance(value, tuple):
        return tuple(fix_json_for_postgres(item) for item in value)
    else:
        return value
