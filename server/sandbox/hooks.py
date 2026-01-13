"""
Sandbox Management for Claude SDK
==================================

This module manages the active sandbox instance for sessions.

NOTE: Command execution in Docker containers is handled by the MCP bash_docker tool,
NOT through hooks. The Claude SDK doesn't support overriding tool execution results
via hooks, so we use the MCP server's bash_docker tool for container commands.

The agent is instructed via prompts to use bash_docker instead of the regular Bash
tool when a Docker sandbox is active.
"""

import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)

# Global sandbox instance (set by orchestrator before running agent session)
_active_sandbox: Optional[Any] = None


def set_active_sandbox(sandbox):
    """
    Set the active sandbox for this session.

    Called by orchestrator before starting agent session.
    The sandbox manages the Docker container lifecycle, but command
    execution goes through the MCP bash_docker tool.
    """
    global _active_sandbox
    _active_sandbox = sandbox
    logger.debug(f"Active sandbox set: {type(sandbox).__name__}")


def clear_active_sandbox():
    """Clear the active sandbox after session ends."""
    global _active_sandbox
    _active_sandbox = None
    logger.debug("Active sandbox cleared")


def get_active_sandbox():
    """Get the currently active sandbox instance."""
    return _active_sandbox
