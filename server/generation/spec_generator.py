"""
AI-Powered Specification Generator
===================================

Generates structured application specifications from natural language descriptions
using Claude AI. Outputs markdown format with required sections for YokeFlow projects.
"""

import asyncio
import json
import logging
import os
from typing import Optional, Dict, Any, List, AsyncGenerator
from pathlib import Path
from dotenv import load_dotenv

from anthropic import AsyncAnthropic
from server.utils.config import Config
from server.utils.logging import get_logger

# Load environment variables from .env file
_current_file = Path(__file__)
_generation_dir = _current_file.parent
_server_dir = _generation_dir.parent
_project_root = _server_dir.parent
_env_file = _project_root / ".env"

# Load the .env file
load_dotenv(dotenv_path=_env_file)

logger = get_logger(__name__)


class SpecGenerator:
    """Generate application specifications using Claude AI."""

    # Template for the generated specification
    SPEC_TEMPLATE = """# {project_name}

## Overview
{overview}

## Tech Stack
{tech_stack}

## Frontend
{frontend}

## Backend
{backend}

## Database
{database}

## Additional Features
{features}

## Development Notes
{notes}
"""

    # Prompt template for Claude
    GENERATION_PROMPT = """You are an expert software architect helping to create a detailed application specification.

Based on the following description, generate a comprehensive specification document for a web application.

Description: {description}

{context_section}

Please generate a detailed specification in markdown format with the following sections:
1. **Overview** - A clear description of what the application does and its main purpose
2. **Tech Stack** - The technologies to be used (frameworks, libraries, tools)
3. **Frontend** - Detailed frontend requirements, components, and user interface
4. **Backend** - API endpoints, business logic, and server-side functionality
5. **Database** - Schema design, tables, relationships, and data models
6. **Additional Features** - Authentication, security, performance, deployment considerations
7. **Development Notes** - Implementation suggestions and best practices

Make the specification detailed enough that a developer could implement the application from it.
Focus on modern web development best practices and use popular, well-maintained technologies.

Return ONLY the markdown content, no explanations or meta-commentary."""

    CONTEXT_TEMPLATE = """
Context Files Provided:
{context_summaries}

Please incorporate insights from these context files into the specification where relevant.
"""

    def __init__(self, config: Optional[Config] = None):
        """Initialize the spec generator.

        Args:
            config: Optional configuration object
        """
        self.config = config or Config()
        self.client = None
        self._ensure_client()

        # Model selection - use Sonnet for cost efficiency
        # Access the generation model if it exists in config
        self.model = "claude-3-5-sonnet-20241022"  # Default model
        if hasattr(self.config, 'generation') and hasattr(self.config.generation, 'model'):
            self.model = self.config.generation.model

    def _ensure_client(self):
        """Ensure the Anthropic client is initialized."""
        if not self.client:
            # Get API key from environment variable
            api_key = os.getenv("CLAUDE_CODE_OAUTH_TOKEN")
            if not api_key:
                raise ValueError(
                    "CLAUDE_CODE_OAUTH_TOKEN not configured. "
                    "Please set your Anthropic API key in the environment variables."
                )
            self.client = AsyncAnthropic(api_key=api_key)

    async def generate_spec(
        self,
        description: str,
        project_name: str,
        context_files: Optional[List[Dict[str, str]]] = None,
        stream: bool = True
    ) -> AsyncGenerator[str, None]:
        """Generate a specification from a natural language description.

        Args:
            description: Natural language description of the application
            project_name: Name of the project
            context_files: Optional list of context file summaries
            stream: Whether to stream the response

        Yields:
            Chunks of the generated specification (if streaming)

        Returns:
            Complete specification (if not streaming)
        """
        self._ensure_client()

        # Build context section if files provided
        context_section = ""
        if context_files:
            summaries = []
            for file_info in context_files:
                summaries.append(f"- **{file_info['name']}**: {file_info.get('summary', 'No summary available')}")
            context_section = self.CONTEXT_TEMPLATE.format(
                context_summaries="\n".join(summaries)
            )

        # Build the prompt
        prompt = self.GENERATION_PROMPT.format(
            description=description,
            context_section=context_section
        )

        logger.info(f"Generating specification for project: {project_name}")
        logger.debug(f"Description: {description[:200]}...")

        try:
            if stream:
                # Stream the response
                async with self.client.messages.stream(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=8000,
                    temperature=0.7
                ) as stream_response:
                    async for chunk in stream_response.text_stream:
                        yield chunk
            else:
                # Get complete response
                response = await self.client.messages.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=8000,
                    temperature=0.7
                )
                # Yield the complete response as a single chunk
                yield response.content[0].text

        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "authentication_error" in error_msg:
                logger.error(
                    "Authentication failed. Please ensure CLAUDE_CODE_OAUTH_TOKEN "
                    "contains a valid Anthropic API key. You may need to use a standard "
                    "API key (sk-ant-api...) instead of an OAuth token for direct API calls."
                )
                raise ValueError(
                    "Invalid API key. Please check your CLAUDE_CODE_OAUTH_TOKEN in .env file. "
                    "For AI generation, you need a valid Anthropic API key."
                )
            logger.error(f"Error generating specification: {error_msg}")
            raise

    async def generate_spec_sections(
        self,
        description: str,
        project_name: str,
        context_files: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, str]:
        """Generate specification and parse into sections.

        Args:
            description: Natural language description
            project_name: Name of the project
            context_files: Optional context file summaries

        Returns:
            Dictionary with parsed sections
        """
        # Generate the complete specification
        full_spec = ""
        async for chunk in self.generate_spec(description, project_name, context_files, stream=True):
            full_spec += chunk

        # Parse into sections
        sections = self._parse_markdown_sections(full_spec)
        sections["project_name"] = project_name

        return sections

    def _parse_markdown_sections(self, markdown: str) -> Dict[str, str]:
        """Parse markdown into sections based on headers.

        Args:
            markdown: Markdown content to parse

        Returns:
            Dictionary of section names to content
        """
        sections = {}
        current_section = None
        current_content = []

        for line in markdown.split("\n"):
            # Check for main headers
            if line.startswith("## "):
                # Save previous section
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()

                # Start new section
                current_section = line[3:].strip().lower().replace(" ", "_")
                current_content = []
            elif current_section:
                current_content.append(line)
            elif line.startswith("# "):
                # Project title
                sections["title"] = line[2:].strip()

        # Save last section
        if current_section:
            sections[current_section] = "\n".join(current_content).strip()

        return sections

    async def enhance_spec(self, existing_spec: str, feedback: str) -> str:
        """Enhance an existing specification based on user feedback.

        Args:
            existing_spec: Current specification markdown
            feedback: User feedback for improvements

        Returns:
            Enhanced specification
        """
        self._ensure_client()

        prompt = f"""You are helping to improve an application specification.

Current Specification:
{existing_spec}

User Feedback:
{feedback}

Please update the specification to address the feedback while maintaining the same markdown format and section structure.
Return ONLY the updated markdown content."""

        try:
            response = await self.client.messages.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=8000,
                temperature=0.7
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Error enhancing specification: {str(e)}")
            raise

    async def generate_summary(self, content: str, max_length: int = 500) -> str:
        """Generate a concise summary of content.

        Args:
            content: Content to summarize
            max_length: Maximum length of summary

        Returns:
            Concise summary
        """
        self._ensure_client()

        # Use Haiku for summaries (cheaper)
        summary_model = self.config.get("generation.summary_model", "claude-3-haiku-20240307")

        prompt = f"""Summarize the following content in {max_length} characters or less.
Focus on the key technical details and purpose.

Content:
{content[:5000]}  # Limit input to avoid token limits

Return ONLY the summary, no explanations."""

        try:
            response = await self.client.messages.create(
                model=summary_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.5
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            # Fallback to simple truncation
            return content[:max_length] + "..." if len(content) > max_length else content