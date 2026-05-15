"""Azure SDK client factories — cached and lazy.

Importa SDKs sob demanda para que o webapp continue subindo mesmo sem as libs
instaladas / sem credenciais. Cada função retorna ``None`` em qualquer falha,
e o sub-app responsável cai pro mock automaticamente.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any, Optional

log = logging.getLogger("contoso.azure_clients")


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def get_credential() -> Optional[Any]:
    try:
        from azure.identity import DefaultAzureCredential
        return DefaultAzureCredential(exclude_interactive_browser_credential=True)
    except Exception as exc:
        log.warning("DefaultAzureCredential indisponível: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Azure AI Search
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def get_search_client() -> Optional[Any]:
    endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
    index = os.getenv("AZURE_SEARCH_INDEX_NAME")
    if not endpoint or not index:
        return None
    try:
        from azure.search.documents import SearchClient
        from azure.core.credentials import AzureKeyCredential
        api_key = os.getenv("AZURE_SEARCH_API_KEY")
        if api_key:
            cred = AzureKeyCredential(api_key)
        else:
            cred = get_credential()
            if cred is None:
                return None
        return SearchClient(endpoint=endpoint, index_name=index, credential=cred)
    except Exception as exc:
        log.warning("SearchClient indisponível: %s", exc)
        return None


# Cache one SearchClient per index name so we can talk to multiple datasets.
@lru_cache(maxsize=8)
def get_search_client_for(index_name: str) -> Optional[Any]:
    """Return a SearchClient bound to a specific index, or ``None`` if config missing."""
    endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
    if not endpoint or not index_name:
        return None
    try:
        from azure.search.documents import SearchClient
        from azure.core.credentials import AzureKeyCredential
        api_key = os.getenv("AZURE_SEARCH_API_KEY")
        if api_key:
            cred = AzureKeyCredential(api_key)
        else:
            cred = get_credential()
            if cred is None:
                return None
        return SearchClient(endpoint=endpoint, index_name=index_name, credential=cred)
    except Exception as exc:
        log.warning("SearchClient(%s) indisponível: %s", index_name, exc)
        return None


# Friendly dataset id → real index name (env-overridable)
def resolve_index_name(dataset: str) -> str:
    if dataset == "regulations":
        return os.getenv("AZURE_SEARCH_INDEX_REGULATIONS", "internal-regulations")
    # default & "telecom" both fall back to telecom-products
    return os.getenv("AZURE_SEARCH_INDEX_TELECOM",
                     os.getenv("AZURE_SEARCH_INDEX_NAME", "telecom-products"))


# ---------------------------------------------------------------------------
# Azure OpenAI (via Foundry project endpoint)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def get_openai_client() -> Optional[Any]:
    """Returns an AzureOpenAI client wired to the Foundry project (Entra auth)."""
    endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT") or os.getenv("AZURE_OPENAI_ENDPOINT")
    if not endpoint:
        return None
    # Strip /api/projects/<name> tail to leave Cognitive Services endpoint.
    base = endpoint.split("/api/projects")[0]
    try:
        from openai import AzureOpenAI
        cred = get_credential()
        if cred is None:
            return None

        def _token_provider() -> str:
            tok = cred.get_token("https://cognitiveservices.azure.com/.default")
            return tok.token

        return AzureOpenAI(
            azure_endpoint=base,
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
            azure_ad_token_provider=_token_provider,
        )
    except Exception as exc:
        log.warning("AzureOpenAI indisponível: %s", exc)
        return None


def get_chat_deployment() -> str:
    return os.getenv("AZURE_AI_MODEL_DEPLOYMENT", "gpt-4.1-mini")


# ---------------------------------------------------------------------------
# Azure AI Project (Hosted Agents, Evaluators)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def get_project_client() -> Optional[Any]:
    endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    if not endpoint:
        return None
    try:
        from azure.ai.projects import AIProjectClient
        cred = get_credential()
        if cred is None:
            return None
        # `allow_preview=True` is required by azure-ai-projects>=2.x to access
        # Hosted Agents (`agents.create_version`, `get_openai_client(agent_name=...)`,
        # `beta.agents.*` sessions). Older SDKs don't accept the kwarg — fall back.
        try:
            return AIProjectClient(endpoint=endpoint, credential=cred, allow_preview=True)
        except TypeError:
            return AIProjectClient(endpoint=endpoint, credential=cred)
    except Exception as exc:
        log.warning("AIProjectClient indisponível: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Content Safety
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def get_content_safety_client() -> Optional[Any]:
    endpoint = os.getenv("AZURE_CONTENT_SAFETY_ENDPOINT")
    if not endpoint:
        return None
    try:
        from azure.ai.contentsafety import ContentSafetyClient
        from azure.core.credentials import AzureKeyCredential
        key = os.getenv("AZURE_CONTENT_SAFETY_KEY")
        if key:
            cred = AzureKeyCredential(key)
        else:
            cred = get_credential()
            if cred is None:
                return None
        return ContentSafetyClient(endpoint=endpoint, credential=cred)
    except Exception as exc:
        log.warning("ContentSafetyClient indisponível: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Log Analytics (KQL para a seção Observabilidade em Produção)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def get_logs_query_client() -> Optional[Any]:
    """Return an `azure.monitor.query.LogsQueryClient` or `None` if SDK/credentials missing."""
    try:
        from azure.monitor.query import LogsQueryClient
    except Exception as exc:
        log.warning("azure-monitor-query indisponível: %s", exc)
        return None
    cred = get_credential()
    if cred is None:
        return None
    try:
        return LogsQueryClient(cred)
    except Exception as exc:
        log.warning("LogsQueryClient indisponível: %s", exc)
        return None


def get_log_analytics_workspace_id() -> Optional[str]:
    """Customer/Workspace GUID used to scope KQL queries."""
    wid = os.getenv("LOG_ANALYTICS_WORKSPACE_ID")
    return wid or None


__all__ = [
    "get_credential",
    "get_search_client",
    "get_search_client_for",
    "resolve_index_name",
    "get_openai_client",
    "get_chat_deployment",
    "get_project_client",
    "get_content_safety_client",
    "get_logs_query_client",
    "get_log_analytics_workspace_id",
]
