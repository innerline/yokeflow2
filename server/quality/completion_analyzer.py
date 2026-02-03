"""
Completion Analyzer for Project Completion Review
Phase 7: Project Completion Review
Created: February 2, 2026

Analyzes project completion against specification and generates
comprehensive review using Claude.
"""

import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from uuid import UUID
from datetime import datetime

from server.quality.spec_parser import SpecificationParser, ParsedSpecification
from server.quality.requirement_matcher import RequirementMatcher, RequirementMatch
from server.database.operations import TaskDatabase
from server.quality.reviews import create_review_client
from server.client.prompts import load_prompt

logger = logging.getLogger(__name__)


class CompletionAnalyzer:
    """
    Analyze project completion against specification.

    Orchestrates the full completion review process:
    1. Parse specification
    2. Match requirements to implementation
    3. Calculate metrics
    4. Generate Claude-powered review
    5. Store results in database
    """

    # Scoring weights
    COVERAGE_WEIGHT = 0.60  # 60% of score from coverage
    QUALITY_WEIGHT = 0.20   # 20% from test pass rates
    EXTRA_BONUS_WEIGHT = 0.10  # 10% bonus for extra features
    PRIORITY_PENALTY_WEIGHT = 0.10  # 10% penalty for missing high-priority

    # Penalties
    MISSING_HIGH_PRIORITY_PENALTY = 15  # Points per missing high-priority req
    MISSING_MEDIUM_PRIORITY_PENALTY = 5  # Points per missing medium-priority req

    def __init__(
        self,
        use_semantic_matching: bool = True,
        claude_model: str = "claude-sonnet-4-5-20250929"
    ):
        """
        Initialize analyzer.

        Args:
            use_semantic_matching: Use Claude for requirement matching
            claude_model: Model to use for completion review
        """
        self.parser = SpecificationParser()
        self.matcher = RequirementMatcher(use_semantic_matching=use_semantic_matching)
        self.claude_model = claude_model
        self.claude_client = None  # Created on demand in generate_claude_review()

    async def analyze_completion(
        self,
        project_id: UUID,
        db: TaskDatabase
    ) -> Dict[str, Any]:
        """
        Run complete completion analysis.

        Args:
            project_id: Project UUID
            db: Database connection

        Returns:
            Completion review data ready for database storage
        """
        logger.info(f"Starting completion analysis for project {project_id}")

        # Get project data
        project = await db.get_project(project_id)
        if not project:
            raise ValueError(f"Project not found: {project_id}")

        # Parse specification
        spec_path = Path(project['spec_file_path'])
        parsed_spec = self.parser.parse_spec(spec_path)

        logger.info(
            f"Parsed specification: {len(parsed_spec.requirements)} requirements "
            f"across {len(parsed_spec.sections)} sections"
        )

        # Match requirements to implementation
        matches = await self.matcher.match_requirements(parsed_spec, project_id, db)

        logger.info(f"Matched {len(matches)} requirements to implementation")

        # Calculate metrics
        metrics = self._calculate_metrics(matches, project_id, db)

        logger.info(
            f"Metrics calculated: {metrics['coverage_percentage']:.1f}% coverage, "
            f"score={metrics['overall_score']}"
        )

        # Get epic/task data for review
        epics = await self._fetch_epics(project_id, db)
        tasks = await self._fetch_tasks(project_id, db)

        # Generate Claude review
        review_text, executive_summary = await self._generate_claude_review(
            parsed_spec,
            matches,
            metrics,
            project,
            epics,
            tasks
        )

        logger.info("Claude review generated")

        # Determine recommendation
        recommendation = self._determine_recommendation(metrics, matches)

        # Build result
        result = {
            'project_id': str(project_id),
            'spec_file_path': str(spec_path),
            'spec_hash': parsed_spec.spec_hash,
            'spec_parsed_at': datetime.utcnow().isoformat(),
            'requirements_total': metrics['requirements_total'],
            'requirements_met': metrics['requirements_met'],
            'requirements_missing': metrics['requirements_missing'],
            'requirements_extra': metrics['requirements_extra'],
            'coverage_percentage': metrics['coverage_percentage'],
            'overall_score': metrics['overall_score'],
            'recommendation': recommendation,
            'executive_summary': executive_summary,
            'review_text': review_text,
            'review_model': self.claude_model,
            'matches': matches  # For database storage
        }

        logger.info(
            f"Completion analysis finished: {recommendation.upper()} "
            f"(score={metrics['overall_score']})"
        )

        return result

    def _calculate_metrics(
        self,
        matches: List[RequirementMatch],
        project_id: UUID,
        db: TaskDatabase
    ) -> Dict[str, Any]:
        """
        Calculate completion metrics.

        Returns:
            Dict with coverage, score, and other metrics
        """
        # Count requirements by status
        status_counts = {
            'met': 0,
            'partial': 0,
            'missing': 0,
            'extra': 0
        }

        for match in matches:
            status_counts[match.status] = status_counts.get(match.status, 0) + 1

        total_reqs = status_counts['met'] + status_counts['partial'] + status_counts['missing']

        # Calculate coverage percentage
        # Count partial as 0.5 met
        coverage = (status_counts['met'] + 0.5 * status_counts['partial']) / total_reqs if total_reqs > 0 else 0.0
        coverage_percentage = round(coverage * 100, 2)

        # Calculate overall score
        score = self._calculate_score(matches, status_counts, coverage)

        return {
            'requirements_total': total_reqs,
            'requirements_met': status_counts['met'],
            'requirements_partial': status_counts['partial'],
            'requirements_missing': status_counts['missing'],
            'requirements_extra': status_counts['extra'],
            'coverage_percentage': coverage_percentage,
            'overall_score': score
        }

    def _calculate_score(
        self,
        matches: List[RequirementMatch],
        status_counts: Dict[str, int],
        coverage: float
    ) -> int:
        """
        Calculate overall completion score (1-100).

        Scoring algorithm:
        - 60% weight: Coverage percentage
        - 20% weight: Quality (epic test pass rates)
        - 10% bonus: Extra features (capped at +10)
        - 10% penalty: Missing high-priority requirements
        """
        score = 0.0

        # Base coverage score (60% weight)
        score += coverage * 100 * self.COVERAGE_WEIGHT

        # Quality bonus (20% weight) - placeholder
        # TODO: Fetch actual epic test pass rates from database
        # For now, assume 80% quality if coverage > 50%
        estimated_quality = 0.8 if coverage > 0.5 else 0.6
        score += estimated_quality * 100 * self.QUALITY_WEIGHT

        # Extra features bonus (10% weight, capped at +10 points)
        extra_bonus = min(status_counts['extra'] * 5, 10)
        score += extra_bonus

        # Penalties for missing requirements (10% weight)
        missing_high = sum(
            1 for m in matches
            if m.status == 'missing' and m.requirement.priority == 'high'
        )
        missing_medium = sum(
            1 for m in matches
            if m.status == 'missing' and m.requirement.priority == 'medium'
        )

        penalty = (
            missing_high * self.MISSING_HIGH_PRIORITY_PENALTY +
            missing_medium * self.MISSING_MEDIUM_PRIORITY_PENALTY
        )
        score -= penalty

        # Clamp to 1-100
        return max(1, min(100, int(score)))

    async def _fetch_epics(
        self,
        project_id: UUID,
        db: TaskDatabase
    ) -> List[Dict[str, Any]]:
        """Fetch all epics for project."""
        return await db.list_epics(project_id)

    async def _fetch_tasks(
        self,
        project_id: UUID,
        db: TaskDatabase
    ) -> List[Dict[str, Any]]:
        """Fetch all tasks for project."""
        # list_tasks returns all tasks for the project
        return await db.list_tasks(project_id)

    async def _generate_claude_review(
        self,
        parsed_spec: ParsedSpecification,
        matches: List[RequirementMatch],
        metrics: Dict[str, Any],
        project: Dict[str, Any],
        epics: List[Dict[str, Any]],
        tasks: List[Dict[str, Any]]
    ) -> tuple[str, str]:
        """
        Generate comprehensive review using Claude.

        Returns:
            Tuple of (full_review_text, executive_summary)
        """
        # Create Claude client for review (if not already created)
        if self.claude_client is None:
            self.claude_client = create_review_client(self.claude_model)

        # Load prompt template (load_prompt adds .md automatically)
        prompt_template = load_prompt('completion_review_prompt')

        # Build requirements table
        requirements_table = self._build_requirements_table(matches)

        # Calculate test pass rate
        all_tests_passing = self._check_all_tests_passing(epics)

        completed_tasks = sum(1 for t in tasks if t.get('status') == 'completed')

        # Fill in prompt variables
        prompt = prompt_template.format(
            spec_text=Path(project['spec_file_path']).read_text(encoding='utf-8')[:5000],  # Limit length
            project_name=project['name'],
            epic_count=len(epics),
            task_count=len(tasks),
            completed_task_count=completed_tasks,
            all_tests_passing="Yes" if all_tests_passing else "No",
            requirements_total=metrics['requirements_total'],
            requirements_met=metrics['requirements_met'],
            requirements_missing=metrics['requirements_missing'],
            requirements_partial=metrics.get('requirements_partial', 0),
            requirements_extra=metrics['requirements_extra'],
            coverage_percentage=metrics['coverage_percentage'],
            requirements_table=requirements_table
        )

        # Call Claude using SDK client
        try:
            review_text = ""
            async with self.claude_client:
                # Send review prompt
                await self.claude_client.query(prompt)

                # Collect response text (only TextBlocks, ignore ToolUseBlocks)
                async for msg in self.claude_client.receive_response():
                    msg_type = type(msg).__name__

                    # Handle AssistantMessage
                    if msg_type == "AssistantMessage" and hasattr(msg, "content"):
                        for block in msg.content:
                            block_type = type(block).__name__

                            if block_type == "TextBlock" and hasattr(block, "text"):
                                review_text += block.text

            # Extract executive summary (first section)
            exec_summary = self._extract_executive_summary(review_text)

            return review_text, exec_summary

        except Exception as e:
            logger.error(f"Failed to generate Claude review: {e}")
            # Return fallback review
            fallback = self._generate_fallback_review(metrics, matches)
            return fallback, "Review generation failed. See full report for details."

    def _build_requirements_table(
        self,
        matches: List[RequirementMatch]
    ) -> str:
        """Build a markdown table of requirements and their status."""
        # Group by section
        by_section: Dict[str, List[RequirementMatch]] = {}
        for match in matches:
            section = match.requirement.section
            if section not in by_section:
                by_section[section] = []
            by_section[section].append(match)

        # Build table
        lines = ["| Section | Requirement | Status | Confidence | Notes |"]
        lines.append("|---------|-------------|--------|------------|-------|")

        for section, section_matches in by_section.items():
            for match in section_matches:
                status_emoji = {
                    'met': '✅',
                    'partial': '⚠️',
                    'missing': '❌',
                    'extra': '➕'
                }[match.status]

                req_text = match.requirement.text[:60] + "..." if len(match.requirement.text) > 60 else match.requirement.text
                notes = match.implementation_notes[:50] + "..." if len(match.implementation_notes) > 50 else match.implementation_notes

                lines.append(
                    f"| {section} | {req_text} | {status_emoji} {match.status} | "
                    f"{match.match_confidence:.0%} | {notes} |"
                )

        return "\n".join(lines)

    def _check_all_tests_passing(self, epics: List[Dict[str, Any]]) -> bool:
        """Check if all epic tests are passing."""
        for epic in epics:
            if epic.get('status') != 'completed':
                return False
        return True

    def _extract_executive_summary(self, review_text: str) -> str:
        """Extract executive summary from Claude's review."""
        import re

        # Try to find "Executive Summary" section
        match = re.search(
            r'#+\s*Executive Summary\s*\n+(.*?)(?=\n#+|\Z)',
            review_text,
            re.DOTALL | re.IGNORECASE
        )

        if match:
            return match.group(1).strip()[:500]  # Limit length

        # Fallback: Use first paragraph
        paragraphs = review_text.split('\n\n')
        return paragraphs[0][:500] if paragraphs else "See full review for details."

    def _generate_fallback_review(
        self,
        metrics: Dict[str, Any],
        matches: List[RequirementMatch]
    ) -> str:
        """Generate a simple fallback review if Claude fails."""
        missing = [m for m in matches if m.status == 'missing']
        missing_high = [m for m in missing if m.requirement.priority == 'high']

        review = f"""# Project Completion Review

## Summary

- Coverage: {metrics['coverage_percentage']:.1f}%
- Score: {metrics['overall_score']}/100
- Requirements Met: {metrics['requirements_met']}/{metrics['requirements_total']}
- Missing: {metrics['requirements_missing']}
- Extra Features: {metrics['requirements_extra']}

## Missing Requirements

"""
        if missing_high:
            review += "**High Priority:**\n"
            for m in missing_high:
                review += f"- {m.requirement.text}\n"

        review += "\n## Recommendation\n\n"
        if metrics['coverage_percentage'] >= 90:
            review += "Project appears complete and ready for use."
        elif metrics['coverage_percentage'] >= 70:
            review += "Project is mostly complete but has some gaps."
        else:
            review += "Project has significant gaps and needs more work."

        return review

    def _determine_recommendation(
        self,
        metrics: Dict[str, Any],
        matches: List[RequirementMatch]
    ) -> str:
        """
        Determine final recommendation: complete, needs_work, or failed.

        Criteria:
        - complete: >= 90% coverage, score >= 85, no missing high-priority
        - needs_work: >= 70% coverage, score >= 70
        - failed: < 70% coverage or score < 70
        """
        coverage = metrics['coverage_percentage']
        score = metrics['overall_score']

        missing_high = sum(
            1 for m in matches
            if m.status == 'missing' and m.requirement.priority == 'high'
        )

        if coverage >= 90 and score >= 85 and missing_high == 0:
            return 'complete'
        elif coverage >= 70 and score >= 70:
            return 'needs_work'
        else:
            return 'failed'
