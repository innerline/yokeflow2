"""
Remote Control Module
=====================

Enables remote control of YokeFlow from messaging platforms (Telegram, Slack, GitHub).

This module provides:
- Platform adapters for different messaging services
- Command handling for YokeFlow operations
- Session management for remote conversations
"""

from server.remote.adapters.base import IPlatformAdapter, PlatformMessage
from server.remote.commands import RemoteCommandHandler

__all__ = [
    "IPlatformAdapter",
    "PlatformMessage",
    "RemoteCommandHandler",
]
