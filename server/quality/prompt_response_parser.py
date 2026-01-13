"""
Enhanced response parser for prompt improvements.
Handles multiple response formats from Claude.

This parser addresses the issue where Claude may return responses in various
formats (JSON, markdown, prose) rather than strict JSON, causing parsing failures.
"""

import json
import re
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class PromptResponseParser:
    """
    Parse Claude responses for prompt improvements with multiple fallback strategies.

    Handles:
    - JSON in code blocks
    - Direct JSON objects
    - Markdown-structured responses
    - Prose responses with structured sections
    - Malformed JSON with recovery attempts
    """

    def __init__(self):
        """Initialize the parser with strategy tracking."""
        self.last_strategy_used = None
        self.parse_attempts = 0

    def parse_improvement_response(self, response_text: str) -> Dict[str, Any]:
        """
        Parse improvement response with multiple strategies.

        Strategies (in order):
        1. JSON code block (```json)
        2. Direct JSON object
        3. Markdown sections extraction
        4. Structured text parsing
        5. Fallback with error details

        Args:
            response_text: Raw response from Claude

        Returns:
            Dict with improved_prompt, changes, summary, and confidence
        """
        self.parse_attempts = 0

        if not response_text:
            logger.error("Empty response text provided")
            return self._create_error_response("Empty response", "")

        # Log first 500 chars for debugging
        logger.debug(f"Attempting to parse response (first 500 chars): {response_text[:500]}")

        # Strategy 1: JSON code block
        result = self._try_json_code_block(response_text)
        if result:
            self.last_strategy_used = "json_code_block"
            logger.info(f"Successfully parsed using JSON code block strategy")
            return self._validate_and_complete(result)

        # Strategy 2: Direct JSON
        result = self._try_direct_json(response_text)
        if result:
            self.last_strategy_used = "direct_json"
            logger.info(f"Successfully parsed using direct JSON strategy")
            return self._validate_and_complete(result)

        # Strategy 3: Extract from markdown sections
        result = self._try_markdown_extraction(response_text)
        if result:
            self.last_strategy_used = "markdown_extraction"
            logger.info(f"Successfully parsed using markdown extraction strategy")
            return self._validate_and_complete(result)

        # Strategy 4: Parse structured text
        result = self._try_structured_text(response_text)
        if result:
            self.last_strategy_used = "structured_text"
            logger.info(f"Successfully parsed using structured text strategy")
            return self._validate_and_complete(result)

        # Strategy 5: Ultimate fallback - if response is large, assume it's the improved prompt
        if len(response_text) > 5000:
            logger.warning(f"All parsing strategies failed, but response is large ({len(response_text)} chars). Using as improved prompt.")
            return {
                'improved_prompt': response_text.strip(),
                'changes': [{'section': 'Unknown', 'description': 'Unable to parse specific changes'}],
                'summary': 'Response parsing failed - using full response as improved prompt',
                'confidence': 3
            }

        # Strategy 6: Fallback - return error with details
        logger.warning(f"All parsing strategies failed after {self.parse_attempts} attempts")
        return self._create_error_response(
            "Failed to parse response after all strategies",
            response_text
        )

    def _try_json_code_block(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Extract JSON from various code block formats.

        Handles:
        - ```json ... ```
        - ``` { ... } ```
        - <json> ... </json>
        """
        self.parse_attempts += 1

        patterns = [
            (r'```json\s*\n(.*?)\n```', True),
            (r'```json\s*(.*?)```', True),  # Single line
            (r'```\s*\n(\{.*?\})\s*\n```', True),
            (r'<json>(.*?)</json>', True),
            (r'<code>(.*?)</code>', True)
        ]

        for pattern, is_code_block in patterns:
            matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
            for match in matches:
                try:
                    # Clean up common issues
                    cleaned = self._clean_json_string(match)
                    result = json.loads(cleaned)
                    if isinstance(result, dict):
                        logger.debug(f"JSON extracted with pattern: {pattern[:30]}...")
                        return result
                except (json.JSONDecodeError, Exception) as e:
                    logger.debug(f"JSON decode failed for pattern {pattern[:30]}...: {e}")
                    continue

        return None

    def _try_direct_json(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Try to extract JSON object directly from text.

        Looks for { ... } patterns and attempts to parse them.
        """
        self.parse_attempts += 1

        # First try to parse the entire text as JSON
        try:
            cleaned = self._clean_json_string(text.strip())
            result = json.loads(cleaned)
            if isinstance(result, dict):
                logger.debug("Direct JSON parse of entire text succeeded")
                return result
        except (json.JSONDecodeError, Exception) as e:
            logger.debug(f"Full text JSON parse failed: {e}")

        # Find potential JSON objects (balanced braces)
        json_candidates = self._extract_json_objects(text)

        for candidate in json_candidates:
            try:
                cleaned = self._clean_json_string(candidate)
                result = json.loads(cleaned)
                if isinstance(result, dict):
                    # Accept any dict that has relevant fields
                    if any(key in result for key in ['improved_prompt', 'changes', 'summary', 'confidence']):
                        logger.debug("Direct JSON object found and parsed")
                        return result
            except (json.JSONDecodeError, Exception) as e:
                logger.debug(f"Direct JSON parse failed: {e}")
                continue

        return None

    def _try_markdown_extraction(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Extract improvements from markdown structure.

        Looks for common markdown patterns like:
        - ## Improved Prompt
        - ### Changes Made
        - ## Summary
        """
        self.parse_attempts += 1

        result = {}

        # Look for improved prompt section - expanded patterns for Opus
        improved_patterns = [
            # Standard patterns
            r'(?:##+ (?:Improved|Updated|New|Complete|Full) (?:Prompt|Version).*?)\n```(?:markdown|md)?\s*\n(.*?)\n```',
            r'(?:##+ (?:Improved|Updated|New) Prompt.*?)\n(.*?)(?:##|$)',
            r'(?:improved_prompt|new_prompt):\s*\n```(?:markdown)?\s*\n(.*?)\n```',
            # Opus-specific patterns (may use different formatting)
            r'Here is the complete improved prompt:?\s*\n```(?:markdown)?\s*\n(.*?)\n```',
            r'Complete improved version:?\s*\n```(?:markdown)?\s*\n(.*?)\n```',
            r'The improved prompt file:?\s*\n```(?:markdown)?\s*\n(.*?)\n```',
            # Very broad pattern - look for any large markdown code block
            r'```(?:markdown|md)?\s*\n((?:.*?\n){50,}?)```'  # At least 50 lines
        ]

        for pattern in improved_patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                content = match.group(1).strip()
                # Check if this looks like a prompt file (should contain certain keywords)
                # Make keyword check more lenient - accept if it has "prompt" or typical prompt keywords
                prompt_keywords = ['docker', 'task', 'tool', 'mcp', 'bash', 'prompt', 'instructions', 'examples', 'claude', 'ai']
                if any(keyword in content.lower() for keyword in prompt_keywords) or len(content) > 200:
                    result['improved_prompt'] = content
                    logger.debug(f"Found improved prompt with pattern: {pattern[:50]}...")
                    break

        if 'improved_prompt' not in result:
            # Last resort: look for the largest code block in the response
            code_blocks = re.findall(r'```[^\n]*\n(.*?)\n```', text, re.DOTALL)
            if code_blocks:
                # Find the longest code block that looks like a prompt
                valid_blocks = []
                prompt_keywords = ['docker', 'task', 'tool', 'mcp', 'bash', 'prompt', 'instructions', 'examples']
                for block in code_blocks:
                    # Accept blocks that are reasonably long OR contain prompt keywords
                    if len(block) > 100 and (len(block) > 1000 or any(kw in block.lower() for kw in prompt_keywords)):
                        valid_blocks.append(block)

                if valid_blocks:
                    result['improved_prompt'] = max(valid_blocks, key=len)
                    logger.debug("Found improved prompt in largest code block")

        if 'improved_prompt' not in result:
            return None

        # Extract changes list
        changes = []
        changes_patterns = [
            r'(?:##+ (?:Changes|Modifications|Updates|Key Changes|What Changed).*?)\n(.*?)(?:##|$)',
            r'(?:changes|modifications):\s*\n(.*?)(?:\n##|\n\n|\Z)'
        ]

        for pattern in changes_patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                changes_text = match.group(1)
                changes = self._parse_change_list(changes_text)
                logger.debug(f"Found {len(changes)} changes")
                break

        result['changes'] = changes

        # Extract summary
        summary_patterns = [
            r'(?:##+ Summary.*?)\n(.*?)(?:\n##|\n###|\Z)',
            r'(?:summary|overview):\s*(.*?)(?:\n\n|\n##|\Z)'
        ]

        for pattern in summary_patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                result['summary'] = match.group(1).strip()
                logger.debug("Found summary section")
                break

        if 'summary' not in result:
            result['summary'] = "Prompt improvements applied based on review feedback"

        # Default confidence for markdown extraction
        result['confidence'] = 7

        return result

    def _try_structured_text(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Parse structured text that's not quite JSON or markdown.

        Looks for key-value patterns and structured sections.
        """
        self.parse_attempts += 1

        result = {}

        # Look for key sections even without markdown headers
        # Try to find the improved prompt between clear delimiters
        improved_patterns = [
            r'(?:improved[_\s]prompt|new[_\s]prompt|updated[_\s]prompt)[\s:]*\n(.*?)(?:\n\n|\n(?:changes|summary|confidence)[\s:]|$)',
            r'(?:improved[_\s]prompt|new[_\s]prompt|updated[_\s]prompt):\s*([^\n].*?)(?:\n\n|\n(?:changes|summary)[\s:]|$)'
        ]

        for pattern in improved_patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                content = match.group(1).strip()
                # Remove quotes if wrapped
                if content.startswith('"') and content.endswith('"'):
                    content = content[1:-1]
                result['improved_prompt'] = content
                break

        # If we didn't find improved_prompt, this strategy fails
        if 'improved_prompt' not in result:
            return None

        # Look for changes section
        changes_match = re.search(
            r'(?:changes|modifications)[\s:]*\n(.*?)(?:\n(?:summary|confidence)|$)',
            text,
            re.DOTALL | re.IGNORECASE
        )

        if changes_match:
            result['changes'] = self._parse_change_list(changes_match.group(1))
        else:
            result['changes'] = []

        # Look for summary
        summary_match = re.search(
            r'(?:summary|overview)[\s:]*\n?(.*?)(?:\n(?:confidence)|$)',
            text,
            re.DOTALL | re.IGNORECASE
        )

        if summary_match:
            result['summary'] = summary_match.group(1).strip()
        else:
            result['summary'] = "Improvements applied to prompt"

        # Look for confidence score
        confidence_match = re.search(r'confidence[\s:]*(\d+)', text, re.IGNORECASE)
        if confidence_match:
            result['confidence'] = int(confidence_match.group(1))
        else:
            result['confidence'] = 6

        return result

    def _extract_json_objects(self, text: str) -> List[str]:
        """
        Extract potential JSON objects with balanced braces.

        Returns list of strings that might be valid JSON.
        """
        objects = []
        used_ranges = []  # Track which character ranges we've already used

        # Find all { positions
        starts = [m.start() for m in re.finditer(r'\{', text)]

        for start in starts:
            # Skip if this position is inside an already extracted object
            if any(r[0] <= start < r[1] for r in used_ranges):
                continue

            brace_count = 0
            in_string = False
            escape_next = False

            for i in range(start, len(text)):
                char = text[i]

                if escape_next:
                    escape_next = False
                    continue

                if char == '\\':
                    escape_next = True
                    continue

                if char == '"' and not escape_next:
                    in_string = not in_string
                    continue

                if not in_string:
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1

                        if brace_count == 0:
                            objects.append(text[start:i+1])
                            used_ranges.append((start, i+1))
                            break

        # Sort by length (longer objects likely more complete)
        objects.sort(key=len, reverse=True)
        return objects

    def _parse_change_list(self, text: str) -> List[Dict[str, str]]:
        """
        Parse a list of changes from text.

        Handles bullet points, numbered lists, and structured items.
        """
        changes = []

        # Split into lines and process
        lines = text.split('\n')

        for line in lines:
            line = line.strip()

            # Skip empty lines
            if not line:
                continue

            # Check for bullet points or numbers
            if re.match(r'^[-*•·]\s+', line):
                change_text = re.sub(r'^[-*•·]\s+', '', line)
            elif re.match(r'^\d+[.)]\s+', line):
                change_text = re.sub(r'^\d+[.)]\s+', '', line)
            else:
                # Not a list item, skip or add as-is depending on context
                continue

            # Try to extract section and description
            if ':' in change_text:
                parts = change_text.split(':', 1)
                changes.append({
                    'section': parts[0].strip(),
                    'description': parts[1].strip() if len(parts) > 1 else ''
                })
            else:
                # No clear section/description split
                changes.append({
                    'section': 'General',
                    'description': change_text
                })

        return changes

    def _clean_json_string(self, json_str: str) -> str:
        """
        Clean common issues in JSON strings.

        Fixes:
        - Trailing commas
        - Single quotes (convert to double)
        - Unescaped newlines in strings
        - Comments
        """
        # Remove comments
        json_str = re.sub(r'//.*?\n', '', json_str)
        json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)

        # Fix trailing commas
        json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)

        # Fix unescaped newlines within string values
        # This is a simple approach: find strings and escape newlines within them
        def escape_newlines_in_strings(match):
            """Escape newlines within JSON string values."""
            content = match.group(1)
            # Replace actual newlines with escaped versions
            content = content.replace('\n', '\\n')
            content = content.replace('\r', '\\r')
            content = content.replace('\t', '\\t')
            return f'"{content}"'

        # Find and fix string values (basic approach - handles most cases)
        json_str = re.sub(r'"([^"]*)"', escape_newlines_in_strings, json_str)

        return json_str

    def _validate_and_complete(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate the parsed result and add missing required fields.

        Ensures the result has all expected fields with reasonable defaults.
        """
        # Required fields and defaults
        defaults = {
            'improved_prompt': '',
            'changes': [],
            'summary': 'Prompt improvements applied',
            'confidence': 5
        }

        # Add missing fields
        for key, default in defaults.items():
            if key not in result:
                result[key] = default
                logger.debug(f"Added missing field '{key}' with default value")

        # Validate types
        if not isinstance(result.get('changes'), list):
            result['changes'] = []

        if not isinstance(result.get('confidence'), (int, float)):
            try:
                result['confidence'] = int(result.get('confidence', 5))
            except (TypeError, ValueError):
                result['confidence'] = 5

        # Ensure confidence is in valid range
        result['confidence'] = max(0, min(10, result['confidence']))

        # Log successful parse
        logger.info(
            f"Successfully parsed response: "
            f"strategy={self.last_strategy_used}, "
            f"prompt_length={len(result.get('improved_prompt', ''))}, "
            f"changes={len(result.get('changes', []))}, "
            f"confidence={result.get('confidence')}"
        )

        return result

    def _create_error_response(self, error_msg: str, original_text: str) -> Dict[str, Any]:
        """
        Create an error response when all parsing fails.

        Includes debugging information to help diagnose the issue.
        """
        return {
            'improved_prompt': '',
            'changes': [],
            'summary': f"Error: {error_msg}",
            'confidence': 0,
            'error': error_msg,
            'parse_attempts': self.parse_attempts,
            'last_strategy': self.last_strategy_used,
            'original_response_preview': original_text[:500] if original_text else ''
        }

    def create_follow_up_prompt(self, original_response: str) -> str:
        """
        Create a follow-up prompt to request JSON formatting.

        Used when initial parsing fails and we need to ask Claude again.
        """
        return f"""Your previous response could not be parsed. Please provide your response in strict JSON format.

REQUIRED FORMAT (copy this structure exactly):
{{
  "improved_prompt": "PASTE THE COMPLETE IMPROVED PROMPT HERE",
  "changes": [
    {{"section": "Section name", "description": "What was changed"}},
    {{"section": "Another section", "description": "Another change"}}
  ],
  "summary": "Brief one-line summary of all improvements",
  "confidence": 8
}}

IMPORTANT:
1. The "improved_prompt" field must contain the COMPLETE improved prompt text
2. Use valid JSON syntax (double quotes, no trailing commas)
3. Ensure all strings are properly escaped
4. Do NOT include any text outside the JSON object
5. Do NOT wrap the JSON in markdown code blocks

Based on your previous response, please provide the improvements in the JSON format above.

Previous response preview:
{original_response[:1000]}"""