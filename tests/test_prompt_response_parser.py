"""
Test suite for the PromptResponseParser.

Tests various response formats to ensure robust parsing.
"""

import pytest
import json
from server.quality.prompt_response_parser import PromptResponseParser


class TestPromptResponseParser:
    """Test the robust response parser."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = PromptResponseParser()

    def test_parse_json_code_block(self):
        """Test parsing JSON in code blocks."""
        response = '''Here's the improved prompt:

```json
{
  "improved_prompt": "# Enhanced Prompt\n\nThis is the improved version.",
  "changes": [
    {"section": "Introduction", "description": "Added clarity"}
  ],
  "summary": "Enhanced clarity and structure",
  "confidence": 8
}
```

That should address the issues.'''

        result = self.parser.parse_improvement_response(response)

        assert result['confidence'] == 8
        assert "Enhanced Prompt" in result['improved_prompt']
        assert len(result['changes']) == 1
        assert result['changes'][0]['section'] == "Introduction"
        assert self.parser.last_strategy_used == "json_code_block"

    def test_parse_direct_json(self):
        """Test parsing direct JSON object."""
        response = '''{
  "improved_prompt": "# Direct JSON Prompt\n\nContent here.",
  "changes": [],
  "summary": "Direct JSON response",
  "confidence": 7
}'''

        result = self.parser.parse_improvement_response(response)

        assert result['confidence'] == 7
        assert "Direct JSON Prompt" in result['improved_prompt']
        assert self.parser.last_strategy_used == "direct_json"

    def test_parse_markdown_structure(self):
        """Test parsing markdown-structured response."""
        response = '''## Improved Prompt

```markdown
# Better Prompt

This is a much better prompt with:
- Clear instructions
- Better examples
- Enhanced structure
```

## Changes Made

- **Introduction**: Added clearer context and purpose
- **Examples Section**: Included more diverse examples
- **Error Handling**: Added guidance for edge cases

## Summary

Enhanced the prompt with better structure, clearer instructions, and more comprehensive examples.'''

        result = self.parser.parse_improvement_response(response)

        assert result['improved_prompt']
        assert "Better Prompt" in result['improved_prompt']
        assert len(result['changes']) == 3
        assert result['summary']
        assert result['confidence'] == 7  # Default for markdown
        assert self.parser.last_strategy_used == "markdown_extraction"

    def test_parse_structured_text(self):
        """Test parsing structured text without markdown."""
        response = '''improved_prompt:
# Structured Text Prompt

This is the improved version with better formatting.

changes:
- Section A: Made it clearer
- Section B: Added examples
- Section C: Fixed typos

summary: Improved clarity and examples

confidence: 6'''

        result = self.parser.parse_improvement_response(response)

        assert "Structured Text Prompt" in result['improved_prompt']
        assert result['confidence'] == 6
        assert self.parser.last_strategy_used == "structured_text"

    def test_parse_malformed_json(self):
        """Test handling of malformed JSON with recovery."""
        response = '''```json
{
  "improved_prompt": "# Fixed Prompt",
  "changes": [
    {"section": "Main", "description": "Fixed"},  // Comment should be removed
  ],  // Trailing comma should be fixed
  "summary": "Fixed issues",
  "confidence": 5,
}
```'''

        result = self.parser.parse_improvement_response(response)

        # Parser should clean and parse successfully
        assert result['improved_prompt']
        assert result['confidence'] == 5

    def test_empty_response(self):
        """Test handling of empty response."""
        response = ""

        result = self.parser.parse_improvement_response(response)

        assert result['confidence'] == 0
        assert result['error'] == "Empty response"
        assert result['improved_prompt'] == ''

    def test_no_improved_prompt_field(self):
        """Test handling when improved_prompt is missing."""
        response = '''```json
{
  "changes": [{"section": "Test", "description": "Changed"}],
  "summary": "Made changes",
  "confidence": 7
}
```'''

        result = self.parser.parse_improvement_response(response)

        # Should add default improved_prompt
        assert 'improved_prompt' in result
        assert result['improved_prompt'] == ''  # Default empty

    def test_mixed_format_with_code_blocks(self):
        """Test parsing response with multiple code blocks."""
        response = '''I'll improve the prompt now.

First, here's some context:

```python
# This is not the JSON we want
def example():
    pass
```

Now here's the actual improvement:

```json
{
  "improved_prompt": "# Multi-block Response\n\nContent",
  "changes": [],
  "summary": "Handled multiple code blocks",
  "confidence": 9
}
```'''

        result = self.parser.parse_improvement_response(response)

        assert result['confidence'] == 9
        assert "Multi-block Response" in result['improved_prompt']

    def test_prose_response_with_sections(self):
        """Test parsing prose response with clear sections."""
        response = '''Let me improve this prompt for you.

## Updated Prompt

```markdown
# Improved Agent Prompt

This prompt now includes:
1. Better error handling
2. Clearer instructions
3. More examples
```

### What Changed

I made the following improvements:
- Error Handling: Added comprehensive error recovery guidance
- Instructions: Clarified ambiguous sections
- Examples: Added 5 new examples for edge cases

### Summary

The prompt is now more robust and handles edge cases better.'''

        result = self.parser.parse_improvement_response(response)

        assert result['improved_prompt']
        assert "Improved Agent Prompt" in result['improved_prompt']
        assert len(result['changes']) == 3
        assert result['confidence'] == 7

    def test_extract_changes_from_bullets(self):
        """Test extraction of changes from bullet lists."""
        text = """
- Introduction: Made it clearer and more concise
- Error Handling: Added comprehensive error recovery
- Examples Section: Included 10 new examples
* Tool Usage: Fixed incorrect tool references
• Verification: Added mandatory checks
"""

        changes = self.parser._parse_change_list(text)

        assert len(changes) == 5
        assert changes[0]['section'] == 'Introduction'
        assert changes[1]['section'] == 'Error Handling'
        assert changes[4]['section'] == 'Verification'

    def test_extract_changes_from_numbered_list(self):
        """Test extraction of changes from numbered lists."""
        text = """
1. First Section: Updated with new content
2. Second Section: Removed outdated info
3) Third Section: Added examples
4. Fourth Section: Fixed formatting
"""

        changes = self.parser._parse_change_list(text)

        assert len(changes) == 4
        assert changes[0]['section'] == 'First Section'
        assert changes[2]['section'] == 'Third Section'

    def test_json_extraction_patterns(self):
        """Test various JSON extraction patterns."""
        test_cases = [
            ('```json\n{"test": 1}\n```', {"test": 1}),
            ('```\n{"test": 2}\n```', {"test": 2}),
            ('<json>{"test": 3}</json>', {"test": 3}),
            ('<code>{"test": 4}</code>', {"test": 4}),
        ]

        for response, expected in test_cases:
            result = self.parser._try_json_code_block(response)
            assert result == expected

    def test_balanced_braces_extraction(self):
        """Test extraction of JSON with nested objects."""
        text = 'Some text {"outer": {"inner": {"deep": "value"}}} more text'

        objects = self.parser._extract_json_objects(text)

        assert len(objects) == 1
        parsed = json.loads(objects[0])
        assert parsed['outer']['inner']['deep'] == 'value'

    def test_create_follow_up_prompt(self):
        """Test follow-up prompt generation."""
        original = "This was the original response that failed"

        follow_up = self.parser.create_follow_up_prompt(original)

        assert "strict JSON format" in follow_up
        assert "improved_prompt" in follow_up
        assert original in follow_up

    def test_confidence_validation(self):
        """Test confidence score validation and bounds."""
        test_cases = [
            ('{"improved_prompt": "test", "confidence": 15}', 10),  # Over max
            ('{"improved_prompt": "test", "confidence": -5}', 0),   # Under min
            ('{"improved_prompt": "test", "confidence": "7"}', 7),  # String to int
            ('{"improved_prompt": "test"}', 5),  # Missing, uses default
        ]

        for response, expected_confidence in test_cases:
            result = self.parser.parse_improvement_response(response)
            assert result['confidence'] == expected_confidence

    def test_parse_attempts_tracking(self):
        """Test that parse attempts are tracked correctly."""
        # This will try multiple strategies before failing
        response = "This is just plain text with no structure"

        result = self.parser.parse_improvement_response(response)

        assert result['confidence'] == 0
        assert result['parse_attempts'] > 0
        assert 'error' in result


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])