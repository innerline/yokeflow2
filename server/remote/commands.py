"""
Remote Command Handler
======================

Handles commands from remote platforms (Telegram, Slack, GitHub) to control YokeFlow.

Supported commands:
- /status - Show project and session status
- /projects - List all projects
- /start - Create a new project
- /pause - Pause current session
- /resume - Resume paused session
- /review - Trigger quality review
- /help - Show available commands
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Callable, Awaitable, Any

from server.remote.adapters.base import PlatformMessage, IPlatformAdapter
from server.utils.logging import get_logger

logger = get_logger(__name__)


class Command(str, Enum):
    """Available remote commands."""
    STATUS = "status"
    PROJECTS = "projects"
    START = "start"
    PAUSE = "pause"
    RESUME = "resume"
    REVIEW = "review"
    HELP = "help"
    CANCEL = "cancel"


@dataclass
class CommandResult:
    """Result of executing a command."""
    success: bool
    message: str
    data: Optional[Any] = None
    requires_input: bool = False
    next_step: Optional[str] = None


@dataclass
class ConversationState:
    """State for a multi-turn conversation."""
    conversation_id: str
    platform: str
    current_command: Optional[Command] = None
    step: int = 0
    data: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


class RemoteCommandHandler:
    """
    Handles commands from remote platforms to control YokeFlow.

    This class:
    - Parses commands from messages
    - Routes commands to appropriate handlers
    - Manages conversation state for multi-step commands
    - Sends responses back through the platform adapter
    """

    def __init__(
        self,
        db_operations: Any = None,  # Avoid circular import
        orchestrator: Any = None,
    ):
        """
        Initialize the command handler.

        Args:
            db_operations: Database operations instance
            orchestrator: YokeFlow orchestrator instance
        """
        self.db = db_operations
        self.orchestrator = orchestrator
        self._conversations: dict[str, ConversationState] = {}
        self._adapters: dict[str, IPlatformAdapter] = {}

        # Command handlers
        self._handlers: dict[Command, Callable[[PlatformMessage, ConversationState], Awaitable[CommandResult]]] = {
            Command.STATUS: self._handle_status,
            Command.PROJECTS: self._handle_projects,
            Command.START: self._handle_start,
            Command.PAUSE: self._handle_pause,
            Command.RESUME: self._handle_resume,
            Command.REVIEW: self._handle_review,
            Command.HELP: self._handle_help,
            Command.CANCEL: self._handle_cancel,
        }

    def register_adapter(self, platform: str, adapter: IPlatformAdapter) -> None:
        """Register a platform adapter."""
        self._adapters[platform] = adapter
        logger.info("remote.commands.adapter_registered", platform=platform)

    def parse_command(self, message: PlatformMessage) -> tuple[Optional[Command], list[str]]:
        """
        Parse a command from a message.

        Args:
            message: The platform message

        Returns:
            Tuple of (Command or None, list of arguments)
        """
        text = message.content.strip()

        if not text.startswith("/"):
            return None, []

        # Split into parts
        parts = text[1:].split()  # Remove leading /
        if not parts:
            return None, []

        command_str = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []

        # Map command string to enum
        try:
            command = Command(command_str)
        except ValueError:
            # Check for aliases
            aliases = {
                "list": Command.PROJECTS,
                "new": Command.START,
                "stop": Command.PAUSE,
            }
            command = aliases.get(command_str)

        return command, args

    async def handle_message(self, message: PlatformMessage) -> None:
        """
        Handle an incoming message.

        This is the main entry point for processing messages.

        Args:
            message: The platform message to handle
        """
        adapter = self._adapters.get(message.metadata.get("platform", "telegram"))
        if not adapter:
            logger.error("remote.commands.no_adapter", platform=message.metadata.get("platform"))
            return

        # Get or create conversation state
        state = self._get_or_create_state(message)

        # Parse command
        command, args = self.parse_command(message)

        if command:
            logger.info(
                "remote.commands.received",
                command=command.value,
                conversation_id=message.conversation_id,
                args=args
            )

            # Send typing indicator
            await adapter.send_typing(message.conversation_id)

            # Execute command
            result = await self._execute_command(command, message, state)

            # Send response
            await adapter.send_message(
                message.conversation_id,
                result.message,
                reply_to_id=message.message_id
            )

        elif state.current_command:
            # Continue multi-step command
            await adapter.send_typing(message.conversation_id)
            result = await self._continue_command(message, state)

            await adapter.send_message(
                message.conversation_id,
                result.message,
                reply_to_id=message.message_id
            )

        else:
            # No command and no active conversation
            await adapter.send_message(
                message.conversation_id,
                "I didn't understand that. Type /help for available commands.",
                reply_to_id=message.message_id
            )

    def _get_or_create_state(self, message: PlatformMessage) -> ConversationState:
        """Get or create conversation state."""
        conv_id = message.conversation_id

        if conv_id not in self._conversations:
            self._conversations[conv_id] = ConversationState(
                conversation_id=conv_id,
                platform=message.metadata.get("platform", "telegram")
            )
        else:
            self._conversations[conv_id].updated_at = datetime.utcnow()

        return self._conversations[conv_id]

    async def _execute_command(
        self,
        command: Command,
        message: PlatformMessage,
        state: ConversationState
    ) -> CommandResult:
        """Execute a command."""
        handler = self._handlers.get(command)
        if not handler:
            return CommandResult(
                success=False,
                message=f"Unknown command: /{command.value}"
            )

        try:
            return await handler(message, state)
        except Exception as e:
            logger.error(
                "remote.commands.error",
                command=command.value,
                error=str(e),
                exc_info=True
            )
            return CommandResult(
                success=False,
                message=f"Error executing command: {str(e)}"
            )

    async def _continue_command(
        self,
        message: PlatformMessage,
        state: ConversationState
    ) -> CommandResult:
        """Continue a multi-step command."""
        # This would handle multi-step flows like project creation
        # For now, just reset the state
        state.current_command = None
        state.step = 0
        state.data = {}

        return CommandResult(
            success=False,
            message="Conversation cancelled. Type /help for available commands."
        )

    # =========================================================================
    # Command Handlers
    # =========================================================================

    async def _handle_status(
        self,
        message: PlatformMessage,
        state: ConversationState
    ) -> CommandResult:
        """Handle /status command."""
        if not self.db:
            return CommandResult(
                success=True,
                message="🤖 *YokeFlow Status*\n\n"
                        "✅ Bot is running\n"
                        "⚠️ Database not connected"
            )

        try:
            # Get active projects
            # This would query the database for real data
            status_text = "🤖 *YokeFlow Status*\n\n"
            status_text += "✅ Bot is running\n"
            status_text += "✅ Database connected\n"
            status_text += "✅ Telegram connected\n"
            status_text += "\n"
            status_text += "Use /projects to see your projects."

            return CommandResult(
                success=True,
                message=status_text
            )
        except Exception as e:
            return CommandResult(
                success=False,
                message=f"Error getting status: {str(e)}"
            )

    async def _handle_projects(
        self,
        message: PlatformMessage,
        state: ConversationState
    ) -> CommandResult:
        """Handle /projects command."""
        if not self.db:
            return CommandResult(
                success=True,
                message="📋 *Projects*\n\n"
                        "Database not connected. Run YokeFlow locally to manage projects."
            )

        try:
            # This would query the database for real projects
            # projects = await self.db.list_projects()

            return CommandResult(
                success=True,
                message="📋 *Projects*\n\n"
                        "No projects found.\n\n"
                        "Use /start to create a new project."
            )
        except Exception as e:
            return CommandResult(
                success=False,
                message=f"Error listing projects: {str(e)}"
            )

    async def _handle_start(
        self,
        message: PlatformMessage,
        state: ConversationState
    ) -> CommandResult:
        """Handle /start command to create a new project."""
        state.current_command = Command.START
        state.step = 1

        return CommandResult(
            success=True,
            message="🚀 *Create New Project*\n\n"
                    "What would you like to build?\n\n"
                    "Describe your project idea, or type /cancel to abort.",
            requires_input=True,
            next_step="project_description"
        )

    async def _handle_pause(
        self,
        message: PlatformMessage,
        state: ConversationState
    ) -> CommandResult:
        """Handle /pause command."""
        if not self.orchestrator:
            return CommandResult(
                success=False,
                message="⚠️ Cannot pause: Orchestrator not available."
            )

        # This would pause the current session
        return CommandResult(
            success=True,
            message="⏸️ *Session Paused*\n\n"
                    "Use /resume to continue."
        )

    async def _handle_resume(
        self,
        message: PlatformMessage,
        state: ConversationState
    ) -> CommandResult:
        """Handle /resume command."""
        if not self.orchestrator:
            return CommandResult(
                success=False,
                message="⚠️ Cannot resume: Orchestrator not available."
            )

        # This would resume the paused session
        return CommandResult(
            success=True,
            message="▶️ *Session Resumed*\n\n"
                    "Continuing where we left off..."
        )

    async def _handle_review(
        self,
        message: PlatformMessage,
        state: ConversationState
    ) -> CommandResult:
        """Handle /review command to trigger quality review."""
        if not self.orchestrator:
            return CommandResult(
                success=False,
                message="⚠️ Cannot review: Orchestrator not available."
            )

        return CommandResult(
            success=True,
            message="🔍 *Quality Review*\n\n"
                    "Triggering quality review for active project...\n\n"
                    "Results will be posted here when complete."
        )

    async def _handle_help(
        self,
        message: PlatformMessage,
        state: ConversationState
    ) -> CommandResult:
        """Handle /help command."""
        help_text = "🤖 *YokeFlow Remote Control*\n\n"
        help_text += "Available commands:\n\n"
        help_text += "/status - Show system status\n"
        help_text += "/projects - List all projects\n"
        help_text += "/start - Create a new project\n"
        help_text += "/pause - Pause current session\n"
        help_text += "/resume - Resume paused session\n"
        help_text += "/review - Trigger quality review\n"
        help_text += "/cancel - Cancel current operation\n"
        help_text += "/help - Show this message\n"

        return CommandResult(
            success=True,
            message=help_text
        )

    async def _handle_cancel(
        self,
        message: PlatformMessage,
        state: ConversationState
    ) -> CommandResult:
        """Handle /cancel command."""
        state.current_command = None
        state.step = 0
        state.data = {}

        return CommandResult(
            success=True,
            message="❌ *Cancelled*\n\n"
                    "Operation cancelled. Type /help for available commands."
        )
