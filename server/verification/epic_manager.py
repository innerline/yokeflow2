#!/usr/bin/env python3
"""
Epic Manager - Loop-back Mechanism for Epic Validation
========================================================

Manages the lifecycle of epic validation and creates rework tasks when needed.
Handles the loop-back mechanism to add new tasks when validation fails.
"""

import asyncio
from typing import Dict, Any, List, Optional, Tuple
from uuid import UUID
from datetime import datetime
from pathlib import Path

from server.database.connection import DatabaseManager
from server.verification.epic_validator import EpicValidator, EpicValidationResult
from server.utils.logging import get_logger
from server.utils.config import Config

logger = get_logger(__name__)


class EpicManager:
    """Manages epic lifecycle and validation loop-back mechanism."""

    def __init__(self, db, project_path: Path, config: Config):
        """Initialize the Epic Manager.

        Args:
            db: Database instance
            project_path: Path to the project
            config: Configuration instance
        """
        self.db = db
        self.project_path = project_path
        self.config = config
        self.epic_validator = EpicValidator(project_path, db)

    async def check_epic_completion(
        self,
        epic_id: int,
        session_id: Optional[UUID] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Check if an epic is ready for validation and validate if needed.

        Args:
            epic_id: Epic ID to check
            session_id: Current session ID

        Returns:
            Tuple of (should_continue, validation_result)
            - should_continue: Whether to continue with more tasks or wait
            - validation_result: Results of validation if performed
        """
        logger.info(f"Checking epic {epic_id} for completion")

        # Check if all tasks in epic are done
        tasks = await self.db.list_tasks(epic_id=epic_id)
        incomplete_tasks = [t for t in tasks if not t['done']]

        if incomplete_tasks:
            logger.info(
                f"Epic {epic_id} has {len(incomplete_tasks)} incomplete tasks",
                extra={"incomplete_count": len(incomplete_tasks)}
            )
            return True, None  # Continue with remaining tasks

        # All tasks done - check if already validated
        epic = await self.db.get_epic(epic_id)
        if epic.get('validated'):
            logger.info(f"Epic {epic_id} already validated")
            return True, None  # Move to next epic

        # Perform validation
        logger.info(f"All tasks complete for epic {epic_id}, starting validation")
        validation_result = await self.epic_validator.validate_epic(
            epic_id=epic_id,
            session_id=session_id
        )

        # Handle validation results
        if validation_result.status == "passed":
            logger.info(
                f"Epic {epic_id} validation PASSED",
                extra={
                    "tasks_verified": validation_result.tasks_verified,
                    "integration_tests_passed": validation_result.integration_tests_passed
                }
            )

            # Mark epic as validated
            await self.mark_epic_validated(
                epic_id=epic_id,
                validation_id=validation_result.validation_id,
                session_id=session_id
            )

            return True, validation_result.to_dict()

        else:
            logger.warning(
                f"Epic {epic_id} validation FAILED",
                extra={
                    "tasks_failed": validation_result.tasks_failed,
                    "integration_tests_failed": validation_result.integration_tests_failed,
                    "rework_tasks_created": validation_result.rework_tasks_created
                }
            )

            # Create rework tasks
            rework_task_ids = await self.create_rework_tasks(
                epic_id=epic_id,
                validation_result=validation_result,
                session_id=session_id
            )

            logger.info(
                f"Created {len(rework_task_ids)} rework tasks for epic {epic_id}",
                extra={"rework_task_ids": rework_task_ids}
            )

            # Continue with rework tasks
            return True, validation_result.to_dict()

    async def create_rework_tasks(
        self,
        epic_id: int,
        validation_result: EpicValidationResult,
        session_id: Optional[UUID] = None
    ) -> List[int]:
        """Create rework tasks based on validation failures.

        Args:
            epic_id: Epic ID
            validation_result: Results from epic validation
            session_id: Current session ID

        Returns:
            List of created rework task IDs
        """
        rework_task_ids = []

        if not validation_result.rework_tasks:
            logger.warning(f"No rework tasks generated for epic {epic_id}")
            return rework_task_ids

        for rework_task in validation_result.rework_tasks:
            try:
                # Create the rework task using database function
                task_id = await self.db.execute_scalar(
                    """
                    SELECT create_epic_rework_task(
                        $1, $2, $3, $4, $5, $6, $7, $8
                    )
                    """,
                    epic_id,
                    validation_result.validation_id,
                    rework_task.get('original_task_id'),
                    rework_task['description'],
                    rework_task['action'],
                    rework_task['failure_reason'],
                    rework_task['rework_type'],
                    rework_task.get('priority', 1)
                )

                rework_task_ids.append(task_id)
                logger.info(
                    f"Created rework task {task_id}",
                    extra={
                        "epic_id": epic_id,
                        "rework_type": rework_task['rework_type'],
                        "original_task_id": rework_task.get('original_task_id')
                    }
                )

            except Exception as e:
                logger.error(
                    f"Failed to create rework task: {e}",
                    extra={"rework_task": rework_task}
                )

        return rework_task_ids

    async def mark_epic_validated(
        self,
        epic_id: int,
        validation_id: UUID,
        session_id: Optional[UUID] = None
    ) -> bool:
        """Mark an epic as validated.

        Args:
            epic_id: Epic ID
            validation_id: Validation result ID
            session_id: Current session ID

        Returns:
            True if successfully marked
        """
        try:
            result = await self.db.execute_scalar(
                """
                SELECT mark_epic_validated($1, $2, $3)
                """,
                epic_id,
                validation_id,
                session_id
            )

            if result:
                logger.info(f"Epic {epic_id} marked as validated")
            else:
                logger.warning(f"Failed to mark epic {epic_id} as validated")

            return result

        except Exception as e:
            logger.error(f"Error marking epic as validated: {e}")
            return False

    async def get_next_epic_to_validate(
        self,
        project_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """Get the next epic that needs validation.

        Args:
            project_id: Project ID

        Returns:
            Epic info if found, None otherwise
        """
        try:
            result = await self.db.fetch_one(
                """
                SELECT * FROM get_next_epic_to_validate($1)
                """,
                project_id
            )

            if result:
                logger.info(
                    f"Next epic to validate: {result['epic_name']}",
                    extra={
                        "epic_id": result['epic_id'],
                        "validation_level": result['validation_level']
                    }
                )
                return dict(result)

            logger.info("No epics pending validation")
            return None

        except Exception as e:
            logger.error(f"Error getting next epic to validate: {e}")
            return None

    async def get_epic_validation_status(
        self,
        epic_id: int
    ) -> Dict[str, Any]:
        """Get current validation status for an epic.

        Args:
            epic_id: Epic ID

        Returns:
            Validation status information
        """
        try:
            result = await self.db.fetch_one(
                """
                SELECT * FROM v_epic_validation_status
                WHERE epic_id = $1
                """,
                epic_id
            )

            if result:
                return dict(result)

            return {
                "epic_id": epic_id,
                "validated": False,
                "validation_status": "not_started",
                "total_tasks": 0,
                "tasks_verified": 0
            }

        except Exception as e:
            logger.error(f"Error getting epic validation status: {e}")
            return {}

    async def get_project_validation_metrics(
        self,
        project_id: UUID
    ) -> Dict[str, Any]:
        """Get validation metrics for entire project.

        Args:
            project_id: Project ID

        Returns:
            Project validation metrics
        """
        try:
            result = await self.db.fetch_one(
                """
                SELECT * FROM v_epic_validation_metrics
                WHERE project_id = $1
                """,
                project_id
            )

            if result:
                return dict(result)

            return {
                "project_id": project_id,
                "total_epics": 0,
                "validated_epics": 0,
                "total_validations": 0,
                "passed_validations": 0,
                "failed_validations": 0
            }

        except Exception as e:
            logger.error(f"Error getting project validation metrics: {e}")
            return {}

    async def add_epic_dependency(
        self,
        epic_id: int,
        depends_on_epic_id: int,
        dependency_type: str = "functionality",
        must_validate_first: bool = True
    ) -> bool:
        """Add a dependency between epics.

        Args:
            epic_id: Epic that has the dependency
            depends_on_epic_id: Epic that must be validated first
            dependency_type: Type of dependency
            must_validate_first: Whether dependency must be validated first

        Returns:
            True if successfully added
        """
        try:
            await self.db.execute(
                """
                INSERT INTO epic_dependencies (
                    epic_id, depends_on_epic_id, dependency_type, must_validate_first
                ) VALUES ($1, $2, $3, $4)
                ON CONFLICT (epic_id, depends_on_epic_id) DO UPDATE
                SET dependency_type = $3, must_validate_first = $4
                """,
                epic_id,
                depends_on_epic_id,
                dependency_type,
                must_validate_first
            )

            logger.info(
                f"Added dependency: Epic {epic_id} depends on Epic {depends_on_epic_id}",
                extra={
                    "dependency_type": dependency_type,
                    "must_validate_first": must_validate_first
                }
            )
            return True

        except Exception as e:
            logger.error(f"Error adding epic dependency: {e}")
            return False

    async def check_circular_dependencies(
        self,
        epic_id: int
    ) -> bool:
        """Check if an epic has circular dependencies.

        Args:
            epic_id: Epic ID to check

        Returns:
            True if circular dependencies exist
        """
        try:
            result = await self.db.fetch_one(
                """
                SELECT has_circular_dependency
                FROM v_epic_validation_order
                WHERE epic_id = $1
                """,
                epic_id
            )

            if result and result['has_circular_dependency']:
                logger.warning(f"Epic {epic_id} has circular dependencies!")
                return True

            return False

        except Exception as e:
            logger.error(f"Error checking circular dependencies: {e}")
            return False

    async def should_validate_epic(
        self,
        epic_id: int
    ) -> Tuple[bool, str]:
        """Check if an epic should be validated now.

        Args:
            epic_id: Epic ID

        Returns:
            Tuple of (should_validate, reason)
        """
        # Check if all tasks are done
        tasks = await self.db.list_tasks(epic_id=epic_id)
        incomplete_tasks = [t for t in tasks if not t['done']]

        if incomplete_tasks:
            return False, f"Epic has {len(incomplete_tasks)} incomplete tasks"

        # Check if already validated
        epic = await self.db.get_epic(epic_id)
        if epic.get('validated'):
            return False, "Epic already validated"

        # Check dependencies
        deps = await self.db.fetch(
            """
            SELECT ed.depends_on_epic_id, e.name, e.validated
            FROM epic_dependencies ed
            JOIN epics e ON e.id = ed.depends_on_epic_id
            WHERE ed.epic_id = $1 AND ed.must_validate_first = true
            """,
            epic_id
        )

        unvalidated_deps = [d for d in deps if not d['validated']]
        if unvalidated_deps:
            dep_names = [d['name'] for d in unvalidated_deps]
            return False, f"Waiting for dependencies: {', '.join(dep_names)}"

        return True, "Ready for validation"

    async def cleanup_old_validation_results(
        self,
        epic_id: int,
        keep_latest: int = 5
    ) -> int:
        """Clean up old validation results for an epic.

        Args:
            epic_id: Epic ID
            keep_latest: Number of latest results to keep

        Returns:
            Number of records deleted
        """
        try:
            # Get IDs to keep
            keep_ids = await self.db.fetch(
                """
                SELECT id FROM epic_validation_results
                WHERE epic_id = $1
                ORDER BY started_at DESC
                LIMIT $2
                """,
                epic_id,
                keep_latest
            )

            keep_id_list = [r['id'] for r in keep_ids]

            if not keep_id_list:
                return 0

            # Delete old results
            deleted = await self.db.execute(
                """
                DELETE FROM epic_validation_results
                WHERE epic_id = $1 AND id != ALL($2::UUID[])
                """,
                epic_id,
                keep_id_list
            )

            if deleted:
                logger.info(f"Cleaned up {deleted} old validation results for epic {epic_id}")

            return deleted

        except Exception as e:
            logger.error(f"Error cleaning up validation results: {e}")
            return 0