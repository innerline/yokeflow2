"""
Requirement Matcher for Project Completion Review
Phase 7: Project Completion Review
Created: February 2, 2026

Matches specification requirements to implemented epics/tasks using
keyword matching and semantic analysis.
"""

import re
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from uuid import UUID

from server.quality.spec_parser import Requirement, ParsedSpecification
from server.database.operations import TaskDatabase
from server.quality.reviews import create_review_client

logger = logging.getLogger(__name__)


@dataclass
class RequirementMatch:
    """A requirement matched to epics/tasks."""
    requirement: Requirement
    matched_epic_ids: List[int] = field(default_factory=list)
    matched_task_ids: List[int] = field(default_factory=list)
    match_confidence: float = 0.0  # 0.0 to 1.0
    status: str = "missing"  # met, missing, partial, extra
    implementation_notes: str = ""


class RequirementMatcher:
    """
    Match specification requirements to implemented epics/tasks.

    Uses a hybrid approach:
    1. Keyword matching (fast, 60% confidence baseline)
    2. Semantic matching with Claude (slower, 80% confidence)
    3. Combined weighted score
    """

    # Matching thresholds
    KEYWORD_MATCH_THRESHOLD = 0.4  # Min keyword similarity to consider
    SEMANTIC_MATCH_THRESHOLD = 0.7  # Min semantic similarity for match
    COMBINED_MATCH_THRESHOLD = 0.6  # Min combined score for "met" status
    PARTIAL_MATCH_THRESHOLD = 0.4  # Min score for "partial" status

    # Weights for combined scoring
    KEYWORD_WEIGHT = 0.4
    SEMANTIC_WEIGHT = 0.6

    def __init__(self, use_semantic_matching: bool = True, claude_model: str = "claude-sonnet-4-5-20250929"):
        """
        Initialize matcher.

        Args:
            use_semantic_matching: Whether to use Claude for semantic matching
                                  (more accurate but slower and costs API calls)
            claude_model: Model to use for semantic matching
        """
        self.use_semantic_matching = use_semantic_matching
        self.claude_model = claude_model
        self.claude_client = None  # Created on demand if semantic matching is enabled

    async def match_requirements(
        self,
        parsed_spec: ParsedSpecification,
        project_id: UUID,
        db: TaskDatabase
    ) -> List[RequirementMatch]:
        """
        Match requirements to epics/tasks.

        Args:
            parsed_spec: Parsed specification with requirements
            project_id: Project UUID
            db: Database connection

        Returns:
            List of RequirementMatch objects
        """
        logger.info(
            f"Matching {len(parsed_spec.requirements)} requirements "
            f"for project {project_id}"
        )

        # Fetch all epics and tasks for project
        epics = await self._fetch_project_epics(project_id, db)
        tasks = await self._fetch_project_tasks(project_id, db)

        logger.debug(f"Loaded {len(epics)} epics and {len(tasks)} tasks")

        # Match each requirement
        matches = []
        for req in parsed_spec.requirements:
            match = await self._match_requirement(req, epics, tasks)
            matches.append(match)

            logger.debug(
                f"Matched {req.id}: {match.status} "
                f"(confidence={match.match_confidence:.2f})"
            )

        # Identify extra epics (not matched to any requirement)
        self._identify_extra_features(matches, epics, parsed_spec)

        logger.info(f"Matching complete: {len(matches)} matches created")

        return matches

    async def _fetch_project_epics(
        self,
        project_id: UUID,
        db: TaskDatabase
    ) -> List[Dict[str, Any]]:
        """Fetch all epics for a project with their tasks and tests."""
        epics_data = await db.list_epics(project_id)

        epics = []
        for epic in epics_data:
            # Get tasks for this epic
            tasks = await db.list_tasks(project_id, epic_id=epic['id'])

            # Get epic tests (integration tests with detailed requirements)
            epic_tests = await db.get_epic_tests(epic['id'])

            epics.append({
                'id': epic['id'],
                'title': epic.get('name', ''),  # epics have 'name', not 'title'
                'description': epic.get('description', ''),
                'status': epic.get('status', ''),
                'tasks': tasks,
                'task_count': len(tasks),
                'epic_tests': epic_tests  # Include epic tests for matching
            })

        return epics

    async def _fetch_project_tasks(
        self,
        project_id: UUID,
        db: TaskDatabase
    ) -> List[Dict[str, Any]]:
        """Fetch all tasks for a project with their tests."""
        # list_tasks returns all tasks for the project when no epic_id is specified
        tasks = await db.list_tasks(project_id)

        # Fetch tests for all tasks
        # Get task IDs
        task_ids = [t['id'] for t in tasks]

        if task_ids:
            # Fetch all task tests in one query
            async with db.acquire() as conn:
                tests_rows = await conn.fetch(
                    """
                    SELECT id, task_id, category, description,
                           requirements, success_criteria, test_type
                    FROM task_tests
                    WHERE task_id = ANY($1)
                    ORDER BY task_id, category, id
                    """,
                    task_ids
                )

                # Group tests by task_id
                tests_by_task = {}
                for test in tests_rows:
                    task_id = test['task_id']
                    if task_id not in tests_by_task:
                        tests_by_task[task_id] = []
                    tests_by_task[task_id].append(dict(test))

                # Add tests to tasks
                for task in tasks:
                    task['tests'] = tests_by_task.get(task['id'], [])

        return tasks

    async def _match_requirement(
        self,
        requirement: Requirement,
        epics: List[Dict[str, Any]],
        tasks: List[Dict[str, Any]]
    ) -> RequirementMatch:
        """
        Match a single requirement to epics/tasks.

        Returns:
            RequirementMatch with matched IDs and confidence score
        """
        # Perform keyword matching
        epic_keyword_scores = self._keyword_match_epics(requirement, epics)
        task_keyword_scores = self._keyword_match_tasks(requirement, tasks)

        # Get top matches from keyword matching
        top_epic_matches = self._get_top_matches(epic_keyword_scores, n=3)
        top_task_matches = self._get_top_matches(task_keyword_scores, n=5)

        # Perform semantic matching if enabled
        if self.use_semantic_matching and self.claude_client:
            semantic_scores = await self._semantic_match(
                requirement,
                [epics[i] for i, _ in top_epic_matches],
                [tasks[i] for i, _ in top_task_matches]
            )
        else:
            # Use keyword scores as fallback
            semantic_scores = {
                'epics': {i: score for i, score in top_epic_matches},
                'tasks': {i: score for i, score in top_task_matches}
            }

        # Combine scores
        final_epic_scores = self._combine_scores(
            epic_keyword_scores,
            semantic_scores['epics']
        )
        final_task_scores = self._combine_scores(
            task_keyword_scores,
            semantic_scores['tasks']
        )

        # Determine best matches
        best_epics = [
            i for i, score in final_epic_scores.items()
            if score >= self.KEYWORD_MATCH_THRESHOLD
        ]
        best_tasks = [
            i for i, score in final_task_scores.items()
            if score >= self.KEYWORD_MATCH_THRESHOLD
        ]

        # Calculate overall confidence
        max_epic_score = max(final_epic_scores.values()) if final_epic_scores else 0.0
        max_task_score = max(final_task_scores.values()) if final_task_scores else 0.0
        confidence = max(max_epic_score, max_task_score)

        # Determine status
        status = self._determine_status(confidence, best_epics, best_tasks)

        # Generate notes
        notes = self._generate_implementation_notes(
            requirement,
            [epics[i] for i in best_epics],
            [tasks[i] for i in best_tasks],
            confidence
        )

        return RequirementMatch(
            requirement=requirement,
            matched_epic_ids=[epics[i]['id'] for i in best_epics],
            matched_task_ids=[tasks[i]['id'] for i in best_tasks],
            match_confidence=round(confidence, 2),
            status=status,
            implementation_notes=notes
        )

    def _keyword_match_epics(
        self,
        requirement: Requirement,
        epics: List[Dict[str, Any]]
    ) -> Dict[int, float]:
        """
        Match requirement to epics using keyword similarity.

        Returns:
            Dict mapping epic index to similarity score (0.0-1.0)
        """
        scores = {}

        req_keywords = set(requirement.keywords)

        for i, epic in enumerate(epics):
            # Extract keywords from epic name, description, AND epic tests
            # epics have 'name' field (or 'title' if already transformed)
            epic_name = epic.get('title', epic.get('name', ''))
            epic_text = f"{epic_name} {epic.get('description', '')}"

            # Add epic test requirements and success criteria (rich detail!)
            epic_tests = epic.get('epic_tests', [])
            for test in epic_tests:
                if test.get('requirements'):
                    epic_text += f" {test['requirements']}"
                if test.get('success_criteria'):
                    epic_text += f" {test['success_criteria']}"
                if test.get('name'):
                    epic_text += f" {test['name']}"

            epic_keywords = set(self._extract_keywords(epic_text))

            # Calculate Jaccard similarity
            if req_keywords and epic_keywords:
                intersection = req_keywords & epic_keywords
                union = req_keywords | epic_keywords
                score = len(intersection) / len(union) if union else 0.0
                scores[i] = score

        return scores

    def _keyword_match_tasks(
        self,
        requirement: Requirement,
        tasks: List[Dict[str, Any]]
    ) -> Dict[int, float]:
        """Match requirement to tasks using keyword similarity."""
        scores = {}

        req_keywords = set(requirement.keywords)

        for i, task in enumerate(tasks):
            # Extract keywords from task description, action, AND task tests
            # tasks have 'description' and 'action' fields (or 'title' if already transformed)
            task_desc = task.get('title', task.get('description', ''))
            task_text = f"{task_desc} {task.get('action', '')}"

            # Add task test requirements and success criteria (rich detail!)
            task_tests = task.get('tests', [])
            for test in task_tests:
                if test.get('requirements'):
                    task_text += f" {test['requirements']}"
                if test.get('success_criteria'):
                    task_text += f" {test['success_criteria']}"
                if test.get('description'):
                    task_text += f" {test['description']}"

            task_keywords = set(self._extract_keywords(task_text))

            # Calculate Jaccard similarity
            if req_keywords and task_keywords:
                intersection = req_keywords & task_keywords
                union = req_keywords | task_keywords
                score = len(intersection) / len(union) if union else 0.0
                scores[i] = score

        return scores

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text (same logic as spec_parser)."""
        STOP_WORDS = {
            "a", "an", "the", "and", "or", "but", "in", "on", "at", "to",
            "for", "of", "with", "by", "from", "as", "is", "are", "was",
            "were", "be", "been", "being", "have", "has", "had", "do",
            "does", "did", "will", "would", "should", "could", "may",
            "might", "can", "must", "shall"
        }

        words = re.findall(r'\b\w+\b', text.lower())
        keywords = [
            word for word in words
            if word not in STOP_WORDS and len(word) > 2
        ]

        return keywords[:20]  # Limit to top 20

    def _get_top_matches(
        self,
        scores: Dict[int, float],
        n: int = 5
    ) -> List[Tuple[int, float]]:
        """Get top N matches by score."""
        sorted_scores = sorted(
            scores.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return sorted_scores[:n]

    async def _semantic_match(
        self,
        requirement: Requirement,
        epics: List[Dict[str, Any]],
        tasks: List[Dict[str, Any]]
    ) -> Dict[str, Dict[int, float]]:
        """
        Use Claude to perform semantic matching.

        Returns:
            Dict with 'epics' and 'tasks' keys, each mapping index to score
        """
        # Create Claude client if not already created
        if self.claude_client is None:
            self.claude_client = create_review_client(self.claude_model)

        # Build prompt for Claude
        prompt = self._build_semantic_match_prompt(requirement, epics, tasks)

        try:
            # Call Claude using SDK client
            content = ""
            async with self.claude_client:
                # Send semantic matching prompt
                await self.claude_client.query(prompt)

                # Collect response text
                async for msg in self.claude_client.receive_response():
                    msg_type = type(msg).__name__

                    if msg_type == "AssistantMessage" and hasattr(msg, "content"):
                        for block in msg.content:
                            block_type = type(block).__name__

                            if block_type == "TextBlock" and hasattr(block, "text"):
                                content += block.text

            # Parse response
            return self._parse_semantic_response(content, len(epics), len(tasks))

        except Exception as e:
            logger.warning(f"Semantic matching failed: {e}, falling back to keyword scores")
            # Return empty scores on error
            return {'epics': {}, 'tasks': {}}

    def _build_semantic_match_prompt(
        self,
        requirement: Requirement,
        epics: List[Dict[str, Any]],
        tasks: List[Dict[str, Any]]
    ) -> str:
        """Build prompt for Claude semantic matching."""
        epic_list = "\n".join([
            f"{i}. {epic.get('title', epic.get('name', 'Unnamed'))}: {epic.get('description', 'No description')[:100]}"
            for i, epic in enumerate(epics)
        ])

        task_list = "\n".join([
            f"{i}. {task.get('title', task.get('description', 'Unnamed'))[:100]}: {task.get('action', '')[:100]}"
            for i, task in enumerate(tasks)
        ])

        return f"""Analyze if the following requirement was implemented in the project:

Requirement: "{requirement.text}"
Section: {requirement.section}
Priority: {requirement.priority}

Implemented Epics:
{epic_list if epic_list else "None"}

Implemented Tasks:
{task_list if task_list else "None"}

For each epic and task, provide a confidence score (0.0-1.0) indicating how well it implements the requirement.

Response format (JSON):
{{
  "epics": {{"0": 0.85, "1": 0.3, ...}},
  "tasks": {{"0": 0.75, "2": 0.5, ...}}
}}

Only include items with score > 0.3. Return empty object if nothing matches."""

    def _parse_semantic_response(
        self,
        response: str,
        epic_count: int,
        task_count: int
    ) -> Dict[str, Dict[int, float]]:
        """Parse Claude's semantic matching response."""
        import json

        try:
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))

                # Convert string keys to int and validate scores
                result = {'epics': {}, 'tasks': {}}

                if 'epics' in data:
                    result['epics'] = {
                        int(k): min(1.0, max(0.0, float(v)))
                        for k, v in data['epics'].items()
                        if int(k) < epic_count
                    }

                if 'tasks' in data:
                    result['tasks'] = {
                        int(k): min(1.0, max(0.0, float(v)))
                        for k, v in data['tasks'].items()
                        if int(k) < task_count
                    }

                return result

        except Exception as e:
            logger.warning(f"Failed to parse semantic response: {e}")

        return {'epics': {}, 'tasks': {}}

    def _combine_scores(
        self,
        keyword_scores: Dict[int, float],
        semantic_scores: Dict[int, float]
    ) -> Dict[int, float]:
        """Combine keyword and semantic scores with weighting."""
        combined = {}

        # Get all indices
        all_indices = set(keyword_scores.keys()) | set(semantic_scores.keys())

        for idx in all_indices:
            kw_score = keyword_scores.get(idx, 0.0)
            sem_score = semantic_scores.get(idx, 0.0)

            combined[idx] = (
                self.KEYWORD_WEIGHT * kw_score +
                self.SEMANTIC_WEIGHT * sem_score
            )

        return combined

    def _determine_status(
        self,
        confidence: float,
        matched_epics: List[int],
        matched_tasks: List[int]
    ) -> str:
        """Determine requirement status based on matches."""
        if confidence >= self.COMBINED_MATCH_THRESHOLD:
            return "met"
        elif confidence >= self.PARTIAL_MATCH_THRESHOLD:
            return "partial"
        else:
            return "missing"

    def _generate_implementation_notes(
        self,
        requirement: Requirement,
        matched_epics: List[Dict[str, Any]],
        matched_tasks: List[Dict[str, Any]],
        confidence: float
    ) -> str:
        """Generate human-readable notes about implementation."""
        if not matched_epics and not matched_tasks:
            return f"No implementation found for requirement: {requirement.text}"

        notes = []

        if matched_epics:
            epic_titles = [e.get('title', e.get('name', 'Unnamed')) for e in matched_epics]
            notes.append(f"Implemented in epics: {', '.join(epic_titles)}")

        if matched_tasks:
            task_titles = [t.get('title', t.get('description', 'Unnamed'))[:50] for t in matched_tasks[:3]]  # Limit to 3
            notes.append(f"Related tasks: {', '.join(task_titles)}")

        notes.append(f"Match confidence: {confidence:.0%}")

        return " | ".join(notes)

    def _identify_extra_features(
        self,
        matches: List[RequirementMatch],
        epics: List[Dict[str, Any]],
        parsed_spec: ParsedSpecification
    ) -> None:
        """
        Identify epics that don't match any requirement (extra features).

        Adds "extra" requirement entries to matches list.
        """
        # Get all matched epic IDs
        matched_epic_ids = set()
        for match in matches:
            matched_epic_ids.update(match.matched_epic_ids)

        # Find unmatched epics
        unmatched_epics = [
            epic for epic in epics
            if epic['id'] not in matched_epic_ids
        ]

        # Create "extra" requirements for unmatched epics
        for epic in unmatched_epics:
            epic_name = epic.get('title', epic.get('name', 'Unnamed'))
            extra_req = Requirement(
                id=f"extra_{epic['id']}",
                section="Extra Features",
                text=f"Extra feature: {epic_name}",
                keywords=[],
                priority="low"
            )

            extra_match = RequirementMatch(
                requirement=extra_req,
                matched_epic_ids=[epic['id']],
                matched_task_ids=[],
                match_confidence=1.0,
                status="extra",
                implementation_notes=f"Extra feature not in original spec: {epic.get('description', '')[:100]}"
            )

            matches.append(extra_match)

            logger.debug(f"Identified extra feature: {epic_name}")
