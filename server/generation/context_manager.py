"""
Context File Manager
====================

Manages context files for YokeFlow projects, including storage, retrieval,
and loading strategy determination.
"""

import os
import json
import shutil
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass
from uuid import uuid4

from server.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ContextFile:
    """Represents a context file."""
    name: str
    path: str
    size: int
    content_hash: str
    summary: Optional[str] = None
    file_type: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "path": self.path,
            "size": self.size,
            "content_hash": self.content_hash,
            "summary": self.summary,
            "file_type": self.file_type
        }


@dataclass
class LoadingStrategy:
    """Represents a context loading strategy."""
    strategy_type: str  # "load_all" or "task_specific"
    reason: str
    total_size: int
    file_count: int
    recommended_files: List[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "strategy_type": self.strategy_type,
            "reason": self.reason,
            "total_size": self.total_size,
            "file_count": self.file_count,
            "recommended_files": self.recommended_files or []
        }


class ContextManager:
    """Manage context files for YokeFlow projects."""

    # Default limits for loading strategy
    DEFAULT_MAX_FILES = 10
    DEFAULT_MAX_SIZE = 100 * 1024  # 100KB

    # Supported file extensions
    SUPPORTED_EXTENSIONS = {
        ".txt", ".md", ".py", ".js", ".ts", ".jsx", ".tsx",
        ".json", ".yaml", ".yml", ".toml", ".ini",
        ".sql", ".sh", ".bash", ".zsh",
        ".html", ".css", ".scss", ".sass",
        ".go", ".rs", ".java", ".c", ".cpp", ".h",
        ".rb", ".php", ".swift", ".kt",
        ".dockerfile", ".dockerignore", ".gitignore",
        ".env", ".env.example", ".config"
    }

    # File type categories
    FILE_CATEGORIES = {
        "code": {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".c", ".cpp", ".rb", ".php", ".swift", ".kt"},
        "config": {".json", ".yaml", ".yml", ".toml", ".ini", ".env", ".config"},
        "documentation": {".md", ".txt", ".rst"},
        "database": {".sql"},
        "scripts": {".sh", ".bash", ".zsh"},
        "web": {".html", ".css", ".scss", ".sass"},
        "docker": {".dockerfile", ".dockerignore"}
    }

    def __init__(self, project_dir: Path, max_files: int = None, max_size: int = None):
        """Initialize the context manager.

        Args:
            project_dir: Project directory path
            max_files: Maximum files for load_all strategy
            max_size: Maximum total size for load_all strategy
        """
        self.project_dir = Path(project_dir)
        self.context_dir = self.project_dir / ".yokeflow" / "context"
        self.max_files = max_files or self.DEFAULT_MAX_FILES
        self.max_size = max_size or self.DEFAULT_MAX_SIZE

        # Create context directory if it doesn't exist
        self.context_dir.mkdir(parents=True, exist_ok=True)

    def add_context_files(self, files: List[Tuple[str, bytes]]) -> List[ContextFile]:
        """Add context files to the project.

        Args:
            files: List of (filename, content) tuples

        Returns:
            List of ContextFile objects
        """
        context_files = []

        for filename, content in files:
            # Validate file extension
            file_ext = Path(filename).suffix.lower()
            if file_ext not in self.SUPPORTED_EXTENSIONS:
                logger.warning(f"Unsupported file type: {filename} (skipping)")
                continue

            # Generate unique filename to avoid conflicts
            unique_name = f"{uuid4().hex[:8]}_{filename}"
            file_path = self.context_dir / unique_name

            # Save file
            try:
                file_path.write_bytes(content)

                # Create ContextFile object
                context_file = ContextFile(
                    name=filename,
                    path=str(file_path.relative_to(self.project_dir)),
                    size=len(content),
                    content_hash=self._calculate_hash(content),
                    file_type=self._categorize_file(file_ext)
                )
                context_files.append(context_file)

                logger.info(f"Added context file: {filename} ({len(content)} bytes)")

            except Exception as e:
                logger.error(f"Error saving context file {filename}: {str(e)}")

        return context_files

    def get_loading_strategy(self, context_files: List[ContextFile]) -> LoadingStrategy:
        """Determine the loading strategy for context files.

        Args:
            context_files: List of context files

        Returns:
            LoadingStrategy object
        """
        if not context_files:
            return LoadingStrategy(
                strategy_type="load_all",
                reason="No context files provided",
                total_size=0,
                file_count=0
            )

        total_size = sum(f.size for f in context_files)
        file_count = len(context_files)

        # Determine strategy based on size and count
        if file_count <= self.max_files and total_size <= self.max_size:
            return LoadingStrategy(
                strategy_type="load_all",
                reason=f"Small context: {file_count} files, {total_size} bytes",
                total_size=total_size,
                file_count=file_count,
                recommended_files=[f.name for f in context_files]
            )
        else:
            # For task_specific, recommend key files
            recommended = self._get_recommended_files(context_files)

            reason = ""
            if file_count > self.max_files:
                reason = f"Too many files: {file_count} > {self.max_files}"
            elif total_size > self.max_size:
                reason = f"Too large: {total_size} > {self.max_size} bytes"

            return LoadingStrategy(
                strategy_type="task_specific",
                reason=reason,
                total_size=total_size,
                file_count=file_count,
                recommended_files=recommended
            )

    def _get_recommended_files(self, context_files: List[ContextFile]) -> List[str]:
        """Get recommended files for initial loading.

        Args:
            context_files: All context files

        Returns:
            List of recommended file names
        """
        recommended = []

        # Priority order for file types
        priority_categories = ["documentation", "config", "database"]

        for category in priority_categories:
            for file in context_files:
                if file.file_type == category and len(recommended) < 5:
                    recommended.append(file.name)

        # Add small code files if room
        for file in context_files:
            if file.file_type == "code" and file.size < 5000 and len(recommended) < self.max_files:
                recommended.append(file.name)

        return recommended

    def load_context_file(self, filename: str) -> Optional[str]:
        """Load a specific context file.

        Args:
            filename: Name of the file to load

        Returns:
            File content or None if not found
        """
        # Search for file in context directory
        for file_path in self.context_dir.glob(f"*_{filename}"):
            try:
                return file_path.read_text()
            except Exception as e:
                logger.error(f"Error reading context file {filename}: {str(e)}")
                return None

        logger.warning(f"Context file not found: {filename}")
        return None

    def load_all_context_files(self) -> Dict[str, str]:
        """Load all context files.

        Returns:
            Dictionary of filename to content
        """
        context_files = {}

        for file_path in self.context_dir.glob("*"):
            if file_path.is_file():
                # Extract original filename (remove UUID prefix)
                original_name = "_".join(file_path.name.split("_")[1:])
                try:
                    context_files[original_name] = file_path.read_text()
                except Exception as e:
                    logger.error(f"Error reading context file {file_path}: {str(e)}")

        return context_files

    def get_context_manifest(self) -> Dict[str, Any]:
        """Get manifest of all context files.

        Returns:
            Manifest dictionary
        """
        manifest = {
            "files": [],
            "total_size": 0,
            "file_count": 0,
            "categories": {}
        }

        for file_path in self.context_dir.glob("*"):
            if file_path.is_file():
                original_name = "_".join(file_path.name.split("_")[1:])
                file_size = file_path.stat().st_size
                file_ext = Path(original_name).suffix.lower()
                file_type = self._categorize_file(file_ext)

                manifest["files"].append({
                    "name": original_name,
                    "size": file_size,
                    "type": file_type,
                    "path": str(file_path.relative_to(self.project_dir))
                })

                manifest["total_size"] += file_size
                manifest["file_count"] += 1

                # Count by category
                if file_type not in manifest["categories"]:
                    manifest["categories"][file_type] = 0
                manifest["categories"][file_type] += 1

        return manifest

    def cleanup_context_files(self):
        """Remove all context files for the project."""
        try:
            if self.context_dir.exists():
                shutil.rmtree(self.context_dir)
                logger.info(f"Cleaned up context files for project: {self.project_dir}")
        except Exception as e:
            logger.error(f"Error cleaning up context files: {str(e)}")

    def _calculate_hash(self, content: bytes) -> str:
        """Calculate hash of file content.

        Args:
            content: File content

        Returns:
            Hash string
        """
        import hashlib
        return hashlib.sha256(content).hexdigest()[:16]

    def _categorize_file(self, extension: str) -> str:
        """Categorize file by extension.

        Args:
            extension: File extension

        Returns:
            Category name
        """
        for category, extensions in self.FILE_CATEGORIES.items():
            if extension in extensions:
                return category
        return "other"

    def export_manifest(self, output_path: Optional[Path] = None) -> str:
        """Export manifest to JSON file.

        Args:
            output_path: Optional output path

        Returns:
            Path to exported manifest
        """
        manifest = self.get_context_manifest()

        if output_path is None:
            output_path = self.context_dir / "manifest.json"

        output_path.write_text(json.dumps(manifest, indent=2))
        logger.info(f"Exported manifest to: {output_path}")

        return str(output_path)