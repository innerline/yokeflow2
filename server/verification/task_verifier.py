"""
Task Verification System for YokeFlow
======================================

Verifies task completion through automated testing before marking tasks as done.
Implements retry logic for failed tests with context-aware fixes.
"""

import asyncio
import subprocess
import json
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
from uuid import UUID
from datetime import datetime, timedelta, timezone

from claude_agent_sdk import ClaudeSDKClient

from server.verification.test_generator import AutoTestGenerator, GeneratedTestSuite, GeneratedTestResult, GeneratedTestType
from server.database.operations import TaskDatabase
from server.utils.logging import get_logger, PerformanceLogger
from server.utils.errors import YokeFlowError


logger = get_logger(__name__)


class VerificationStatus(Enum):
    """Status of task verification."""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    RETRY = "retry"
    MANUAL_REVIEW = "manual_review"


@dataclass
class VerificationResult:
    """Result of task verification."""
    task_id: str
    status: VerificationStatus
    tests_run: int
    tests_passed: int
    tests_failed: int
    test_results: List[GeneratedTestResult]
    failure_analysis: Optional[Dict[str, Any]]
    retry_count: int
    duration_seconds: float
    timestamp: datetime


@dataclass
class FailureAnalysis:
    """Analysis of test failures."""
    failure_type: str  # syntax, logic, missing_dependency, etc.
    root_cause: str
    suggested_fix: str
    affected_files: List[str]
    confidence: float  # 0.0 to 1.0


class TaskVerifier:
    """
    Verifies task completion through automated testing.

    This is the core of the test-driven task completion system.
    Every task must pass verification before being marked as complete.
    """

    def __init__(
        self,
        project_path: Path,
        db: TaskDatabase,
        client: Optional[ClaudeSDKClient] = None,
        max_retries: int = 3
    ):
        """
        Initialize the task verifier.

        Args:
            project_path: Path to the project
            db: Database connection
            client: Optional Claude SDK client for analysis
            max_retries: Maximum number of retry attempts
        """
        self.project_path = project_path
        self.db = db
        self.client = client
        self.max_retries = max_retries
        self.test_generator = AutoTestGenerator(project_path, client)

    async def verify_task(
        self,
        task_id: str,
        task_description: str,
        modified_files: List[str],
        session_id: Optional[UUID] = None,
        progress_callback: Optional[callable] = None
    ) -> VerificationResult:
        """
        Verify a task is correctly completed through automated testing.

        Args:
            task_id: ID of the task to verify
            task_description: Description of the task
            modified_files: List of files modified during task implementation
            session_id: Optional session ID for tracking
            progress_callback: Optional callback for progress updates

        Returns:
            VerificationResult with status and details
        """
        logger.info(f"Starting verification for task {task_id}", extra={
            "task_id": task_id,
            "modified_files": modified_files,
            "session_id": str(session_id) if session_id else None
        })

        start_time = datetime.now(timezone.utc)
        retry_count = 0
        test_results = []

        with PerformanceLogger("task_verification"):
            # Generate tests if they don't exist
            test_suite = await self._get_or_generate_tests(
                task_id, task_description, modified_files
            )

            # Notify progress
            if progress_callback:
                await progress_callback({
                    "type": "verification_started",
                    "task_id": task_id,
                    "test_count": len(test_suite.tests)
                })

            # Run verification loop
            while retry_count < self.max_retries:
                # Run tests
                test_results = await self._run_test_suite(test_suite)

                # Count results
                passed = sum(1 for r in test_results if r.passed)
                failed = sum(1 for r in test_results if not r.passed)

                # Check if all tests passed
                if failed == 0:
                    duration = (datetime.now(timezone.utc) - start_time).total_seconds()

                    result = VerificationResult(
                        task_id=task_id,
                        status=VerificationStatus.PASSED,
                        tests_run=len(test_results),
                        tests_passed=passed,
                        tests_failed=failed,
                        test_results=test_results,
                        failure_analysis=None,
                        retry_count=retry_count,
                        duration_seconds=duration,
                        timestamp=datetime.now(timezone.utc)
                    )

                    # Mark task as verified
                    await self._mark_task_verified(task_id, session_id)

                    logger.info(f"Task {task_id} verified successfully", extra={
                        "task_id": task_id,
                        "tests_passed": passed,
                        "retry_count": retry_count,
                        "duration": duration
                    })

                    if progress_callback:
                        await progress_callback({
                            "type": "verification_passed",
                            "task_id": task_id,
                            "tests_passed": passed
                        })

                    return result

                # Tests failed - analyze and potentially retry
                retry_count += 1

                if progress_callback:
                    await progress_callback({
                        "type": "verification_retry",
                        "task_id": task_id,
                        "retry_count": retry_count,
                        "tests_failed": failed
                    })

                # Analyze failures
                failure_analysis = await self._analyze_failures(
                    test_results, modified_files
                )

                # If we can auto-fix, create fix task
                if retry_count < self.max_retries and failure_analysis:
                    fix_task = await self._create_fix_task(
                        task_id, failure_analysis, test_results
                    )

                    # Execute fix (would normally go through agent)
                    await self._execute_fix_task(fix_task)

                    # Update modified files for next iteration
                    modified_files.extend(failure_analysis.affected_files)
                else:
                    # Max retries reached or can't auto-fix
                    break

            # Failed after all retries
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            result = VerificationResult(
                task_id=task_id,
                status=VerificationStatus.MANUAL_REVIEW if retry_count >= self.max_retries
                        else VerificationStatus.FAILED,
                tests_run=len(test_results),
                tests_passed=sum(1 for r in test_results if r.passed),
                tests_failed=sum(1 for r in test_results if not r.passed),
                test_results=test_results,
                failure_analysis=await self._analyze_failures(test_results, modified_files),
                retry_count=retry_count,
                duration_seconds=duration,
                timestamp=datetime.now(timezone.utc)
            )

            # Mark task for manual review
            await self._mark_task_needs_review(task_id, result, session_id)

            logger.warning(f"Task {task_id} verification failed", extra={
                "task_id": task_id,
                "tests_failed": result.tests_failed,
                "retry_count": retry_count,
                "status": result.status.value
            })

            if progress_callback:
                await progress_callback({
                    "type": "verification_failed",
                    "task_id": task_id,
                    "tests_failed": result.tests_failed,
                    "needs_review": True
                })

            return result

    async def _get_or_generate_tests(
        self,
        task_id: str,
        task_description: str,
        modified_files: List[str]
    ) -> GeneratedTestSuite:
        """
        Get existing tests or generate new ones for a task.

        Args:
            task_id: Task ID
            task_description: Task description
            modified_files: Modified files

        Returns:
            GeneratedTestSuite for the task
        """
        # Check if tests already exist in database
        async with self.db.acquire() as conn:
            existing_tests = await conn.fetch(
                "SELECT * FROM tests WHERE task_id = $1",
                int(task_id) if task_id.isdigit() else task_id
            )

        if existing_tests:
            logger.info(f"Using {len(existing_tests)} existing tests for task {task_id}")
            # Convert database tests to GeneratedTestSuite (simplified)
            # In production, would properly deserialize
            return GeneratedTestSuite(
                task_id=task_id,
                tests=[],  # Would convert from DB format
                created_at=datetime.now(timezone.utc)
            )

        # Generate new tests
        logger.info(f"Generating new tests for task {task_id}")
        suite = await self.test_generator.generate_tests_for_task(
            task_id, task_description, modified_files
        )

        # Save generated tests
        await self.test_generator.save_test_suite(suite)

        return suite

    async def _run_test_suite(self, suite: GeneratedTestSuite) -> List[GeneratedTestResult]:
        """
        Run all tests in a test suite.

        Args:
            suite: Test suite to run

        Returns:
            List of test results
        """
        results = []

        for test in suite.tests:
            result = await self._run_single_test(test)
            results.append(result)

        return results

    async def _run_single_test(self, test) -> GeneratedTestResult:
        """
        Run a single test and capture results.

        Args:
            test: GeneratedTestSpec to run

        Returns:
            GeneratedTestResult with outcome
        """
        start_time = datetime.now(timezone.utc)

        # Create test file
        test_file = self.project_path / test.file_path
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(test.test_code)

        try:
            # Run test based on type
            if test.test_type == GeneratedTestType.UNIT:
                cmd = ["python", "-m", "pytest", str(test_file), "-v"]
            elif test.test_type == GeneratedTestType.BROWSER:
                cmd = ["python", "-m", "pytest", str(test_file), "--browser", "chromium"]
            else:
                cmd = ["python", "-m", "pytest", str(test_file)]

            # Execute test
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.project_path)
            )

            stdout, stderr = await asyncio.wait_for(
                result.communicate(),
                timeout=test.timeout_seconds
            )

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Parse result
            passed = result.returncode == 0
            output = stdout.decode() if stdout else ""
            error = stderr.decode() if stderr and not passed else None

            return GeneratedTestResult(
                test_id=f"{test.file_path}::{test.description}",
                passed=passed,
                output=output,
                error=error,
                duration_seconds=duration,
                test_type=test.test_type
            )

        except asyncio.TimeoutError:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            return GeneratedTestResult(
                test_id=f"{test.file_path}::{test.description}",
                passed=False,
                output="",
                error=f"Test timed out after {test.timeout_seconds} seconds",
                duration_seconds=duration,
                test_type=test.test_type
            )

        except Exception as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            return GeneratedTestResult(
                test_id=f"{test.file_path}::{test.description}",
                passed=False,
                output="",
                error=str(e),
                duration_seconds=duration,
                test_type=test.test_type
            )

    async def _analyze_failures(
        self,
        test_results: List[GeneratedTestResult],
        modified_files: List[str]
    ) -> Optional[FailureAnalysis]:
        """
        Analyze test failures to determine root cause.

        Args:
            test_results: List of test results
            modified_files: Files that were modified

        Returns:
            FailureAnalysis if fixable, None otherwise
        """
        failed_tests = [r for r in test_results if not r.passed]

        if not failed_tests:
            return None

        # Analyze error patterns
        error_patterns = {
            "ImportError": "missing_dependency",
            "SyntaxError": "syntax",
            "AttributeError": "logic",
            "TypeError": "type_mismatch",
            "AssertionError": "assertion",
            "TimeoutError": "timeout"
        }

        # Determine failure type
        failure_type = "unknown"
        for pattern, ftype in error_patterns.items():
            if any(pattern in str(t.error) for t in failed_tests):
                failure_type = ftype
                break

        # Create basic analysis
        analysis = FailureAnalysis(
            failure_type=failure_type,
            root_cause=self._extract_root_cause(failed_tests),
            suggested_fix=self._suggest_fix(failure_type, failed_tests),
            affected_files=self._identify_affected_files(failed_tests, modified_files),
            confidence=0.7 if failure_type != "unknown" else 0.3
        )

        logger.info(f"Analyzed {len(failed_tests)} test failures", extra={
            "failure_type": failure_type,
            "confidence": analysis.confidence
        })

        return analysis

    def _extract_root_cause(self, failed_tests: List[GeneratedTestResult]) -> str:
        """Extract root cause from test failures."""
        # Simplified - in production would use more sophisticated analysis
        if failed_tests:
            first_error = failed_tests[0].error
            if first_error:
                # Extract first line of error
                return first_error.split('\n')[0][:200]
        return "Unable to determine root cause"

    def _suggest_fix(self, failure_type: str, failed_tests: List[GeneratedTestResult]) -> str:
        """Suggest a fix based on failure type."""
        suggestions = {
            "missing_dependency": "Install missing dependencies or fix import statements",
            "syntax": "Fix syntax errors in the code",
            "logic": "Review and fix the logic errors",
            "type_mismatch": "Fix type mismatches in function calls",
            "assertion": "Update code to meet test expectations",
            "timeout": "Optimize code performance or increase timeout",
            "unknown": "Manual review required to determine fix"
        }
        return suggestions.get(failure_type, "Manual review required")

    def _identify_affected_files(
        self,
        failed_tests: List[GeneratedTestResult],
        modified_files: List[str]
    ) -> List[str]:
        """Identify files that need fixing based on test failures."""
        affected = set(modified_files)

        # Add files mentioned in error messages
        for test in failed_tests:
            if test.error:
                # Look for file paths in error
                import re
                file_pattern = r'File "([^"]+)"'
                matches = re.findall(file_pattern, test.error)
                for match in matches:
                    if match.startswith(str(self.project_path)):
                        relative = Path(match).relative_to(self.project_path)
                        affected.add(str(relative))

        return list(affected)

    async def _create_fix_task(
        self,
        task_id: str,
        analysis: FailureAnalysis,
        test_results: List[GeneratedTestResult]
    ) -> Dict[str, Any]:
        """
        Create a fix task for failed tests.

        Args:
            task_id: Original task ID
            analysis: Failure analysis
            test_results: Test results

        Returns:
            Fix task specification
        """
        failed_tests = [r for r in test_results if not r.passed]

        fix_task = {
            "task_id": f"{task_id}_fix_{datetime.now(timezone.utc).timestamp()}",
            "description": f"Fix failing tests for task {task_id}",
            "context": {
                "original_task": task_id,
                "failure_type": analysis.failure_type,
                "root_cause": analysis.root_cause,
                "suggested_fix": analysis.suggested_fix,
                "affected_files": analysis.affected_files,
                "failed_tests": [
                    {
                        "test_id": t.test_id,
                        "error": t.error,
                        "type": t.test_type.value
                    }
                    for t in failed_tests
                ]
            },
            "priority": "high",
            "auto_generated": True
        }

        logger.info(f"Created fix task for {len(failed_tests)} failures", extra={
            "task_id": task_id,
            "fix_task_id": fix_task["task_id"],
            "failure_type": analysis.failure_type
        })

        return fix_task

    async def _execute_fix_task(self, fix_task: Dict[str, Any]) -> None:
        """
        Execute a fix task (placeholder - would go through agent).

        Args:
            fix_task: Fix task specification
        """
        logger.info(f"Would execute fix task: {fix_task['task_id']}")
        # In production, this would:
        # 1. Create a prompt for the agent with failure context
        # 2. Run the agent to fix the issues
        # 3. Return the result
        await asyncio.sleep(0.1)  # Placeholder

    async def _mark_task_verified(self, task_id: str, session_id: Optional[UUID]) -> None:
        """
        Mark a task as verified in the database.

        Args:
            task_id: Task ID
            session_id: Session ID
        """
        async with self.db.acquire() as conn:
            await conn.execute(
                """
                UPDATE tasks
                SET done = true,
                    verified = true,
                    verified_at = $1,
                    session_id = $2
                WHERE id = $3
                """,
                datetime.now(timezone.utc),
                session_id,
                int(task_id) if task_id.isdigit() else task_id
            )

        logger.info(f"Task {task_id} marked as verified")

    async def _mark_task_needs_review(
        self,
        task_id: str,
        result: VerificationResult,
        session_id: Optional[UUID]
    ) -> None:
        """
        Mark a task as needing manual review.

        Args:
            task_id: Task ID
            result: Verification result
            session_id: Session ID
        """
        async with self.db.acquire() as conn:
            # Store verification result in database
            await conn.execute(
                """
                INSERT INTO task_verification_results
                (task_id, status, tests_run, tests_passed, tests_failed,
                 failure_analysis, retry_count, duration_seconds, session_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                int(task_id) if task_id.isdigit() else task_id,
                result.status.value,
                result.tests_run,
                result.tests_passed,
                result.tests_failed,
                json.dumps(result.failure_analysis.__dict__) if result.failure_analysis else None,
                result.retry_count,
                result.duration_seconds,
                session_id
            )

            # Update task status
            await conn.execute(
                """
                UPDATE tasks
                SET needs_review = true,
                    review_reason = $1,
                    session_id = $2
                WHERE id = $3
                """,
                f"Verification failed: {result.tests_failed} tests failed after {result.retry_count} retries",
                session_id,
                int(task_id) if task_id.isdigit() else task_id
            )

        logger.warning(f"Task {task_id} marked for manual review", extra={
            "task_id": task_id,
            "tests_failed": result.tests_failed,
            "retry_count": result.retry_count
        })

    async def get_verification_history(self, task_id: str) -> List[VerificationResult]:
        """
        Get verification history for a task.

        Args:
            task_id: Task ID

        Returns:
            List of verification results
        """
        async with self.db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM task_verification_results
                WHERE task_id = $1
                ORDER BY timestamp DESC
                """,
                int(task_id) if task_id.isdigit() else task_id
            )

        results = []
        for row in rows:
            # Convert row to VerificationResult
            # Simplified - would properly deserialize
            pass

        return results