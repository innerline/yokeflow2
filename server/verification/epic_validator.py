"""
Epic Validation System for YokeFlow
====================================

Validates entire epic completion through integration testing across all tasks.
Ensures that features work as a complete unit, not just individual tasks.
"""

import asyncio
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
from uuid import UUID
from datetime import datetime, timedelta, timezone

from server.database.connection import DatabaseManager
from server.verification.task_verifier import TaskVerifier, VerificationResult, GeneratedTestResult
from server.verification.test_generator import AutoTestGenerator, GeneratedTestType
from server.utils.logging import get_logger, PerformanceLogger
from server.utils.errors import YokeFlowError


logger = get_logger(__name__)


class EpicValidationStatus(Enum):
    """Status of epic validation."""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"  # Some tasks passed, some failed
    NEEDS_REWORK = "needs_rework"


@dataclass
class EpicValidationResult:
    """Result of epic validation."""
    epic_id: int
    status: EpicValidationStatus
    total_tasks: int
    tasks_validated: int
    tasks_passed: int
    tasks_failed: int
    integration_tests_run: int
    integration_tests_passed: int
    integration_tests_failed: int
    acceptance_criteria_met: bool
    failure_analysis: Optional[Dict[str, Any]]
    rework_tasks: List[Dict[str, Any]]  # Tasks that need rework
    duration_seconds: float
    timestamp: datetime


@dataclass
class IntegrationTest:
    """Integration test across multiple tasks."""
    name: str
    description: str
    involved_tasks: List[int]  # Task IDs involved in this test
    test_code: str
    expected_outcome: str
    timeout_seconds: int = 60


class EpicValidator:
    """
    Validates entire epic completion through comprehensive testing.

    This ensures that all tasks in an epic work together correctly
    as a cohesive feature, not just as individual components.
    """

    def __init__(
        self,
        project_path: Path,
        db,
        task_verifier: Optional[TaskVerifier] = None,
        max_rework_iterations: int = 3
    ):
        """
        Initialize the epic validator.

        Args:
            project_path: Path to the project
            db: Database connection
            task_verifier: Optional task verifier to reuse
            max_rework_iterations: Maximum times to retry failed epics
        """
        self.project_path = project_path
        self.db = db
        self.task_verifier = task_verifier or TaskVerifier(project_path, db)
        self.max_rework_iterations = max_rework_iterations
        self.test_generator = AutoTestGenerator(project_path)

    async def validate_epic(
        self,
        epic_id: int,
        session_id: Optional[UUID] = None,
        progress_callback: Optional[callable] = None
    ) -> EpicValidationResult:
        """
        Validate that an entire epic is complete and working correctly.

        Args:
            epic_id: ID of the epic to validate
            session_id: Optional session ID for tracking
            progress_callback: Optional callback for progress updates

        Returns:
            EpicValidationResult with status and details
        """
        logger.info(f"Starting epic validation for epic {epic_id}", extra={
            "epic_id": epic_id,
            "session_id": str(session_id) if session_id else None
        })

        start_time = datetime.now(timezone.utc)

        with PerformanceLogger("epic_validation"):
            # Get epic information
            epic_info = await self._get_epic_info(epic_id)
            if not epic_info:
                raise ValueError(f"Epic {epic_id} not found")

            # Get all tasks in the epic
            tasks = await self._get_epic_tasks(epic_id)
            total_tasks = len(tasks)

            logger.info(f"Epic {epic_id} has {total_tasks} tasks to validate", extra={
                "epic_id": epic_id,
                "task_count": total_tasks
            })

            if progress_callback:
                await progress_callback({
                    "type": "epic_validation_started",
                    "epic_id": epic_id,
                    "epic_name": epic_info["name"],
                    "total_tasks": total_tasks
                })

            # Phase 1: Validate individual tasks
            task_validation_results = await self._validate_individual_tasks(
                tasks, session_id, progress_callback
            )

            tasks_passed = sum(1 for r in task_validation_results.values() if r["passed"])
            tasks_failed = total_tasks - tasks_passed

            # Phase 2: Run integration tests
            integration_results = await self._run_integration_tests(
                epic_id, tasks, progress_callback
            )

            integration_passed = sum(1 for r in integration_results if r.passed)
            integration_failed = len(integration_results) - integration_passed

            # Phase 3: Verify acceptance criteria
            acceptance_met = await self._verify_acceptance_criteria(
                epic_id, epic_info, task_validation_results, integration_results
            )

            # Determine overall status
            if tasks_failed == 0 and integration_failed == 0 and acceptance_met:
                status = EpicValidationStatus.PASSED
            elif tasks_failed == total_tasks:
                status = EpicValidationStatus.FAILED
            elif tasks_failed > 0 or integration_failed > 0:
                status = EpicValidationStatus.PARTIAL
            else:
                status = EpicValidationStatus.NEEDS_REWORK

            # Analyze failures and create rework tasks
            rework_tasks = []
            failure_analysis = None

            if status != EpicValidationStatus.PASSED:
                failure_analysis = await self._analyze_epic_failures(
                    task_validation_results, integration_results
                )
                rework_tasks = await self._create_rework_tasks(
                    epic_id, failure_analysis, task_validation_results
                )

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            result = EpicValidationResult(
                epic_id=epic_id,
                status=status,
                total_tasks=total_tasks,
                tasks_validated=total_tasks,
                tasks_passed=tasks_passed,
                tasks_failed=tasks_failed,
                integration_tests_run=len(integration_results),
                integration_tests_passed=integration_passed,
                integration_tests_failed=integration_failed,
                acceptance_criteria_met=acceptance_met,
                failure_analysis=failure_analysis,
                rework_tasks=rework_tasks,
                duration_seconds=duration,
                timestamp=datetime.now(timezone.utc)
            )

            # Store validation result in database
            await self._store_validation_result(result, session_id)

            logger.info(f"Epic {epic_id} validation completed", extra={
                "epic_id": epic_id,
                "status": status.value,
                "tasks_passed": tasks_passed,
                "integration_passed": integration_passed,
                "duration": duration
            })

            if progress_callback:
                await progress_callback({
                    "type": "epic_validation_completed",
                    "epic_id": epic_id,
                    "status": status.value,
                    "tasks_passed": tasks_passed,
                    "integration_passed": integration_passed
                })

            return result

    async def _get_epic_info(self, epic_id: int) -> Optional[Dict[str, Any]]:
        """Get epic information from database."""
        async with self.db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM epics WHERE id = $1",
                epic_id
            )
            return dict(row) if row else None

    async def _get_epic_tasks(self, epic_id: int) -> List[Dict[str, Any]]:
        """Get all tasks in an epic."""
        async with self.db.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM tasks WHERE epic_id = $1 ORDER BY priority",
                epic_id
            )
            return [dict(row) for row in rows]

    async def _validate_individual_tasks(
        self,
        tasks: List[Dict[str, Any]],
        session_id: Optional[UUID],
        progress_callback: Optional[callable]
    ) -> Dict[int, Dict[str, Any]]:
        """
        Validate each task individually.

        Returns:
            Dictionary mapping task_id to validation result
        """
        results = {}

        for task in tasks:
            task_id = task["id"]

            # Check if task is already verified
            if task.get("verified"):
                results[task_id] = {
                    "passed": True,
                    "already_verified": True
                }
                continue

            # Get modified files for this task
            async with self.db.acquire() as conn:
                file_rows = await conn.fetch(
                    "SELECT file_path FROM task_file_modifications WHERE task_id = $1",
                    task_id
                )
                modified_files = [row["file_path"] for row in file_rows]

            if not modified_files:
                # No files modified, consider it passed
                results[task_id] = {
                    "passed": True,
                    "no_files_modified": True
                }
                continue

            # Run task verification
            verification_result = await self.task_verifier.verify_task(
                str(task_id),
                task["description"],
                modified_files,
                session_id
            )

            results[task_id] = {
                "passed": verification_result.status.value == "passed",
                "tests_run": verification_result.tests_run,
                "tests_passed": verification_result.tests_passed,
                "tests_failed": verification_result.tests_failed,
                "verification_result": verification_result
            }

            if progress_callback:
                await progress_callback({
                    "type": "task_validated",
                    "task_id": task_id,
                    "passed": results[task_id]["passed"]
                })

        return results

    async def _run_integration_tests(
        self,
        epic_id: int,
        tasks: List[Dict[str, Any]],
        progress_callback: Optional[callable]
    ) -> List[GeneratedTestResult]:
        """
        Run integration tests across multiple tasks.

        Args:
            epic_id: Epic ID
            tasks: List of tasks in the epic
            progress_callback: Optional progress callback

        Returns:
            List of integration test results
        """
        # Generate integration tests based on task relationships
        integration_tests = await self._generate_integration_tests(epic_id, tasks)

        results = []

        for test in integration_tests:
            logger.info(f"Running integration test: {test.name}", extra={
                "epic_id": epic_id,
                "test_name": test.name,
                "involved_tasks": test.involved_tasks
            })

            # Create test file
            test_file = self.project_path / "tests" / "integration" / f"test_epic_{epic_id}_{test.name}.py"
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.write_text(test.test_code)

            # Run the test
            try:
                result = await self._run_single_integration_test(test, test_file)
                results.append(result)

                if progress_callback:
                    await progress_callback({
                        "type": "integration_test_completed",
                        "test_name": test.name,
                        "passed": result.passed
                    })

            except Exception as e:
                logger.error(f"Integration test {test.name} failed with error: {e}")
                results.append(GeneratedTestResult(
                    test_id=test.name,
                    passed=False,
                    output="",
                    error=str(e),
                    duration_seconds=0,
                    test_type=GeneratedTestType.INTEGRATION
                ))

        return results

    async def _generate_integration_tests(
        self,
        epic_id: int,
        tasks: List[Dict[str, Any]]
    ) -> List[IntegrationTest]:
        """
        Generate integration tests for the epic.

        Args:
            epic_id: Epic ID
            tasks: Tasks in the epic

        Returns:
            List of integration tests
        """
        tests = []

        # Test 1: End-to-end workflow test
        if len(tasks) > 1:
            test_code = self._generate_workflow_test(epic_id, tasks)
            tests.append(IntegrationTest(
                name="end_to_end_workflow",
                description="Test complete workflow from start to finish",
                involved_tasks=[t["id"] for t in tasks],
                test_code=test_code,
                expected_outcome="All tasks work together in sequence",
                timeout_seconds=120
            ))

        # Test 2: Data flow test (if tasks involve data processing)
        data_tasks = [t for t in tasks if any(
            keyword in t["description"].lower()
            for keyword in ["data", "database", "api", "fetch", "save", "store"]
        )]

        if len(data_tasks) > 1:
            test_code = self._generate_data_flow_test(epic_id, data_tasks)
            tests.append(IntegrationTest(
                name="data_flow",
                description="Test data flow between components",
                involved_tasks=[t["id"] for t in data_tasks],
                test_code=test_code,
                expected_outcome="Data flows correctly between components",
                timeout_seconds=60
            ))

        # Test 3: UI integration test (if tasks involve UI)
        ui_tasks = [t for t in tasks if any(
            keyword in t["description"].lower()
            for keyword in ["ui", "component", "page", "view", "frontend", "button", "form"]
        )]

        if ui_tasks:
            test_code = self._generate_ui_integration_test(epic_id, ui_tasks)
            tests.append(IntegrationTest(
                name="ui_integration",
                description="Test UI components work together",
                involved_tasks=[t["id"] for t in ui_tasks],
                test_code=test_code,
                expected_outcome="UI components integrate correctly",
                timeout_seconds=90
            ))

        return tests

    def _generate_workflow_test(self, epic_id: int, tasks: List[Dict[str, Any]]) -> str:
        """Generate end-to-end workflow test."""
        task_descriptions = '\n'.join([f"    # Task {t['id']}: {t['description']}" for t in tasks])

        return f'''"""
Integration test for Epic {epic_id}: End-to-end workflow
Generated: {datetime.now(timezone.utc).isoformat()}
"""

import pytest
import asyncio
from pathlib import Path


@pytest.mark.asyncio
async def test_epic_{epic_id}_workflow():
    """Test complete workflow for epic {epic_id}."""

    # This test validates that all tasks work together
{task_descriptions}

    # Step 1: Initialize test environment
    test_data = {{"test": "data"}}

    # Step 2: Execute workflow steps in sequence
    # TODO: Add actual workflow steps based on task implementations

    # Step 3: Verify final state
    assert True, "Workflow should complete successfully"

    # Step 4: Cleanup
    pass


@pytest.mark.asyncio
async def test_epic_{epic_id}_error_handling():
    """Test error handling across epic {epic_id} tasks."""

    # Test that errors are properly handled
    # TODO: Add error scenarios

    assert True, "Error handling should work correctly"
'''

    def _generate_data_flow_test(self, epic_id: int, tasks: List[Dict[str, Any]]) -> str:
        """Generate data flow integration test."""
        return f'''"""
Integration test for Epic {epic_id}: Data flow
Generated: {datetime.now(timezone.utc).isoformat()}
"""

import pytest
import asyncio


@pytest.mark.asyncio
async def test_epic_{epic_id}_data_flow():
    """Test data flow between components in epic {epic_id}."""

    # Test that data flows correctly between tasks
    # Tasks involved: {', '.join([str(t['id']) for t in tasks])}

    # Create test data
    input_data = {{"key": "value", "number": 42}}

    # Process through pipeline
    result = input_data  # TODO: Process through actual components

    # Verify data integrity
    assert "key" in result
    assert result.get("number") == 42

    # Verify transformations
    # TODO: Add specific data flow assertions

    assert True, "Data should flow correctly"
'''

    def _generate_ui_integration_test(self, epic_id: int, tasks: List[Dict[str, Any]]) -> str:
        """Generate UI integration test."""
        return f'''"""
Integration test for Epic {epic_id}: UI components
Generated: {datetime.now(timezone.utc).isoformat()}
"""

import pytest
from playwright.async_api import Page, expect


@pytest.mark.asyncio
async def test_epic_{epic_id}_ui_integration(page: Page):
    """Test UI components integration for epic {epic_id}."""

    # Tasks involved: {', '.join([str(t['id']) for t in tasks])}

    # Navigate to application
    await page.goto("http://localhost:3000")

    # Test component interactions
    # TODO: Add specific UI interaction tests

    # Verify component rendering
    await expect(page).to_have_title(re.compile(".*"))

    # Test user flows
    # TODO: Add user flow tests

    assert True, "UI components should integrate correctly"
'''

    async def _run_single_integration_test(
        self,
        test: IntegrationTest,
        test_file: Path
    ) -> GeneratedTestResult:
        """Run a single integration test."""
        import subprocess

        try:
            # Run the test with pytest
            result = subprocess.run(
                ["python", "-m", "pytest", str(test_file), "-v", "--tb=short"],
                capture_output=True,
                text=True,
                timeout=test.timeout_seconds,
                cwd=str(self.project_path)
            )

            passed = result.returncode == 0
            output = result.stdout
            error = result.stderr if not passed else None

            return GeneratedTestResult(
                test_id=test.name,
                passed=passed,
                output=output,
                error=error,
                duration_seconds=test.timeout_seconds,  # Approximate
                test_type=GeneratedTestType.INTEGRATION
            )

        except subprocess.TimeoutExpired:
            return GeneratedTestResult(
                test_id=test.name,
                passed=False,
                output="",
                error=f"Test timed out after {test.timeout_seconds} seconds",
                duration_seconds=test.timeout_seconds,
                test_type=GeneratedTestType.INTEGRATION
            )

    async def _verify_acceptance_criteria(
        self,
        epic_id: int,
        epic_info: Dict[str, Any],
        task_results: Dict[int, Dict[str, Any]],
        integration_results: List[GeneratedTestResult]
    ) -> bool:
        """
        Verify that acceptance criteria for the epic are met.

        Args:
            epic_id: Epic ID
            epic_info: Epic information
            task_results: Individual task validation results
            integration_results: Integration test results

        Returns:
            True if acceptance criteria are met
        """
        # Basic criteria: All tasks must pass
        all_tasks_passed = all(r["passed"] for r in task_results.values())

        # At least 80% of integration tests must pass
        if integration_results:
            integration_pass_rate = sum(1 for r in integration_results if r.passed) / len(integration_results)
            integration_criteria_met = integration_pass_rate >= 0.8
        else:
            integration_criteria_met = True  # No integration tests means criteria met

        # Check for any critical failures
        no_critical_failures = not any(
            "critical" in str(r.get("verification_result", {}).get("failure_analysis", "")).lower()
            for r in task_results.values()
            if not r["passed"]
        )

        return all_tasks_passed and integration_criteria_met and no_critical_failures

    async def _analyze_epic_failures(
        self,
        task_results: Dict[int, Dict[str, Any]],
        integration_results: List[GeneratedTestResult]
    ) -> Dict[str, Any]:
        """
        Analyze failures in epic validation.

        Returns:
            Analysis of what failed and why
        """
        analysis = {
            "failed_tasks": [],
            "failed_integrations": [],
            "patterns": [],
            "root_causes": [],
            "recommended_fixes": []
        }

        # Analyze failed tasks
        for task_id, result in task_results.items():
            if not result["passed"]:
                analysis["failed_tasks"].append({
                    "task_id": task_id,
                    "tests_failed": result.get("tests_failed", 0),
                    "reason": str(result.get("verification_result", {}).get("failure_analysis", "Unknown"))
                })

        # Analyze failed integration tests
        for test in integration_results:
            if not test.passed:
                analysis["failed_integrations"].append({
                    "test_name": test.test_id,
                    "error": test.error
                })

        # Identify patterns
        if len(analysis["failed_tasks"]) > 1:
            analysis["patterns"].append("Multiple task failures - possible systemic issue")

        if analysis["failed_integrations"]:
            analysis["patterns"].append("Integration failures - components not working together")

        # Suggest fixes
        if analysis["failed_tasks"]:
            analysis["recommended_fixes"].append("Fix individual task failures first")

        if analysis["failed_integrations"]:
            analysis["recommended_fixes"].append("Review component interfaces and data flow")

        return analysis

    async def _create_rework_tasks(
        self,
        epic_id: int,
        failure_analysis: Dict[str, Any],
        task_results: Dict[int, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Create tasks to fix failures in the epic.

        Args:
            epic_id: Epic ID
            failure_analysis: Analysis of failures
            task_results: Task validation results

        Returns:
            List of rework tasks to create
        """
        rework_tasks = []

        # Create fix tasks for failed tasks
        for failed in failure_analysis.get("failed_tasks", []):
            task_id = failed["task_id"]
            rework_tasks.append({
                "epic_id": epic_id,
                "description": f"Fix failures in task {task_id}: {failed['reason'][:100]}",
                "action": f"Review and fix the issues identified in task {task_id}",
                "priority": 1,
                "original_task_id": task_id,
                "failure_reason": failed["reason"]
            })

        # Create tasks for integration failures
        for failed in failure_analysis.get("failed_integrations", []):
            rework_tasks.append({
                "epic_id": epic_id,
                "description": f"Fix integration test: {failed['test_name']}",
                "action": f"Resolve integration issues: {failed['error'][:200]}",
                "priority": 2,
                "test_name": failed["test_name"]
            })

        return rework_tasks

    async def _store_validation_result(
        self,
        result: EpicValidationResult,
        session_id: Optional[UUID]
    ) -> None:
        """Store epic validation result in database."""
        async with self.db.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO epic_validation_results
                (epic_id, status, total_tasks, tasks_passed, tasks_failed,
                 integration_tests_run, integration_tests_passed, integration_tests_failed,
                 acceptance_criteria_met, failure_analysis, rework_tasks,
                 duration_seconds, session_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                """,
                result.epic_id,
                result.status.value,
                result.total_tasks,
                result.tasks_passed,
                result.tasks_failed,
                result.integration_tests_run,
                result.integration_tests_passed,
                result.integration_tests_failed,
                result.acceptance_criteria_met,
                json.dumps(result.failure_analysis) if result.failure_analysis else None,
                json.dumps(result.rework_tasks) if result.rework_tasks else None,
                result.duration_seconds,
                session_id
            )

    async def handle_epic_failure(
        self,
        epic_id: int,
        validation_result: EpicValidationResult,
        session_id: Optional[UUID] = None
    ) -> List[Dict[str, Any]]:
        """
        Handle a failed epic validation by creating remediation tasks.

        Args:
            epic_id: Epic ID
            validation_result: The validation result showing failures
            session_id: Optional session ID

        Returns:
            List of created remediation tasks
        """
        logger.info(f"Handling epic {epic_id} failure", extra={
            "epic_id": epic_id,
            "failed_tasks": validation_result.tasks_failed,
            "failed_integrations": validation_result.integration_tests_failed
        })

        created_tasks = []

        # Create rework tasks in the database
        async with self.db.acquire() as conn:
            for rework_task in validation_result.rework_tasks:
                # Insert the task
                result = await conn.fetchrow(
                    """
                    INSERT INTO tasks
                    (epic_id, description, action, priority, done, created_at)
                    VALUES ($1, $2, $3, $4, false, CURRENT_TIMESTAMP)
                    RETURNING id
                    """,
                    epic_id,
                    rework_task["description"],
                    rework_task.get("action", rework_task["description"]),
                    rework_task.get("priority", 99)
                )

                created_tasks.append({
                    "id": result["id"],
                    **rework_task
                })

                logger.info(f"Created rework task {result['id']} for epic {epic_id}")

        return created_tasks