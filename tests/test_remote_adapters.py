"""
Tests for Remote Control Layer

Tests for platform adapters and command handling.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from server.remote.adapters.base import (
    IPlatformAdapter,
    PlatformMessage,
    MessageType,
    SendResult,
)
from server.remote.commands import (
    RemoteCommandHandler,
    Command,
    CommandResult,
    ConversationState,
)


class TestPlatformMessage:
    """Tests for PlatformMessage dataclass."""

    def test_create_text_message(self):
        """Test creating a text message."""
        msg = PlatformMessage(
            message_id="123",
            conversation_id="456",
            sender_id="789",
            content="Hello world"
        )
        assert msg.message_id == "123"
        assert msg.message_type == MessageType.TEXT
        assert msg.sender_name is None
        assert msg.reply_to_id is None

    def test_create_command_message(self):
        """Test creating a command message."""
        msg = PlatformMessage(
            message_id="123",
            conversation_id="456",
            sender_id="789",
            content="/status",
            message_type=MessageType.COMMAND
        )
        assert msg.message_type == MessageType.COMMAND

    def test_message_with_metadata(self):
        """Test message with metadata."""
        msg = PlatformMessage(
            message_id="123",
            conversation_id="456",
            sender_id="789",
            content="Test",
            metadata={"platform": "telegram"}
        )
        assert msg.metadata["platform"] == "telegram"


class TestSendResult:
    """Tests for SendResult dataclass."""

    def test_success_result(self):
        """Test successful send result."""
        result = SendResult(success=True, message_id="msg123")
        assert result.success is True
        assert result.message_id == "msg123"
        assert result.error is None

    def test_failure_result(self):
        """Test failed send result."""
        result = SendResult(success=False, error="Network error")
        assert result.success is False
        assert result.error == "Network error"


class TestConversationState:
    """Tests for ConversationState dataclass."""

    def test_create_state(self):
        """Test creating conversation state."""
        state = ConversationState(
            conversation_id="conv123",
            platform="telegram"
        )
        assert state.conversation_id == "conv123"
        assert state.platform == "telegram"
        assert state.current_command is None
        assert state.step == 0
        assert state.data == {}

    def test_state_with_command(self):
        """Test state with active command."""
        state = ConversationState(
            conversation_id="conv123",
            platform="telegram",
            current_command=Command.STATUS,
            step=1
        )
        assert state.current_command == Command.STATUS
        assert state.step == 1


class TestRemoteCommandHandler:
    """Tests for RemoteCommandHandler."""

    @pytest.fixture
    def handler(self):
        """Create a command handler instance."""
        return RemoteCommandHandler(db_operations=None, orchestrator=None)

    def test_parse_status_command(self, handler):
        """Test parsing /status command."""
        msg = PlatformMessage(
            message_id="1",
            conversation_id="2",
            sender_id="3",
            content="/status",
            message_type=MessageType.COMMAND
        )
        command, args = handler.parse_command(msg)
        assert command == Command.STATUS
        assert args == []

    def test_parse_command_with_args(self, handler):
        """Test parsing command with arguments."""
        msg = PlatformMessage(
            message_id="1",
            conversation_id="2",
            sender_id="3",
            content="/start my awesome project",
            message_type=MessageType.COMMAND
        )
        command, args = handler.parse_command(msg)
        assert command == Command.START
        assert args == ["my", "awesome", "project"]

    def test_parse_non_command(self, handler):
        """Test parsing non-command message."""
        msg = PlatformMessage(
            message_id="1",
            conversation_id="2",
            sender_id="3",
            content="Hello there!"
        )
        command, args = handler.parse_command(msg)
        assert command is None
        assert args == []

    def test_parse_alias(self, handler):
        """Test parsing command aliases."""
        msg = PlatformMessage(
            message_id="1",
            conversation_id="2",
            sender_id="3",
            content="/list",
            message_type=MessageType.COMMAND
        )
        command, args = handler.parse_command(msg)
        assert command == Command.PROJECTS  # 'list' is alias for 'projects'

    def test_get_or_create_state(self, handler):
        """Test getting or creating conversation state."""
        msg = PlatformMessage(
            message_id="1",
            conversation_id="conv123",
            sender_id="2",
            content="Test",
            metadata={"platform": "telegram"}
        )
        state = handler._get_or_create_state(msg)
        assert state.conversation_id == "conv123"
        assert state.platform == "telegram"

        # Getting again should return same state
        state2 = handler._get_or_create_state(msg)
        assert state is state2

    @pytest.mark.asyncio
    async def test_handle_status_command(self, handler):
        """Test handling /status command."""
        msg = PlatformMessage(
            message_id="1",
            conversation_id="2",
            sender_id="3",
            content="/status",
            message_type=MessageType.COMMAND
        )
        state = ConversationState(conversation_id="2", platform="telegram")
        result = await handler._handle_status(msg, state)
        assert result.success is True
        assert "YokeFlow Status" in result.message

    @pytest.mark.asyncio
    async def test_handle_help_command(self, handler):
        """Test handling /help command."""
        msg = PlatformMessage(
            message_id="1",
            conversation_id="2",
            sender_id="3",
            content="/help",
            message_type=MessageType.COMMAND
        )
        state = ConversationState(conversation_id="2", platform="telegram")
        result = await handler._handle_help(msg, state)
        assert result.success is True
        assert "/status" in result.message
        assert "/start" in result.message

    @pytest.mark.asyncio
    async def test_handle_cancel_command(self, handler):
        """Test handling /cancel command."""
        msg = PlatformMessage(
            message_id="1",
            conversation_id="2",
            sender_id="3",
            content="/cancel",
            message_type=MessageType.COMMAND
        )
        state = ConversationState(
            conversation_id="2",
            platform="telegram",
            current_command=Command.START,
            step=1,
            data={"name": "test"}
        )
        result = await handler._handle_cancel(msg, state)
        assert result.success is True
        assert state.current_command is None
        assert state.step == 0
        assert state.data == {}


class TestTelegramAdapter:
    """Tests for Telegram adapter."""

    def test_parse_message(self):
        """Test parsing Telegram message."""
        from server.remote.adapters.telegram import TelegramAdapter

        adapter = TelegramAdapter(bot_token="test_token")
        update = {
            "update_id": 123,
            "message": {
                "message_id": 456,
                "chat": {"id": 789},
                "from": {"id": 111, "first_name": "Test", "last_name": "User"},
                "text": "/status",
                "date": 1700000000
            }
        }

        msg = adapter.parse_message(update)
        assert msg is not None
        assert msg.message_id == "456"
        assert msg.conversation_id == "789"
        assert msg.sender_id == "111"
        assert msg.sender_name == "Test User"
        assert msg.content == "/status"
        assert msg.message_type == MessageType.COMMAND

    def test_parse_edited_message(self):
        """Test parsing edited Telegram message."""
        from server.remote.adapters.telegram import TelegramAdapter

        adapter = TelegramAdapter(bot_token="test_token")
        update = {
            "update_id": 123,
            "edited_message": {
                "message_id": 456,
                "chat": {"id": 789},
                "from": {"id": 111, "first_name": "Test"},
                "text": "Updated text",
                "date": 1700000000
            }
        }

        msg = adapter.parse_message(update)
        assert msg is not None
        assert msg.content == "Updated text"

    def test_parse_non_message_update(self):
        """Test parsing non-message update."""
        from server.remote.adapters.telegram import TelegramAdapter

        adapter = TelegramAdapter(bot_token="test_token")
        update = {"update_id": 123, "callback_query": {"id": "abc"}}

        msg = adapter.parse_message(update)
        assert msg is None


class TestGitHubAdapter:
    """Tests for GitHub adapter."""

    def test_verify_webhook_signature(self):
        """Test webhook signature verification."""
        from server.remote.adapters.github import GitHubAdapter

        adapter = GitHubAdapter(token="test", webhook_secret="my_secret")

        payload = b'{"test": "data"}'
        import hmac
        import hashlib
        expected_sig = "sha256=" + hmac.new(
            b"my_secret", payload, hashlib.sha256
        ).hexdigest()

        assert adapter.verify_webhook_signature(payload, expected_sig) is True
        assert adapter.verify_webhook_signature(payload, "sha256=invalid") is False

    def test_parse_issue_comment(self):
        """Test parsing issue comment event."""
        from server.remote.adapters.github import GitHubAdapter

        adapter = GitHubAdapter(token="test", webhook_secret="secret")
        event = {
            "type": "issue_comment",
            "action": "created",
            "comment": {
                "id": 123,
                "body": "/status",
                "created_at": "2024-01-01T00:00:00Z"
            },
            "issue": {"number": 42},
            "repository": {"full_name": "owner/repo"},
            "sender": {"id": 789, "login": "testuser"}
        }

        msg = adapter._parse_webhook_event("issue_comment", event)
        assert msg is not None
        assert msg.content == "/status"
        assert "owner/repo#42" in msg.conversation_id
        assert msg.sender_name == "testuser"

    def test_parse_non_command_comment(self):
        """Test parsing non-command comment."""
        from server.remote.adapters.github import GitHubAdapter

        adapter = GitHubAdapter(token="test", webhook_secret="secret")
        event = {
            "type": "issue_comment",
            "action": "created",
            "comment": {
                "id": 123,
                "body": "This is a regular comment",
                "created_at": "2024-01-01T00:00:00Z"
            },
            "issue": {"number": 42},
            "repository": {"full_name": "owner/repo"},
            "sender": {"id": 789, "login": "testuser"}
        }

        msg = adapter._parse_webhook_event("issue_comment", event)
        assert msg is None  # Non-command comments are ignored
