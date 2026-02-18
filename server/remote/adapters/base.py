"""
Base Platform Adapter
=====================

Abstract interface for platform adapters.
All platform adapters (Telegram, Slack, GitHub) must implement this interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import AsyncIterator, Optional, Any


class MessageType(Enum):
    """Types of messages."""
    TEXT = "text"
    COMMAND = "command"
    FILE = "file"
    IMAGE = "image"


@dataclass
class PlatformMessage:
    """
    Unified message format across all platforms.

    This normalizes messages from different platforms (Telegram, Slack, GitHub)
    into a common format that YokeFlow can process.
    """
    # Core fields
    message_id: str
    conversation_id: str  # Platform-specific conversation/thread ID
    sender_id: str
    content: str
    message_type: MessageType = MessageType.TEXT

    # Optional fields
    sender_name: Optional[str] = None
    reply_to_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict = field(default_factory=dict)

    # Platform-specific raw data
    raw_event: Optional[Any] = None


@dataclass
class SendResult:
    """Result of sending a message."""
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None


class IPlatformAdapter(ABC):
    """
    Abstract interface for platform adapters.

    All platform adapters must implement this interface to work with
    YokeFlow's remote control system.
    """

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Return the platform name (e.g., 'telegram', 'slack', 'github')."""
        pass

    @abstractmethod
    async def start(self) -> None:
        """
        Start the adapter.

        This should begin listening for messages (polling or webhooks).
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the adapter and clean up resources."""
        pass

    @abstractmethod
    async def send_message(
        self,
        conversation_id: str,
        message: str,
        reply_to_id: Optional[str] = None,
        **kwargs
    ) -> SendResult:
        """
        Send a text message to a conversation.

        Args:
            conversation_id: Platform-specific conversation ID
            message: Text content to send
            reply_to_id: Optional message ID to reply to
            **kwargs: Platform-specific options

        Returns:
            SendResult indicating success/failure
        """
        pass

    @abstractmethod
    async def send_typing(self, conversation_id: str) -> None:
        """
        Send a typing indicator to show the bot is processing.

        Args:
            conversation_id: Platform-specific conversation ID
        """
        pass

    async def stream_message(
        self,
        conversation_id: str,
        stream: AsyncIterator[str],
        reply_to_id: Optional[str] = None,
        **kwargs
    ) -> SendResult:
        """
        Stream a message to a conversation.

        Default implementation accumulates the stream and sends as one message.
        Subclasses can override for real-time streaming.

        Args:
            conversation_id: Platform-specific conversation ID
            stream: Async iterator of text chunks
            reply_to_id: Optional message ID to reply to
            **kwargs: Platform-specific options

        Returns:
            SendResult indicating success/failure
        """
        chunks = []
        async for chunk in stream:
            chunks.append(chunk)

        full_message = "".join(chunks)
        return await self.send_message(conversation_id, full_message, reply_to_id, **kwargs)

    @abstractmethod
    def parse_message(self, raw_event: Any) -> Optional[PlatformMessage]:
        """
        Parse a raw platform event into a unified PlatformMessage.

        Args:
            raw_event: Platform-specific event data

        Returns:
            PlatformMessage if valid, None if not a message to process
        """
        pass

    async def health_check(self) -> bool:
        """
        Check if the adapter is healthy and can send/receive messages.

        Returns:
            True if healthy, False otherwise
        """
        return True
