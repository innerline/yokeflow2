"""
Context Manifest Generator
==========================

Generates intelligent manifests for context files with AI-powered summaries
to enable efficient loading strategies.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from server.generation.spec_generator import SpecGenerator
from server.generation.context_manager import ContextFile, LoadingStrategy
from server.utils.logging import get_logger

logger = get_logger(__name__)


class ContextManifest:
    """Generate and manage context file manifests with AI summaries."""

    def __init__(self, project_dir: Path, spec_generator: Optional[SpecGenerator] = None):
        """Initialize the manifest generator.

        Args:
            project_dir: Project directory path
            spec_generator: Optional SpecGenerator instance for summaries
        """
        self.project_dir = Path(project_dir)
        self.context_dir = self.project_dir / ".yokeflow" / "context"
        self.spec_generator = spec_generator or SpecGenerator()
        self.manifest_path = self.context_dir / "manifest.json"

    async def generate_manifest(
        self,
        context_files: List[ContextFile],
        loading_strategy: LoadingStrategy,
        project_name: str
    ) -> Dict[str, Any]:
        """Generate a complete manifest with AI summaries.

        Args:
            context_files: List of context files
            loading_strategy: Determined loading strategy
            project_name: Name of the project

        Returns:
            Complete manifest dictionary
        """
        logger.info(f"Generating manifest for {len(context_files)} context files")

        manifest = {
            "version": "1.0",
            "project_name": project_name,
            "created_at": datetime.utcnow().isoformat(),
            "loading_strategy": loading_strategy.to_dict(),
            "files": [],
            "summary": "",
            "categories": {},
            "statistics": {
                "total_files": len(context_files),
                "total_size": sum(f.size for f in context_files),
                "file_types": {}
            }
        }

        # Process each file
        for context_file in context_files:
            file_entry = await self._process_file(context_file)
            manifest["files"].append(file_entry)

            # Update categories
            if context_file.file_type not in manifest["categories"]:
                manifest["categories"][context_file.file_type] = []
            manifest["categories"][context_file.file_type].append(context_file.name)

            # Update file type statistics
            ext = Path(context_file.name).suffix.lower()
            if ext not in manifest["statistics"]["file_types"]:
                manifest["statistics"]["file_types"][ext] = 0
            manifest["statistics"]["file_types"][ext] += 1

        # Generate overall summary
        manifest["summary"] = await self._generate_overall_summary(manifest, context_files)

        # Add recommendations
        manifest["recommendations"] = self._generate_recommendations(manifest, loading_strategy)

        return manifest

    async def _process_file(self, context_file: ContextFile) -> Dict[str, Any]:
        """Process a single file and generate its summary.

        Args:
            context_file: ContextFile to process

        Returns:
            File entry for manifest
        """
        file_entry = context_file.to_dict()

        # Try to load and summarize the file
        try:
            file_path = self.project_dir / context_file.path
            if file_path.exists():
                content = file_path.read_text(errors='ignore')[:2000]  # First 2000 chars

                # Generate AI summary for important files
                if context_file.file_type in ["documentation", "config", "database"]:
                    summary = await self.spec_generator.generate_summary(content, max_length=200)
                    file_entry["summary"] = summary
                else:
                    # Basic summary for other files
                    file_entry["summary"] = self._generate_basic_summary(context_file.name, content)

                # Add content preview
                file_entry["preview"] = content[:500] if len(content) > 500 else content

        except Exception as e:
            logger.error(f"Error processing file {context_file.name}: {str(e)}")
            file_entry["summary"] = f"Failed to generate summary: {str(e)}"

        return file_entry

    def _generate_basic_summary(self, filename: str, content: str) -> str:
        """Generate a basic summary without AI.

        Args:
            filename: Name of the file
            content: File content preview

        Returns:
            Basic summary string
        """
        lines = content.split('\n')
        non_empty_lines = [l for l in lines if l.strip()]

        ext = Path(filename).suffix.lower()

        if ext in ['.py', '.js', '.ts']:
            # Code files - count functions/classes
            functions = content.count('def ') + content.count('function ')
            classes = content.count('class ')
            return f"Code file with ~{functions} functions and ~{classes} classes"

        elif ext in ['.json', '.yaml', '.yml']:
            # Config files - count top-level keys
            if ext == '.json':
                try:
                    data = json.loads(content)
                    if isinstance(data, dict):
                        return f"Configuration with {len(data)} top-level keys"
                except:
                    pass
            return f"Configuration file with {len(non_empty_lines)} lines"

        elif ext == '.sql':
            # SQL files - count queries
            creates = content.lower().count('create table')
            selects = content.lower().count('select ')
            return f"SQL file with ~{creates} tables and ~{selects} queries"

        elif ext in ['.md', '.txt']:
            # Documentation - count sections
            headers = sum(1 for l in lines if l.startswith('#'))
            return f"Documentation with {headers} sections and {len(non_empty_lines)} lines"

        else:
            return f"File with {len(non_empty_lines)} lines"

    async def _generate_overall_summary(
        self,
        manifest: Dict[str, Any],
        context_files: List[ContextFile]
    ) -> str:
        """Generate an overall summary of all context files.

        Args:
            manifest: Current manifest data
            context_files: All context files

        Returns:
            Overall summary string
        """
        summary_parts = []

        # Describe file composition
        total_files = manifest["statistics"]["total_files"]
        total_size = manifest["statistics"]["total_size"]
        summary_parts.append(f"Context includes {total_files} files totaling {total_size:,} bytes.")

        # Describe categories
        if manifest["categories"]:
            category_desc = []
            for category, files in manifest["categories"].items():
                category_desc.append(f"{len(files)} {category} files")
            summary_parts.append(f"Files include: {', '.join(category_desc)}.")

        # Describe key files
        key_files = []
        for category in ["documentation", "config", "database"]:
            if category in manifest["categories"]:
                for file in manifest["categories"][category][:2]:  # First 2 of each
                    key_files.append(file)

        if key_files:
            summary_parts.append(f"Key files: {', '.join(key_files)}")

        # Describe loading strategy
        strategy = manifest["loading_strategy"]
        if strategy["strategy_type"] == "load_all":
            summary_parts.append("All files will be loaded due to small context size.")
        else:
            summary_parts.append(f"Task-specific loading recommended due to {strategy['reason']}.")

        return " ".join(summary_parts)

    def _generate_recommendations(
        self,
        manifest: Dict[str, Any],
        loading_strategy: LoadingStrategy
    ) -> Dict[str, Any]:
        """Generate recommendations based on context analysis.

        Args:
            manifest: Current manifest data
            loading_strategy: Determined loading strategy

        Returns:
            Recommendations dictionary
        """
        recommendations = {
            "initial_files": loading_strategy.recommended_files or [],
            "suggestions": []
        }

        # Check for missing documentation
        if "documentation" not in manifest["categories"]:
            recommendations["suggestions"].append("Consider adding README or documentation files for better context")

        # Check for large files
        large_files = [f for f in manifest["files"] if f["size"] > 50000]
        if large_files:
            recommendations["suggestions"].append(f"Consider summarizing large files: {', '.join([f['name'] for f in large_files[:3]])}")

        # Check for config files
        if "config" in manifest["categories"] and len(manifest["categories"]["config"]) > 5:
            recommendations["suggestions"].append("Multiple config files detected - ensure they're properly organized")

        # Check for database files
        if "database" in manifest["categories"]:
            recommendations["suggestions"].append("Database schema files detected - will be prioritized for initial loading")

        return recommendations

    async def save_manifest(self, manifest: Dict[str, Any]) -> Path:
        """Save manifest to JSON file.

        Args:
            manifest: Manifest data to save

        Returns:
            Path to saved manifest
        """
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(json.dumps(manifest, indent=2))
        logger.info(f"Saved manifest to: {self.manifest_path}")
        return self.manifest_path

    def load_manifest(self) -> Optional[Dict[str, Any]]:
        """Load existing manifest.

        Returns:
            Manifest data or None if not found
        """
        if self.manifest_path.exists():
            try:
                return json.loads(self.manifest_path.read_text())
            except Exception as e:
                logger.error(f"Error loading manifest: {str(e)}")
        return None

    def update_manifest(self, updates: Dict[str, Any]) -> bool:
        """Update existing manifest with new data.

        Args:
            updates: Data to update in manifest

        Returns:
            Success status
        """
        try:
            manifest = self.load_manifest() or {}
            manifest.update(updates)
            manifest["updated_at"] = datetime.utcnow().isoformat()
            self.manifest_path.write_text(json.dumps(manifest, indent=2))
            return True
        except Exception as e:
            logger.error(f"Error updating manifest: {str(e)}")
            return False

    def get_file_summary(self, filename: str) -> Optional[str]:
        """Get summary for a specific file from manifest.

        Args:
            filename: Name of the file

        Returns:
            Summary string or None
        """
        manifest = self.load_manifest()
        if manifest:
            for file_entry in manifest.get("files", []):
                if file_entry["name"] == filename:
                    return file_entry.get("summary")
        return None

    def get_recommended_files(self) -> List[str]:
        """Get list of recommended files from manifest.

        Returns:
            List of recommended file names
        """
        manifest = self.load_manifest()
        if manifest:
            recommendations = manifest.get("recommendations", {})
            return recommendations.get("initial_files", [])
        return []