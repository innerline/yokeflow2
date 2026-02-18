"""
Telegram Platform Adapter
=========================

Adapter for Telegram Bot API with polling support.

Features:
- Long polling for updates
- Typing indicators
- Message parsing
- Streaming support
"""

import asyncio
import os
from datetime import datetime
from typing import Any, Optional, AsyncIterator, Callable, Awaitable

import httpx

from server.remote.adapters.base import (
    IPlatformAdapter,
    PlatformMessage,
    MessageType,
    SendResult,
)
from server.utils.logging import get_logger

logger = get_logger(__name__)


class TelegramAdapter(IPlatformAdapter):
    """
    Telegram Bot API adapter using long polling.

    This adapter connects to Telegram's Bot API and receives updates
    via long polling (not webhooks). This is simpler for development
    and works behind NAT/firewalls.
    """

    API_BASE = "https://api.telegram.org/bot"

    def __init__(
        self,
        bot_token: Optional[str] = None,
        polling_timeout: int = 30,
        polling_limit: int = 100,
        allowed_updates: Optional[list] = None,
        message_handler: Optional[Callable[[PlatformMessage], Awaitable[None]]] = None,
    ):
        """
        Initialize the Telegram adapter.

        Args:
            bot_token: Telegram bot token (from @BotFather). Falls back to TELEGRAM_BOT_TOKEN env var.
            polling_timeout: Long polling timeout in seconds
            polling_limit: Maximum number of updates per poll
            allowed_updates: List of update types to receive (None = all)
            message_handler: Async callback for received messages
        """
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.polling_timeout = polling_timeout
        self.polling_limit = polling_limit
        self.allowed_updates = allowed_updates or ["message", "edited_message"]
        self.message_handler = message_handler

        self._client: Optional[httpx.AsyncClient] = None
        self._running = False
        self._poll_task: Optional[asyncio.Task] = None
        self._last_update_id = 0

        if not self.bot_token:
            logger.warning("remote.telegram.no_token")

    @property
    def platform_name(self) -> str:
        return "telegram"

    def _get_api_url(self, method: str) -> str:
        """Get full API URL for a method."""
        return f"{self.API_BASE}{self.bot_token}/{method}"

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    async def start(self) -> None:
        """Start polling for updates."""
        if self._running:
            logger.warning("remote.telegram.already_running")
            return

        if not self.bot_token:
            raise ValueError("Telegram bot token not configured")

        # Verify bot is accessible
        me = await self._call_api("getMe")
        if not me.get("ok"):
            raise ValueError(f"Failed to verify bot: {me}")

        bot_info = me.get("result", {})
        logger.info(
            "remote.telegram.started",
            bot_username=bot_info.get("username"),
            bot_name=bot_info.get("first_name")
        )

        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        """Stop polling and clean up."""
        self._running = False

        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

        logger.info("remote.telegram.stopped")

    async def _call_api(self, method: str, params: Optional[dict] = None) -> dict:
        """
        Call a Telegram Bot API method.

        Args:
            method: API method name (e.g., 'sendMessage', 'getUpdates')
            params: Method parameters

        Returns:
            API response as dict
        """
        client = await self._get_client()
        url = self._get_api_url(method)

        try:
            response = await client.post(url, json=params or {})
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(
                "remote.telegram.api_error",
                method=method,
                error=str(e)
            )
            return {"ok": False, "error": str(e)}

    async def _poll_loop(self) -> None:
        """Long polling loop for updates."""
        logger.info("remote.telegram.polling_started")

        while self._running:
            try:
                updates = await self._get_updates()

                for update in updates:
                    await self._process_update(update)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "remote.telegram.poll_error",
                    error=str(e),
                    exc_info=True
                )
                # Wait before retrying
                await asyncio.sleep(5)

        logger.info("remote.telegram.polling_stopped")

    async def _get_updates(self) -> list:
        """Fetch updates from Telegram."""
        params = {
            "timeout": self.polling_timeout,
            "limit": self.polling_limit,
            "offset": self._last_update_id + 1,
            "allowed_updates": self.allowed_updates,
        }

        response = await self._call_api("getUpdates", params)

        if not response.get("ok"):
            return []

        updates = response.get("result", [])

        if updates:
            # Update offset to not receive these updates again
            self._last_update_id = updates[-1]["update_id"]

        return updates

    async def _process_update(self, update: dict) -> None:
        """Process a single update from Telegram."""
        message = self.parse_message(update)

        if message and self.message_handler:
            try:
                await self.message_handler(message)
            except Exception as e:
                logger.error(
                    "remote.telegram.handler_error",
                    error=str(e),
                    message_id=message.message_id,
                    exc_info=True
                )

    def parse_message(self, raw_event: Any) -> Optional[PlatformMessage]:
        """
        Parse a Telegram update into a PlatformMessage.

        Args:
            raw_event: Telegram update object

        Returns:
            PlatformMessage if valid message, None otherwise
        """
        if not isinstance(raw_event, dict):
            return None

        # Handle message or edited_message
        message_data = raw_event.get("message") or raw_event.get("edited_message")
        if not message_data:
            return None

        # Extract chat ID (conversation ID)
        chat = message_data.get("chat", {})
        chat_id = str(chat.get("id", ""))
        if not chat_id:
            return None

        # Extract sender info
        from_user = message_data.get("from", {})
        sender_id = str(from_user.get("id", ""))
        sender_name = from_user.get("first_name", "")
        if from_user.get("last_name"):
            sender_name += f" {from_user['last_name']}"

        # Extract text content
        text = message_data.get("text", "")
        if not text:
            # Handle other content types (photos, files, etc.)
            if "photo" in message_data:
                text = "[Photo]"
            elif "document" in message_data:
                text = f"[Document: {message_data['document'].get('file_name', 'unknown')}]"
            else:
                return None

        # Determine message type
        message_type = MessageType.TEXT
        if text.startswith("/"):
            message_type = MessageType.COMMAND

        return PlatformMessage(
            message_id=str(message_data.get("message_id", "")),
            conversation_id=chat_id,
            sender_id=sender_id,
            sender_name=sender_name,
            content=text,
            message_type=message_type,
            timestamp=datetime.fromtimestamp(message_data.get("date", 0)),
            reply_to_id=str(message_data.get("reply_to_message", {}).get("message_id", "")) if message_data.get("reply_to_message") else None,
            raw_event=raw_event,
        )

    async def send_message(
        self,
        conversation_id: str,
        message: str,
        reply_to_id: Optional[str] = None,
        parse_mode: str = "Markdown",
        **kwargs
    ) -> SendResult:
        """
        Send a text message to a Telegram chat.

        Args:
            conversation_id: Telegram chat ID
            message: Text to send (supports Markdown/HTML)
            reply_to_id: Message ID to reply to
            parse_mode: 'Markdown' or 'HTML' or None
            **kwargs: Additional parameters (disable_notification, etc.)

        Returns:
            SendResult indicating success/failure
        """
        params = {
            "chat_id": conversation_id,
            "text": message,
        }

        if parse_mode:
            params["parse_mode"] = parse_mode

        if reply_to_id:
            params["reply_to_message_id"] = reply_to_id

        # Add any additional parameters
        params.update(kwargs)

        response = await self._call_api("sendMessage", params)

        if response.get("ok"):
            result = response.get("result", {})
            logger.info(
                "remote.telegram.message_sent",
                chat_id=conversation_id,
                message_id=result.get("message_id")
            )
            return SendResult(
                success=True,
                message_id=str(result.get("message_id", ""))
            )
        else:
            error = response.get("description", "Unknown error")
            logger.error(
                "remote.telegram.send_failed",
                chat_id=conversation_id,
                error=error
            )
            return SendResult(
                success=False,
                error=error
            )

    async def send_typing(self, conversation_id: str) -> None:
        """
        Send a typing indicator to a Telegram chat.

        Args:
            conversation_id: Telegram chat ID
        """
        await self._call_api("sendChatAction", {
            "chat_id": conversation_id,
            "action": "typing"
        })

    async def health_check(self) -> bool:
        """
        Check if the bot is accessible.

        Returns:
            True if bot is healthy
        """
        if not self.bot_token:
            return False

        response = await self._call_api("getMe")
        return response.get("ok", False)

    async def set_commands(self, commands: list[dict]) -> bool:
        """
        Set bot commands for the menu.

        Args:
            commands: List of command dicts with 'command' and 'description'

        Returns:
            True if successful
        """
        response = await self._call_api("setMyCommands", {
            "commands": commands
        })
        return response.get("ok", False)

    async def get_me(self) -> Optional[dict]:
        """
        Get information about the bot.

        Returns:
            Bot info dict or None
        """
        response = await self._call_api("getMe")
        if response.get("ok"):
            return response.get("result")
        return None
