"""
Tests for Codebase Import System
==================================

Tests for server/agent/codebase_import.py covering:
- Local import (success, exclude patterns, nonexistent path)
- GitHub import (success mock, invalid URL)
- Codebase analysis (languages, frameworks, tests, CI, empty dir)
- Git branch setup
"""

import asyncio
import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
import pytest

import sys
sys.path.append(str(Path(__file__).parent.parent))

from server.agent.codebase_import import (
    CodebaseImporter,
    CodebaseAnalysis,
    ImportResult,
    LANGUAGE_EXTENSIONS,
    FRAMEWORK_INDICATORS,
)


# Path to the fixture
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sample_brownfield_project"


@pytest.mark.unit
class TestLocalImport:
    """Tests for importing from local filesystem."""

    @pytest.fixture
    def importer(self):
        return CodebaseImporter()

    @pytest.mark.asyncio
    async def test_import_from_local_success(self, importer, tmp_path):
        """Test successful local import copies files correctly."""
        target = tmp_path / "target"
        target.mkdir()

        result = await importer.import_from_local(FIXTURE_DIR, target)

        assert result.success is True
        assert result.source_type == "local"
        assert result.file_count > 0
        assert result.error is None
        # Should have copied key files
        assert (target / "package.json").exists()
        assert (target / "src" / "index.ts").exists()
        assert (target / "tsconfig.json").exists()

    @pytest.mark.asyncio
    async def test_import_excludes_patterns(self, importer, tmp_path):
        """Test that excluded directories are not copied."""
        # Create a source with node_modules and .git
        source = tmp_path / "source"
        source.mkdir()
        (source / "index.ts").write_text("export default 1;")
        (source / "node_modules").mkdir()
        (source / "node_modules" / "foo.js").write_text("module.exports = 1;")
        (source / ".git").mkdir()
        (source / ".git" / "HEAD").write_text("ref: refs/heads/main")
        (source / "__pycache__").mkdir()
        (source / "__pycache__" / "mod.pyc").write_bytes(b"\x00")

        target = tmp_path / "target"
        target.mkdir()

        result = await importer.import_from_local(source, target)

        assert result.success is True
        assert (target / "index.ts").exists()
        assert not (target / "node_modules").exists()
        assert not (target / ".git").exists()
        assert not (target / "__pycache__").exists()

    @pytest.mark.asyncio
    async def test_import_nonexistent_path(self, importer, tmp_path):
        """Test import from nonexistent path returns failure."""
        target = tmp_path / "target"
        target.mkdir()

        result = await importer.import_from_local(
            Path("/nonexistent/path/that/does/not/exist"), target
        )

        assert result.success is False
        assert "does not exist" in result.error

    @pytest.mark.asyncio
    async def test_import_file_not_directory(self, importer, tmp_path):
        """Test import from a file (not directory) returns failure."""
        source_file = tmp_path / "not_a_dir.txt"
        source_file.write_text("hello")
        target = tmp_path / "target"
        target.mkdir()

        result = await importer.import_from_local(source_file, target)

        assert result.success is False
        assert "not a directory" in result.error


@pytest.mark.unit
class TestGitHubImport:
    """Tests for importing from GitHub."""

    @pytest.fixture
    def importer(self):
        return CodebaseImporter()

    @pytest.mark.asyncio
    async def test_import_from_github_success(self, importer, tmp_path):
        """Test GitHub clone with mocked subprocess."""
        target = tmp_path / "target"
        target.mkdir()

        clone_dir = target / ".clone_temp"

        def mock_run(cmd, **kwargs):
            """Simulate git clone by creating files in clone_dir."""
            if "clone" in cmd:
                clone_dir.mkdir(parents=True, exist_ok=True)
                (clone_dir / "package.json").write_text('{"name": "test"}')
                (clone_dir / "src").mkdir()
                (clone_dir / "src" / "index.ts").write_text("export default 1;")
                return MagicMock(returncode=0, stderr="")
            elif "rev-parse" in cmd:
                return MagicMock(returncode=0, stdout="abc123def456\n", stderr="")
            return MagicMock(returncode=0, stderr="")

        async def mock_to_thread(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        with patch("server.agent.codebase_import.subprocess.run", side_effect=mock_run):
            with patch("server.agent.codebase_import.asyncio.to_thread", side_effect=mock_to_thread):
                result = await importer.import_from_github(
                    "https://github.com/user/repo.git", "main", target
                )

        assert result.success is True
        assert result.source_type == "github"
        assert result.commit_sha == "abc123def456"

    @pytest.mark.asyncio
    async def test_import_from_github_clone_failure(self, importer, tmp_path):
        """Test GitHub clone failure returns error result."""
        target = tmp_path / "target"
        target.mkdir()

        def mock_run(cmd, **kwargs):
            if "clone" in cmd:
                return MagicMock(
                    returncode=128,
                    stderr="fatal: repository not found"
                )
            return MagicMock(returncode=0)

        async def mock_to_thread(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        with patch("server.agent.codebase_import.asyncio.to_thread", side_effect=mock_to_thread):
            with patch("server.agent.codebase_import.subprocess.run", side_effect=mock_run):
                result = await importer.import_from_github(
                    "https://github.com/nonexistent/repo.git", "main", target
                )

        assert result.success is False
        assert "repository not found" in result.error


@pytest.mark.unit
class TestCodebaseAnalysis:
    """Tests for codebase analysis."""

    @pytest.fixture
    def importer(self):
        return CodebaseImporter()

    @pytest.mark.asyncio
    async def test_analyze_detects_languages(self, importer):
        """Test language detection from file extensions."""
        analysis = await importer.analyze_codebase(FIXTURE_DIR)

        assert "typescript" in analysis.languages

    @pytest.mark.asyncio
    async def test_analyze_detects_frameworks(self, importer):
        """Test framework detection from config files and package.json."""
        analysis = await importer.analyze_codebase(FIXTURE_DIR)

        # Should detect Next.js from jest.config.ts (no next.config, but react from package.json)
        assert "react" in analysis.frameworks or "next.js" in analysis.frameworks

    @pytest.mark.asyncio
    async def test_analyze_detects_test_framework(self, importer):
        """Test test framework detection."""
        analysis = await importer.analyze_codebase(FIXTURE_DIR)

        assert analysis.has_tests is True
        assert analysis.test_framework == "jest"
        assert analysis.test_runner_command == "npx jest"

    @pytest.mark.asyncio
    async def test_analyze_detects_ci(self, importer):
        """Test CI platform detection."""
        analysis = await importer.analyze_codebase(FIXTURE_DIR)

        assert analysis.has_ci is True
        assert analysis.ci_platform == "github-actions"

    @pytest.mark.asyncio
    async def test_analyze_detects_package_manager(self, importer):
        """Test package manager detection."""
        analysis = await importer.analyze_codebase(FIXTURE_DIR)

        assert "npm" in analysis.package_managers

    @pytest.mark.asyncio
    async def test_analyze_finds_entry_points(self, importer):
        """Test entry point detection."""
        analysis = await importer.analyze_codebase(FIXTURE_DIR)

        assert "src/index.ts" in analysis.entry_points

    @pytest.mark.asyncio
    async def test_analyze_finds_config_files(self, importer):
        """Test key config file detection."""
        analysis = await importer.analyze_codebase(FIXTURE_DIR)

        assert "package.json" in analysis.key_config_files
        assert "tsconfig.json" in analysis.key_config_files

    @pytest.mark.asyncio
    async def test_analyze_counts_loc(self, importer):
        """Test LOC estimate is nonzero."""
        analysis = await importer.analyze_codebase(FIXTURE_DIR)

        assert analysis.loc_estimate > 0

    @pytest.mark.asyncio
    async def test_analyze_empty_directory(self, importer, tmp_path):
        """Test analysis of empty directory."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        analysis = await importer.analyze_codebase(empty_dir)

        assert analysis.languages == []
        assert analysis.frameworks == []
        assert analysis.loc_estimate == 0
        assert analysis.has_tests is False
        assert analysis.has_ci is False

    @pytest.mark.asyncio
    async def test_analysis_to_dict(self, importer):
        """Test CodebaseAnalysis.to_dict() serialization."""
        analysis = await importer.analyze_codebase(FIXTURE_DIR)
        d = analysis.to_dict()

        assert isinstance(d, dict)
        assert 'languages' in d
        assert 'frameworks' in d
        assert 'loc_estimate' in d
        # Should be JSON-serializable
        json.dumps(d)

    @pytest.mark.asyncio
    async def test_analyze_detects_tailwind(self, importer):
        """Test tailwindcss pattern detection from package.json."""
        analysis = await importer.analyze_codebase(FIXTURE_DIR)

        assert "tailwindcss" in analysis.detected_patterns

    @pytest.mark.asyncio
    async def test_directory_structure_summary(self, importer):
        """Test directory structure summary generation."""
        analysis = await importer.analyze_codebase(FIXTURE_DIR)

        assert len(analysis.directory_structure_summary) > 0
        assert "src/" in analysis.directory_structure_summary


@pytest.mark.unit
class TestGitBranchSetup:
    """Tests for brownfield git branch setup."""

    @pytest.fixture
    def importer(self):
        return CodebaseImporter()

    @pytest.mark.asyncio
    async def test_setup_brownfield_git_creates_branch(self, importer, tmp_path):
        """Test git branch creation for brownfield project."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "file.txt").write_text("content")

        branch = await importer.setup_brownfield_git(project_dir)

        assert branch == "yokeflow/modifications"
        # Verify git was initialized and branch created
        result = subprocess.run(
            ['git', 'branch', '--show-current'],
            cwd=str(project_dir), capture_output=True, text=True
        )
        assert result.stdout.strip() == "yokeflow/modifications"

    @pytest.mark.asyncio
    async def test_setup_brownfield_git_custom_branch(self, importer, tmp_path):
        """Test custom branch name for brownfield setup."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "file.txt").write_text("content")

        branch = await importer.setup_brownfield_git(
            project_dir, branch_name="yokeflow/feature-x"
        )

        assert branch == "yokeflow/feature-x"
