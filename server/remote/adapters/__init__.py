"""
Platform Adapters
=================

Adapters for different messaging platforms (Telegram, Slack, GitHub).
"""

from server.remote.adapters.base import IPlatformAdapter, PlatformMessage

__all__ = [
    "IPlatformAdapter",
    "PlatformMessage",
]
