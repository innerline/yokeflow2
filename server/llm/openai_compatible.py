"""
OpenAI-Compatible Client
========================

Client for OpenAI-compatible APIs (LMStudio, llama.cpp, etc.).

Both LMStudio and llama.cpp expose OpenAI-compatible APIs, allowing
us to use a single client implementation for both.
"""

import httpx
from typing import Optional, AsyncIterator, Any, Dict, List
from dataclasses import dataclass

from server.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ChatMessage:
    """A chat message."""
    role: str
    content: str


class OpenAICompatibleClient:
    """
    Client for OpenAI-compatible LLM APIs.

    Works with:
    - LMStudio (http://localhost:1234/v1)
    - llama.cpp server (http://localhost:8080/v1)
    - Any other OpenAI-compatible server
    """

    def __init__(
        self,
        base_url: str,
        model: str = "local-model",
        api_key: str = "dummy",  # Many local servers don't require real keys
        timeout: float = 300.0,  # 5 minutes for long generations
    ):
        """
        Initialize the client.

        Args:
            base_url: Base URL of the OpenAI-compatible API (e.g., http://localhost:1234/v1)
            model: Model name to use
            api_key: API key (often not required for local servers)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

        logger.info(
            "llm.openai_compatible.initialized",
            base_url=self.base_url,
            model=self.model
        )

    async def _make_request(
        self,
        endpoint: str,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Make an HTTP request to the API.

        Args:
            endpoint: API endpoint (e.g., /chat/completions)
            payload: Request payload

        Returns:
            Response JSON
        """
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()

    async def _stream_request(
        self,
        endpoint: str,
        payload: Dict[str, Any]
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Make a streaming HTTP request to the API.

        Args:
            endpoint: API endpoint
            payload: Request payload

        Yields:
            Streamed response chunks
        """
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload["stream"] = True

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]  # Remove "data: " prefix
                        if data == "[DONE]":
                            break
                        import json
                        yield json.loads(data)

    async def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs
    ) -> str:
        """
        Complete a prompt.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters

        Returns:
            Generated text
        """
        messages: List[Dict[str, str]] = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs
        }

        logger.debug(
            "llm.openai_compatible.complete.started",
            model=self.model,
            prompt_length=len(prompt),
            max_tokens=max_tokens
        )

        try:
            response = await self._make_request("/chat/completions", payload)
            content = response["choices"][0]["message"]["content"]

            logger.info(
                "llm.openai_compatible.complete.success",
                model=self.model,
                response_length=len(content)
            )

            return content

        except httpx.HTTPError as e:
            logger.error(
                "llm.openai_compatible.complete.failed",
                error=str(e),
                model=self.model
            )
            raise

    async def stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs
    ) -> AsyncIterator[str]:
        """
        Stream a completion.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters

        Yields:
            Generated text chunks
        """
        messages: List[Dict[str, str]] = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs
        }

        logger.debug(
            "llm.openai_compatible.stream.started",
            model=self.model,
            prompt_length=len(prompt)
        )

        try:
            async for chunk in self._stream_request("/chat/completions", payload):
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    yield content

            logger.info("llm.openai_compatible.stream.completed")

        except httpx.HTTPError as e:
            logger.error(
                "llm.openai_compatible.stream.failed",
                error=str(e)
            )
            raise

    async def chat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs
    ) -> str:
        """
        Multi-turn chat completion.

        Args:
            messages: List of chat messages
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters

        Returns:
            Generated response
        """
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs
        }

        response = await self._make_request("/chat/completions", payload)
        return response["choices"][0]["message"]["content"]

    async def health_check(self) -> bool:
        """
        Check if the API is available.

        Returns:
            True if healthy, False otherwise
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Try to get models list (most OpenAI-compatible servers support this)
                response = await client.get(f"{self.base_url}/models")
                return response.status_code == 200
        except Exception as e:
            logger.warning(
                "llm.openai_compatible.health_check.failed",
                error=str(e),
                base_url=self.base_url
            )
            return False

    async def list_models(self) -> List[str]:
        """
        List available models.

        Returns:
            List of model names
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/models")
                response.raise_for_status()
                data = response.json()
                return [m["id"] for m in data.get("data", [])]
        except Exception as e:
            logger.warning(
                "llm.openai_compatible.list_models.failed",
                error=str(e)
            )
            return []
