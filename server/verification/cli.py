"""
CLI interface for verification system.

Called by MCP server to run task verification during task completion.
This module provides a standalone entry point for the verification system
that can be invoked via subprocess from the TypeScript MCP server.

Exit codes:
    0: Verification passed (all tests passed)
    1: Verification failed (tests failed or error occurred)
    2: Configuration error (verification disabled, invalid arguments)
"""
import sys
import argparse
import asyncio
import json
from pathlib import Path
from uuid import UUID
from typing import Optional

from server.verification.task_verifier import TaskVerifier
from server.database.connection import DatabaseManager
from server.utils.config import Config
from server.utils.logging import get_logger

logger = get_logger(__name__)


async def run_verification(
    task_id: str,
    project_path: str,
    session_id: Optional[str] = None
) -> int:
    """
    Run task verification and return exit code.

    Args:
        task_id: UUID of task to verify
        project_path: Path to project directory
        session_id: Optional UUID of current session

    Returns:
        Exit code (0 = success, 1 = failure, 2 = config error)
    """
    try:
        # Load configuration
        config = Config.load_default()
        verification_config = config.verification

        # Check if verification is enabled
        if not verification_config.enabled:
            print("⚠️  Verification is disabled in configuration", file=sys.stderr)
            print("Task will be marked complete without verification", file=sys.stderr)
            return 2  # Config error - don't block task completion

        # Convert string UUIDs to UUID objects
        task_uuid = UUID(task_id)
        session_uuid = UUID(session_id) if session_id else None
        project_path_obj = Path(project_path)

        # Initialize database and verifier
        async with DatabaseManager() as db:
            verifier = TaskVerifier(
                project_path=project_path_obj,
                db=db
            )

            logger.info(
                f"Running verification for task {task_id}",
                extra={"task_id": task_id, "session_id": session_id}
            )

            # Run verification
            result = await verifier.verify_task(
                task_id=task_uuid,
                session_id=session_uuid
            )

            # Output results
            if result.status == "passed":
                print(f"✓ Task {task_id} verification PASSED")
                print(f"  Tests run: {result.tests_run}")
                print(f"  Tests passed: {result.tests_passed}")
                if result.generated_tests:
                    print(f"  Generated tests: {len(result.generated_tests)}")
                print()
                print("All tests passed! Task can be marked complete.")

                logger.info(
                    f"Verification passed for task {task_id}",
                    extra={
                        "task_id": task_id,
                        "tests_run": result.tests_run,
                        "tests_passed": result.tests_passed
                    }
                )

                return 0  # Success

            else:
                print(f"✗ Task {task_id} verification FAILED", file=sys.stderr)
                print(f"  Status: {result.status}", file=sys.stderr)
                print(f"  Tests run: {result.tests_run}", file=sys.stderr)
                print(f"  Tests passed: {result.tests_passed}", file=sys.stderr)
                print(f"  Tests failed: {result.tests_failed}", file=sys.stderr)

                if result.failure_reason:
                    print(f"  Reason: {result.failure_reason}", file=sys.stderr)

                if result.retry_count > 0:
                    print(f"  Retry attempts: {result.retry_count}", file=sys.stderr)

                print(file=sys.stderr)
                print("Task CANNOT be marked complete until tests pass.", file=sys.stderr)
                print("Please fix the issues and try again.", file=sys.stderr)

                logger.warning(
                    f"Verification failed for task {task_id}",
                    extra={
                        "task_id": task_id,
                        "status": result.status,
                        "tests_failed": result.tests_failed,
                        "failure_reason": result.failure_reason
                    }
                )

                return 1  # Verification failed

    except ValueError as e:
        print(f"✗ Invalid UUID format: {e}", file=sys.stderr)
        logger.error(f"Invalid UUID in verification CLI: {e}")
        return 2  # Config error

    except FileNotFoundError as e:
        print(f"✗ Project path not found: {e}", file=sys.stderr)
        logger.error(f"Project path not found: {e}")
        return 2  # Config error

    except Exception as e:
        print(f"✗ Verification system error: {e}", file=sys.stderr)
        logger.exception(f"Verification system error for task {task_id}")

        # Don't block task completion on verification system errors
        print(file=sys.stderr)
        print("⚠️  Verification system encountered an error.", file=sys.stderr)
        print("Task will be marked complete, but manual verification is recommended.", file=sys.stderr)
        return 2  # Config/system error - don't block


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Run YokeFlow task verification",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Verify a task
  python -m server.verification.cli --task-id UUID --project-path /path/to/project

  # Verify with session context
  python -m server.verification.cli --task-id UUID --project-path /path/to/project --session-id UUID

Exit codes:
  0 = Verification passed (all tests passed)
  1 = Verification failed (tests failed)
  2 = Configuration error (verification disabled or system error)
"""
    )

    parser.add_argument(
        '--task-id',
        required=True,
        help='UUID of the task to verify'
    )

    parser.add_argument(
        '--project-path',
        required=True,
        help='Path to the project directory'
    )

    parser.add_argument(
        '--session-id',
        required=False,
        help='UUID of the current session (optional)'
    )

    parser.add_argument(
        '--json',
        action='store_true',
        help='Output results in JSON format'
    )

    args = parser.parse_args()

    # Run verification
    exit_code = asyncio.run(run_verification(
        task_id=args.task_id,
        project_path=args.project_path,
        session_id=args.session_id
    ))

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
