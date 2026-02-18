"""
Slack Platform Adapter
======================

Adapter for Slack Bot API using Socket Mode.

Features:
- Socket Mode for secure connection (no public endpoint needed)
- Typing indicators
- Message parsing
- Thread support
"""

import asyncio
import os
from datetime import datetime
from typing import Any, Optional, Callable, Awaitable

from server.remote.adapters.base import (
    IPlatformAdapter,
    PlatformMessage,
    MessageType,
    SendResult,
)
from server.utils.logging import get_logger

logger = get_logger(__name__)


class SlackAdapter(IPlatformAdapter):
    """
    Slack Bot API adapter using Socket Mode.

    Socket Mode allows your app to communicate with Slack via WebSocket
    instead of receiving HTTP requests. This is ideal for development
    and works behind NAT/firewalls.

    Requirements:
    - Slack app with Socket Mode enabled
    - App-level token with connections:write scope
    - Bot token with chat:write, channels:history, etc.
    """

    def __init__(
        self,
        bot_token: Optional[str] = None,
        app_token: Optional[str] = None,
        message_handler: Optional[Callable[[PlatformMessage], Awaitable[None]]] = None,
    ):
        """
        Initialize the Slack adapter.

        Args:
            bot_token: Slack bot token (xoxb-...). Falls back to SLACK_BOT_TOKEN env var.
            app_token: Slack app-level token (xapp-...). Falls back to SLACK_APP_TOKEN env var.
            message_handler: Async callback for received messages
        """
        self.bot_token = bot_token or os.getenv("SLACK_BOT_TOKEN")
        self.app_token = app_token or os.getenv("SLACK_APP_TOKEN")
        self.message_handler = message_handler

        self._client = None
        self._socket_mode_client = None
        self._running = False

        if not self.bot_token or not self.app_token:
            logger.warning("remote.slack.no_tokens")

    @property
    def platform_name(self) -> str:
        return "slack"

    async def start(self) -> None:
        """Start Socket Mode connection."""
        if self._running:
            logger.warning("remote.slack.already_running")
            return

        if not self.bot_token or not self.app_token:
            raise ValueError("Slack bot_token and app_token are required")

        try:
            # Import here to allow module to load without slack-sdk
            from slack_sdk.web.async_client import AsyncWebClient
            from slack_sdk.socket_mode.aiohttp import SocketModeClient
            from slack_sdk.socket_mode.request import SocketModeRequest
            from slack_sdk.socket_mode.response import SocketModeResponse
        except ImportError:
            raise ImportError(
                "slack-sdk package not installed. "
                "Install with: pip install slack-sdk"
            )

        # Create web client for sending messages
        self._client = AsyncWebClient(token=self.bot_token)

        # Verify bot is accessible
        try:
            auth_test = await self._client.auth_test()
            logger.info(
                "remote.slack.started",
                bot_id=auth_test.get("bot_id"),
                team=auth_test.get("team")
            )
        except Exception as e:
            raise ValueError(f"Failed to verify Slack bot: {e}")

        # Create Socket Mode client
        self._socket_mode_client = SocketModeClient(
            app_token=self.app_token,
            web_client=self._client
        )

        # Register event handler
        @self._socket_mode_client.socket_mode_request_listeners.append
        async def handle_request(client: SocketModeClient, request: SocketModeRequest):
            await self._process_socket_request(client, request)

        # Connect to Slack
        await self._socket_mode_client.connect()
        self._running = True

        logger.info("remote.slack.socket_mode_connected")

    async def stop(self) -> None:
        """Stop Socket Mode connection and clean up."""
        self._running = False

        if self._socket_mode_client:
            await self._socket_mode_client.disconnect()
            self._socket_mode_client = None

        if self._client:
            self._client = None

        logger.info("remote.slack.stopped")

    async def _process_socket_request(self, client: Any, request: Any) -> None:
        """Process a Socket Mode request from Slack."""
        from slack_sdk.socket_mode.response import SocketModeResponse

        # Acknowledge the request
        response = SocketModeResponse(envelope_id=request.envelope_id)
        await client.send_socket_mode_response(response)

        # Handle events
        if request.type == "events_api":
            event = request.payload.get("event", {})
            message = self.parse_message(event)

            if message and self.message_handler:
                message.metadata["platform"] = "slack"
                try:
                    await self.message_handler(message)
                except Exception as e:
                    logger.error(
                        "remote.slack.handler_error",
                        error=str(e),
                        message_id=message.message_id,
                        exc_info=True
                    )

    def parse_message(self, raw_event: Any) -> Optional[PlatformMessage]:
        """
        Parse a Slack event into a PlatformMessage.

        Args:
            raw_event: Slack event object

        Returns:
            PlatformMessage if valid message, None otherwise
        """
        if not isinstance(raw_event, dict):
            return None

        # Only handle message events
        event_type = raw_event.get("type")
        if event_type != "message":
            return None

        # Skip bot messages and message_changed/deleted subtypes
        if raw_event.get("bot_id") or raw_event.get("subtype"):
            return None

        # Extract channel ID (conversation ID)
        channel_id = raw_event.get("channel")
        if not channel_id:
            return None

        # Extract user info
        user_id = raw_event.get("user", "")
        text = raw_event.get("text", "")

        if not text:
            return None

        # Extract timestamp
        ts = raw_event.get("ts", "")
        try:
            # Slack timestamps are Unix timestamps with microseconds
            timestamp = datetime.fromtimestamp(float(ts))
        except (ValueError, TypeError):
            timestamp = datetime.utcnow()

        # Determine message type
        message_type = MessageType.TEXT
        if text.strip().startswith("/"):
            # Note: Slack doesn't use / commands like Telegram
            # Commands are handled via slash command events
            pass

        # Get thread timestamp if replying in thread
        thread_ts = raw_event.get("thread_ts")

        return PlatformMessage(
            message_id=ts,
            conversation_id=channel_id,
            sender_id=user_id,
            sender_name=None,  # Would need users.info API call
            content=text,
            message_type=message_type,
            timestamp=timestamp,
            reply_to_id=thread_ts,
            raw_event=raw_event,
        )

    async def send_message(
        self,
        conversation_id: str,
        message: str,
        reply_to_id: Optional[str] = None,
        blocks: Optional[list] = None,
        **kwargs
    ) -> SendResult:
        """
        Send a message to a Slack channel.

        Args:
            conversation_id: Slack channel ID
            message: Text to send
            reply_to_id: Thread timestamp to reply in thread
            blocks: Slack Block Kit blocks for rich formatting
            **kwargs: Additional parameters

        Returns:
            SendResult indicating success/failure
        """
        if not self._client:
            return SendResult(success=False, error="Slack client not initialized")

        try:
            params = {
                "channel": conversation_id,
                "text": message,
            }

            if reply_to_id:
                params["thread_ts"] = reply_to_id

            if blocks:
                params["blocks"] = blocks

            # Add any additional parameters
            params.update(kwargs)

            response = await self._client.chat_postMessage(**params)

            logger.info(
                "remote.slack.message_sent",
                channel=conversation_id,
                ts=response.get("ts")
            )

            return SendResult(
                success=True,
                message_id=response.get("ts")
            )

        except Exception as e:
            logger.error(
                "remote.slack.send_failed",
                channel=conversation_id,
                error=str(e)
            )
            return SendResult(
                success=False,
                error=str(e)
            )

    async def send_typing(self, conversation_id: str) -> None:
        """
        Send a typing indicator to a Slack channel.

        Note: Slack doesn't have a true typing indicator for bots.
        This is a no-op but included for interface compatibility.
        """
        # Slack doesn't support typing indicators for bots
        pass

    async def health_check(self) -> bool:
        """
        Check if the bot is accessible.

        Returns:
            True if bot is healthy
        """
        if not self._client:
            return False

        try:
            await self._client.auth_test()
            return True
        except Exception:
            return False

    async def get_channel_info(self, channel_id: str) -> Optional[dict]:
        """
        Get information about a channel.

        Args:
            channel_id: Slack channel ID

        Returns:
            Channel info dict or None
        """
        if not self._client:
            return None

        try:
            response = await self._client.conversations_info(channel=channel_id)
            return response.get("channel")
        except Exception as e:
            logger.warning("remote.slack.channel_info_failed", error=str(e))
            return None

    async def get_user_info(self, user_id: str) -> Optional[dict]:
        """
        Get information about a user.

        Args:
            user_id: Slack user ID

        Returns:
            User info dict or None
        """
        if not self._client:
            return None

        try:
            response = await self._client.users_info(user=user_id)
            return response.get("user")
        except Exception as e:
            logger.warning("remote.slack.user_info_failed", error=str(e))
            return None
