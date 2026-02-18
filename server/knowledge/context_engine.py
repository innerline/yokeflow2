"""
Context Engine
==============

Semantic search and context retrieval for YokeFlow.

Features:
- Semantic search using embeddings
- Context retrieval for tasks
- Integration with LLM provider routing
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from server.utils.logging import get_logger
from server.knowledge.vault_manager import VaultManager, Note, SearchResult

logger = get_logger(__name__)


@dataclass
class ContextChunk:
    """A chunk of context for a task."""
    source: str  # Note path or source identifier
    content: str
    relevance_score: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskContext:
    """Context gathered for a specific task."""
    task_id: str
    task_description: str
    chunks: List[ContextChunk] = field(default_factory=list)
    total_tokens: int = 0
    sources: List[str] = field(default_factory=list)


class ContextEngine:
    """
    Engine for retrieving relevant context for tasks.

    Uses the VaultManager to search notes and the LLM router
    to determine which provider to use for embeddings.
    """

    def __init__(
        self,
        vault_manager: Optional[VaultManager] = None,
        max_chunks: int = 10,
        max_chunk_tokens: int = 500,
        max_total_tokens: int = 4000,
    ):
        """
        Initialize the context engine.

        Args:
            vault_manager: VaultManager instance
            max_chunks: Maximum number of chunks to retrieve
            max_chunk_tokens: Maximum tokens per chunk
            max_total_tokens: Maximum total tokens for context
        """
        self.vault_manager = vault_manager or VaultManager()
        self.max_chunks = max_chunks
        self.max_chunk_tokens = max_chunk_tokens
        self.max_total_tokens = max_total_tokens

        logger.info(
            "knowledge.context_engine.initialized",
            max_chunks=max_chunks,
            max_total_tokens=max_total_tokens
        )

    async def get_context_for_task(
        self,
        task_id: str,
        task_description: str,
        project_context: Optional[str] = None,
        vault_type: str = "default"
    ) -> TaskContext:
        """
        Get relevant context for a task.

        Args:
            task_id: Task identifier
            task_description: Description of the task
            project_context: Additional project context
            vault_type: 'default', 'personal', or 'agents'

        Returns:
            TaskContext with relevant chunks
        """
        context = TaskContext(
            task_id=task_id,
            task_description=task_description
        )

        # Build search query from task description
        query = self._build_query(task_description, project_context)

        # Search vault
        results = self.vault_manager.search(
            query=query,
            vault_type=vault_type,
            limit=self.max_chunks
        )

        # Convert results to chunks
        for result in results:
            chunk = self._result_to_chunk(result)
            if chunk:
                context.chunks.append(chunk)
                context.sources.append(result.note.path)

        # Calculate token estimate
        context.total_tokens = sum(
            len(chunk.content.split()) // 4  # Rough token estimate
            for chunk in context.chunks
        )

        # Truncate if over limit
        while context.total_tokens > self.max_total_tokens and context.chunks:
            removed = context.chunks.pop()
            context.sources.remove(removed.source)
            context.total_tokens -= len(removed.content.split()) // 4

        logger.info(
            "knowledge.context_engine.retrieved",
            task_id=task_id,
            chunks=len(context.chunks),
            tokens=context.total_tokens
        )

        return context

    async def get_context_for_query(
        self,
        query: str,
        vault_type: str = "default",
        include_related: bool = True
    ) -> List[ContextChunk]:
        """
        Get context for a general query.

        Args:
            query: Search query
            vault_type: 'default', 'personal', or 'agents'
            include_related: Whether to include related notes

        Returns:
            List of ContextChunks
        """
        chunks = []

        # Search vault
        results = self.vault_manager.search(
            query=query,
            vault_type=vault_type,
            limit=self.max_chunks
        )

        for result in results:
            chunk = self._result_to_chunk(result)
            if chunk:
                chunks.append(chunk)

        # Include related notes if requested
        if include_related and results:
            # Get related notes for top result
            top_note = results[0].note
            related = self.vault_manager.find_related(
                top_note.path,
                vault_type=vault_type,
                max_depth=1
            )

            for note in related[:3]:  # Limit related notes
                chunk = ContextChunk(
                    source=note.path,
                    content=self._truncate_content(note.content),
                    relevance_score=0.5,  # Lower score for related
                    metadata={
                        "type": "related",
                        "title": note.title,
                        "tags": note.tags
                    }
                )
                chunks.append(chunk)

        logger.info(
            "knowledge.context_engine.query",
            query=query[:50],
            chunks=len(chunks)
        )

        return chunks

    async def index_project_knowledge(
        self,
        project_id: str,
        project_path: str,
        vault_type: str = "agents"
    ) -> Dict[str, Any]:
        """
        Index a project's documentation into the knowledge vault.

        Args:
            project_id: Project identifier
            project_path: Path to project root
            vault_type: Target vault type

        Returns:
            Indexing statistics
        """
        from pathlib import Path

        project_dir = Path(project_path)
        if not project_dir.exists():
            return {"error": "Project path not found"}

        # Find documentation files
        doc_patterns = ["**/*.md", "**/README*", "**/docs/**"]
        doc_files = []

        for pattern in doc_patterns:
            doc_files.extend(project_dir.glob(pattern))

        # Remove duplicates
        doc_files = list(set(doc_files))

        indexed = 0
        errors = 0

        for doc_file in doc_files:
            if not doc_file.is_file():
                continue

            try:
                content = doc_file.read_text(encoding="utf-8")

                # Create note path
                rel_path = doc_file.relative_to(project_dir)
                note_path = f"projects/{project_id}/{rel_path}"

                # Write to vault
                success = self.vault_manager.write_note(
                    note_path=note_path,
                    content=content,
                    vault_type=vault_type,
                    frontmatter={
                        "project_id": project_id,
                        "indexed_at": str(doc_file.stat().st_mtime),
                        "source_type": "project_doc"
                    }
                )

                if success:
                    indexed += 1
                else:
                    errors += 1

            except Exception as e:
                logger.warning(
                    "knowledge.context_engine.index_error",
                    file=str(doc_file),
                    error=str(e)
                )
                errors += 1

        logger.info(
            "knowledge.context_engine.indexed",
            project_id=project_id,
            indexed=indexed,
            errors=errors
        )

        return {
            "project_id": project_id,
            "indexed": indexed,
            "errors": errors,
            "total_files": len(doc_files)
        }

    def _build_query(
        self,
        task_description: str,
        project_context: Optional[str] = None
    ) -> str:
        """Build a search query from task and context."""
        # Extract key terms from task description
        query_parts = []

        # Add task keywords
        keywords = self._extract_keywords(task_description)
        query_parts.extend(keywords[:5])  # Limit keywords

        # Add project context keywords
        if project_context:
            context_keywords = self._extract_keywords(project_context)
            query_parts.extend(context_keywords[:3])

        return " ".join(query_parts)

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract key terms from text."""
        # Simple keyword extraction
        # Remove common words
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "must", "shall",
            "can", "need", "to", "of", "in", "for", "on", "with", "at",
            "by", "from", "as", "into", "through", "during", "before",
            "after", "above", "below", "between", "under", "again",
            "further", "then", "once", "here", "there", "when", "where",
            "why", "how", "all", "each", "few", "more", "most", "other",
            "some", "such", "no", "nor", "not", "only", "own", "same",
            "so", "than", "too", "very", "just", "and", "but", "if",
            "or", "because", "until", "while", "this", "that", "these",
            "those", "it", "its", "they", "them", "their", "what", "which",
            "who", "whom", "we", "us", "our", "you", "your", "he", "him",
            "his", "she", "her", "i", "me", "my"
        }

        # Tokenize and filter
        import re
        words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
        keywords = [w for w in words if w not in stop_words]

        # Count and sort by frequency
        from collections import Counter
        word_counts = Counter(keywords)

        return [word for word, _ in word_counts.most_common(10)]

    def _result_to_chunk(self, result: SearchResult) -> Optional[ContextChunk]:
        """Convert a SearchResult to a ContextChunk."""
        if not result.note.content:
            return None

        content = self._truncate_content(result.note.content)

        return ContextChunk(
            source=result.note.path,
            content=content,
            relevance_score=result.score,
            metadata={
                "type": "search_result",
                "title": result.note.title,
                "tags": result.note.tags,
                "matches": result.matches[:3]
            }
        )

    def _truncate_content(self, content: str, max_words: int = 500) -> str:
        """Truncate content to max words."""
        words = content.split()
        if len(words) <= max_words:
            return content

        return " ".join(words[:max_words]) + "..."

    def format_context_for_prompt(
        self,
        context: TaskContext,
        style: str = "default"
    ) -> str:
        """
        Format context for inclusion in an LLM prompt.

        Args:
            context: TaskContext to format
            style: Formatting style ('default', 'compact', 'detailed')

        Returns:
            Formatted context string
        """
        if not context.chunks:
            return ""

        if style == "compact":
            # Minimal formatting
            parts = []
            for chunk in context.chunks:
                parts.append(f"- {chunk.content[:200]}...")
            return "\n".join(parts)

        elif style == "detailed":
            # Detailed formatting with metadata
            parts = ["## Relevant Context\n"]
            for i, chunk in enumerate(context.chunks, 1):
                parts.append(f"### Source {i}: {chunk.source}")
                parts.append(f"Relevance: {chunk.relevance_score:.2f}")
                if chunk.metadata.get("tags"):
                    parts.append(f"Tags: {', '.join(chunk.metadata['tags'])}")
                parts.append(f"\n{chunk.content}\n")
            return "\n".join(parts)

        else:
            # Default formatting
            parts = ["## Relevant Context from Knowledge Base\n"]
            for chunk in context.chunks:
                parts.append(f"**{chunk.source}**")
                parts.append(chunk.content)
                parts.append("")
            return "\n".join(parts)
