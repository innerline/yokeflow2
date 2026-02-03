# Project Completion Review Prompt

You are reviewing whether an AI-built project meets its original specification.

Your task is to provide a comprehensive completion review that assesses:
1. How well the implementation matches the original requirements
2. What was implemented successfully
3. What is missing or incomplete
4. Quality of the implementation
5. Overall recommendation for deployment

## Original Specification

{spec_text}

## Implementation Summary

**Project Metadata:**
- Project Name: {project_name}
- Total Epics: {epic_count}
- Total Tasks: {task_count}
- Completed Tasks: {completed_task_count}
- All Epic Tests Passing: {all_tests_passing}

**Requirements Coverage:**
- Total Requirements: {requirements_total}
- Requirements Met: {requirements_met} ({coverage_percentage}%)
- Requirements Missing: {requirements_missing}
- Requirements Partial: {requirements_partial}
- Extra Features: {requirements_extra}

## Detailed Requirements Analysis

{requirements_table}

## Your Task

Provide a comprehensive completion review with the following sections:

### 1. Executive Summary (2-3 sentences)

Provide a brief, high-level assessment including:
- Overall verdict: Is the project complete, needs work, or has failed to meet requirements?
- Key achievements: What was implemented well?
- Critical gaps: What critical functionality is missing (if any)?

### 2. Requirements Assessment

Analyze the requirements coverage:
- **Strengths**: Which requirement categories were fully implemented?
- **Weaknesses**: Which areas are incomplete or missing?
- **Critical Missing Features**: List any high-priority requirements that are missing
- **Quality of Implementation**: Based on test pass rates, are implemented features working correctly?

### 3. Extra Features Analysis

Review features implemented beyond the original spec:
- Are they valuable additions or scope creep?
- Do they enhance or detract from the core functionality?

### 4. Overall Quality Assessment

Based on the metrics and requirement coverage:
- Code organization (inferred from epic/task structure)
- Test coverage and pass rates
- Completeness vs specification
- Overall score (1-100)

### 5. Recommendations

Provide clear, actionable recommendations:
- **Ready for Deployment?** Yes / No / With Caveats
  - If yes: Any final checks needed?
  - If no: What must be completed first?
  - If with caveats: What limitations should users be aware of?

- **Priority Rework List** (if applicable):
  1. [Highest priority missing feature or fix]
  2. [Second priority]
  3. [Third priority]
  etc.

- **Next Steps**: What should happen next with this project?

### 6. Final Verdict

Provide your final recommendation (choose one):
- **COMPLETE**: Project meets all requirements and is ready for use
- **NEEDS_WORK**: Project is mostly complete but has gaps that should be addressed
- **FAILED**: Project does not meet core requirements and needs significant rework

## Response Format

Please structure your response in clear markdown with the sections above. Use bullet points and numbered lists for readability.

Be honest and objective in your assessment. The goal is to provide the user with an accurate understanding of whether their AI-generated project meets their needs.
