"""
LLM Provider Router
===================

Smart routing for LLM requests based on context (vault type, task type, etc.).

Routing Rules:
- Personal Obsidian Vault: LMStudio (MANDATORY - privacy, no data leaves local)
- Agents (Local) Vault: Claude (with agent models)
- Generated Projects: Claude (default)
- Fallback/Backup: LMStudio
"""

import os
from enum import Enum
from pathlib import Path
from typing import Optional, Any, AsyncIterator
from dataclasses import dataclass

from server.utils.logging import get_logger

logger = get_logger(__name__)


class LLMProvider(str, Enum):
    """Available LLM providers."""
    CLAUDE = "claude"
    LMSTUDIO = "lmstudio"
    LLAMACPP = "llamacpp"


@dataclass
class LLMConfig:
    """Configuration for LLM providers."""
    # Primary provider (default)
    default_provider: LLMProvider = LLMProvider.CLAUDE

    # Claude configuration
    claude_api_key: Optional[str] = None

    # LMStudio configuration (mandatory for Personal Vault)
    lmstudio_api_base: str = "http://localhost:1234/v1"
    lmstudio_model: str = "local-model"

    # llama.cpp configuration (future)
    llamacpp_api_base: str = "http://localhost:8080/v1"

    # Vault paths for routing
    personal_vault_path: Optional[str] = None
    agents_vault_path: Optional[str] = None

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Create config from environment variables."""
        provider_str = os.getenv("LLM_PROVIDER", "claude").lower()
        provider = LLMProvider(provider_str) if provider_str in [p.value for p in LLMProvider] else LLMProvider.CLAUDE

        return cls(
            default_provider=provider,
            claude_api_key=os.getenv("CLAUDE_API_KEY"),
            lmstudio_api_base=os.getenv("LMSTUDIO_API_BASE", "http://localhost:1234/v1"),
            lmstudio_model=os.getenv("LMSTUDIO_MODEL", "local-model"),
            llamacpp_api_base=os.getenv("LLAMACPP_API_BASE", "http://localhost:8080/v1"),
            personal_vault_path=os.getenv("PERSONAL_VAULT_PATH"),
            agents_vault_path=os.getenv("AGENTS_VAULT_PATH"),
        )


def get_provider_for_vault(
    vault_path: Optional[str],
    config: Optional[LLMConfig] = None
) -> LLMProvider:
    """
    Determine the LLM provider to use based on vault path.

    Routing Rules:
    - Personal Vault path -> LMStudio (MANDATORY for privacy)
    - Agents Vault path -> Claude (with agent models)
    - Unknown/None -> Default provider (Claude)

    Args:
        vault_path: Path to the vault being accessed
        config: LLM configuration (loaded from env if not provided)

    Returns:
        LLMProvider to use for this vault
    """
    if config is None:
        config = LLMConfig.from_env()

    if vault_path is None:
        return config.default_provider

    # Normalize paths for comparison
    vault_path_normalized = Path(vault_path).resolve()

    # Check Personal Vault - MUST use LMStudio for privacy
    if config.personal_vault_path:
        personal_path = Path(config.personal_vault_path).resolve()
        if str(vault_path_normalized).startswith(str(personal_path)):
            logger.info(
                "llm.routing.personal_vault",
                vault_path=vault_path,
                provider="lmstudio",
                reason="Privacy - Personal Vault must use local LLM"
            )
            return LLMProvider.LMSTUDIO

    # Check Agents Vault - Uses Claude with agent models
    if config.agents_vault_path:
        agents_path = Path(config.agents_vault_path).resolve()
        if str(vault_path_normalized).startswith(str(agents_path)):
            logger.info(
                "llm.routing.agents_vault",
                vault_path=vault_path,
                provider="claude",
                reason="Quality - Agents Vault uses Claude with agent models"
            )
            return LLMProvider.CLAUDE

    # Default to configured provider
    logger.debug(
        "llm.routing.default",
        vault_path=vault_path,
        provider=config.default_provider.value
    )
    return config.default_provider


def get_default_provider(config: Optional[LLMConfig] = None) -> LLMProvider:
    """
    Get the default LLM provider.

    Args:
        config: LLM configuration (loaded from env if not provided)

    Returns:
        Default LLMProvider
    """
    if config is None:
        config = LLMConfig.from_env()
    return config.default_provider


def get_provider_for_task(
    task_type: str,
    vault_path: Optional[str] = None,
    config: Optional[LLMConfig] = None
) -> LLMProvider:
    """
    Determine the LLM provider based on task type and optional vault context.

    Task-specific routing:
    - initialization: Claude (complex planning)
    - coding: Claude (default) or LMStudio (if vault requires)
    - review: Claude (quality critical)
    - vault_query: Based on vault path

    Args:
        task_type: Type of task (initialization, coding, review, vault_query)
        vault_path: Optional vault path for context
        config: LLM configuration

    Returns:
        LLMProvider to use for this task
    """
    if config is None:
        config = LLMConfig.from_env()

    # Vault queries must respect vault routing rules
    if task_type == "vault_query" and vault_path:
        return get_provider_for_vault(vault_path, config)

    # Complex tasks that benefit from Claude
    claude_preferred_tasks = {"initialization", "review", "planning", "architecture"}

    if task_type in claude_preferred_tasks:
        return LLMProvider.CLAUDE

    # Coding tasks: use vault routing if vault specified, else default
    if vault_path:
        return get_provider_for_vault(vault_path, config)

    return config.default_provider


async def route_request(
    prompt: str,
    vault_path: Optional[str] = None,
    task_type: str = "general",
    config: Optional[LLMConfig] = None,
    **kwargs
) -> Any:
    """
    Route an LLM request to the appropriate provider.

    This is the main entry point for all LLM calls in YokeFlow.

    Args:
        prompt: The prompt to send
        vault_path: Optional vault path for routing decisions
        task_type: Type of task for routing decisions
        config: LLM configuration
        **kwargs: Additional arguments for the LLM call

    Returns:
        Response from the LLM provider
    """
    if config is None:
        config = LLMConfig.from_env()

    provider = get_provider_for_task(task_type, vault_path, config)

    logger.info(
        "llm.request.routed",
        provider=provider.value,
        task_type=task_type,
        vault_path=vault_path,
        prompt_length=len(prompt)
    )

    if provider == LLMProvider.CLAUDE:
        from server.llm.claude_client import ClaudeClient
        client = ClaudeClient(api_key=config.claude_api_key)
        return await client.complete(prompt, **kwargs)

    elif provider == LLMProvider.LMSTUDIO:
        from server.llm.openai_compatible import OpenAICompatibleClient
        client = OpenAICompatibleClient(
            base_url=config.lmstudio_api_base,
            model=config.lmstudio_model
        )
        return await client.complete(prompt, **kwargs)

    elif provider == LLMProvider.LLAMACPP:
        from server.llm.openai_compatible import OpenAICompatibleClient
        client = OpenAICompatibleClient(
            base_url=config.llamacpp_api_base,
            model="local"
        )
        return await client.complete(prompt, **kwargs)

    else:
        raise ValueError(f"Unknown provider: {provider}")


async def stream_request(
    prompt: str,
    vault_path: Optional[str] = None,
    task_type: str = "general",
    config: Optional[LLMConfig] = None,
    **kwargs
) -> AsyncIterator[str]:
    """
    Stream an LLM request from the appropriate provider.

    Args:
        prompt: The prompt to send
        vault_path: Optional vault path for routing decisions
        task_type: Type of task for routing decisions
        config: LLM configuration
        **kwargs: Additional arguments for the LLM call

    Yields:
        Chunks of the response
    """
    if config is None:
        config = LLMConfig.from_env()

    provider = get_provider_for_task(task_type, vault_path, config)

    logger.info(
        "llm.stream.routed",
        provider=provider.value,
        task_type=task_type,
        vault_path=vault_path
    )

    if provider == LLMProvider.CLAUDE:
        from server.llm.claude_client import ClaudeClient
        client = ClaudeClient(api_key=config.claude_api_key)
        async for chunk in client.stream(prompt, **kwargs):
            yield chunk

    elif provider == LLMProvider.LMSTUDIO:
        from server.llm.openai_compatible import OpenAICompatibleClient
        client = OpenAICompatibleClient(
            base_url=config.lmstudio_api_base,
            model=config.lmstudio_model
        )
        async for chunk in client.stream(prompt, **kwargs):
            yield chunk

    elif provider == LLMProvider.LLAMACPP:
        from server.llm.openai_compatible import OpenAICompatibleClient
        client = OpenAICompatibleClient(
            base_url=config.llamacpp_api_base,
            model="local"
        )
        async for chunk in client.stream(prompt, **kwargs):
            yield chunk
