"""
Task Verification Integration for YokeFlow
===========================================

Integrates automated task verification into the agent workflow.
Intercepts task completion requests and runs verification before marking tasks done.
"""

import asyncio
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from uuid import UUID
from datetime import datetime

from server.verification.task_verifier import TaskVerifier, VerificationStatus
from server.verification.test_generator import AutoTestGenerator
from server.database.operations import TaskDatabase
from server.utils.logging import get_logger
from server.utils.errors import YokeFlowError


logger = get_logger(__name__)


class VerificationIntegration:
    """
    Integrates task verification into the agent workflow.

    This module intercepts MCP tool calls for update_task_status
    and automatically runs verification before allowing tasks to be marked complete.
    """

    def __init__(
        self,
        project_path: Path,
        db: TaskDatabase,
        enabled: bool = True,
        auto_retry: bool = True,
        max_retries: int = 3
    ):
        """
        Initialize verification integration.

        Args:
            project_path: Path to the project
            db: Database connection
            enabled: Whether verification is enabled
            auto_retry: Whether to automatically retry failed tests
            max_retries: Maximum number of retry attempts
        """
        self.project_path = project_path
        self.db = db
        self.enabled = enabled
        self.auto_retry = auto_retry
        self.max_retries = max_retries
        self.verifier = None  # Lazy initialization
        self.modified_files_tracker = {}  # Track files per task

    def is_enabled(self) -> bool:
        """Check if verification is enabled."""
        return self.enabled

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable verification."""
        self.enabled = enabled
        logger.info(f"Task verification {'enabled' if enabled else 'disabled'}")

    async def intercept_tool_call(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        session_id: Optional[UUID] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Intercept MCP tool calls and run verification if needed.

        Args:
            tool_name: Name of the MCP tool being called
            tool_input: Input parameters for the tool
            session_id: Current session ID

        Returns:
            Tuple of (should_proceed, modified_response)
            - should_proceed: Whether to allow the tool call
            - modified_response: Optional modified response to return instead
        """
        # Only intercept update_task_status calls
        if tool_name != "mcp__task-manager__update_task_status":
            return True, None

        # Only intercept when marking task as done
        if not tool_input.get("done", False):
            return True, None

        # If verification is disabled, allow task completion
        if not self.enabled:
            logger.info("Task verification disabled, allowing task completion")
            return True, None

        task_id = str(tool_input.get("task_id", ""))

        logger.info(f"Intercepting task completion for verification", extra={
            "task_id": task_id,
            "session_id": str(session_id) if session_id else None
        })

        # Run verification
        try:
            verification_passed = await self.verify_before_completion(
                task_id, session_id
            )

            if verification_passed:
                logger.info(f"Task {task_id} passed verification, allowing completion")
                return True, None
            else:
                logger.warning(f"Task {task_id} failed verification, blocking completion")

                # Return a custom response explaining why task can't be marked complete
                error_response = {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"❌ Task {task_id} cannot be marked complete - verification failed.\n\n"
                                f"The automated tests for this task have failed. Please:\n"
                                f"1. Review the test failures in the verification report\n"
                                f"2. Fix the issues identified\n"
                                f"3. Re-run verification before marking the task complete\n\n"
                                f"Use 'run_task_verification' tool to see detailed results."
                            )
                        }
                    ]
                }
                return False, error_response

        except Exception as e:
            logger.error(f"Error during task verification: {e}", exc_info=True)
            # On error, be conservative and block completion
            return False, {
                "content": [
                    {
                        "type": "text",
                        "text": f"❌ Error during verification: {str(e)}"
                    }
                ]
            }

    async def verify_before_completion(
        self,
        task_id: str,
        session_id: Optional[UUID] = None
    ) -> bool:
        """
        Run verification before allowing task completion.

        Args:
            task_id: Task ID to verify
            session_id: Current session ID

        Returns:
            True if verification passed, False otherwise
        """
        # Initialize verifier if needed
        if not self.verifier:
            self.verifier = TaskVerifier(
                self.project_path,
                self.db,
                max_retries=self.max_retries if self.auto_retry else 0
            )

        # Get task details
        task_info = await self._get_task_info(task_id)
        if not task_info:
            logger.error(f"Task {task_id} not found")
            return False

        # Get modified files for this task
        modified_files = self.modified_files_tracker.get(task_id, [])

        # If no modified files tracked, try to detect them
        if not modified_files:
            modified_files = await self._detect_modified_files(task_id)

        # Run verification
        result = await self.verifier.verify_task(
            task_id,
            task_info["description"],
            modified_files,
            session_id
        )

        # Check result
        return result.status == VerificationStatus.PASSED

    async def track_file_modification(
        self,
        task_id: str,
        file_path: str
    ) -> None:
        """
        Track that a file was modified during a task.

        Args:
            task_id: Current task ID
            file_path: Path to the modified file
        """
        if task_id not in self.modified_files_tracker:
            self.modified_files_tracker[task_id] = []

        if file_path not in self.modified_files_tracker[task_id]:
            self.modified_files_tracker[task_id].append(file_path)

    async def _get_task_info(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get task information from database.

        Args:
            task_id: Task ID

        Returns:
            Task information dict or None
        """
        try:
            async with self.db.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM tasks WHERE id = $1",
                    int(task_id) if task_id.isdigit() else task_id
                )

            if row:
                return dict(row)
            return None

        except Exception as e:
            logger.error(f"Failed to get task info: {e}")
            return None

    async def _detect_modified_files(self, task_id: str) -> List[str]:
        """
        Detect files modified during a task using git.

        Args:
            task_id: Task ID

        Returns:
            List of modified file paths
        """
        try:
            # Use git to detect changes since task started
            # This is a simplified version - in production would track more precisely
            import subprocess

            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                capture_output=True,
                text=True,
                cwd=str(self.project_path)
            )

            if result.returncode == 0:
                files = result.stdout.strip().split('\n')
                files = [f for f in files if f]  # Remove empty strings
                logger.info(f"Detected {len(files)} modified files for task {task_id}")
                return files

        except Exception as e:
            logger.warning(f"Could not detect modified files: {e}")

        return []

    async def get_verification_report(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the latest verification report for a task.

        Args:
            task_id: Task ID

        Returns:
            Verification report or None
        """
        if not self.verifier:
            return None

        history = await self.verifier.get_verification_history(task_id)
        if history:
            latest = history[0]
            return {
                "task_id": task_id,
                "status": latest.status.value,
                "tests_run": latest.tests_run,
                "tests_passed": latest.tests_passed,
                "tests_failed": latest.tests_failed,
                "retry_count": latest.retry_count,
                "duration": latest.duration_seconds,
                "timestamp": latest.timestamp.isoformat(),
                "test_results": [
                    {
                        "test_id": r.test_id,
                        "passed": r.passed,
                        "error": r.error,
                        "duration": r.duration_seconds
                    }
                    for r in latest.test_results
                ]
            }
        return None

    async def cleanup_task(self, task_id: str) -> None:
        """
        Clean up tracking data for a completed task.

        Args:
            task_id: Task ID
        """
        if task_id in self.modified_files_tracker:
            del self.modified_files_tracker[task_id]


class VerificationConfig:
    """Configuration for task verification."""

    def __init__(
        self,
        enabled: bool = True,
        auto_retry: bool = True,
        max_retries: int = 3,
        test_timeout: int = 30,
        require_all_tests_pass: bool = True,
        min_test_coverage: float = 0.8
    ):
        """
        Initialize verification configuration.

        Args:
            enabled: Whether verification is enabled
            auto_retry: Whether to automatically retry failed tests
            max_retries: Maximum retry attempts
            test_timeout: Timeout for individual tests in seconds
            require_all_tests_pass: Whether all tests must pass
            min_test_coverage: Minimum required test coverage (0.0 to 1.0)
        """
        self.enabled = enabled
        self.auto_retry = auto_retry
        self.max_retries = max_retries
        self.test_timeout = test_timeout
        self.require_all_tests_pass = require_all_tests_pass
        self.min_test_coverage = min_test_coverage

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "auto_retry": self.auto_retry,
            "max_retries": self.max_retries,
            "test_timeout": self.test_timeout,
            "require_all_tests_pass": self.require_all_tests_pass,
            "min_test_coverage": self.min_test_coverage
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VerificationConfig":
        """Create from dictionary."""
        return cls(
            enabled=data.get("enabled", True),
            auto_retry=data.get("auto_retry", True),
            max_retries=data.get("max_retries", 3),
            test_timeout=data.get("test_timeout", 30),
            require_all_tests_pass=data.get("require_all_tests_pass", True),
            min_test_coverage=data.get("min_test_coverage", 0.8)
        )


# Global verification integration instance
_verification_integration: Optional[VerificationIntegration] = None


def get_verification_integration() -> Optional[VerificationIntegration]:
    """Get the global verification integration instance."""
    return _verification_integration


def set_verification_integration(integration: VerificationIntegration) -> None:
    """Set the global verification integration instance."""
    global _verification_integration
    _verification_integration = integration


async def should_verify_task(
    tool_name: str,
    tool_input: Dict[str, Any],
    session_id: Optional[UUID] = None
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Check if a task should be verified before completion.

    This is the main entry point for the verification system.

    Args:
        tool_name: MCP tool name
        tool_input: Tool input parameters
        session_id: Current session ID

    Returns:
        Tuple of (should_proceed, modified_response)
    """
    integration = get_verification_integration()
    if not integration:
        # No verification configured, allow all operations
        return True, None

    return await integration.intercept_tool_call(tool_name, tool_input, session_id)