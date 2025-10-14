"""Generate a list of fictional Mexican/Tex-Mex restaurant menu items using an LLM, ensuring uniqueness."""

import json

import openai
from pydantic import JsonValue


def llm_json_query(prompt: str, model: str = "gpt-4o") -> JsonValue:
    """Send a prompt to the LLM and expect aa JSON response."""
    client = openai.Client()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
    )
    assert isinstance(response.choices[0].message.content, str)
    return json.loads(response.choices[0].message.content)


def normalize_name(s: str) -> str:
    """Normalize a menu item name to find more collisions."""
    s = s.lower().replace("&", " and ")
    s = "".join(
        c if c.isalnum() or c.isspace() else " " for c in s
    )  # Remove punctuation
    tokens = sorted(s.split())

    # Remove stopwords
    stopwords = {
        "the",
        "a",
        "an",
        "and",
        "with",
        "of",
        "in",
        "on",
        "to",
        "for",
        "at",
        "by",
        "from",
        "is",
        "it",
        "its",
        "s",
    }
    tokens = [t for t in tokens if t not in stopwords]

    return "".join(tokens)


def find_similar(items: list[str]) -> None | tuple[str, str]:
    """Check if any item is similar to another item.  If so, return the first such match, otherwise return None."""
    for i in range(len(items)):
        for j in range(len(items)):
            if i != j and is_similar(items[i], items[j]):
                return (items[i], items[j])
    return None


def is_similar(a: str, b: str) -> bool:
    """Check if two strings are similar."""
    a_lower = a.lower()
    b_lower = b.lower()
    a_normalized = normalize_name(a)
    b_normalized = normalize_name(b)

    if a_lower in b_lower or b_lower in a_lower:
        return True
    if a_normalized in b_normalized or b_normalized in a_normalized:
        return True

    return False
