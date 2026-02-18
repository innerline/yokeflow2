"""
Remote Control API Routes
=========================

API endpoints for remote control functionality.
Includes webhook handlers and status endpoints.
"""

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
import asyncio

from server.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/remote", tags=["remote"])


# =============================================================================
# Models
# =============================================================================

class TelegramUpdate(BaseModel):
    """Telegram update payload."""
    update_id: int
    message: Optional[dict] = None
    edited_message: Optional[dict] = None
    callback_query: Optional[dict] = None


class RemoteStatus(BaseModel):
    """Remote control status response."""
    telegram_enabled: bool
    telegram_bot_name: Optional[str] = None
    active_conversations: int


# =============================================================================
# Global instances (initialized in app.py)
# =============================================================================

_telegram_adapter = None
_command_handler = None


def init_remote_control(telegram_adapter=None, command_handler=None):
    """Initialize remote control with adapters."""
    global _telegram_adapter, _command_handler
    _telegram_adapter = telegram_adapter
    _command_handler = command_handler


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/status", response_model=RemoteStatus)
async def get_remote_status():
    """
    Get remote control status.

    Returns information about enabled platforms and active conversations.
    """
    telegram_enabled = _telegram_adapter is not None
    telegram_bot_name = None

    if telegram_enabled and _telegram_adapter:
        try:
            bot_info = await _telegram_adapter.get_me()
            if bot_info:
                telegram_bot_name = bot_info.get("username")
        except Exception as e:
            logger.warning("remote.status.telegram_check_failed", error=str(e))

    active_conversations = 0
    if _command_handler:
        active_conversations = len(_command_handler._conversations)

    return RemoteStatus(
        telegram_enabled=telegram_enabled,
        telegram_bot_name=telegram_bot_name,
        active_conversations=active_conversations
    )


@router.post("/telegram/webhook")
async def telegram_webhook(
    update: TelegramUpdate,
    background_tasks: BackgroundTasks
):
    """
    Handle Telegram webhook updates.

    Note: This is for webhook mode. If using polling (recommended for development),
    this endpoint is not used.

    Args:
        update: Telegram update payload
        background_tasks: FastAPI background tasks
    """
    if not _telegram_adapter or not _command_handler:
        raise HTTPException(status_code=503, detail="Telegram not configured")

    logger.debug(
        "remote.webhook.telegram",
        update_id=update.update_id
    )

    # Process in background
    from server.remote.adapters.base import PlatformMessage
    message = _telegram_adapter.parse_message(update.model_dump())

    if message:
        message.metadata["platform"] = "telegram"
        background_tasks.add_task(_command_handler.handle_message, message)

    return {"status": "ok"}


@router.post("/telegram/start")
async def start_telegram_polling():
    """
    Start Telegram polling.

    This starts long polling for Telegram updates.
    """
    if not _telegram_adapter:
        raise HTTPException(status_code=503, detail="Telegram adapter not configured")

    try:
        await _telegram_adapter.start()
        return {"status": "started", "message": "Telegram polling started"}
    except Exception as e:
        logger.error("remote.telegram.start_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/telegram/stop")
async def stop_telegram_polling():
    """Stop Telegram polling."""
    if not _telegram_adapter:
        raise HTTPException(status_code=503, detail="Telegram adapter not configured")

    try:
        await _telegram_adapter.stop()
        return {"status": "stopped", "message": "Telegram polling stopped"}
    except Exception as e:
        logger.error("remote.telegram.stop_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/telegram/commands")
async def set_telegram_commands():
    """Set bot commands for Telegram menu."""
    if not _telegram_adapter:
        raise HTTPException(status_code=503, detail="Telegram adapter not configured")

    commands = [
        {"command": "status", "description": "Show system status"},
        {"command": "projects", "description": "List all projects"},
        {"command": "start", "description": "Create a new project"},
        {"command": "pause", "description": "Pause current session"},
        {"command": "resume", "description": "Resume paused session"},
        {"command": "review", "description": "Trigger quality review"},
        {"command": "help", "description": "Show available commands"},
    ]

    try:
        success = await _telegram_adapter.set_commands(commands)
        if success:
            return {"status": "ok", "message": "Commands set successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to set commands")
    except Exception as e:
        logger.error("remote.telegram.commands_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations")
async def list_conversations():
    """List active remote conversations."""
    if not _command_handler:
        return {"conversations": []}

    conversations = []
    for conv_id, state in _command_handler._conversations.items():
        conversations.append({
            "id": conv_id,
            "platform": state.platform,
            "current_command": state.current_command.value if state.current_command else None,
            "step": state.step,
            "updated_at": state.updated_at.isoformat()
        })

    return {"conversations": conversations}
