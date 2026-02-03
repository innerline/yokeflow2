"""
Epic Re-testing Manager (Phase 5 - Quality System)

Manages epic re-testing to catch regressions as projects evolve.

Strategy: Epic-based scheduling (not session-based)
- Trigger: After every 2nd epic completion (epic 3, 5, 7, etc.)
- Priority: Foundation epics > Dependency epics > Standard epics
- Benefits: Scales to any project size, catches regressions early

Created: February 2, 2026
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from uuid import UUID

from server.database.operations import DatabaseOperations
from server.utils.config import load_config
from server.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class EpicRetestCandidate:
    """An epic that's a candidate for re-testing."""
    epic_id: int
    epic_name: str
    priority: int
    status: str
    completed_at: Optional[datetime]
    last_retest_at: Optional[datetime]
    stability_score: Optional[float]
    selection_reason: str
    retest_priority_score: int


@dataclass
class RetestConfig:
    """Configuration for epic re-testing."""
    enabled: bool = True
    trigger_frequency: int = 2
    foundation_retest_days: int = 7
    max_retests_per_trigger: int = 2
    prioritize_foundation: bool = True
    prioritize_dependents: bool = True
    pause_on_regression: bool = False
    auto_create_rework_tasks: bool = True

    @classmethod
    def from_config_dict(cls, config: Dict[str, Any]) -> 'RetestConfig':
        """Load from configuration dictionary."""
        epic_retesting = config.get('epic_retesting', {})
        return cls(
            enabled=epic_retesting.get('enabled', True),
            trigger_frequency=epic_retesting.get('trigger_frequency', 2),
            foundation_retest_days=epic_retesting.get('foundation_retest_days', 7),
            max_retests_per_trigger=epic_retesting.get('max_retests_per_trigger', 2),
            prioritize_foundation=epic_retesting.get('prioritize_foundation', True),
            prioritize_dependents=epic_retesting.get('prioritize_dependents', True),
            pause_on_regression=epic_retesting.get('pause_on_regression', False),
            auto_create_rework_tasks=epic_retesting.get('auto_create_rework_tasks', True)
        )


class EpicRetestManager:
    """Manages epic re-testing for regression detection."""

    def __init__(self, db: DatabaseOperations, project_id: UUID):
        self.db = db
        self.project_id = project_id

        # Load configuration
        config = load_config()
        self.config = RetestConfig.from_config_dict(config)

        # Foundation epic keywords (database, auth, API, etc.)
        self.foundation_keywords = [
            'database', 'db', 'schema', 'migration',
            'auth', 'authentication', 'authorization', 'security',
            'api', 'endpoint', 'server', 'backend',
            'config', 'configuration', 'setup', 'foundation'
        ]

    async def should_trigger_retest(self, epic_id: int) -> bool:
        """
        Determine if re-testing should be triggered after completing this epic.

        Triggers after every Nth completed epic (e.g., epic 3, 5, 7, etc.)

        Args:
            epic_id: The epic that was just completed

        Returns:
            True if re-testing should be triggered
        """
        if not self.config.enabled:
            logger.debug("Epic re-testing is disabled")
            return False

        # Get count of completed epics
        completed_count = await self._get_completed_epic_count()

        # Trigger after every Nth epic
        should_trigger = completed_count % self.config.trigger_frequency == 0

        if should_trigger:
            logger.info(
                f"Re-testing triggered: {completed_count} epics completed "
                f"(trigger frequency: {self.config.trigger_frequency})"
            )

        return should_trigger

    async def select_epics_for_retest(
        self,
        triggered_by_epic_id: int
    ) -> List[EpicRetestCandidate]:
        """
        Select which epics to re-test using smart prioritization.

        Priority Tiers:
        1. Critical Foundation (database, auth, API) - if >7 days old
        2. High Dependency (shared components) - if multiple dependents
        3. Standard (random sampling) - for general coverage

        Args:
            triggered_by_epic_id: The epic that triggered re-testing

        Returns:
            List of epics to re-test, ordered by priority
        """
        candidates: List[EpicRetestCandidate] = []

        # Get all completed epics
        completed_epics = await self._get_completed_epics()

        # Get stability metrics for all epics
        stability_metrics = await self._get_stability_metrics()

        # Evaluate each epic as a candidate
        for epic in completed_epics:
            # Skip the epic that just completed (can't re-test it yet)
            if epic['id'] == triggered_by_epic_id:
                continue

            # Get stability data
            stability = stability_metrics.get(epic['id'])

            # Calculate priority score and reason
            priority_score, reason = await self._calculate_priority_score(
                epic, stability
            )

            if priority_score > 0:
                candidates.append(EpicRetestCandidate(
                    epic_id=epic['id'],
                    epic_name=epic['name'],
                    priority=epic.get('priority', 0),
                    status=epic['status'],
                    completed_at=epic.get('completed_at'),
                    last_retest_at=stability['last_retest_at'] if stability else None,
                    stability_score=stability['stability_score'] if stability else None,
                    selection_reason=reason,
                    retest_priority_score=priority_score
                ))

        # Sort by priority score (highest first)
        candidates.sort(key=lambda c: c.retest_priority_score, reverse=True)

        # Limit to max_retests_per_trigger
        selected = candidates[:self.config.max_retests_per_trigger]

        logger.info(
            f"Selected {len(selected)} epics for re-testing "
            f"(from {len(candidates)} candidates): "
            f"{[c.epic_name for c in selected]}"
        )

        return selected

    async def _calculate_priority_score(
        self,
        epic: Dict[str, Any],
        stability: Optional[Dict[str, Any]]
    ) -> tuple[int, str]:
        """
        Calculate priority score for an epic.

        Returns:
            (priority_score, selection_reason)
        """
        score = 0
        reasons = []

        # 1. Foundation epic check
        if self.config.prioritize_foundation:
            is_foundation = self._is_foundation_epic(epic['name'])

            if is_foundation:
                # Foundation epics get high priority
                if stability is None or stability['last_retest_at'] is None:
                    score += 100
                    reasons.append('foundation_never_tested')
                else:
                    # Check age
                    days_since = (datetime.now(tz=stability['last_retest_at'].tzinfo) -
                                 stability['last_retest_at']).days

                    if days_since > self.config.foundation_retest_days:
                        score += 50
                        reasons.append(f'foundation_aged_{days_since}d')
                    else:
                        score += 20
                        reasons.append('foundation_recent')

        # 2. Never tested before (high priority)
        if stability is None or stability['last_retest_at'] is None:
            score += 80
            if 'foundation_never_tested' not in reasons:
                reasons.append('never_tested')

        # 3. Low stability score (test is flaky or has regressed)
        if stability and stability['stability_score'] is not None:
            if stability['stability_score'] < 0.60:
                score += 40
                reasons.append(f'low_stability_{stability["stability_score"]:.2f}')
            elif stability['stability_score'] < 0.80:
                score += 20
                reasons.append(f'fair_stability_{stability["stability_score"]:.2f}')

        # 4. Age-based priority (stale tests)
        if stability and stability['last_retest_at']:
            days_since = (datetime.now(tz=stability['last_retest_at'].tzinfo) -
                         stability['last_retest_at']).days

            if days_since > 14:
                score += 30
                if not any('aged' in r for r in reasons):
                    reasons.append(f'aged_{days_since}d')
            elif days_since > 7:
                score += 15
                if not any('aged' in r for r in reasons):
                    reasons.append(f'aged_{days_since}d')

        # 5. Dependency priority (TODO: implement dependency tracking)
        # This would require analyzing task dependencies between epics
        # For now, we use epic priority as a proxy
        if self.config.prioritize_dependents and epic.get('priority', 0) >= 90:
            score += 10
            reasons.append('high_priority')

        # 6. Random sampling for general coverage (base score for any completed epic)
        if score == 0:
            score = 5
            reasons.append('random_sampling')

        reason = ', '.join(reasons) if reasons else 'random_sampling'
        return score, reason

    def _is_foundation_epic(self, epic_name: str) -> bool:
        """Check if an epic is a foundation epic based on name keywords."""
        epic_name_lower = epic_name.lower()
        return any(keyword in epic_name_lower for keyword in self.foundation_keywords)

    async def _get_completed_epic_count(self) -> int:
        """Get count of completed epics in the project."""
        async with self.db.acquire() as conn:
            count = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM epics
                WHERE project_id = $1 AND status = 'completed'
                """,
                self.project_id
            )
            return count or 0

    async def _get_completed_epics(self) -> List[Dict[str, Any]]:
        """Get all completed epics in the project."""
        async with self.db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, name, priority, status, completed_at, created_at
                FROM epics
                WHERE project_id = $1 AND status = 'completed'
                ORDER BY priority DESC, created_at
                """,
                self.project_id
            )
            return [dict(row) for row in rows]

    async def _get_stability_metrics(self) -> Dict[int, Dict[str, Any]]:
        """
        Get stability metrics for all epics.

        Returns:
            Dict mapping epic_id to stability data
        """
        async with self.db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    esm.epic_id,
                    esm.total_retests,
                    esm.passed_retests,
                    esm.failed_retests,
                    esm.regression_count,
                    esm.stability_score,
                    esm.last_retest_at,
                    esm.last_retest_result
                FROM epic_stability_metrics esm
                JOIN epics e ON esm.epic_id = e.id
                WHERE e.project_id = $1
                """,
                self.project_id
            )

            return {
                row['epic_id']: dict(row)
                for row in rows
            }

    async def record_retest_result(
        self,
        epic_id: int,
        triggered_by_epic_id: Optional[int],
        session_id: Optional[UUID],
        test_result: str,
        execution_time_ms: Optional[int] = None,
        error_details: Optional[str] = None,
        tests_run: int = 0,
        tests_passed: int = 0,
        tests_failed: int = 0,
        selection_reason: Optional[str] = None
    ) -> UUID:
        """
        Record an epic re-test result in the database.

        This uses the record_epic_retest() database function which:
        - Auto-detects regressions
        - Updates stability metrics
        - Calculates stability scores

        Args:
            epic_id: Epic that was re-tested
            triggered_by_epic_id: Epic that triggered the re-test
            session_id: Session that ran the re-test
            test_result: 'passed', 'failed', 'skipped', 'error'
            execution_time_ms: Test execution time
            error_details: Error message if failed
            tests_run: Number of tests executed
            tests_passed: Number of tests passed
            tests_failed: Number of tests failed
            selection_reason: Why this epic was selected for re-testing

        Returns:
            UUID of the created retest run record
        """
        # Determine if this is a regression
        is_regression = await self._is_regression(epic_id, test_result)

        async with self.db.acquire() as conn:
            retest_id = await conn.fetchval(
                """
                SELECT record_epic_retest(
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11
                )
                """,
                epic_id,
                triggered_by_epic_id,
                session_id,
                test_result,
                is_regression,
                execution_time_ms,
                error_details,
                tests_run,
                tests_passed,
                tests_failed,
                selection_reason
            )

            logger.info(
                f"Recorded epic re-test: epic_id={epic_id}, "
                f"result={test_result}, is_regression={is_regression}, "
                f"retest_id={retest_id}"
            )

            return retest_id

    async def _is_regression(self, epic_id: int, current_result: str) -> bool:
        """
        Check if the current test result is a regression.

        A regression is when:
        - Previous test passed
        - Current test failed or errored
        """
        if current_result in ('passed', 'skipped'):
            return False

        async with self.db.acquire() as conn:
            previous_result = await conn.fetchval(
                """
                SELECT test_result
                FROM epic_retest_runs
                WHERE epic_id = $1
                ORDER BY created_at DESC
                LIMIT 1
                """,
                epic_id
            )

            # It's a regression if previous was passing and now it's not
            return previous_result == 'passed' and current_result in ('failed', 'error')

    async def get_retest_history(
        self,
        epic_id: Optional[int] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get re-test history, optionally filtered by epic.

        Args:
            epic_id: Filter by specific epic (None = all epics)
            limit: Maximum number of records to return

        Returns:
            List of re-test records with epic details
        """
        async with self.db.acquire() as conn:
            if epic_id:
                query = """
                    SELECT * FROM v_epic_retest_history
                    WHERE epic_id = $1
                    ORDER BY created_at DESC
                    LIMIT $2
                """
                rows = await conn.fetch(query, epic_id, limit)
            else:
                query = """
                    SELECT * FROM v_epic_retest_history
                    ORDER BY created_at DESC
                    LIMIT $1
                """
                rows = await conn.fetch(query, limit)

            return [dict(row) for row in rows]

    async def get_stability_summary(self) -> List[Dict[str, Any]]:
        """
        Get stability summary for all epics in the project.

        Returns:
            List of epic stability metrics with ratings
        """
        async with self.db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM v_epic_stability_summary
                WHERE epic_id IN (
                    SELECT id FROM epics WHERE project_id = $1
                )
                ORDER BY priority DESC, stability_score ASC
                """,
                self.project_id
            )

            return [dict(row) for row in rows]

    async def get_regressions_by_epic(self) -> List[Dict[str, Any]]:
        """
        Get list of epics that have caused regressions.

        Shows which epics are breaking other epics when they're developed.

        Returns:
            List of epics with regression counts
        """
        async with self.db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM v_regressions_by_epic
                WHERE epic_id IN (
                    SELECT id FROM epics WHERE project_id = $1
                )
                ORDER BY regressions_caused DESC
                """,
                self.project_id
            )

            return [dict(row) for row in rows]
