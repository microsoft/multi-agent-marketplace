"""Simple text message model for text-only protocol."""

from typing import Literal

from pydantic import BaseModel, Field


class TextMessage(BaseModel):
    """A simple text message."""

    type: Literal["text"] = "text"
    content: str = Field(description="Text content of the message")
