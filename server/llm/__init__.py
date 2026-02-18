"""
LLM Provider Module
===================

Smart LLM routing for YokeFlow with vault-aware provider selection.

Routing Rules:
- Personal Obsidian Vault: LMStudio (MANDATORY - privacy)
- Agents (Local) Vault: Claude (with agent models)
- Generated Projects: Claude (default)
- Fallback/Backup: LMStudio
"""

from server.llm.provider_router import (
    LLMProvider,
    get_provider_for_vault,
    get_default_provider,
    route_request,
)
from server.llm.openai_compatible import OpenAICompatibleClient

__all__ = [
    "LLMProvider",
    "get_provider_for_vault",
    "get_default_provider",
    "route_request",
    "OpenAICompatibleClient",
]
