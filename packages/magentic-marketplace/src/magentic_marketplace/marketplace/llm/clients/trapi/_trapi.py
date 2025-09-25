"""TRAPI client models and configuration.

This module provides the configuration and client classes for Microsoft Research TRAPI service, including Azure OpenAI configurations and client management.
"""

import inspect
import logging
import re
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from threading import Lock
from typing import Any

from azure.identity import (
    AzureCliCredential,
    ChainedTokenCredential,
    DefaultAzureCredential,
    ManagedIdentityCredential,
    get_bearer_token_provider,
)
from openai import AsyncAzureOpenAI
from openai.lib.azure import AzureADTokenProvider
from openai.resources.chat.completions import Completions as _OpenAICompletions

logger = logging.getLogger(__name__)


@dataclass
class AzureOpenAIConfig:
    """Configuration for Azure OpenAI client.

    Attributes:
        azure_endpoint: The Azure OpenAI endpoint URL
        api_version: The API version to use
        azure_deployment: Optional deployment name
        azure_ad_token_provider: Optional Azure AD token provider

    """

    azure_endpoint: str
    api_version: str
    azure_deployment: str | None = None
    azure_ad_token_provider: Callable[[], str] | AzureADTokenProvider | None = None


TRAPI_BASE_URL = "https://trapi.research.microsoft.com"

# Use get_client_configs to get these
_CLIENT_CONFIGS: dict[str, list[AzureOpenAIConfig]] = {
    "gpt-4o_2024-11-20": [
        AzureOpenAIConfig(
            azure_endpoint=f"{TRAPI_BASE_URL}/gcr/shared",
            api_version="2024-10-21",
            azure_deployment="gpt-4o_2024-11-20",
        ),
        AzureOpenAIConfig(
            azure_endpoint=f"{TRAPI_BASE_URL}/msraif/shared",
            api_version="2024-10-21",
            azure_deployment="gpt-4o_2024-11-20",
        ),
    ],
    # This deployment is failing as of 09/04/2025
    # "gpt-4o_2024-05-13": [
    #     AzureOpenAIConfig(
    #         azure_endpoint=f"{TRAPI_BASE_URL}/gcr/preview",
    #         api_version="2024-10-21",
    #         azure_deployment="gpt-4o_2024-05-13",
    #     ),
    # ],
    # This deployment is still not working 08/11/2025
    # "o3-mini": [
    #     AzureOpenAIConfig(
    #         azure_endpoint=f"{TRAPI_BASE_URL}/gcr/shared",
    #         api_version="2024-12-01-preview",
    #         azure_deployment="o3-mini_2025-01-31",
    #     )
    # ],
    # "o3-mini_2025-01-31": [
    #     AzureOpenAIConfig(
    #         azure_endpoint=f"{TRAPI_BASE_URL}/gcr/shared",
    #         api_version="2024-12-01-preview",
    #         azure_deployment="o3-mini_2025-01-31",
    #     )
    # ],
    "gpt-4.1_2025-04-14": [
        AzureOpenAIConfig(
            azure_endpoint=f"{TRAPI_BASE_URL}/gcr/shared",
            api_version="2024-10-21",
            azure_deployment="gpt-4.1_2025-04-14",
        ),
        AzureOpenAIConfig(
            azure_endpoint=f"{TRAPI_BASE_URL}/msraif/shared",
            api_version="2024-10-21",
            azure_deployment="gpt-4.1_2025-04-14",
        ),
    ],
    # These deployments are still not working 08/11/2025
    # "o3": [
    #     AzureOpenAIConfig(
    #         azure_endpoint=f"{TRAPI_BASE_URL}/gcr/shared",
    #         api_version="2024-12-01-preview",
    #         azure_deployment="o3_2025-04-16",
    #     ),
    #     AzureOpenAIConfig(
    #         azure_endpoint=f"{TRAPI_BASE_URL}/msraif/shared",
    #         api_version="2024-12-01-preview",
    #         azure_deployment="o3_2025-04-16",
    #     ),
    # ],
    # "o3_2025-04-16": [
    #     AzureOpenAIConfig(
    #         azure_endpoint=f"{TRAPI_BASE_URL}/gcr/shared",
    #         api_version="2024-12-01-preview",
    #         azure_deployment="o3_2025-04-16",
    #     ),
    #     AzureOpenAIConfig(
    #         azure_endpoint=f"{TRAPI_BASE_URL}/msraif/shared",
    #         api_version="2024-12-01-preview",
    #         azure_deployment="o3_2025-04-16",
    #     ),
    # ],
    # Too Outdated
    # "gpt-4_turbo-2024-04-09": [
    #     AzureOpenAIConfig(
    #         azure_endpoint=f"{TRAPI_BASE_URL}/gcr/shared",
    #         api_version="2024-10-21",
    #         azure_deployment="gpt-4_turbo-2024-04-09",
    #     ),
    #     AzureOpenAIConfig(
    #         azure_endpoint=f"{TRAPI_BASE_URL}/msraif/shared",
    #         api_version="2024-10-21",
    #         azure_deployment="gpt-4_turbo-2024-04-09",
    #     ),
    # ],
    # "gpt-35-turbo_1106": [
    #     AzureOpenAIConfig(
    #         azure_endpoint=f"{TRAPI_BASE_URL}/gcr/shared",
    #         api_version="2024-10-21",
    #         azure_deployment="gpt-35-turbo_1106",
    #     ),
    #     AzureOpenAIConfig(
    #         azure_endpoint=f"{TRAPI_BASE_URL}/msraif/shared",
    #         api_version="2024-10-21",
    #         azure_deployment="gpt-35-turbo_1106",
    #     ),
    # ],
    "gpt-4o_2024-08-06": [
        AzureOpenAIConfig(
            azure_endpoint=f"{TRAPI_BASE_URL}/gcr/shared",
            api_version="2024-10-21",
            azure_deployment="gpt-4o_2024-08-06",
        ),
        AzureOpenAIConfig(
            azure_endpoint=f"{TRAPI_BASE_URL}/msraif/shared",
            api_version="2024-10-21",
            azure_deployment="gpt-4o_2024-08-06",
        ),
    ],
    "gpt-4o-mini_2024-07-18": [
        AzureOpenAIConfig(
            azure_endpoint=f"{TRAPI_BASE_URL}/gcr/shared",
            api_version="2024-10-21",
            azure_deployment="gpt-4o-mini_2024-07-18",
        ),
        AzureOpenAIConfig(
            azure_endpoint=f"{TRAPI_BASE_URL}/msraif/shared",
            api_version="2024-10-21",
            azure_deployment="gpt-4o-mini_2024-07-18",
        ),
    ],
    "o1-mini_2024-09-12": [
        AzureOpenAIConfig(
            azure_endpoint=f"{TRAPI_BASE_URL}/gcr/shared",
            api_version="2024-10-21",
            azure_deployment="o1-mini_2024-09-12",
        ),
        AzureOpenAIConfig(
            azure_endpoint=f"{TRAPI_BASE_URL}/msraif/shared",
            api_version="2024-10-21",
            azure_deployment="o1-mini_2024-09-12",
        ),
    ],
    "o1_2024-12-17": [
        AzureOpenAIConfig(
            azure_endpoint=f"{TRAPI_BASE_URL}/gcr/shared",
            api_version="2024-12-01-preview",
            azure_deployment="o1_2024-12-17",
        ),
        AzureOpenAIConfig(
            azure_endpoint=f"{TRAPI_BASE_URL}/msraif/shared",
            api_version="2024-12-01-preview",
            azure_deployment="o1_2024-12-17",
        ),
    ],
    "gpt-4.1-nano_2025-04-14": [
        AzureOpenAIConfig(
            azure_endpoint=f"{TRAPI_BASE_URL}/gcr/shared",
            api_version="2025-04-01-preview",
            azure_deployment="gpt-4.1-nano_2025-04-14",
        ),
        AzureOpenAIConfig(
            azure_endpoint=f"{TRAPI_BASE_URL}/msraif/shared",
            api_version="2025-04-01-preview",
            azure_deployment="gpt-4.1-nano_2025-04-14",
        ),
    ],
    "gpt-4.1-mini_2025-04-14": [
        AzureOpenAIConfig(
            azure_endpoint=f"{TRAPI_BASE_URL}/gcr/shared",
            api_version="2025-04-01-preview",
            azure_deployment="gpt-4.1-mini_2025-04-14",
        ),
        AzureOpenAIConfig(
            azure_endpoint=f"{TRAPI_BASE_URL}/msraif/shared",
            api_version="2025-04-01-preview",
            azure_deployment="gpt-4.1-mini_2025-04-14",
        ),
    ],
    "o4-mini_2025-04-16": [
        AzureOpenAIConfig(
            azure_endpoint=f"{TRAPI_BASE_URL}/gcr/shared",
            api_version="2024-12-01-preview",
            azure_deployment="o4-mini_2025-04-16",
        ),
        AzureOpenAIConfig(
            azure_endpoint=f"{TRAPI_BASE_URL}/msraif/shared",
            api_version="2024-12-01-preview",
            azure_deployment="o4-mini_2025-04-16",
        ),
    ],
    "gpt-5_2025-08-07": [
        AzureOpenAIConfig(
            azure_endpoint=f"{TRAPI_BASE_URL}/gcr/shared",
            api_version="2025-04-01-preview",
            azure_deployment="gpt-5_2025-08-07",
        ),
        AzureOpenAIConfig(
            azure_endpoint=f"{TRAPI_BASE_URL}/msraif/shared",
            api_version="2025-04-01-preview",
            azure_deployment="gpt-5_2025-08-07",
        ),
    ],
    "gpt-5-mini_2025-08-07": [
        AzureOpenAIConfig(
            azure_endpoint=f"{TRAPI_BASE_URL}/gcr/shared",
            api_version="2025-04-01-preview",
            azure_deployment="gpt-5-mini_2025-08-07",
        ),
        AzureOpenAIConfig(
            azure_endpoint=f"{TRAPI_BASE_URL}/msraif/shared",
            api_version="2025-04-01-preview",
            azure_deployment="gpt-5-mini_2025-08-07",
        ),
    ],
    "gpt-5-nano_2025-08-07": [
        AzureOpenAIConfig(
            azure_endpoint=f"{TRAPI_BASE_URL}/gcr/shared",
            api_version="2025-04-01-preview",
            azure_deployment="gpt-5-nano_2025-08-07",
        ),
        AzureOpenAIConfig(
            azure_endpoint=f"{TRAPI_BASE_URL}/msraif/shared",
            api_version="2025-04-01-preview",
            azure_deployment="gpt-5-nano_2025-08-07",
        ),
    ],
    "gpt-5-chat_2025-08-07": [
        AzureOpenAIConfig(
            azure_endpoint=f"{TRAPI_BASE_URL}/gcr/shared",
            api_version="2025-04-01-preview",
            azure_deployment="gpt-5-chat_2025-08-07",
        ),
        AzureOpenAIConfig(
            azure_endpoint=f"{TRAPI_BASE_URL}/msraif/shared",
            api_version="2025-04-01-preview",
            azure_deployment="gpt-5-chat_2025-08-07",
        ),
    ],
}

# Catch latest YYYY-MM-DD format
_FULL_DATE_RE = re.compile(r"^(.*)[-_](\d{4}-\d{2}-\d{2})$")
# Legacy MMDD format from 2023
_SHORT_DATE_RE = re.compile(r"^(.*)[-_](\d{2}\d{2})$")
_model_dates: dict[str, list[tuple[datetime, str]]] = {}
for model in _CLIENT_CONFIGS.keys():
    alias = None
    date = None

    try:
        fullmatch = _FULL_DATE_RE.fullmatch(model)
        if fullmatch:
            alias, date_str = fullmatch.groups()
            date = datetime.strptime(date_str, "%Y-%m-%d")
        else:
            fullmatch = _SHORT_DATE_RE.fullmatch(model)
            if fullmatch:
                alias, date_str = fullmatch.groups()
                date = datetime.strptime(date_str, "%m%d")

        if alias and date:
            if alias not in _model_dates:
                _model_dates[alias] = []

            _model_dates[alias].append((date, model))
        else:
            raise ValueError("Unrecognized model format.")
    except Exception:
        logger.warning(f"Failed to parse alias for model {model}", exc_info=True)

# Construct aliases (e.g. "gpt-4o") for the newest version of the model
_CLIENT_ALIASES = {
    alias: sorted(values)[-1][1] for alias, values in _model_dates.items()
}


def get_azure_token_provider(scope: str | None = None) -> Callable[[], str]:
    """Get the default Azure token provider function.

    Arguments:
        scope (str | None): The scope for the token provider. Defaults to "api://trapi/.default".

    Returns:
        A function that returns an Azure AD token string when called.

    """
    logger.debug("Creating default Azure token provider")

    if scope is None:
        scope = "api://trapi/.default"

    return get_bearer_token_provider(
        ChainedTokenCredential(
            AzureCliCredential(),
            ManagedIdentityCredential(),
            DefaultAzureCredential(),
        ),
        scope,
    )


def get_azure_openai_client(
    *,
    azure_endpoint: str,
    api_version: str,
    azure_deployment: str,
    azure_ad_token_provider: AzureADTokenProvider | None = None,
    scope: str | None = None,
    **kwds: Any,
):
    """Create an Azure OpenAI client with the given configuration.

    Args:
        azure_endpoint: The Azure OpenAI endpoint URL
        api_version: The API version to use
        azure_deployment: The deployment name
        azure_ad_token_provider: Optional Azure AD token provider
        scope: Optional scope for token provider
        **kwds: Additional keyword arguments

    Returns:
        AzureOpenAI client instance

    """
    if azure_ad_token_provider is None:
        azure_ad_token_provider = get_azure_token_provider(scope)

    return AsyncAzureOpenAI(
        azure_endpoint=azure_endpoint,
        api_version=api_version,
        azure_deployment=azure_deployment,
        azure_ad_token_provider=azure_ad_token_provider,
        **kwds,
    )


def get_client_configs(
    azure_ad_token_provider: AzureADTokenProvider | AzureADTokenProvider | None = None,
    include: Sequence[str] | None = None,
    exclude: Sequence[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Get client configurations for TRAPI models.

    Args:
        azure_ad_token_provider: Optional Azure AD token provider
        include: Optional list of models to include
        exclude: Optional list of models to exclude

    Returns:
        Dictionary mapping model names to their configurations

    """
    logger.debug("Getting model configurations")
    if azure_ad_token_provider is None:
        logger.debug("No token provider specified, using default")
        azure_ad_token_provider = get_azure_token_provider()

    models: dict[str, list[dict[str, Any]]] = {}
    for model, deployments in _CLIENT_CONFIGS.items():
        models[model] = [
            asdict(
                AzureOpenAIConfig(
                    azure_endpoint=deployment.azure_endpoint,
                    api_version=deployment.api_version,
                    azure_deployment=deployment.azure_deployment,
                    azure_ad_token_provider=azure_ad_token_provider,
                )
            )
            for deployment in deployments
        ]

    for alias, model in _CLIENT_ALIASES.items():
        if model in models:
            models[alias] = models[model]
        else:
            logger.warning(f"No matching model {model} for alias {alias}.")

    if include:
        logger.debug(f"Only including models: {include}")
        models = {k: v for k, v in models.items() if k in include}

    if exclude:
        logger.debug(f"Excluding models: {exclude}")
        models = {k: v for k, v in models.items() if k not in exclude}

    logger.debug(
        f"Loaded {sum(map(len, models.values()))} model configurations across {len(models)} unique models"
    )
    return models


class _TrapiChatCompletions:
    def __init__(self, context: "Trapi") -> None:
        self.trapi = context

    def __getattribute__(self, name: str) -> Any:
        if "trapi" in name or not hasattr(_OpenAICompletions, name):
            return super().__getattribute__(name)
        else:
            logger.debug(f"Wrapping OpenAI completions method: {name}")
            value = getattr(_OpenAICompletions, name)
            if callable(value):
                sig = inspect.signature(value)
                if "model" in sig.parameters:
                    logger.debug(
                        f"Method {name} accepts model parameter, wrapping with Trapi logic"
                    )
                    return self._trapi_wrap(name)
                else:
                    logger.error(
                        f"Method '{name}' does not accept a 'model' keyword argument"
                    )
                    raise AttributeError(
                        f"Method '{name}' does not accept a 'model' keyword argument"
                    )
            else:
                logger.error(f"Cannot get non-callable attribute: {name}")
                raise AttributeError("Cannot get attributes that aren't callable")

    def _trapi_wrap(self, method: str):
        async def wrapper(*, model: str, **kwargs: Any):
            logger.debug(f"Calling {method} for model: {model}")
            clients = self.trapi.list_clients(model)
            logger.debug(f"Found {len(clients)} clients for model: {model}")
            exceptions: list[Exception] = []
            for i, client in enumerate(clients):
                try:
                    logger.debug(
                        f"Attempting {method} with client {id(client)} ({i + 1}/{len(clients)}) for model: {model}"
                    )
                    result = await getattr(client.chat.completions, method)(
                        model=model, **kwargs
                    )
                    self.trapi.client_succeeded(model, client)
                    logger.debug(
                        f"Successfully completed {method} for model: {model} using client {i + 1}"
                    )
                    return result
                except Exception as e:
                    logger.warning(
                        f"Client {id(client)} ({i + 1}/{len(clients)}) failed for model {model}: {str(e)}"
                    )
                    self.trapi.client_failed(model, client)
                    exceptions.append(e)

            logger.error(f"All {len(clients)} clients failed for model: {model}")
            # Format all exceptions into a single readable message
            error_msg = f"All {len(clients)} clients failed for model: {model}\n"
            for i, exc in enumerate(exceptions, 1):
                error_msg += f"  Client {i}: {type(exc).__name__}: {str(exc)}\n"
            raise Exception(error_msg.rstrip())

        return wrapper


class _TrapiChat:
    def __init__(self, context: "Trapi") -> None:
        self.completions: _OpenAICompletions = _TrapiChatCompletions(context)  # type: ignore


class Trapi:
    """TRAPI client for Microsoft Research TRAPI service.

    Provides access to multiple Azure OpenAI deployments with automatic failover
    and load balancing across different endpoints.
    """

    def __init__(
        self,
        azure_ad_token_provider: AzureADTokenProvider | None = None,
        include_models: Sequence[str] | None = None,
        exclude_models: Sequence[str] | None = None,
        additional_clients: dict[str, Sequence[AsyncAzureOpenAI]] | None = None,
    ) -> None:
        """Initialize TRAPI client.

        Args:
            azure_ad_token_provider: Optional Azure AD token provider
            include_models: Optional list of models to include
            exclude_models: Optional list of models to exclude
            additional_clients: Optional additional clients to add

        """
        logger.debug("Initializing Trapi client")
        self._clients: dict[str, OrderedDict[int, AsyncAzureOpenAI]] = {}
        self._lock = Lock()

        model_configs = get_client_configs(
            azure_ad_token_provider=azure_ad_token_provider,
            include=include_models,
            exclude=exclude_models,
        )
        logger.debug("Creating Azure OpenAI clients for each model configuration")
        for model, configs in model_configs.items():
            self._clients[model] = OrderedDict()
            for config in configs:
                try:
                    client = AsyncAzureOpenAI(**config)
                    self._clients[model][id(client)] = client
                    logger.debug(
                        f"Created client for model: {model} with endpoint: {config.get('azure_endpoint', 'unknown')}"
                    )
                except Exception:
                    logger.exception(f"Failed to create client for model {model}")
                    raise

        if additional_clients:
            for model, clients in additional_clients.items():
                if model not in self._clients:
                    self._clients[model] = OrderedDict()

                for client in clients:
                    self._clients[model][id(client)] = client
                    # Move to front
                    self._clients[model].move_to_end(id(client), last=False)

        total_clients = sum(len(clients) for clients in self._clients.values())
        logger.debug(
            f"Successfully initialized Trapi with {len(self._clients)} models and {total_clients} total clients"
        )

        self.chat = _TrapiChat(self)

    def list_clients(self, model: str):
        """Get list of clients for the specified model.

        Args:
            model: The model name

        Returns:
            List of Azure OpenAI clients for the model

        Raises:
            KeyError: If the model is not supported

        """
        if model not in self._clients:
            logger.error(
                f"Unsupported model requested: {model}. Available models: {list(self._clients.keys())}"
            )
            raise KeyError(f"Unsupported model: {model}")

        with self._lock:
            clients = list(self._clients[model].values())
            logger.debug(f"Retrieved {len(clients)} clients for model: {model}")
            return clients

    def client_failed(self, model: str, client: AsyncAzureOpenAI):
        """Mark a client as failed and move it to the end of the queue.

        Args:
            model: The model name
            client: The failed Azure OpenAI client

        """
        with self._lock:
            logger.debug(f"Moving failed client to end of queue for model: {model}")
            self._clients[model].move_to_end(id(client))

    def client_succeeded(self, model: str, client: AsyncAzureOpenAI):
        """Mark a client as successful.

        Args:
            model: The model name
            client: The successful Azure OpenAI client

        """
        logger.debug(f"Client succeeded for model: {model}")
        pass
