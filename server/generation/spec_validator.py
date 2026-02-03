"""
Specification Validator
=======================

Validates markdown specifications to ensure they contain all required sections
and follow the expected structure for YokeFlow projects.
"""

import re
import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field

from server.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationResult:
    """Result of specification validation."""
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    sections_found: List[str] = field(default_factory=list)
    sections_missing: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "sections_found": self.sections_found,
            "sections_missing": self.sections_missing
        }


class SpecValidator:
    """Validate application specifications for completeness and structure."""

    # Required sections in a specification
    REQUIRED_SECTIONS = [
        "overview",
        "tech_stack",
        "frontend",
        "backend",
        "database"
    ]

    # Optional but recommended sections
    RECOMMENDED_SECTIONS = [
        "additional_features",
        "development_notes",
        "deployment",
        "testing",
        "security"
    ]

    # Minimum content length for sections (in characters)
    MIN_SECTION_LENGTH = 50

    # Section name variations (for flexible matching)
    SECTION_ALIASES = {
        "overview": ["overview", "introduction", "summary", "description"],
        "tech_stack": ["tech stack", "technology stack", "technologies", "stack"],
        "frontend": ["frontend", "front-end", "ui", "user interface", "client"],
        "backend": ["backend", "back-end", "api", "server", "server-side"],
        "database": ["database", "data", "schema", "data model", "storage"],
        "additional_features": ["additional features", "features", "extra features", "other features"],
        "development_notes": ["development notes", "notes", "implementation notes", "dev notes"],
        "deployment": ["deployment", "hosting", "infrastructure", "deploy"],
        "testing": ["testing", "tests", "test strategy", "quality assurance"],
        "security": ["security", "authentication", "authorization", "safety"]
    }

    def __init__(self):
        """Initialize the validator."""
        pass

    def validate(self, spec_content: str) -> ValidationResult:
        """Validate a specification document.

        Args:
            spec_content: Markdown content of the specification

        Returns:
            ValidationResult with validation details
        """
        logger.info("Validating specification")

        result = ValidationResult(valid=True)

        # Parse sections from markdown
        sections = self._parse_sections(spec_content)

        # Check for required sections
        for required_section in self.REQUIRED_SECTIONS:
            section_found = False

            # Check against aliases
            for alias in self.SECTION_ALIASES[required_section]:
                normalized_alias = self._normalize_section_name(alias)
                if any(self._normalize_section_name(s) == normalized_alias for s in sections.keys()):
                    section_found = True
                    result.sections_found.append(required_section)
                    # Get the actual section name used
                    actual_name = next(s for s in sections.keys() if self._normalize_section_name(s) == normalized_alias)

                    # Check section content length
                    content = sections[actual_name].strip()
                    if len(content) < self.MIN_SECTION_LENGTH:
                        result.warnings.append(
                            f"Section '{actual_name}' is too short ({len(content)} chars). "
                            f"Minimum recommended: {self.MIN_SECTION_LENGTH} chars"
                        )
                    break

            if not section_found:
                result.errors.append(f"Required section missing: {required_section}")
                result.sections_missing.append(required_section)
                result.valid = False

        # Check for recommended sections
        for recommended_section in self.RECOMMENDED_SECTIONS:
            section_found = False

            for alias in self.SECTION_ALIASES.get(recommended_section, [recommended_section]):
                normalized_alias = self._normalize_section_name(alias)
                if any(self._normalize_section_name(s) == normalized_alias for s in sections.keys()):
                    section_found = True
                    result.sections_found.append(recommended_section)
                    break

            if not section_found:
                result.warnings.append(f"Recommended section missing: {recommended_section}")

        # Additional validation checks
        self._validate_content_quality(spec_content, result)
        self._validate_markdown_structure(spec_content, result)

        logger.info(f"Validation complete: valid={result.valid}, errors={len(result.errors)}, warnings={len(result.warnings)}")

        return result

    def _parse_sections(self, markdown: str) -> Dict[str, str]:
        """Parse markdown into sections based on headers.

        Args:
            markdown: Markdown content

        Returns:
            Dictionary of section names to content
        """
        sections = {}
        current_section = None
        current_content = []

        lines = markdown.split("\n")
        for line in lines:
            # Check for headers (## or ###)
            if re.match(r'^#{2,3}\s+', line):
                # Save previous section
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()

                # Extract section name
                current_section = re.sub(r'^#{2,3}\s+', '', line).strip()
                current_content = []
            elif current_section:
                current_content.append(line)

        # Save last section
        if current_section:
            sections[current_section] = "\n".join(current_content).strip()

        return sections

    def _normalize_section_name(self, name: str) -> str:
        """Normalize section name for comparison.

        Args:
            name: Section name to normalize

        Returns:
            Normalized name (lowercase, no special chars)
        """
        return re.sub(r'[^a-z0-9]+', '', name.lower())

    def _validate_content_quality(self, content: str, result: ValidationResult):
        """Validate overall content quality.

        Args:
            content: Specification content
            result: ValidationResult to update
        """
        # Check minimum overall length
        if len(content.strip()) < 500:
            result.errors.append("Specification is too short. Please provide more detail.")
            result.valid = False

        # Check for placeholder text
        placeholders = ["TODO", "FIXME", "XXX", "[placeholder]", "[add details]"]
        for placeholder in placeholders:
            if placeholder in content:
                result.warnings.append(f"Specification contains placeholder text: {placeholder}")

        # Check for code blocks (good sign of detailed spec)
        if "```" not in content:
            result.warnings.append("Consider adding code examples or technical details in code blocks")

    def _validate_markdown_structure(self, content: str, result: ValidationResult):
        """Validate markdown structure and formatting.

        Args:
            content: Markdown content
            result: ValidationResult to update
        """
        lines = content.split("\n")

        # Check for title (# header)
        has_title = any(line.strip().startswith("# ") for line in lines)
        if not has_title:
            result.warnings.append("Specification should have a main title (# Title)")

        # Check for proper header hierarchy
        header_levels = []
        for line in lines:
            match = re.match(r'^(#{1,6})\s+', line)
            if match:
                header_levels.append(len(match.group(1)))

        # Check if headers skip levels (e.g., # then ###)
        if header_levels:
            for i in range(1, len(header_levels)):
                if header_levels[i] > header_levels[i-1] + 1:
                    result.warnings.append("Header hierarchy skips levels (e.g., # followed by ###)")
                    break

        # Check for lists (bullets or numbers)
        has_lists = any(re.match(r'^\s*[-*+]\s+', line) or re.match(r'^\s*\d+\.\s+', line) for line in lines)
        if not has_lists:
            result.warnings.append("Consider using lists to organize requirements and features")

    def validate_section(self, section_name: str, content: str) -> Tuple[bool, List[str]]:
        """Validate a specific section.

        Args:
            section_name: Name of the section
            content: Section content

        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []
        is_valid = True

        # Check content length
        if len(content.strip()) < self.MIN_SECTION_LENGTH:
            issues.append(f"Section is too short ({len(content.strip())} chars)")
            is_valid = False

        # Section-specific validation
        normalized_name = self._normalize_section_name(section_name)

        if normalized_name in ["techstack", "technologystack"]:
            # Tech stack should mention specific technologies
            if not re.search(r'\b(react|vue|angular|next|django|flask|fastapi|express|postgres|mysql|mongodb)\b', content.lower()):
                issues.append("Tech stack should specify concrete technologies")

        elif normalized_name == "database":
            # Database section should mention tables or schema
            if not re.search(r'\b(table|schema|model|entity|relationship|field|column)\b', content.lower()):
                issues.append("Database section should describe schema or data models")

        elif normalized_name == "frontend":
            # Frontend should mention UI components or pages
            if not re.search(r'\b(page|component|view|screen|form|button|navigation|layout)\b', content.lower()):
                issues.append("Frontend section should describe UI components or pages")

        elif normalized_name == "backend":
            # Backend should mention APIs or endpoints
            if not re.search(r'\b(api|endpoint|route|service|controller|middleware|authentication)\b', content.lower()):
                issues.append("Backend section should describe APIs or services")

        return is_valid, issues

    def suggest_improvements(self, spec_content: str) -> List[str]:
        """Suggest improvements for a specification.

        Args:
            spec_content: Specification content

        Returns:
            List of improvement suggestions
        """
        suggestions = []
        sections = self._parse_sections(spec_content)

        # Check for missing recommended sections
        for section in self.RECOMMENDED_SECTIONS:
            found = False
            for alias in self.SECTION_ALIASES.get(section, [section]):
                if any(self._normalize_section_name(s) == self._normalize_section_name(alias) for s in sections.keys()):
                    found = True
                    break
            if not found:
                suggestions.append(f"Consider adding a '{section.replace('_', ' ').title()}' section")

        # Check for API documentation
        if "api" not in spec_content.lower():
            suggestions.append("Consider documenting API endpoints if your app has them")

        # Check for user stories
        if "user" not in spec_content.lower() or "story" not in spec_content.lower():
            suggestions.append("Consider adding user stories or use cases")

        # Check for error handling
        if "error" not in spec_content.lower() and "exception" not in spec_content.lower():
            suggestions.append("Consider describing error handling strategies")

        # Check for performance considerations
        if "performance" not in spec_content.lower() and "optimization" not in spec_content.lower():
            suggestions.append("Consider adding performance requirements or optimization strategies")

        return suggestions