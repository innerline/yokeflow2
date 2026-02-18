"""
Claude Client
=============

Wrapper for Anthropic Claude API used by YokeFlow.

This is the PRIMARY LLM provider for YokeFlow operations.
"""

import os
from typing import Optional, AsyncIterator, Any, List

from server.utils.logging import get_logger

logger = get_logger(__name__)


class ClaudeClient:
    """
    Client for Anthropic Claude API.

    This is the primary LLM provider for YokeFlow, used for:
    - Project initialization (Opus model)
    - Coding tasks (Sonnet model)
    - Reviews and quality checks
    - Generated projects
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: str = "claude-sonnet-4-5-20250929",
    ):
        """
        Initialize the Claude client.

        Args:
            api_key: Anthropic API key (from env if not provided)
            default_model: Default model to use
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
        self.default_model = default_model
        self._client = None

        if not self.api_key:
            logger.warning("llm.claude.no_api_key")

    def _get_client(self):
        """Get or create the Anthropic client."""
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic
                self._client = AsyncAnthropic(api_key=self.api_key)
            except ImportError:
                raise ImportError(
                    "anthropic package not installed. "
                    "Install with: pip install anthropic"
                )
        return self._client

    async def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs
    ) -> str:
        """
        Complete a prompt.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            model: Model to use (default_model if not specified)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters for the API

        Returns:
            Generated text
        """
        client = self._get_client()
        model = model or self.default_model

        logger.debug(
            "llm.claude.complete.started",
            model=model,
            prompt_length=len(prompt),
            max_tokens=max_tokens
        )

        try:
            params = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
                **kwargs
            }

            if system_prompt:
                params["system"] = system_prompt

            if temperature is not None:
                params["temperature"] = temperature

            response = await client.messages.create(**params)
            content = response.content[0].text

            logger.info(
                "llm.claude.complete.success",
                model=model,
                response_length=len(content),
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens
            )

            return content

        except Exception as e:
            logger.error(
                "llm.claude.complete.failed",
                error=str(e),
                model=model
            )
            raise

    async def stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs
    ) -> AsyncIterator[str]:
        """
        Stream a completion.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            model: Model to use
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters

        Yields:
            Generated text chunks
        """
        client = self._get_client()
        model = model or self.default_model

        logger.debug(
            "llm.claude.stream.started",
            model=model,
            prompt_length=len(prompt)
        )

        try:
            params = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
                **kwargs
            }

            if system_prompt:
                params["system"] = system_prompt

            if temperature is not None:
                params["temperature"] = temperature

            async with client.messages.stream(**params) as stream:
                async for text in stream.text_stream:
                    yield text

            logger.info("llm.claude.stream.completed", model=model)

        except Exception as e:
            logger.error(
                "llm.claude.stream.failed",
                error=str(e)
            )
            raise

    async def chat(
        self,
        messages: List[dict],
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs
    ) -> str:
        """
        Multi-turn chat completion.

        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: Optional system prompt
            model: Model to use
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters

        Returns:
            Generated response
        """
        client = self._get_client()
        model = model or self.default_model

        params = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
            **kwargs
        }

        if system_prompt:
            params["system"] = system_prompt

        if temperature is not None:
            params["temperature"] = temperature

        response = await client.messages.create(**params)
        return response.content[0].text

    async def count_tokens(self, text: str) -> int:
        """
        Count tokens in text.

        Args:
            text: Text to count tokens for

        Returns:
            Token count
        """
        client = self._get_client()
        # Use a simple approximation if exact counting not available
        # Claude uses ~4 chars per token on average
        return len(text) // 4

    @staticmethod
    def get_initializer_model() -> str:
        """Get the model for initialization tasks (Opus)."""
        return os.getenv(
            "DEFAULT_INITIALIZER_MODEL",
            "claude-opus-4-5-20251101"
        )

    @staticmethod
    def get_coding_model() -> str:
        """Get the model for coding tasks (Sonnet)."""
        return os.getenv(
            "DEFAULT_CODING_MODEL",
            "claude-sonnet-4-5-20250929"
        )

    @staticmethod
    def get_review_model() -> str:
        """Get the model for review tasks (Sonnet)."""
        return os.getenv(
            "DEFAULT_REVIEW_MODEL",
            "claude-sonnet-4-5-20250929"
        )
