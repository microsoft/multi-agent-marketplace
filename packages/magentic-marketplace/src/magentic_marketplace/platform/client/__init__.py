"""Client module for the Magentic Marketplace API."""

from .base import ClientError, HTTPError
from .client import MarketplaceClient

__all__ = ["MarketplaceClient", "ClientError", "HTTPError"]
