"""
Prompt Improvement Analyzer (Refactored)
=========================================

Analyzes deep review recommendations across sessions to generate
consolidated, evidence-backed prompt improvement proposals.

**Architecture:**
1. Query sessions with prompt_improvements from session_deep_reviews
2. Parse RECOMMENDATIONS section from review_text markdown
3. Cluster similar recommendations by theme
4. Calculate evidence metrics (frequency, sessions, quality)
5. Generate prioritized proposals with confidence scores

**Status:** Phase 2 of Review Prompt Refactoring
**Created:** December 25, 2025
"""

import asyncio
import json
import re
from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID, uuid4
from datetime import datetime, timedelta
from collections import defaultdict
import logging

from server.database.operations import TaskDatabase

logger = logging.getLogger(__name__)


class PromptImprovementAnalyzer:
    """
    Analyzes prompt improvement recommendations from deep reviews.

    Uses the refactored review system with session_deep_reviews table.
    """

    def __init__(self, db: TaskDatabase):
        self.db = db

    async def analyze_project(
        self,
        project_id: UUID,
        min_reviews: int = 3,
        store_in_db: bool = True,
        triggered_by: str = "manual",
        analysis_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Analyze prompt improvements for a single project.

        Args:
            project_id: Project UUID to analyze
            min_reviews: Minimum number of deep reviews required
            store_in_db: Whether to store results in database
            triggered_by: Who/what triggered the analysis
            analysis_id: Pre-created analysis ID (for background tasks)

        Returns:
            Analysis results with consolidated proposals and analysis_id if stored
        """
        logger.info(f"Starting prompt improvement analysis for project {project_id}")

        # Get project info to determine sandbox_type
        project = await self.db.get_project(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        # Extract sandbox_type from metadata
        metadata = project.get('metadata', {})
        if isinstance(metadata, str):
            import json
            metadata = json.loads(metadata)

        # Get sandbox_type - default to 'docker' if not specified
        sandbox_type = metadata.get('settings', {}).get('sandbox_type', 'docker')

        # Create analysis record if storing in DB (or use provided ID)
        if store_in_db and not analysis_id:
            # Create new analysis record
            analysis_id = await self._create_analysis_record(
                project_ids=[project_id],
                sandbox_type=sandbox_type,
                triggered_by=triggered_by
            )
        # else: use the pre-created analysis_id from background task

        try:
            # 1. Fetch deep reviews with recommendations
            reviews = await self._fetch_deep_reviews(project_id)

            if len(reviews) < min_reviews:
                logger.warning(
                    f"Not enough deep reviews ({len(reviews)} < {min_reviews}). "
                    f"Analysis requires at least {min_reviews} reviews."
                )

                if store_in_db and analysis_id:
                    await self._mark_analysis_failed(
                        analysis_id,
                        f"Insufficient data: {len(reviews)} reviews < {min_reviews} required"
                    )

                return {
                    "status": "insufficient_data",
                    "reviews_found": len(reviews),
                    "min_required": min_reviews,
                    "proposals": [],
                    "analysis_id": str(analysis_id) if analysis_id else None
                }

            logger.info(f"Found {len(reviews)} deep reviews with recommendations")

            # 2. Get recommendations from reviews
            parsed_reviews = []
            for review in reviews:
                # Get recommendations from the prompt_improvements JSONB field
                structured_recommendations = review.get('prompt_improvements', [])

                # Ensure structured_recommendations is a list
                if isinstance(structured_recommendations, str):
                    try:
                        structured_recommendations = json.loads(structured_recommendations)
                    except (json.JSONDecodeError, TypeError):
                        logger.warning(f"Could not parse prompt_improvements for session {review.get('session_id')}")
                        structured_recommendations = []

                # Ensure it's a list
                if not isinstance(structured_recommendations, list):
                    structured_recommendations = []

                if structured_recommendations:
                    parsed_reviews.append({
                        'session_id': review['session_id'],
                        'session_number': review['session_number'],
                        'overall_rating': review['overall_rating'],
                        'prompt_improvements': structured_recommendations,  # Use parsed version
                        'recommendations': structured_recommendations  # Already structured!
                    })

            logger.info(f"Loaded structured recommendations from {len(parsed_reviews)} reviews")

            # 3. Aggregate by theme
            themes = self._aggregate_by_theme(parsed_reviews)

            # 4. Generate proposals
            proposals = self._generate_proposals(themes)

            # 5. Generate diffs for each proposal using AI
            logger.info(f"Generating diffs for {len(proposals)} proposals...")
            # Store themes for access in _build_improvement_guidance
            self._current_themes = themes
            proposals_with_diffs = await self._generate_diffs_for_proposals(
                proposals,
                sandbox_type
            )

            # 6. Store in database if requested
            if store_in_db and analysis_id:
                await self._store_analysis_results(
                    analysis_id,
                    sandbox_type,
                    parsed_reviews,
                    themes,
                    proposals_with_diffs
                )
                logger.info(f"Stored analysis results in database (ID: {analysis_id})")

            return {
                "status": "completed",
                "analysis_id": str(analysis_id) if analysis_id else None,
                "reviews_analyzed": len(parsed_reviews),
                "themes_identified": len(themes),
                "proposals_generated": len(proposals),
                "proposals": proposals,
                "themes": themes
            }

        except Exception as e:
            logger.error(f"Analysis failed: {e}", exc_info=True)
            if store_in_db and analysis_id:
                await self._mark_analysis_failed(analysis_id, str(e))
            raise

    async def _fetch_deep_reviews(self, project_id: UUID) -> List[Dict[str, Any]]:
        """
        Fetch all deep reviews with prompt_improvements for a project.

        Uses the session_deep_reviews table (new schema).
        """
        async with self.db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    dr.id,
                    dr.session_id,
                    s.session_number,
                    dr.overall_rating,
                    dr.review_text,
                    dr.prompt_improvements,
                    dr.model,
                    dr.created_at
                FROM session_deep_reviews dr
                JOIN sessions s ON dr.session_id = s.id
                WHERE s.project_id = $1
                  AND jsonb_array_length(dr.prompt_improvements) > 0
                ORDER BY s.session_number ASC
                """,
                project_id
            )

            results = []
            for row in rows:
                result = dict(row)
                # Parse JSONB fields
                if isinstance(result.get('prompt_improvements'), str):
                    try:
                        result['prompt_improvements'] = json.loads(result['prompt_improvements'])
                    except json.JSONDecodeError:
                        result['prompt_improvements'] = []
                results.append(result)

            return results
        

    def _aggregate_by_theme(
        self,
        parsed_reviews: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Aggregate recommendations by theme using keyword matching.

        Groups similar recommendations together based on their titles and content.

        Returns:
            Dict mapping theme_name -> {
                'recommendations': List of recommendation objects,
                'sessions': List of session info,
                'frequency': int,
                'avg_quality': float,
                'unique_sessions': int
            }
        """
        # Theme keywords for categorization
        theme_keywords = {
            'browser_verification': ['browser', 'screenshot', 'playwright', 'visual', 'verify', 'ui'],
            'docker_mode': ['docker', 'bash_docker', 'container', 'sandbox'],
            'error_handling': ['error', 'recovery', 'debugging', 'fix', 'retry', 'exception'],
            'git_commits': ['commit', 'git', 'message', 'co-author', 'version control'],
            'testing': ['test', 'testing', 'unit test', 'e2e', 'coverage', 'verification'],
            'parallel_execution': ['parallel', 'concurrent', 'independent', 'simultaneous'],
            'task_management': ['task', 'epic', 'checklist', 'todo', 'workflow'],
            'prompt_adherence': ['prompt', 'instruction', 'guideline', 'follow', 'adherence'],
        }

        themes = defaultdict(lambda: {
            'recommendations': [],
            'sessions': {},  # Use dict for deduplication
            'frequency': 0
        })

        for review in parsed_reviews:
            session_id = str(review['session_id'])
            session_info = {
                'session_id': session_id,
                'session_number': review['session_number'],
                'overall_rating': review['overall_rating']
            }

            for rec in review['recommendations']:
                # Skip if rec is not a dictionary
                if not isinstance(rec, dict):
                    continue

                # Use theme field if present (from structured recommendations)
                matched_themes = []
                if 'theme' in rec and rec['theme']:
                    matched_themes = [rec['theme']]

                # Default to 'general' if no match
                if not matched_themes:
                    matched_themes = ['general']

                # Add to each matched theme
                for theme in matched_themes:
                    themes[theme]['recommendations'].append({
                        **rec,
                        'session_number': review['session_number'],
                        'session_rating': review['overall_rating']
                    })
                    themes[theme]['frequency'] += 1

                    # Track unique sessions
                    if session_id not in themes[theme]['sessions']:
                        themes[theme]['sessions'][session_id] = session_info

        # Calculate averages and convert sessions dict to list
        result = {}
        for theme_name, data in themes.items():
            sessions_list = list(data['sessions'].values())
            unique_sessions = len(sessions_list)

            if unique_sessions > 0:
                avg_quality = sum(s['overall_rating'] for s in sessions_list) / unique_sessions

                result[theme_name] = {
                    'theme_name': theme_name,
                    'recommendations': data['recommendations'],
                    'sessions': sessions_list,
                    'frequency': data['frequency'],
                    'avg_quality': avg_quality,
                    'unique_sessions': unique_sessions
                }

        return result

    def _generate_proposals(
        self,
        themes: Dict[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Generate consolidated proposals from themed recommendations.

        Each proposal includes:
        - title: Consolidated title
        - theme: Theme category
        - priority: Calculated from individual priorities
        - problem: Consolidated problem statement
        - proposed_text: Best proposal (or merged)
        - impact: Expected impact
        - evidence: Session IDs, frequency, quality metrics
        - confidence_level: 1-10 score
        """
        proposals = []

        # Sort themes by frequency (most common first)
        sorted_themes = sorted(
            themes.items(),
            key=lambda x: (x[1]['frequency'], x[1]['avg_quality']),
            reverse=True
        )

        for theme_name, theme_data in sorted_themes:
            # Skip low-frequency themes
            if theme_data['frequency'] < 2:
                continue

            # Consolidate recommendations
            recommendations = theme_data['recommendations']

            # Find most common priority
            priority_counts = defaultdict(int)
            for rec in recommendations:
                priority_counts[rec['priority']] += 1
            consolidated_priority = max(priority_counts.items(), key=lambda x: x[1])[0]

            # Get unique titles (for consolidated title)
            titles = list(set(rec['title'] for rec in recommendations))
            consolidated_title = titles[0] if len(titles) == 1 else f"{theme_name.replace('_', ' ').title()} Improvements"

            # Consolidate problems
            problems = [rec['problem'] for rec in recommendations if rec['problem']]
            consolidated_problem = problems[0] if problems else f"Multiple {theme_name} issues identified"

            # Get best proposed text (longest/most detailed)
            proposed_texts = [rec['proposed_text'] for rec in recommendations if rec['proposed_text']]
            best_proposed = max(proposed_texts, key=len) if proposed_texts else ""

            # Get current text example
            current_texts = [rec['current_text'] for rec in recommendations if rec['current_text']]
            example_current = current_texts[0] if current_texts else ""

            # Consolidate impact
            impacts = [rec['impact'] for rec in recommendations if rec['impact']]
            consolidated_impact = impacts[0] if impacts else f"Improves {theme_name} across sessions"

            # Calculate confidence
            confidence = self._calculate_confidence(theme_data, consolidated_priority)

            # Create proposal
            proposal = {
                'title': consolidated_title,
                'theme': theme_name,
                'priority': consolidated_priority,
                'problem': consolidated_problem,
                'current_text': example_current,
                'proposed_text': best_proposed,
                'impact': consolidated_impact,
                'evidence': {
                    'frequency': theme_data['frequency'],
                    'unique_sessions': theme_data['unique_sessions'],
                    'avg_quality': round(theme_data['avg_quality'], 1),
                    'session_numbers': [s['session_number'] for s in theme_data['sessions']],
                    'session_ids': [s['session_id'] for s in theme_data['sessions']]
                },
                'confidence_level': confidence
            }

            proposals.append(proposal)

        # Deduplicate proposals with identical proposed_text
        # This can happen when multiple themes identify the same underlying issue
        deduplicated = []
        seen_texts = {}  # proposed_text -> index in deduplicated

        for proposal in proposals:
            proposed_text = proposal['proposed_text']

            if proposed_text in seen_texts:
                # Merge with existing proposal
                idx = seen_texts[proposed_text]
                existing = deduplicated[idx]

                # Combine themes
                existing['theme'] = f"{existing['theme']}, {proposal['theme']}"

                # Update title if different
                if proposal['title'] not in existing['title']:
                    existing['title'] = f"{existing['title']} / {proposal['title']}"

                # Merge evidence (combine session lists)
                existing['evidence']['frequency'] += proposal['evidence']['frequency']
                existing['evidence']['unique_sessions'] = max(
                    existing['evidence']['unique_sessions'],
                    proposal['evidence']['unique_sessions']
                )

                # Combine session IDs (deduplicate)
                existing_sessions = set(existing['evidence']['session_ids'])
                new_sessions = set(proposal['evidence']['session_ids'])
                combined_sessions = existing_sessions | new_sessions
                existing['evidence']['session_ids'] = list(combined_sessions)

                # Combine session numbers (deduplicate)
                existing_numbers = set(existing['evidence']['session_numbers'])
                new_numbers = set(proposal['evidence']['session_numbers'])
                combined_numbers = existing_numbers | new_numbers
                existing['evidence']['session_numbers'] = sorted(list(combined_numbers))

                # Update unique_sessions count based on merged data
                existing['evidence']['unique_sessions'] = len(combined_sessions)

                # Take higher confidence
                existing['confidence_level'] = max(
                    existing['confidence_level'],
                    proposal['confidence_level']
                )

            else:
                # New unique proposal
                seen_texts[proposed_text] = len(deduplicated)
                deduplicated.append(proposal)

        # Sort by confidence (highest first)
        deduplicated.sort(key=lambda x: x['confidence_level'], reverse=True)

        return deduplicated

    def _calculate_confidence(
        self,
        theme_data: Dict[str, Any],
        priority: str
    ) -> int:
        """
        Calculate confidence score (1-10) based on evidence.

        Factors:
        - Number of unique sessions mentioning it
        - Average quality of those sessions
        - Priority level
        - Frequency
        """
        unique_sessions = theme_data['unique_sessions']
        avg_quality = theme_data['avg_quality']
        frequency = theme_data['frequency']

        # Base confidence from session count
        if unique_sessions >= 5:
            base = 9
        elif unique_sessions >= 3:
            base = 7
        elif unique_sessions >= 2:
            base = 5
        else:
            base = 3

        # Adjust for priority
        priority_boost = {'High': 1, 'Medium': 0, 'Low': -1}
        base += priority_boost.get(priority, 0)

        # Adjust for quality
        if avg_quality >= 8:
            base += 1
        elif avg_quality < 6:
            base -= 1

        # Cap at 1-10
        return max(1, min(10, base))

    # Database operations

    async def _create_analysis_record(
        self,
        project_ids: List[UUID],
        sandbox_type: str,
        triggered_by: str = "manual"
    ) -> UUID:
        """Create initial analysis record in database."""
        async with self.db.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO prompt_improvement_analyses (
                    projects_analyzed,
                    sandbox_type,
                    triggered_by,
                    status
                )
                VALUES ($1, $2, $3, 'running')
                RETURNING id
                """,
                project_ids,
                sandbox_type,
                triggered_by
            )
            return row['id']

    async def _mark_analysis_failed(self, analysis_id: UUID, error: str):
        """Mark analysis as failed."""
        async with self.db.acquire() as conn:
            await conn.execute(
                """
                UPDATE prompt_improvement_analyses
                SET
                    status = 'failed',
                    completed_at = NOW(),
                    notes = $1
                WHERE id = $2
                """,
                error,
                analysis_id
            )

    def _read_prompt_file(self, sandbox_type: str) -> str:
        """Read the current prompt file content."""
        from pathlib import Path

        prompt_file = f'coding_prompt_{sandbox_type}.md'
        prompt_path = Path(__file__).parent.parent.parent / 'prompts' / prompt_file

        if not prompt_path.exists():
            logger.warning(f"Prompt file not found: {prompt_path}")
            return ""

        return prompt_path.read_text()

    async def _generate_diffs_for_proposals(
        self,
        proposals: List[Dict[str, Any]],
        sandbox_type: str
    ) -> List[Dict[str, Any]]:
        """
        Generate complete improved prompts for each proposal using Claude.

        For each proposal (theme), asks Claude to generate a COMPLETE improved
        version of the prompt file incorporating all the recommendations.
        """
        from server.quality.diff_generator import DiffGenerator

        generator = DiffGenerator()
        proposals_with_prompts = []

        for proposal in proposals:
            try:
                # Build consolidated improvement guidance from recommendations
                guidance = self._build_improvement_guidance(proposal)

                # Generate complete improved prompt
                result = await generator.generate_improved_prompt(
                    prompt_file=f'coding_prompt_{sandbox_type}.md',
                    improvement_guidance=guidance,
                    theme=proposal['theme']
                )

                # Extract relevant snippets instead of storing full prompts
                original_snippet = self._extract_relevant_snippet(
                    result['original_prompt'],
                    result.get('changes', []),
                    is_original=True
                )
                proposed_snippet = self._extract_relevant_snippet(
                    result['improved_prompt'],
                    result.get('changes', []),
                    is_original=False
                )

                # Clean up JSON formatting if present in proposed text
                if proposed_snippet.startswith('```json'):
                    # Extract content between JSON markers
                    import json
                    try:
                        json_match = re.search(r'```json\s*\n(.*?)\n```', proposed_snippet, re.DOTALL)
                        if json_match:
                            json_data = json.loads(json_match.group(1))
                            # Use the improved_prompt field if it exists
                            if 'improved_prompt' in json_data:
                                proposed_snippet = json_data['improved_prompt']
                            elif 'changes' in json_data and json_data['changes']:
                                # Build snippet from changes
                                proposed_snippet = '\n\n'.join([
                                    f"## {change.get('section', 'Change')}\n{change.get('content', '')}"
                                    for change in json_data['changes']
                                ])
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"Failed to parse JSON from proposed text: {e}")
                        # Try to extract just the content after the JSON
                        if '```' in proposed_snippet:
                            proposed_snippet = proposed_snippet.split('```')[-1].strip()

                proposal['original_text'] = original_snippet
                proposal['proposed_text'] = proposed_snippet
                proposal['diff_metadata'] = {
                    'confidence': result.get('confidence', 0),
                    'summary': result.get('summary', ''),
                    'changes': result.get('changes', [])
                }

                logger.info(f"Generated improved prompt for '{proposal['title']}' (confidence: {result.get('confidence', 0)}, {len(result.get('improved_prompt', ''))} chars)")

            except Exception as e:
                logger.error(f"Failed to generate improved prompt for '{proposal['title']}': {e}")
                # Fallback: use empty prompts
                proposal['original_text'] = ''
                proposal['proposed_text'] = ''
                proposal['diff_metadata'] = {
                    'confidence': 0,
                    'summary': f'Error: {str(e)}',
                    'changes': []
                }

            proposals_with_prompts.append(proposal)

        return proposals_with_prompts

    def _extract_relevant_snippet(self, full_text: str, changes: List[Dict[str, Any]], is_original: bool = True, context_lines: int = 10) -> str:
        """
        Extract only the relevant snippet from the full prompt text based on changes.

        Args:
            full_text: The complete prompt text
            changes: List of change dictionaries with section/description info
            is_original: Whether this is the original (True) or proposed (False) text
            context_lines: Number of lines to include around changes

        Returns:
            A snippet containing only the relevant sections
        """
        if not changes or not full_text:
            # If no changes info, try to extract first meaningful section
            lines = full_text.split('\n')
            if len(lines) > 50:
                # Too long, extract key sections
                snippet_lines = []
                for i, line in enumerate(lines[:100]):  # Check first 100 lines
                    if line.startswith('#'):  # Section headers
                        # Add this section until next header or 20 lines
                        section_end = min(i + 20, len(lines))
                        for j in range(i + 1, section_end):
                            if lines[j].startswith('#'):
                                section_end = j
                                break
                        snippet_lines.extend(lines[i:section_end])
                        if len(snippet_lines) > 40:  # Enough content
                            break
                return '\n'.join(snippet_lines[:50]) if snippet_lines else '\n'.join(lines[:30])
            return full_text

        # Extract sections mentioned in changes
        snippets = []
        lines = full_text.split('\n')

        for change in changes[:3]:  # Limit to first 3 changes to avoid huge snippets
            section = change.get('section', '')
            description = change.get('description', '')

            # Find the section in the text
            section_found = False
            for i, line in enumerate(lines):
                if section and (section.lower() in line.lower() or line.strip().startswith('#')):
                    # Found a potential match, extract context
                    start = max(0, i - context_lines//2)
                    end = min(len(lines), i + context_lines)
                    snippet = '\n'.join(lines[start:end])

                    # Add ellipsis if truncated
                    if start > 0:
                        snippet = '...\n' + snippet
                    if end < len(lines):
                        snippet = snippet + '\n...'

                    snippets.append(f"# {section}\n{snippet}")
                    section_found = True
                    break

            if not section_found and description:
                # Try to find by description keywords
                keywords = [w for w in description.split() if len(w) > 4][:3]
                for i, line in enumerate(lines):
                    if any(keyword.lower() in line.lower() for keyword in keywords):
                        start = max(0, i - context_lines//2)
                        end = min(len(lines), i + context_lines)
                        snippet = '\n'.join(lines[start:end])

                        if start > 0:
                            snippet = '...\n' + snippet
                        if end < len(lines):
                            snippet = snippet + '\n...'

                        snippets.append(f"# Related to: {description[:50]}...\n{snippet}")
                        break

        # If no snippets found, return first part of text
        if not snippets:
            max_lines = 30
            lines_to_show = lines[:max_lines]
            result = '\n'.join(lines_to_show)
            if len(lines) > max_lines:
                result += '\n...'
            return result

        return '\n\n---\n\n'.join(snippets)

    def _build_improvement_guidance(self, proposal: Dict[str, Any]) -> str:
        """
        Build consolidated improvement guidance for Claude.

        Combines the problem statement, impact, and evidence into
        clear guidance for improving the prompt.
        """
        guidance_parts = []

        # Add title and theme
        guidance_parts.append(f"# {proposal['title']}")
        guidance_parts.append(f"**Theme**: {proposal['theme']}")
        guidance_parts.append("")

        # Add problem statement
        if proposal.get('problem'):
            guidance_parts.append(f"## Problem")
            guidance_parts.append(proposal['problem'])
            guidance_parts.append("")

        # Add impact
        if proposal.get('impact'):
            guidance_parts.append(f"## Expected Impact")
            guidance_parts.append(proposal['impact'])
            guidance_parts.append("")

        # Add evidence
        if proposal.get('evidence'):
            evidence = proposal['evidence']
            guidance_parts.append(f"## Evidence")
            guidance_parts.append(f"- Observed in {evidence.get('frequency', 0)} occurrences across {evidence.get('unique_sessions', 0)} sessions")
            guidance_parts.append(f"- Average session quality: {evidence.get('avg_quality', 0)}/10")
            guidance_parts.append(f"- Sessions affected: {', '.join(map(str, evidence.get('session_numbers', [])))}")
            guidance_parts.append("")

        # Add priority
        if proposal.get('priority'):
            guidance_parts.append(f"## Priority")
            guidance_parts.append(proposal['priority'])
            guidance_parts.append("")

        # CRITICAL: Add the actual recommendations from the theme data
        # This is where the specific improvement suggestions are stored
        if hasattr(self, '_current_themes') and proposal.get('theme') in self._current_themes:
            theme_data = self._current_themes[proposal['theme']]
            if theme_data.get('recommendations'):
                guidance_parts.append(f"## Specific Recommendations from Reviews")
                guidance_parts.append("")

                # Group recommendations by priority
                high_priority = []
                medium_priority = []
                low_priority = []

                for rec in theme_data['recommendations']:
                    if rec.get('priority') == 'High':
                        high_priority.append(rec)
                    elif rec.get('priority') == 'Medium':
                        medium_priority.append(rec)
                    else:
                        low_priority.append(rec)

                # Add high priority recommendations
                if high_priority:
                    guidance_parts.append("### High Priority Changes")
                    for i, rec in enumerate(high_priority[:3], 1):  # Limit to top 3
                        guidance_parts.append(f"\n**{i}. {rec.get('title', 'Recommendation')}**")
                        if rec.get('problem'):
                            guidance_parts.append(f"Problem: {rec['problem']}")
                        if rec.get('raw_content'):
                            # Extract the proposed solution from raw_content
                            content = rec['raw_content']
                            # Look for proposed solution or recommendation text
                            if 'Proposed Solution:' in content:
                                solution_start = content.find('Proposed Solution:')
                                solution_end = content.find('**Expected Impact:', solution_start)
                                if solution_end == -1:
                                    solution_end = len(content)
                                solution_text = content[solution_start:solution_end].strip()
                                guidance_parts.append(f"\n{solution_text}")
                        guidance_parts.append("")

                # Add medium priority if space
                if medium_priority and len(high_priority) < 3:
                    guidance_parts.append("### Medium Priority Changes")
                    for i, rec in enumerate(medium_priority[:2], 1):
                        guidance_parts.append(f"\n**{i}. {rec.get('title', 'Recommendation')}**")
                        if rec.get('problem'):
                            guidance_parts.append(f"Problem: {rec['problem'][:200]}...")
                    guidance_parts.append("")

        return "\n".join(guidance_parts)

    async def _store_analysis_results(
        self,
        analysis_id: UUID,
        sandbox_type: str,
        parsed_reviews: List[Dict[str, Any]],
        themes: Dict[str, Dict[str, Any]],
        proposals: List[Dict[str, Any]]
    ):
        """Store analysis results and proposals in database."""
        async with self.db.acquire() as conn:
            # Update analysis record
            await conn.execute(
                """
                UPDATE prompt_improvement_analyses
                SET
                    status = 'completed',
                    completed_at = NOW(),
                    sessions_analyzed = $1,
                    patterns_identified = $2,
                    proposed_changes = $3
                WHERE id = $4
                """,
                len(parsed_reviews),
                json.dumps(themes, default=str),  # default=str to handle UUIDs
                json.dumps([p['title'] for p in proposals]),
                analysis_id
            )

            # Determine correct prompt file based on sandbox_type
            prompt_file = f'coding_prompt_{sandbox_type}.md'

            # Store each proposal
            for proposal in proposals:
                # Use AI-generated diff's original text if available
                # Otherwise fallback to current_text from review
                original_text = proposal.get('original_text', proposal.get('current_text', ''))

                # Store diff metadata in the metadata JSONB field
                diff_metadata = proposal.get('diff_metadata', {})

                await conn.execute(
                    """
                    INSERT INTO prompt_proposals (
                        analysis_id,
                        prompt_file,
                        section_name,
                        original_text,
                        proposed_text,
                        change_type,
                        rationale,
                        evidence,
                        confidence_level,
                        status,
                        metadata
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'proposed', $10)
                    """,
                    analysis_id,
                    prompt_file,  # coding_prompt_docker.md or coding_prompt_local.md
                    proposal['theme'],
                    original_text,  # AI-identified section from actual prompt file
                    proposal['proposed_text'],  # AI-generated specific changes
                    'modification',
                    f"{proposal['title']} - {proposal['problem'][:200]}",
                    json.dumps(proposal['evidence'], default=str),
                    proposal['confidence_level'],
                    json.dumps(diff_metadata)  # Store diff metadata (all_changes, summary, etc.)
                )


# Standalone analysis function for testing
async def analyze_project_improvements(
    project_id: UUID,
    min_reviews: int = 3
) -> Dict[str, Any]:
    """
    Convenience function to analyze a project's prompt improvements.

    Args:
        project_id: Project UUID
        min_reviews: Minimum deep reviews required

    Returns:
        Analysis results
    """
    from server.database.connection import get_db

    db = await get_db()
    analyzer = PromptImprovementAnalyzer(db)
    results = await analyzer.analyze_project(project_id, min_reviews)
    return results


if __name__ == "__main__":
    # CLI for testing
    import sys

    if len(sys.argv) < 2:
        print("Usage: python prompt_improvement_analyzer.py <project_id>")
        sys.exit(1)

    project_id = UUID(sys.argv[1])
    min_reviews = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    results = asyncio.run(analyze_project_improvements(project_id, min_reviews))

    print(f"\n{'='*60}")
    print(f"Prompt Improvement Analysis Results")
    print(f"{'='*60}\n")
    print(f"Status: {results['status']}")
    print(f"Reviews Analyzed: {results.get('reviews_analyzed', 0)}")
    print(f"Themes Identified: {results.get('themes_identified', 0)}")
    print(f"Proposals Generated: {results.get('proposals_generated', 0)}\n")

    if results['status'] == 'completed':
        print(f"{'='*60}")
        print(f"PROPOSALS (sorted by confidence)")
        print(f"{'='*60}\n")

        for i, proposal in enumerate(results['proposals'], 1):
            print(f"{i}. {proposal['title']}")
            print(f"   Theme: {proposal['theme']}")
            print(f"   Priority: {proposal['priority']}")
            print(f"   Confidence: {proposal['confidence_level']}/10")
            print(f"   Evidence: {proposal['evidence']['unique_sessions']} sessions, "
                  f"{proposal['evidence']['frequency']} mentions, "
                  f"avg quality {proposal['evidence']['avg_quality']}/10")
            print(f"   Sessions: {proposal['evidence']['session_numbers']}")
            print()
