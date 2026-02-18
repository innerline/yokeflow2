"""
Platform Adapters
=================

Adapters for different messaging platforms (Telegram, Slack, GitHub).
"""

from server.remote.adapters.base import (
    IPlatformAdapter,
    PlatformMessage,
    MessageType,
    SendResult,
)

# Lazy imports to avoid loading dependencies unless needed
def get_telegram_adapter():
    from server.remote.adapters.telegram import TelegramAdapter
    return TelegramAdapter

def get_slack_adapter():
    from server.remote.adapters.slack import SlackAdapter
    return SlackAdapter

def get_github_adapter():
    from server.remote.adapters.github import GitHubAdapter
    return GitHubAdapter

__all__ = [
    "IPlatformAdapter",
    "PlatformMessage",
    "MessageType",
    "SendResult",
    "get_telegram_adapter",
    "get_slack_adapter",
    "get_github_adapter",
]
