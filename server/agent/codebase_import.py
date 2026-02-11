"""
Codebase Import System
======================

Handles importing existing codebases for brownfield projects.
Supports local path copy and GitHub clone.

Analysis is lightweight (file-system inspection only, no LLM cost).
Deep understanding happens in Session 0 via the brownfield initializer prompt.
"""

import asyncio
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, List, Any, Set

from server.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ImportResult:
    """Result of a codebase import operation."""
    success: bool
    source_type: str           # 'local' or 'github'
    source_path: str           # Original source location
    target_path: str           # Where imported to
    commit_sha: Optional[str]  # Git commit SHA (if available)
    file_count: int = 0
    total_size_bytes: int = 0
    error: Optional[str] = None


@dataclass
class CodebaseAnalysis:
    """Structured analysis of an imported codebase."""
    languages: List[str] = field(default_factory=list)
    frameworks: List[str] = field(default_factory=list)
    package_managers: List[str] = field(default_factory=list)
    has_tests: bool = False
    test_framework: Optional[str] = None
    test_runner_command: Optional[str] = None
    has_ci: bool = False
    ci_platform: Optional[str] = None
    entry_points: List[str] = field(default_factory=list)
    loc_estimate: int = 0
    directory_structure_summary: str = ""
    key_config_files: List[str] = field(default_factory=list)
    detected_patterns: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSONB storage."""
        return {
            'languages': self.languages,
            'frameworks': self.frameworks,
            'package_managers': self.package_managers,
            'has_tests': self.has_tests,
            'test_framework': self.test_framework,
            'test_runner_command': self.test_runner_command,
            'has_ci': self.has_ci,
            'ci_platform': self.ci_platform,
            'entry_points': self.entry_points,
            'loc_estimate': self.loc_estimate,
            'directory_structure_summary': self.directory_structure_summary,
            'key_config_files': self.key_config_files,
            'detected_patterns': self.detected_patterns,
        }


# File extension to language mapping
LANGUAGE_EXTENSIONS: Dict[str, str] = {
    '.py': 'python',
    '.ts': 'typescript', '.tsx': 'typescript',
    '.js': 'javascript', '.jsx': 'javascript',
    '.rs': 'rust',
    '.go': 'go',
    '.java': 'java',
    '.rb': 'ruby',
    '.php': 'php',
    '.swift': 'swift',
    '.kt': 'kotlin',
    '.cs': 'csharp',
    '.cpp': 'cpp', '.cc': 'cpp', '.cxx': 'cpp', '.h': 'cpp', '.hpp': 'cpp',
    '.c': 'c',
    '.scala': 'scala',
    '.ex': 'elixir', '.exs': 'elixir',
    '.hs': 'haskell',
    '.lua': 'lua',
    '.r': 'r', '.R': 'r',
    '.dart': 'dart',
    '.vue': 'vue',
    '.svelte': 'svelte',
}

# Config file to framework mapping
FRAMEWORK_INDICATORS: Dict[str, Optional[str]] = {
    'next.config.js': 'next.js',
    'next.config.ts': 'next.js',
    'next.config.mjs': 'next.js',
    'nuxt.config.ts': 'nuxt',
    'nuxt.config.js': 'nuxt',
    'angular.json': 'angular',
    'vite.config.ts': 'vite',
    'vite.config.js': 'vite',
    'svelte.config.js': 'svelte',
    'remix.config.js': 'remix',
    'astro.config.mjs': 'astro',
    'gatsby-config.js': 'gatsby',
    'Cargo.toml': 'rust/cargo',
    'go.mod': 'go',
    'build.gradle': 'gradle',
    'pom.xml': 'maven',
    'Gemfile': 'ruby/bundler',
    'composer.json': 'php/composer',
    'mix.exs': 'elixir/mix',
    'pubspec.yaml': 'flutter/dart',
}

# Test framework detection
TEST_INDICATORS: Dict[str, tuple] = {
    'jest.config.js': ('jest', 'npx jest'),
    'jest.config.ts': ('jest', 'npx jest'),
    'jest.config.mjs': ('jest', 'npx jest'),
    'vitest.config.ts': ('vitest', 'npx vitest run'),
    'vitest.config.js': ('vitest', 'npx vitest run'),
    'pytest.ini': ('pytest', 'pytest'),
    'setup.cfg': ('pytest', 'pytest'),  # May contain [tool:pytest]
    '.mocharc.yml': ('mocha', 'npx mocha'),
    '.mocharc.json': ('mocha', 'npx mocha'),
    'karma.conf.js': ('karma', 'npx karma start'),
    'phpunit.xml': ('phpunit', 'phpunit'),
}

# CI platform detection
CI_INDICATORS: Dict[str, str] = {
    '.github/workflows': 'github-actions',
    '.gitlab-ci.yml': 'gitlab-ci',
    'Jenkinsfile': 'jenkins',
    '.circleci': 'circleci',
    '.travis.yml': 'travis-ci',
    'azure-pipelines.yml': 'azure-devops',
    'bitbucket-pipelines.yml': 'bitbucket',
}


class CodebaseImporter:
    """Import existing codebases for brownfield projects."""

    # Files/dirs to always exclude during local copy
    EXCLUDE_PATTERNS: Set[str] = {
        '.git', 'node_modules', '__pycache__', '.next', 'dist',
        'build', '.venv', 'venv', '.tox', '.mypy_cache',
        '.pytest_cache', 'target', '.DS_Store', '.eggs',
        '*.egg-info', '.cache', '.parcel-cache',
    }

    async def import_from_local(
        self, source_path: Path, target_dir: Path
    ) -> ImportResult:
        """
        Copy a local codebase into the project directory.

        Copies all files respecting exclude patterns (node_modules, .git, etc).
        If the source is a git repo, records the current commit SHA.
        """
        source_path = Path(source_path).resolve()

        if not source_path.exists():
            return ImportResult(
                success=False,
                source_type='local',
                source_path=str(source_path),
                target_path=str(target_dir),
                commit_sha=None,
                error=f"Source path does not exist: {source_path}"
            )

        if not source_path.is_dir():
            return ImportResult(
                success=False,
                source_type='local',
                source_path=str(source_path),
                target_path=str(target_dir),
                commit_sha=None,
                error=f"Source path is not a directory: {source_path}"
            )

        try:
            def _should_exclude(name: str) -> bool:
                return name in self.EXCLUDE_PATTERNS

            # Copy the directory tree
            file_count = 0
            total_size = 0

            for item in source_path.iterdir():
                if _should_exclude(item.name):
                    continue

                dest = target_dir / item.name
                if item.is_dir():
                    shutil.copytree(
                        item, dest,
                        ignore=shutil.ignore_patterns(*self.EXCLUDE_PATTERNS),
                        dirs_exist_ok=True
                    )
                else:
                    shutil.copy2(item, dest)

            # Count files and size
            for f in target_dir.rglob('*'):
                if f.is_file():
                    file_count += 1
                    total_size += f.stat().st_size

            # Try to get commit SHA from source
            commit_sha = self._get_git_sha(source_path)

            logger.info(
                f"Imported local codebase: {file_count} files, "
                f"{total_size / 1024 / 1024:.1f} MB from {source_path}"
            )

            return ImportResult(
                success=True,
                source_type='local',
                source_path=str(source_path),
                target_path=str(target_dir),
                commit_sha=commit_sha,
                file_count=file_count,
                total_size_bytes=total_size,
            )

        except Exception as e:
            logger.error(f"Failed to import local codebase: {e}")
            return ImportResult(
                success=False,
                source_type='local',
                source_path=str(source_path),
                target_path=str(target_dir),
                commit_sha=None,
                error=str(e)
            )

    async def import_from_github(
        self, repo_url: str, branch: str, target_dir: Path
    ) -> ImportResult:
        """
        Clone a GitHub repository into the project directory.

        Uses shallow clone (--depth=1) for faster import.
        Supports GITHUB_TOKEN for private repos.
        """
        try:
            # Build clone command
            cmd = ['git', 'clone', '--depth=1', f'--branch={branch}']

            # Check for GitHub token for private repos
            github_token = os.environ.get('GITHUB_TOKEN')
            if github_token and repo_url.startswith('https://'):
                # Inject token into URL for auth
                auth_url = repo_url.replace(
                    'https://', f'https://x-access-token:{github_token}@'
                )
                cmd.append(auth_url)
            else:
                cmd.append(repo_url)

            # Clone into a temp subdir, then move contents to target
            clone_dir = target_dir / '.clone_temp'
            cmd.append(str(clone_dir))

            logger.info(f"Cloning {repo_url} (branch: {branch})...")

            result = await asyncio.to_thread(
                subprocess.run, cmd,
                capture_output=True, text=True, timeout=300
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip()
                # Sanitize token from error messages
                if github_token:
                    error_msg = error_msg.replace(github_token, '***')
                return ImportResult(
                    success=False,
                    source_type='github',
                    source_path=repo_url,
                    target_path=str(target_dir),
                    commit_sha=None,
                    error=f"git clone failed: {error_msg}"
                )

            # Get commit SHA before moving
            commit_sha = self._get_git_sha(clone_dir)

            # Move contents from clone_dir to target_dir
            for item in clone_dir.iterdir():
                dest = target_dir / item.name
                if dest.exists():
                    if dest.is_dir():
                        shutil.rmtree(dest)
                    else:
                        dest.unlink()
                shutil.move(str(item), str(dest))

            # Remove temp clone dir
            if clone_dir.exists():
                shutil.rmtree(clone_dir)

            # Count files
            file_count = 0
            total_size = 0
            for f in target_dir.rglob('*'):
                if f.is_file() and '.git' not in f.parts:
                    file_count += 1
                    total_size += f.stat().st_size

            logger.info(
                f"Cloned GitHub repo: {file_count} files, "
                f"{total_size / 1024 / 1024:.1f} MB from {repo_url}"
            )

            return ImportResult(
                success=True,
                source_type='github',
                source_path=repo_url,
                target_path=str(target_dir),
                commit_sha=commit_sha,
                file_count=file_count,
                total_size_bytes=total_size,
            )

        except subprocess.TimeoutExpired:
            return ImportResult(
                success=False,
                source_type='github',
                source_path=repo_url,
                target_path=str(target_dir),
                commit_sha=None,
                error="git clone timed out after 300 seconds"
            )
        except Exception as e:
            logger.error(f"Failed to clone GitHub repo: {e}")
            return ImportResult(
                success=False,
                source_type='github',
                source_path=repo_url,
                target_path=str(target_dir),
                commit_sha=None,
                error=str(e)
            )

    async def analyze_codebase(self, project_dir: Path) -> CodebaseAnalysis:
        """
        Analyze the imported codebase structure.

        This is file-system level inspection only (fast, no LLM cost).
        The heavy understanding happens in Session 0 via Claude.
        """
        analysis = CodebaseAnalysis()

        # Detect languages by file extension
        lang_counts: Dict[str, int] = {}
        loc_total = 0

        for f in project_dir.rglob('*'):
            if not f.is_file():
                continue
            # Skip hidden dirs and excluded dirs
            parts = f.relative_to(project_dir).parts
            if any(p.startswith('.') or p in CodebaseImporter.EXCLUDE_PATTERNS for p in parts):
                continue

            ext = f.suffix.lower()
            if ext in LANGUAGE_EXTENSIONS:
                lang = LANGUAGE_EXTENSIONS[ext]
                lang_counts[lang] = lang_counts.get(lang, 0) + 1

            # Rough LOC estimate (count lines in source files)
            if ext in LANGUAGE_EXTENSIONS or ext in {'.html', '.css', '.scss', '.sql', '.md'}:
                try:
                    loc_total += sum(1 for _ in f.open(errors='ignore'))
                except (OSError, UnicodeDecodeError):
                    pass

        # Sort languages by file count, take the most common ones
        analysis.languages = [
            lang for lang, _ in sorted(lang_counts.items(), key=lambda x: -x[1])
        ]
        analysis.loc_estimate = loc_total

        # Detect frameworks from config files
        frameworks = []
        for config_file, framework in FRAMEWORK_INDICATORS.items():
            if (project_dir / config_file).exists():
                if framework:
                    frameworks.append(framework)

        # Check package.json for additional framework hints
        package_json = project_dir / 'package.json'
        if package_json.exists():
            try:
                import json
                pkg = json.loads(package_json.read_text())
                deps = {}
                deps.update(pkg.get('dependencies', {}))
                deps.update(pkg.get('devDependencies', {}))

                if 'react' in deps and 'next.js' not in frameworks:
                    frameworks.append('react')
                if 'express' in deps:
                    frameworks.append('express')
                if 'fastify' in deps:
                    frameworks.append('fastify')
                if 'vue' in deps:
                    frameworks.append('vue')
                if '@angular/core' in deps:
                    if 'angular' not in frameworks:
                        frameworks.append('angular')
                if 'tailwindcss' in deps:
                    analysis.detected_patterns.append('tailwindcss')
            except (json.JSONDecodeError, OSError):
                pass

        # Check requirements.txt / pyproject.toml for Python frameworks
        for req_file in ['requirements.txt', 'requirements-dev.txt']:
            req_path = project_dir / req_file
            if req_path.exists():
                try:
                    content = req_path.read_text().lower()
                    if 'django' in content:
                        frameworks.append('django')
                    if 'flask' in content:
                        frameworks.append('flask')
                    if 'fastapi' in content:
                        frameworks.append('fastapi')
                except OSError:
                    pass

        pyproject = project_dir / 'pyproject.toml'
        if pyproject.exists():
            try:
                content = pyproject.read_text().lower()
                if 'django' in content:
                    frameworks.append('django')
                if 'flask' in content:
                    frameworks.append('flask')
                if 'fastapi' in content:
                    frameworks.append('fastapi')
                if '[tool.pytest' in content:
                    if not analysis.test_framework:
                        analysis.test_framework = 'pytest'
                        analysis.test_runner_command = 'pytest'
                        analysis.has_tests = True
            except OSError:
                pass

        analysis.frameworks = list(dict.fromkeys(frameworks))  # Deduplicate, preserve order

        # Detect package managers
        if (project_dir / 'package.json').exists():
            if (project_dir / 'pnpm-lock.yaml').exists():
                analysis.package_managers.append('pnpm')
            elif (project_dir / 'yarn.lock').exists():
                analysis.package_managers.append('yarn')
            elif (project_dir / 'package-lock.json').exists():
                analysis.package_managers.append('npm')
            else:
                analysis.package_managers.append('npm')
        if (project_dir / 'requirements.txt').exists() or (project_dir / 'pyproject.toml').exists():
            if (project_dir / 'Pipfile').exists():
                analysis.package_managers.append('pipenv')
            elif (project_dir / 'poetry.lock').exists():
                analysis.package_managers.append('poetry')
            else:
                analysis.package_managers.append('pip')
        if (project_dir / 'Cargo.toml').exists():
            analysis.package_managers.append('cargo')
        if (project_dir / 'go.mod').exists():
            analysis.package_managers.append('go modules')

        # Detect test frameworks
        if not analysis.test_framework:
            for config_file, (framework, runner) in TEST_INDICATORS.items():
                if (project_dir / config_file).exists():
                    analysis.test_framework = framework
                    analysis.test_runner_command = runner
                    analysis.has_tests = True
                    break

        # Check for test directories as fallback
        if not analysis.has_tests:
            test_dirs = ['tests', 'test', '__tests__', 'spec', 'specs']
            for td in test_dirs:
                if (project_dir / td).is_dir():
                    analysis.has_tests = True
                    break

        # Detect CI
        for ci_path, ci_platform in CI_INDICATORS.items():
            if (project_dir / ci_path).exists():
                analysis.has_ci = True
                analysis.ci_platform = ci_platform
                break

        # Detect entry points
        entry_candidates = [
            'src/index.ts', 'src/index.js', 'src/main.ts', 'src/main.js',
            'src/app.ts', 'src/app.js', 'app.py', 'main.py', 'server.py',
            'src/index.tsx', 'src/App.tsx', 'src/main.tsx',
            'cmd/main.go', 'main.go', 'src/main.rs', 'src/lib.rs',
            'index.js', 'index.ts', 'server.js', 'server.ts',
        ]
        for entry in entry_candidates:
            if (project_dir / entry).exists():
                analysis.entry_points.append(entry)

        # Key config files
        config_candidates = [
            'package.json', 'tsconfig.json', 'pyproject.toml',
            'requirements.txt', 'Cargo.toml', 'go.mod',
            '.env.example', '.env.local.example',
            'Dockerfile', 'docker-compose.yml', 'docker-compose.yaml',
            'Makefile', '.eslintrc.js', '.prettierrc',
            'tailwind.config.js', 'tailwind.config.ts',
        ]
        for cfg in config_candidates:
            if (project_dir / cfg).exists():
                analysis.key_config_files.append(cfg)

        # Detect patterns
        if (project_dir / 'docker-compose.yml').exists() or (project_dir / 'docker-compose.yaml').exists():
            analysis.detected_patterns.append('docker-compose')
        if (project_dir / 'Dockerfile').exists():
            analysis.detected_patterns.append('docker')
        if (project_dir / '.env.example').exists():
            analysis.detected_patterns.append('env-config')
        if (project_dir / 'Makefile').exists():
            analysis.detected_patterns.append('makefile')

        # Check for monorepo patterns
        if (project_dir / 'lerna.json').exists() or (project_dir / 'turbo.json').exists():
            analysis.detected_patterns.append('monorepo')
        if (project_dir / 'packages').is_dir() or (project_dir / 'apps').is_dir():
            analysis.detected_patterns.append('monorepo')

        # Build directory structure summary (top 2 levels)
        analysis.directory_structure_summary = self._build_directory_summary(project_dir)

        logger.info(
            f"Codebase analysis: {', '.join(analysis.languages[:3])} | "
            f"{', '.join(analysis.frameworks[:3])} | "
            f"{analysis.loc_estimate} LOC | "
            f"tests: {analysis.test_framework or 'none'}"
        )

        return analysis

    async def setup_brownfield_git(
        self, project_dir: Path, branch_name: Optional[str] = None
    ) -> str:
        """
        Set up git branch for brownfield modifications.

        Creates a feature branch for the brownfield changes.
        If the directory isn't a git repo, initializes one.

        Returns the feature branch name.
        """
        if branch_name is None:
            branch_name = "yokeflow/modifications"

        git_dir = project_dir / '.git'

        if not git_dir.exists():
            # Initialize git repo for local imports without git
            await asyncio.to_thread(
                subprocess.run,
                ['git', 'init'],
                cwd=str(project_dir), capture_output=True, text=True
            )
            await asyncio.to_thread(
                subprocess.run,
                ['git', 'add', '.'],
                cwd=str(project_dir), capture_output=True, text=True
            )
            await asyncio.to_thread(
                subprocess.run,
                ['git', 'commit', '-m', 'Initial import for brownfield project'],
                cwd=str(project_dir), capture_output=True, text=True
            )
            logger.info("Initialized git repo for imported codebase")

        # Create and switch to feature branch
        result = await asyncio.to_thread(
            subprocess.run,
            ['git', 'checkout', '-b', branch_name],
            cwd=str(project_dir), capture_output=True, text=True
        )

        if result.returncode != 0:
            # Branch might already exist, try switching to it
            result = await asyncio.to_thread(
                subprocess.run,
                ['git', 'checkout', branch_name],
                cwd=str(project_dir), capture_output=True, text=True
            )

        logger.info(f"Set up brownfield git branch: {branch_name}")
        return branch_name

    def _get_git_sha(self, repo_dir: Path) -> Optional[str]:
        """Get the current git commit SHA, or None if not a git repo."""
        try:
            result = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                cwd=str(repo_dir),
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None

    def _build_directory_summary(self, project_dir: Path, max_depth: int = 2) -> str:
        """Build a tree-like summary of the directory structure (top N levels)."""
        lines = []

        def _walk(directory: Path, prefix: str, depth: int):
            if depth > max_depth:
                return

            try:
                entries = sorted(directory.iterdir(), key=lambda e: (not e.is_dir(), e.name))
            except PermissionError:
                return

            # Filter out excluded patterns and hidden files
            entries = [
                e for e in entries
                if e.name not in self.EXCLUDE_PATTERNS
                and not e.name.startswith('.')
            ]

            for i, entry in enumerate(entries):
                is_last = i == len(entries) - 1
                connector = "--- " if is_last else "|-- "

                if entry.is_dir():
                    lines.append(f"{prefix}{connector}{entry.name}/")
                    extension = "    " if is_last else "|   "
                    _walk(entry, prefix + extension, depth + 1)
                else:
                    lines.append(f"{prefix}{connector}{entry.name}")

        _walk(project_dir, "", 0)

        # Limit to reasonable size
        if len(lines) > 50:
            lines = lines[:50]
            lines.append(f"... ({len(lines)} more entries)")

        return "\n".join(lines)
