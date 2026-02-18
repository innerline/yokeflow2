"""
Vault Manager
=============

Manage and query Obsidian vaults for YokeFlow knowledge integration.

Features:
- List notes in a vault
- Search notes by content
- Read/write notes
- Find related notes via links
"""

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import fnmatch

from server.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Note:
    """Represents an Obsidian note."""
    path: str  # Relative path within vault
    full_path: str  # Absolute path
    title: str
    content: str
    frontmatter: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    links: List[str] = field(default_factory=list)  # Linked note paths
    backlinks: List[str] = field(default_factory=list)  # Notes linking to this
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    size_bytes: int = 0


@dataclass
class SearchResult:
    """Result of a vault search."""
    note: Note
    score: float
    matches: List[str] = field(default_factory=list)  # Matched snippets


class VaultManager:
    """
    Manager for Obsidian vault operations.

    Supports both personal vaults (LMStudio-routed) and agent vaults
    (Claude-routed) based on the vault path configuration.
    """

    def __init__(
        self,
        vault_path: Optional[str] = None,
        personal_vault_path: Optional[str] = None,
        agents_vault_path: Optional[str] = None,
    ):
        """
        Initialize the vault manager.

        Args:
            vault_path: Default vault path
            personal_vault_path: Path to personal vault (uses LMStudio)
            agents_vault_path: Path to agents vault (uses Claude)
        """
        self.vault_path = vault_path or os.getenv("OBSIDIAN_VAULT_PATH")
        self.personal_vault_path = personal_vault_path or os.getenv("PERSONAL_VAULT_PATH")
        self.agents_vault_path = agents_vault_path or os.getenv("AGENTS_VAULT_PATH")

        # Cache for vault indexes
        self._index: Dict[str, Dict[str, Note]] = {}  # vault_path -> {note_path -> Note}

        if self.vault_path:
            logger.info("knowledge.vault.initialized", path=self.vault_path)

    def _get_vault_path(self, vault_type: str = "default") -> Optional[Path]:
        """Get the vault path based on type."""
        if vault_type == "personal":
            return Path(self.personal_vault_path) if self.personal_vault_path else None
        elif vault_type == "agents":
            return Path(self.agents_vault_path) if self.agents_vault_path else None
        else:
            return Path(self.vault_path) if self.vault_path else None

    def list_notes(
        self,
        vault_type: str = "default",
        pattern: str = "*.md",
        limit: int = 100
    ) -> List[Note]:
        """
        List notes in a vault.

        Args:
            vault_type: 'default', 'personal', or 'agents'
            pattern: Glob pattern for filtering (default: *.md)
            limit: Maximum number of notes to return

        Returns:
            List of Note objects
        """
        vault_path = self._get_vault_path(vault_type)
        if not vault_path or not vault_path.exists():
            logger.warning("knowledge.vault.not_found", vault_type=vault_type)
            return []

        notes = []
        for md_file in vault_path.rglob(pattern):
            if md_file.is_file():
                try:
                    note = self._read_note(md_file, vault_path)
                    notes.append(note)
                    if len(notes) >= limit:
                        break
                except Exception as e:
                    logger.warning(
                        "knowledge.vault.read_error",
                        file=str(md_file),
                        error=str(e)
                    )

        logger.info(
            "knowledge.vault.listed",
            vault_type=vault_type,
            count=len(notes)
        )
        return notes

    def get_note(
        self,
        note_path: str,
        vault_type: str = "default"
    ) -> Optional[Note]:
        """
        Get a specific note by path.

        Args:
            note_path: Relative path within vault
            vault_type: 'default', 'personal', or 'agents'

        Returns:
            Note object or None
        """
        vault_path = self._get_vault_path(vault_type)
        if not vault_path:
            return None

        full_path = vault_path / note_path
        if not full_path.exists():
            return None

        try:
            return self._read_note(full_path, vault_path)
        except Exception as e:
            logger.error(
                "knowledge.vault.get_note_error",
                path=note_path,
                error=str(e)
            )
            return None

    def search(
        self,
        query: str,
        vault_type: str = "default",
        case_sensitive: bool = False,
        limit: int = 20
    ) -> List[SearchResult]:
        """
        Search notes by content.

        Args:
            query: Search query
            vault_type: 'default', 'personal', or 'agents'
            case_sensitive: Whether search is case-sensitive
            limit: Maximum results to return

        Returns:
            List of SearchResult objects
        """
        vault_path = self._get_vault_path(vault_type)
        if not vault_path or not vault_path.exists():
            return []

        results = []
        query_lower = query.lower() if not case_sensitive else query

        for md_file in vault_path.rglob("*.md"):
            if not md_file.is_file():
                continue

            try:
                note = self._read_note(md_file, vault_path)
                content_lower = note.content.lower() if not case_sensitive else note.content

                # Simple text search
                if query_lower in content_lower:
                    # Find matching snippets
                    matches = []
                    lines = note.content.split("\n")
                    for line in lines:
                        line_check = line.lower() if not case_sensitive else line
                        if query_lower in line_check:
                            matches.append(line.strip())

                    # Calculate simple score based on match count
                    score = len(matches) / max(len(note.content.split()), 1)

                    results.append(SearchResult(
                        note=note,
                        score=score,
                        matches=matches[:5]  # Limit matches
                    ))

            except Exception as e:
                logger.warning(
                    "knowledge.vault.search_error",
                    file=str(md_file),
                    error=str(e)
                )

        # Sort by score and limit
        results.sort(key=lambda r: r.score, reverse=True)
        results = results[:limit]

        logger.info(
            "knowledge.vault.search",
            vault_type=vault_type,
            query=query,
            results=len(results)
        )

        return results

    def find_related(
        self,
        note_path: str,
        vault_type: str = "default",
        max_depth: int = 2
    ) -> List[Note]:
        """
        Find notes related to a given note via links.

        Args:
            note_path: Relative path of the source note
            vault_type: 'default', 'personal', or 'agents'
            max_depth: Maximum depth to traverse links

        Returns:
            List of related Note objects
        """
        vault_path = self._get_vault_path(vault_type)
        if not vault_path:
            return []

        note = self.get_note(note_path, vault_type)
        if not note:
            return []

        related = []
        visited = {note_path}

        # BFS traversal of links
        queue = [(link, 1) for link in note.links]
        while queue:
            current_path, depth = queue.pop(0)

            if current_path in visited or depth > max_depth:
                continue

            visited.add(current_path)
            related_note = self.get_note(current_path, vault_type)

            if related_note:
                related.append(related_note)

                # Add links from this note
                if depth < max_depth:
                    for link in related_note.links:
                        if link not in visited:
                            queue.append((link, depth + 1))

        logger.info(
            "knowledge.vault.find_related",
            note_path=note_path,
            related_count=len(related)
        )

        return related

    def write_note(
        self,
        note_path: str,
        content: str,
        vault_type: str = "default",
        frontmatter: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Write a note to the vault.

        Args:
            note_path: Relative path within vault
            content: Note content (Markdown)
            vault_type: 'default', 'personal', or 'agents'
            frontmatter: Optional YAML frontmatter

        Returns:
            True if successful
        """
        vault_path = self._get_vault_path(vault_type)
        if not vault_path:
            logger.error("knowledge.vault.no_vault_path")
            return False

        full_path = vault_path / note_path

        # Create parent directories
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Build content with frontmatter
        if frontmatter:
            import yaml
            fm_str = yaml.dump(frontmatter, default_flow_style=False)
            full_content = f"---\n{fm_str}---\n\n{content}"
        else:
            full_content = content

        try:
            full_path.write_text(full_content, encoding="utf-8")
            logger.info(
                "knowledge.vault.wrote_note",
                path=note_path,
                vault_type=vault_type
            )
            return True
        except Exception as e:
            logger.error(
                "knowledge.vault.write_error",
                path=note_path,
                error=str(e)
            )
            return False

    def delete_note(
        self,
        note_path: str,
        vault_type: str = "default"
    ) -> bool:
        """
        Delete a note from the vault.

        Args:
            note_path: Relative path within vault
            vault_type: 'default', 'personal', or 'agents'

        Returns:
            True if successful
        """
        vault_path = self._get_vault_path(vault_type)
        if not vault_path:
            return False

        full_path = vault_path / note_path

        try:
            if full_path.exists():
                full_path.unlink()
                logger.info(
                    "knowledge.vault.deleted_note",
                    path=note_path,
                    vault_type=vault_type
                )
                return True
        except Exception as e:
            logger.error(
                "knowledge.vault.delete_error",
                path=note_path,
                error=str(e)
            )

        return False

    def _read_note(self, full_path: Path, vault_path: Path) -> Note:
        """Read and parse a note file."""
        content = full_path.read_text(encoding="utf-8")
        stat = full_path.stat()

        # Parse frontmatter
        frontmatter = {}
        body = content

        if content.startswith("---\n"):
            parts = content.split("---\n", 2)
            if len(parts) >= 3:
                import yaml
                try:
                    frontmatter = yaml.safe_load(parts[1]) or {}
                except yaml.YAMLError:
                    pass
                body = parts[2]

        # Extract title
        title = frontmatter.get("title")
        if not title:
            # Try to get from first heading
            heading_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
            if heading_match:
                title = heading_match.group(1)
            else:
                title = full_path.stem

        # Extract tags
        tags = frontmatter.get("tags", [])
        if isinstance(tags, str):
            tags = [tags]

        # Also extract inline tags
        inline_tags = re.findall(r"#(\w+)", body)
        tags = list(set(tags + inline_tags))

        # Extract wiki-style links [[note-name]]
        links = re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", body)
        # Normalize links to .md paths
        links = [f"{link}.md" if not link.endswith(".md") else link for link in links]

        # Calculate relative path
        rel_path = str(full_path.relative_to(vault_path))

        return Note(
            path=rel_path,
            full_path=str(full_path),
            title=title,
            content=body.strip(),
            frontmatter=frontmatter,
            tags=tags,
            links=links,
            created_at=datetime.fromtimestamp(stat.st_ctime),
            modified_at=datetime.fromtimestamp(stat.st_mtime),
            size_bytes=stat.st_size,
        )

    def get_stats(self, vault_type: str = "default") -> Dict[str, Any]:
        """
        Get statistics about a vault.

        Args:
            vault_type: 'default', 'personal', or 'agents'

        Returns:
            Dict with vault statistics
        """
        vault_path = self._get_vault_path(vault_type)
        if not vault_path or not vault_path.exists():
            return {"error": "Vault not found"}

        notes = self.list_notes(vault_type, limit=10000)
        total_size = sum(n.size_bytes for n in notes)
        all_tags = []
        for n in notes:
            all_tags.extend(n.tags)

        return {
            "vault_path": str(vault_path),
            "notes_count": len(notes),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "unique_tags": len(set(all_tags)),
            "last_modified": max(
                (n.modified_at for n in notes if n.modified_at),
                default=None
            ),
        }
