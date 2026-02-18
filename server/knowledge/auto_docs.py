"""
Auto Documenter
===============

Auto-documentation for YokeFlow generated projects.

Features:
- Generate documentation from code
- Create knowledge vault entries
- Track project changes
- Integration templates
"""

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import re

from server.utils.logging import get_logger
from server.knowledge.vault_manager import VaultManager

logger = get_logger(__name__)


@dataclass
class DocSection:
    """A section of documentation."""
    title: str
    content: str
    level: int = 2  # Markdown heading level
    order: int = 0


@dataclass
class GeneratedDoc:
    """A generated documentation file."""
    path: str
    title: str
    content: str
    sections: List[DocSection] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class AutoDocumenter:
    """
    Automatic documentation generator for YokeFlow projects.

    Analyzes project structure and code to generate documentation
    that can be stored in the knowledge vault.
    """

    def __init__(
        self,
        vault_manager: Optional[VaultManager] = None,
        output_dir: str = "docs",
    ):
        """
        Initialize the auto documenter.

        Args:
            vault_manager: VaultManager for storing docs
            output_dir: Default output directory name
        """
        self.vault_manager = vault_manager or VaultManager()
        self.output_dir = output_dir

        logger.info("knowledge.auto_docs.initialized")

    async def generate_project_docs(
        self,
        project_path: str,
        project_name: str,
        include_code_docs: bool = True,
        include_api_docs: bool = True,
        include_readme: bool = True
    ) -> List[GeneratedDoc]:
        """
        Generate documentation for a project.

        Args:
            project_path: Path to project root
            project_name: Project name
            include_code_docs: Generate code documentation
            include_api_docs: Generate API documentation
            include_readme: Generate README

        Returns:
            List of generated documentation files
        """
        docs = []
        project_dir = Path(project_path)

        if not project_dir.exists():
            logger.warning("knowledge.auto_docs.project_not_found", path=project_path)
            return docs

        # Analyze project structure
        structure = self._analyze_structure(project_dir)

        # Generate README
        if include_readme:
            readme = self._generate_readme(project_dir, project_name, structure)
            docs.append(readme)

        # Generate code documentation
        if include_code_docs:
            code_docs = self._generate_code_docs(project_dir, project_name, structure)
            docs.extend(code_docs)

        # Generate API documentation
        if include_api_docs and structure.get("has_api"):
            api_docs = self._generate_api_docs(project_dir, project_name)
            docs.extend(api_docs)

        logger.info(
            "knowledge.auto_docs.generated",
            project=project_name,
            docs_count=len(docs)
        )

        return docs

    async def sync_to_vault(
        self,
        docs: List[GeneratedDoc],
        project_id: str,
        vault_type: str = "agents"
    ) -> Dict[str, Any]:
        """
        Sync generated documentation to the knowledge vault.

        Args:
            docs: List of GeneratedDoc objects
            project_id: Project identifier
            vault_type: Target vault type

        Returns:
            Sync statistics
        """
        synced = 0
        errors = 0

        for doc in docs:
            note_path = f"projects/{project_id}/{doc.path}"

            # Build frontmatter
            frontmatter = {
                "title": doc.title,
                "project_id": project_id,
                "generated_at": datetime.utcnow().isoformat(),
                "doc_type": "auto_generated",
                **doc.metadata
            }

            # Build content
            content = self._build_doc_content(doc)

            # Write to vault
            success = self.vault_manager.write_note(
                note_path=note_path,
                content=content,
                vault_type=vault_type,
                frontmatter=frontmatter
            )

            if success:
                synced += 1
            else:
                errors += 1

        logger.info(
            "knowledge.auto_docs.synced",
            project_id=project_id,
            synced=synced,
            errors=errors
        )

        return {
            "synced": synced,
            "errors": errors,
            "total": len(docs)
        }

    async def update_change_log(
        self,
        project_id: str,
        changes: List[Dict[str, Any]],
        vault_type: str = "agents"
    ) -> bool:
        """
        Update or create a change log for a project.

        Args:
            project_id: Project identifier
            changes: List of change descriptions
            vault_type: Target vault type

        Returns:
            True if successful
        """
        note_path = f"projects/{project_id}/CHANGELOG.md"

        # Get existing changelog
        existing = self.vault_manager.get_note(note_path, vault_type)
        existing_content = existing.content if existing else ""

        # Build new entries
        new_entries = []
        for change in changes:
            timestamp = change.get("timestamp", datetime.utcnow().isoformat())
            description = change.get("description", "Unknown change")
            change_type = change.get("type", "changed")

            emoji = {
                "added": "✨",
                "changed": "📝",
                "fixed": "🐛",
                "removed": "🗑️",
                "deprecated": "⚠️",
            }.get(change_type, "📝")

            new_entries.append(f"- {emoji} **{timestamp}**: {description}")

        # Prepend new entries
        if existing_content:
            # Find insertion point after header
            lines = existing_content.split("\n")
            header_end = 0
            for i, line in enumerate(lines):
                if line.startswith("# "):
                    header_end = i + 2  # Skip header and blank line
                    break

            new_content = (
                "\n".join(lines[:header_end]) +
                "\n" +
                "\n".join(new_entries) +
                "\n\n" +
                "\n".join(lines[header_end:])
            )
        else:
            new_content = f"# Changelog\n\n{''.join(new_entries)}\n"

        return self.vault_manager.write_note(
            note_path=note_path,
            content=new_content,
            vault_type=vault_type,
            frontmatter={
                "project_id": project_id,
                "updated_at": datetime.utcnow().isoformat()
            }
        )

    def _analyze_structure(self, project_dir: Path) -> Dict[str, Any]:
        """Analyze project structure."""
        structure = {
            "languages": set(),
            "frameworks": set(),
            "has_api": False,
            "has_tests": False,
            "has_docker": False,
            "directories": [],
            "entry_points": [],
        }

        # Detect languages and frameworks
        if (project_dir / "package.json").exists():
            structure["languages"].add("JavaScript/TypeScript")
            try:
                import json
                pkg = json.loads((project_dir / "package.json").read_text())
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

                if "react" in deps:
                    structure["frameworks"].add("React")
                if "next" in deps:
                    structure["frameworks"].add("Next.js")
                if "express" in deps:
                    structure["frameworks"].add("Express")
                    structure["has_api"] = True
                if "fastify" in deps:
                    structure["frameworks"].add("Fastify")
                    structure["has_api"] = True
            except Exception:
                pass

        if (project_dir / "requirements.txt").exists() or (project_dir / "pyproject.toml").exists():
            structure["languages"].add("Python")
            if (project_dir / "fastapi").exists() or any(
                "fastapi" in f.read_text().lower()
                for f in project_dir.glob("*.txt")
                if f.name == "requirements.txt"
            ):
                structure["frameworks"].add("FastAPI")
                structure["has_api"] = True

        # Check for common directories
        for dirname in ["src", "lib", "app", "server", "api", "tests", "test", "__tests__"]:
            if (project_dir / dirname).exists():
                structure["directories"].append(dirname)
                if "test" in dirname:
                    structure["has_tests"] = True

        # Check for Docker
        if (project_dir / "Dockerfile").exists() or (project_dir / "docker-compose.yml").exists():
            structure["has_docker"] = True

        # Find entry points
        for pattern in ["main.*", "app.*", "index.*", "server.*"]:
            for f in project_dir.glob(pattern):
                structure["entry_points"].append(f.name)

        # Convert sets to lists for serialization
        structure["languages"] = list(structure["languages"])
        structure["frameworks"] = list(structure["frameworks"])

        return structure

    def _generate_readme(
        self,
        project_dir: Path,
        project_name: str,
        structure: Dict[str, Any]
    ) -> GeneratedDoc:
        """Generate README.md."""
        sections = []

        # Description section
        sections.append(DocSection(
            title="Description",
            content=f"Auto-generated project: {project_name}",
            order=1
        ))

        # Tech stack section
        if structure["languages"] or structure["frameworks"]:
            tech_content = "**Languages:** " + ", ".join(structure["languages"]) + "\n\n"
            if structure["frameworks"]:
                tech_content += "**Frameworks:** " + ", ".join(structure["frameworks"])
            sections.append(DocSection(
                title="Tech Stack",
                content=tech_content,
                order=2
            ))

        # Installation section
        install_content = "```bash\n"
        if "JavaScript/TypeScript" in structure["languages"]:
            install_content += "# Install dependencies\nnpm install\n\n"
            install_content += "# Start development server\nnpm run dev\n"
        elif "Python" in structure["languages"]:
            install_content += "# Create virtual environment\npython -m venv venv\n"
            install_content += "source venv/bin/activate  # On Windows: venv\\Scripts\\activate\n\n"
            install_content += "# Install dependencies\npip install -r requirements.txt\n\n"
            install_content += "# Start server\npython main.py\n"
        install_content += "```"
        sections.append(DocSection(
            title="Installation",
            content=install_content,
            order=3
        ))

        # Docker section
        if structure["has_docker"]:
            docker_content = "```bash\n# Build and run with Docker Compose\ndocker-compose up -d\n```"
            sections.append(DocSection(
                title="Docker",
                content=docker_content,
                order=4
            ))

        # Project structure section
        if structure["directories"]:
            structure_content = "```\n"
            structure_content += f"{project_name}/\n"
            for dirname in structure["directories"]:
                structure_content += f"├── {dirname}/\n"
            structure_content += "```"
            sections.append(DocSection(
                title="Project Structure",
                content=structure_content,
                order=5
            ))

        return GeneratedDoc(
            path="README.md",
            title=f"{project_name} - README",
            content="",  # Will be built from sections
            sections=sorted(sections, key=lambda s: s.order),
            metadata={"type": "readme"}
        )

    def _generate_code_docs(
        self,
        project_dir: Path,
        project_name: str,
        structure: Dict[str, Any]
    ) -> List[GeneratedDoc]:
        """Generate code documentation."""
        docs = []

        # Document main source directory
        for dirname in ["src", "lib", "app", "server"]:
            src_dir = project_dir / dirname
            if not src_dir.exists():
                continue

            sections = []
            modules = []

            # List Python modules
            for py_file in src_dir.rglob("*.py"):
                if py_file.name.startswith("__"):
                    continue

                rel_path = py_file.relative_to(src_dir)
                module_doc = self._document_python_file(py_file)
                if module_doc:
                    modules.append({
                        "path": str(rel_path),
                        "doc": module_doc
                    })

            # List JavaScript/TypeScript modules
            for js_file in src_dir.rglob("*.{js,ts,tsx}"):
                rel_path = js_file.relative_to(src_dir)
                module_doc = self._document_js_file(js_file)
                if module_doc:
                    modules.append({
                        "path": str(rel_path),
                        "doc": module_doc
                    })

            if modules:
                content = "## Modules\n\n"
                for module in modules:
                    content += f"### `{module['path']}`\n\n"
                    content += module['doc'] + "\n\n"

                docs.append(GeneratedDoc(
                    path=f"{self.output_dir}/architecture.md",
                    title=f"{project_name} - Architecture",
                    content=content,
                    metadata={"type": "architecture"}
                ))

            break  # Only document first source directory

        return docs

    def _generate_api_docs(
        self,
        project_dir: Path,
        project_name: str
    ) -> List[GeneratedDoc]:
        """Generate API documentation."""
        docs = []

        # Look for API route files
        api_patterns = [
            "**/routes/*.py",
            "**/api/*.py",
            "**/routes/*.ts",
            "**/api/*.ts",
        ]

        endpoints = []

        for pattern in api_patterns:
            for api_file in project_dir.glob(pattern):
                file_endpoints = self._extract_api_endpoints(api_file)
                endpoints.extend(file_endpoints)

        if endpoints:
            content = "## API Endpoints\n\n"
            for endpoint in endpoints:
                content += f"### {endpoint['method']} `{endpoint['path']}`\n\n"
                if endpoint.get("description"):
                    content += f"{endpoint['description']}\n\n"

            docs.append(GeneratedDoc(
                path=f"{self.output_dir}/api.md",
                title=f"{project_name} - API Reference",
                content=content,
                metadata={"type": "api"}
            ))

        return docs

    def _document_python_file(self, file_path: Path) -> str:
        """Extract documentation from a Python file."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception:
            return ""

        # Extract module docstring
        docstring = ""
        match = re.search(r'"""(.+?)"""', content, re.DOTALL)
        if match:
            docstring = match.group(1).strip()

        # Extract classes and functions
        classes = re.findall(r'class\s+(\w+)(?:\(([^)]+)\))?:', content)
        functions = re.findall(r'def\s+(\w+)\s*\(([^)]*)\)', content)

        result_parts = []
        if docstring:
            result_parts.append(docstring)

        if classes:
            result_parts.append("\n**Classes:**")
            for cls_name, base in classes:
                result_parts.append(f"- `{cls_name}`" + (f" ({base})" if base else ""))

        if functions:
            public_funcs = [f for f in functions if not f[0].startswith("_")]
            if public_funcs:
                result_parts.append("\n**Functions:**")
                for func_name, args in public_funcs:
                    result_parts.append(f"- `{func_name}({args})`")

        return "\n".join(result_parts)

    def _document_js_file(self, file_path: Path) -> str:
        """Extract documentation from a JavaScript/TypeScript file."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception:
            return ""

        # Extract JSDoc comments
        comments = re.findall(r'/\*\*(.+?)\*/', content, re.DOTALL)
        doc_comments = [c.strip() for c in comments if c.strip()]

        # Extract exports
        exports = re.findall(r'export\s+(?:default\s+)?(?:function|class|const)\s+(\w+)', content)

        result_parts = []

        if doc_comments:
            result_parts.append("\n".join(doc_comments[:3]))  # First 3 comments

        if exports:
            result_parts.append("\n**Exports:**")
            for export in exports:
                result_parts.append(f"- `{export}`")

        return "\n".join(result_parts)

    def _extract_api_endpoints(self, file_path: Path) -> List[Dict[str, str]]:
        """Extract API endpoint definitions from a file."""
        endpoints = []

        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception:
            return endpoints

        # Python decorators
        for match in re.finditer(r'@(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']', content, re.IGNORECASE):
            endpoints.append({
                "method": match.group(1).upper(),
                "path": match.group(2),
                "file": str(file_path.name)
            })

        # Express.js style
        for match in re.finditer(r'(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']', content, re.IGNORECASE):
            endpoints.append({
                "method": match.group(1).upper(),
                "path": match.group(2),
                "file": str(file_path.name)
            })

        return endpoints

    def _build_doc_content(self, doc: GeneratedDoc) -> str:
        """Build final content from sections."""
        parts = []

        # Add title
        parts.append(f"# {doc.title}\n")

        # Add sections
        for section in doc.sections:
            parts.append(f"\n{'#' * section.level} {section.title}\n")
            parts.append(section.content)

        # Add main content if present
        if doc.content:
            parts.append(f"\n{doc.content}")

        return "\n".join(parts)
