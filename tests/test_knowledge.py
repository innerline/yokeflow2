"""
Tests for Knowledge Layer

Tests for vault management, context engine, and auto-documentation.
"""

import pytest
import tempfile
import os
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock, patch, AsyncMock

from server.knowledge.vault_manager import (
    VaultManager,
    Note,
    SearchResult,
)
from server.knowledge.context_engine import (
    ContextEngine,
    ContextChunk,
    TaskContext,
)
from server.knowledge.auto_docs import (
    AutoDocumenter,
    DocSection,
    GeneratedDoc,
)


class TestNote:
    """Tests for Note dataclass."""

    def test_create_note(self):
        """Test creating a note."""
        note = Note(
            path="test/note.md",
            full_path="/vault/test/note.md",
            title="Test Note",
            content="# Test\n\nContent here"
        )
        assert note.path == "test/note.md"
        assert note.title == "Test Note"
        assert note.tags == []
        assert note.links == []

    def test_note_with_metadata(self):
        """Test note with metadata."""
        note = Note(
            path="test/note.md",
            full_path="/vault/test/note.md",
            title="Test",
            content="Content",
            tags=["python", "testing"],
            links=["other.md"]
        )
        assert note.tags == ["python", "testing"]
        assert note.links == ["other.md"]


class TestVaultManager:
    """Tests for VaultManager."""

    @pytest.fixture
    def temp_vault(self):
        """Create a temporary vault directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir) / "vault"
            vault_path.mkdir()

            # Create test notes
            (vault_path / "note1.md").write_text(
                "---\ntitle: First Note\ntags:\n  - test\n---\n\n# First Note\n\nContent here.\n\n[[note2]]"
            )
            (vault_path / "note2.md").write_text(
                "# Second Note\n\nMore content.\n\n#tag1 #tag2"
            )
            (vault_path / "subdir").mkdir()
            (vault_path / "subdir" / "note3.md").write_text(
                "# Nested Note\n\nNested content."
            )

            yield str(vault_path)

    def test_list_notes(self, temp_vault):
        """Test listing notes in vault."""
        manager = VaultManager(vault_path=temp_vault)
        notes = manager.list_notes()

        assert len(notes) == 3
        titles = [n.title for n in notes]
        assert "First Note" in titles
        assert "Second Note" in titles
        assert "Nested Note" in titles

    def test_list_notes_with_pattern(self, temp_vault):
        """Test listing notes with pattern filter."""
        manager = VaultManager(vault_path=temp_vault)
        notes = manager.list_notes(pattern="note1.md")

        assert len(notes) == 1
        assert notes[0].title == "First Note"

    def test_get_note(self, temp_vault):
        """Test getting a specific note."""
        manager = VaultManager(vault_path=temp_vault)
        note = manager.get_note("note1.md")

        assert note is not None
        assert note.title == "First Note"
        assert "Content here" in note.content
        assert "test" in note.tags

    def test_get_nonexistent_note(self, temp_vault):
        """Test getting a nonexistent note."""
        manager = VaultManager(vault_path=temp_vault)
        note = manager.get_note("nonexistent.md")

        assert note is None

    def test_search_notes(self, temp_vault):
        """Test searching notes."""
        manager = VaultManager(vault_path=temp_vault)
        results = manager.search("content")

        assert len(results) >= 1
        assert all("content" in r.note.content.lower() for r in results)

    def test_parse_frontmatter(self, temp_vault):
        """Test parsing YAML frontmatter."""
        manager = VaultManager(vault_path=temp_vault)
        note = manager.get_note("note1.md")

        assert note is not None
        assert note.frontmatter.get("title") == "First Note"
        assert "test" in note.frontmatter.get("tags", [])

    def test_extract_tags(self, temp_vault):
        """Test extracting inline tags."""
        manager = VaultManager(vault_path=temp_vault)
        note = manager.get_note("note2.md")

        assert note is not None
        assert "tag1" in note.tags
        assert "tag2" in note.tags

    def test_extract_links(self, temp_vault):
        """Test extracting wiki-style links."""
        manager = VaultManager(vault_path=temp_vault)
        note = manager.get_note("note1.md")

        assert note is not None
        assert "note2.md" in note.links

    def test_write_note(self, temp_vault):
        """Test writing a new note."""
        manager = VaultManager(vault_path=temp_vault)

        success = manager.write_note(
            note_path="new_note.md",
            content="# New Note\n\nFresh content.",
            frontmatter={"title": "New Note", "tags": ["new"]}
        )

        assert success is True
        note = manager.get_note("new_note.md")
        assert note is not None
        assert note.title == "New Note"

    def test_delete_note(self, temp_vault):
        """Test deleting a note."""
        manager = VaultManager(vault_path=temp_vault)

        # First verify note exists
        note = manager.get_note("note1.md")
        assert note is not None

        # Delete it
        success = manager.delete_note("note1.md")
        assert success is True

        # Verify it's gone
        note = manager.get_note("note1.md")
        assert note is None

    def test_find_related(self, temp_vault):
        """Test finding related notes via links."""
        manager = VaultManager(vault_path=temp_vault)
        related = manager.find_related("note1.md")

        # note1 links to note2
        assert len(related) >= 1
        paths = [n.path for n in related]
        assert "note2.md" in paths

    def test_get_stats(self, temp_vault):
        """Test getting vault statistics."""
        manager = VaultManager(vault_path=temp_vault)
        stats = manager.get_stats()

        assert stats["notes_count"] == 3
        assert stats["total_size_bytes"] > 0


class TestContextEngine:
    """Tests for ContextEngine."""

    @pytest.fixture
    def temp_vault(self):
        """Create a temporary vault."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir) / "vault"
            vault_path.mkdir()
            (vault_path / "python.md").write_text(
                "# Python Guide\n\nPython is a programming language.\n\n## Variables\n\nUse variables to store data."
            )
            (vault_path / "javascript.md").write_text(
                "# JavaScript Guide\n\nJavaScript runs in browsers."
            )
            yield str(vault_path)

    @pytest.fixture
    def engine(self, temp_vault):
        """Create context engine with temp vault."""
        vault_manager = VaultManager(vault_path=temp_vault)
        return ContextEngine(vault_manager=vault_manager)

    def test_extract_keywords(self, engine):
        """Test keyword extraction."""
        text = "Create a Python function that handles user authentication"
        keywords = engine._extract_keywords(text)

        assert "python" in keywords
        assert "function" in keywords
        assert "user" in keywords
        assert "authentication" in keywords
        # Stop words should be removed
        assert "a" not in keywords
        assert "that" not in keywords

    def test_build_query(self, engine):
        """Test building search query."""
        query = engine._build_query(
            task_description="Implement user login with Python",
            project_context="Web application"
        )

        assert len(query) > 0
        # Should contain keywords from both
        assert "python" in query.lower() or "user" in query.lower()

    def test_truncate_content(self, engine):
        """Test content truncation."""
        long_content = " ".join(["word"] * 1000)
        truncated = engine._truncate_content(long_content, max_words=100)

        assert len(truncated.split()) <= 103  # 100 words + "..."
        assert truncated.endswith("...")

    @pytest.mark.asyncio
    async def test_get_context_for_query(self, engine):
        """Test getting context for a query."""
        chunks = await engine.get_context_for_query("Python programming")

        assert len(chunks) >= 1
        # Should find the Python guide
        assert any("python" in c.content.lower() for c in chunks)

    @pytest.mark.asyncio
    async def test_get_context_for_task(self, engine):
        """Test getting context for a task."""
        context = await engine.get_context_for_task(
            task_id="task123",
            task_description="Write Python code for user authentication"
        )

        assert context.task_id == "task123"
        assert len(context.chunks) >= 1
        assert context.total_tokens > 0

    def test_format_context_compact(self, engine):
        """Test formatting context in compact style."""
        context = TaskContext(
            task_id="task1",
            task_description="Test task",
            chunks=[
                ContextChunk(
                    source="note.md",
                    content="Some content here",
                    relevance_score=0.9
                )
            ]
        )

        formatted = engine.format_context_for_prompt(context, style="compact")
        assert "Some content" in formatted

    def test_format_context_detailed(self, engine):
        """Test formatting context in detailed style."""
        context = TaskContext(
            task_id="task1",
            task_description="Test task",
            chunks=[
                ContextChunk(
                    source="note.md",
                    content="Some content here",
                    relevance_score=0.9,
                    metadata={"tags": ["test"]}
                )
            ]
        )

        formatted = engine.format_context_for_prompt(context, style="detailed")
        assert "Relevant Context" in formatted
        assert "note.md" in formatted


class TestAutoDocumenter:
    """Tests for AutoDocumenter."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir) / "project"
            project_path.mkdir()

            # Create some files
            (project_path / "README.md").write_text("# Test Project\n\nA test project.")
            (project_path / "main.py").write_text(
                '"""Main module."""\n\ndef main():\n    """Main function."""\n    pass'
            )
            (project_path / "package.json").write_text(
                '{"name": "test-project", "dependencies": {"react": "18.0.0"}}'
            )
            yield str(project_path)

    def test_analyze_structure(self, temp_project):
        """Test analyzing project structure."""
        doc = AutoDocumenter()
        structure = doc._analyze_structure(Path(temp_project))

        assert "JavaScript/TypeScript" in structure["languages"]
        assert "React" in structure["frameworks"]
        assert "Python" in structure["languages"]

    def test_generate_readme(self, temp_project):
        """Test generating README."""
        doc = AutoDocumenter()
        structure = doc._analyze_structure(Path(temp_project))
        readme = doc._generate_readme(
            Path(temp_project),
            "Test Project",
            structure
        )

        assert readme.title == "Test Project - README"
        assert len(readme.sections) > 0
        # Should have tech stack section
        assert any("Tech Stack" in s.title for s in readme.sections)

    def test_document_python_file(self, temp_project):
        """Test documenting Python file."""
        doc = AutoDocumenter()
        py_file = Path(temp_project) / "main.py"
        result = doc._document_python_file(py_file)

        assert "Main module" in result
        assert "main" in result.lower()

    def test_build_doc_content(self, temp_project):
        """Test building document content."""
        doc = AutoDocumenter()
        generated = GeneratedDoc(
            path="test.md",
            title="Test Doc",
            content="",
            sections=[
                DocSection(title="Section 1", content="Content 1", order=1),
                DocSection(title="Section 2", content="Content 2", order=2),
            ]
        )

        content = doc._build_doc_content(generated)
        assert "# Test Doc" in content
        assert "Section 1" in content
        assert "Content 1" in content
