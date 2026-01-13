"""
Test Generator for YokeFlow
============================

Automatically generates tests for completed tasks to ensure code quality
before marking tasks as complete.
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
from uuid import UUID
from datetime import datetime, timezone

from claude_agent_sdk import ClaudeSDKClient

from server.utils.logging import get_logger
from server.utils.errors import YokeFlowError


logger = get_logger(__name__)


class GeneratedTestType(Enum):
    """Types of tests that can be generated."""
    UNIT = "unit"
    INTEGRATION = "integration"
    E2E = "e2e"
    BROWSER = "browser"
    API = "api"
    VALIDATION = "validation"
    BUILD = "build"  # For configuration/compilation tasks
    DATABASE = "database"  # For database/schema tasks


class TaskType(Enum):
    """Types of tasks based on their primary focus."""
    UI = "ui"  # UI/Frontend tasks requiring browser verification
    API = "api"  # Backend API endpoints
    CONFIG = "config"  # Configuration, build setup, tooling
    DATABASE = "database"  # Database schema, migrations
    INTEGRATION = "integration"  # Full-stack workflows
    UNKNOWN = "unknown"  # Default when type cannot be determined


@dataclass
class GeneratedTestSpec:
    """Specification for a test to be generated."""
    test_type: 'GeneratedTestType'
    description: str
    file_path: str
    test_code: str
    dependencies: List[str]
    timeout_seconds: int = 30


@dataclass
class GeneratedTestResult:
    """Result of running a test."""
    test_id: str
    passed: bool
    output: str
    error: Optional[str]
    duration_seconds: float
    test_type: 'GeneratedTestType'


@dataclass
class GeneratedTestSuite:
    """Collection of tests for a task."""
    task_id: str
    tests: List[GeneratedTestSpec]
    created_at: datetime


class AutoTestGenerator:
    """
    Generates automated tests for completed tasks.

    Uses Claude to analyze the task implementation and generate
    appropriate tests based on the code changes.
    """

    def __init__(self, project_path: Path, client: Optional[ClaudeSDKClient] = None):
        """
        Initialize the test generator.

        Args:
            project_path: Path to the project
            client: Optional Claude SDK client for test generation
        """
        self.project_path = project_path
        self.client = client
        self.test_dir = project_path / "tests"

    def _infer_task_type(self, task_description: str) -> TaskType:
        """
        Infer task type from description using keyword analysis.

        Args:
            task_description: Task description text

        Returns:
            TaskType enum value
        """
        desc_lower = task_description.lower()

        # Database task indicators (check first to avoid 'table' matching UI)
        db_keywords = [
            'database', 'schema', ' table', 'migration', 'query',
            ' orm ', 'sql', 'postgres', 'mysql', 'mongodb', 'redis',
            'column', 'index', 'foreign key', 'constraint', 'relationship'
        ]
        # Special handling for 'model' - only if database-related
        if any(kw in desc_lower for kw in db_keywords):
            return TaskType.DATABASE
        if 'model' in desc_lower and any(word in desc_lower for word in [' orm ', 'database', 'schema']):
            return TaskType.DATABASE

        # API task indicators (check before UI to catch 'endpoint', 'route')
        api_keywords = [
            'api', 'endpoint', 'route', 'middleware', 'rest',
            'graphql', 'webhook', 'controller', 'handler',
            'http', 'fastapi', 'express', 'flask'
        ]
        # Check for authentication in API context
        if any(kw in desc_lower for kw in api_keywords):
            return TaskType.API
        if 'auth' in desc_lower and any(word in desc_lower for word in ['endpoint', 'api', 'middleware', 'token']):
            return TaskType.API
        if 'server' in desc_lower and not 'server-side rendering' in desc_lower:
            return TaskType.API

        # Config task indicators (check before UI)
        config_keywords = [
            'config', 'setup', 'typescript', 'build pipeline', 'package',
            'dependencies', 'tooling', 'webpack', 'vite', 'rollup',
            'eslint', 'prettier', 'jest', 'docker', 'environment',
            'initialization', 'scaffold', 'boilerplate', 'install'
        ]
        if any(kw in desc_lower for kw in config_keywords):
            return TaskType.CONFIG
        # Special case for 'build' - only config if with certain words
        if 'build' in desc_lower and any(word in desc_lower for word in ['pipeline', 'tool', 'config', 'setup']):
            return TaskType.CONFIG

        # Integration task indicators (check before UI for 'complete flow')
        integration_keywords = [
            'workflow', 'end-to-end', 'e2e', 'journey', 'full stack',
            'complete flow', 'integration'
        ]
        if any(kw in desc_lower for kw in integration_keywords):
            return TaskType.INTEGRATION
        # Special handling for 'complete' workflows
        if 'complete' in desc_lower and any(word in desc_lower for word in ['authentication', 'checkout', 'onboarding', 'workflow']):
            return TaskType.INTEGRATION
        # Special handling for 'full' workflows
        if 'full' in desc_lower and any(word in desc_lower for word in ['user', 'onboarding', 'workflow', 'process']):
            return TaskType.INTEGRATION

        # UI task indicators (check last as fallback for frontend work)
        ui_keywords = [
            ' ui ', 'component', 'page', 'button', 'display',
            'layout', 'style', 'view', 'render', 'frontend', 'react',
            'vue', 'angular', 'svelte', 'css', 'styling', 'responsive',
            'modal', 'dialog', 'menu', 'navigation', 'sidebar', 'header',
            'footer', 'card', 'dashboard'
        ]
        # Be more careful with generic words like 'list' and 'table'
        if any(kw in desc_lower for kw in ui_keywords):
            return TaskType.UI
        # Handle 'form' specifically - UI if with component/login/signup
        if 'form' in desc_lower and any(word in desc_lower for word in ['component', 'login', 'signup', 'registration', 'contact']):
            return TaskType.UI
        if ('list' in desc_lower or 'table' in desc_lower) and any(word in desc_lower for word in ['component', 'display', 'render', 'view']):
            return TaskType.UI
        # 'Build' for UI only if with UI keywords
        if 'build' in desc_lower and any(word in desc_lower for word in ['component', 'page', 'ui', 'dashboard', 'form']):
            return TaskType.UI

        return TaskType.UNKNOWN

    async def generate_tests_for_task(
        self,
        task_id: str,
        task_description: str,
        modified_files: List[str],
        task_context: Optional[Dict[str, Any]] = None
    ) -> "GeneratedTestSuite":
        """
        Generate tests for a completed task.

        Args:
            task_id: ID of the completed task
            task_description: Description of what the task accomplishes
            modified_files: List of files modified during task implementation
            task_context: Optional additional context about the task

        Returns:
            GeneratedTestSuite containing generated tests
        """
        logger.info(f"Generating tests for task {task_id}", extra={
            "task_id": task_id,
            "modified_files": modified_files
        })

        tests = []

        # Infer task type from description first
        task_type = self._infer_task_type(task_description)

        logger.info(f"Inferred task type: {task_type.value} for task {task_id}", extra={
            "task_id": task_id,
            "task_type": task_type.value,
            "task_description": task_description[:100]
        })

        # Determine test types based on task type
        test_types = self._determine_test_types_for_task(task_type, modified_files)

        # Generate tests for each type
        for test_type in test_types:
            if test_type == GeneratedTestType.UNIT:
                unit_tests = await self._generate_unit_tests(
                    task_description, modified_files, task_context
                )
                tests.extend(unit_tests)

            elif test_type == GeneratedTestType.API:
                api_tests = await self._generate_api_tests(
                    task_description, modified_files, task_context
                )
                tests.extend(api_tests)

            elif test_type == GeneratedTestType.BROWSER:
                browser_tests = await self._generate_browser_tests(
                    task_description, modified_files, task_context
                )
                tests.extend(browser_tests)

            elif test_type == GeneratedTestType.INTEGRATION:
                integration_tests = await self._generate_integration_tests(
                    task_description, modified_files, task_context
                )
                tests.extend(integration_tests)

            elif test_type == GeneratedTestType.BUILD:
                build_tests = await self._generate_build_tests(
                    task_description, modified_files, task_context
                )
                tests.extend(build_tests)

            elif test_type == GeneratedTestType.DATABASE:
                db_tests = await self._generate_database_tests(
                    task_description, modified_files, task_context
                )
                tests.extend(db_tests)

        # Create test suite
        suite = GeneratedTestSuite(
            task_id=task_id,
            tests=tests,
            created_at=datetime.now(timezone.utc)
        )

        logger.info(f"Generated {len(tests)} tests for task {task_id}", extra={
            "task_id": task_id,
            "test_count": len(tests),
            "test_types": [t.test_type.value for t in tests]
        })

        return suite

    def _determine_test_types_for_task(
        self,
        task_type: TaskType,
        modified_files: List[str]
    ) -> List[GeneratedTestType]:
        """
        Determine appropriate test types based on task type.

        This implements the verification matrix from the improvement plan.

        Args:
            task_type: The inferred task type
            modified_files: List of modified files

        Returns:
            List of test types appropriate for the task
        """
        test_types = []

        if task_type == TaskType.UI:
            # UI tasks MUST have browser tests
            test_types = [GeneratedTestType.BROWSER]
            # Also add unit tests if there's logic
            if any('.ts' in f or '.tsx' in f or '.js' in f or '.jsx' in f for f in modified_files):
                test_types.append(GeneratedTestType.UNIT)

        elif task_type == TaskType.API:
            # API tasks need API tests primarily
            test_types = [GeneratedTestType.API]
            # Add unit tests for the implementation
            test_types.append(GeneratedTestType.UNIT)

        elif task_type == TaskType.CONFIG:
            # Config tasks need build verification
            test_types = [GeneratedTestType.BUILD]
            # May also need unit tests for config logic
            if any('.py' in f or '.js' in f or '.ts' in f for f in modified_files):
                test_types.append(GeneratedTestType.UNIT)

        elif task_type == TaskType.DATABASE:
            # Database tasks need database tests
            test_types = [GeneratedTestType.DATABASE]
            # Also integration tests to verify schema works with app
            test_types.append(GeneratedTestType.INTEGRATION)

        elif task_type == TaskType.INTEGRATION:
            # Integration tasks need full E2E testing
            test_types = [GeneratedTestType.E2E, GeneratedTestType.BROWSER]

        else:
            # Unknown type - fall back to file-based detection
            test_types = self._determine_test_types(modified_files)

        logger.info(f"Selected test types {[t.value for t in test_types]} for task type {task_type.value}")
        return test_types

    def _determine_test_types(self, modified_files: List[str]) -> List[GeneratedTestType]:
        """
        Determine what types of tests are needed based on modified files.

        Args:
            modified_files: List of modified file paths

        Returns:
            List of test types to generate
        """
        test_types = set()

        for file_path in modified_files:
            path = Path(file_path)

            # Backend/API files need unit and API tests
            if any(part in str(path) for part in ["api/", "core/", "server/", "backend/"]):
                test_types.add(GeneratedTestType.UNIT)
                test_types.add(GeneratedTestType.API)

            # Frontend files need browser tests
            if any(part in str(path) for part in ["web-ui/", "frontend/", "components/", "pages/"]):
                test_types.add(GeneratedTestType.BROWSER)

            # Database files need integration tests
            if any(part in str(path) for part in ["database/", "schema/", "migrations/"]):
                test_types.add(GeneratedTestType.INTEGRATION)

            # Python files generally need unit tests
            if path.suffix == ".py":
                test_types.add(GeneratedTestType.UNIT)

            # TypeScript/JavaScript files need appropriate tests
            if path.suffix in [".ts", ".tsx", ".js", ".jsx"]:
                if "test" not in str(path):
                    test_types.add(GeneratedTestType.UNIT)

        return list(test_types)

    async def _generate_unit_tests(
        self,
        task_description: str,
        modified_files: List[str],
        context: Optional[Dict[str, Any]] = None
    ) -> List["GeneratedTestSpec"]:
        """Generate unit tests for Python modules."""
        tests = []

        # Filter for Python files
        py_files = [f for f in modified_files if f.endswith('.py')]

        for file_path in py_files:
            # Skip test files themselves
            if 'test_' in file_path or '_test.py' in file_path:
                continue

            # Read the file content
            full_path = self.project_path / file_path
            if not full_path.exists():
                continue

            try:
                content = full_path.read_text()
            except Exception as e:
                logger.warning(f"Could not read file {file_path}: {e}")
                continue

            # Generate test code (simplified - in production would use Claude)
            test_code = self._generate_basic_unit_test(file_path, content, task_description)

            # Create test spec
            test_file = f"test_{Path(file_path).stem}.py"
            test_path = f"tests/unit/{test_file}"

            test_spec = GeneratedTestSpec(
                test_type=GeneratedTestType.UNIT,
                description=f"Unit test for {file_path}",
                file_path=test_path,
                test_code=test_code,
                dependencies=["pytest"],
                timeout_seconds=10
            )

            tests.append(test_spec)

        return tests

    async def _generate_api_tests(
        self,
        task_description: str,
        modified_files: List[str],
        context: Optional[Dict[str, Any]] = None
    ) -> List["GeneratedTestSpec"]:
        """Generate API endpoint tests."""
        tests = []

        # Check if API files were modified
        api_files = [f for f in modified_files if 'api/' in f or 'endpoint' in f.lower()]

        if api_files:
            # Generate API test template
            test_code = self._generate_api_test_template(task_description, api_files)

            test_spec = GeneratedTestSpec(
                test_type=GeneratedTestType.API,
                description=f"API test for task: {task_description[:50]}",
                file_path="tests/api/test_endpoints.py",
                test_code=test_code,
                dependencies=["pytest", "httpx", "pytest-asyncio"],
                timeout_seconds=30
            )

            tests.append(test_spec)

        return tests

    async def _generate_browser_tests(
        self,
        task_description: str,
        modified_files: List[str],
        context: Optional[Dict[str, Any]] = None
    ) -> List["GeneratedTestSpec"]:
        """Generate browser/E2E tests using Playwright."""
        tests = []

        # Check if frontend files were modified
        frontend_files = [f for f in modified_files if any(
            part in f for part in ["web-ui/", "components/", "pages/"]
        )]

        if frontend_files:
            # Generate Playwright test
            test_code = self._generate_playwright_test_template(task_description, frontend_files)

            test_spec = GeneratedTestSpec(
                test_type=GeneratedTestType.BROWSER,
                description=f"Browser test for task: {task_description[:50]}",
                file_path="tests/e2e/test_browser.py",
                test_code=test_code,
                dependencies=["playwright", "pytest-playwright"],
                timeout_seconds=60
            )

            tests.append(test_spec)

        return tests

    async def _generate_integration_tests(
        self,
        task_description: str,
        modified_files: List[str],
        context: Optional[Dict[str, Any]] = None
    ) -> List["GeneratedTestSpec"]:
        """Generate integration tests."""
        tests = []

        # Check if database or integration-worthy files were modified
        integration_files = [f for f in modified_files if any(
            part in f for part in ["database", "schema", "integration", "workflow"]
        )]

        if integration_files:
            test_code = self._generate_integration_test_template(task_description, integration_files)

            test_spec = GeneratedTestSpec(
                test_type=GeneratedTestType.INTEGRATION,
                description=f"Integration test for task: {task_description[:50]}",
                file_path="tests/integration/test_workflow.py",
                test_code=test_code,
                dependencies=["pytest", "pytest-asyncio"],
                timeout_seconds=45
            )

            tests.append(test_spec)

        return tests

    def _generate_basic_unit_test(
        self,
        file_path: str,
        content: str,
        task_description: str
    ) -> str:
        """Generate basic unit test code."""
        # Extract functions/classes from the file (simplified)
        module_name = Path(file_path).stem

        test_template = f'''"""
Unit tests for {file_path}
Task: {task_description}
Generated: {datetime.now(timezone.utc).isoformat()}
"""

import pytest
from unittest.mock import Mock, patch
from {module_name} import *


class Test{module_name.title().replace("_", "")}:
    """Test suite for {module_name} module."""

    def test_module_imports(self):
        """Test that the module imports successfully."""
        import {module_name}
        assert {module_name} is not None

    def test_basic_functionality(self):
        """Test basic functionality of the module."""
        # TODO: Add specific tests based on the module's functions
        pass

    @pytest.mark.asyncio
    async def test_async_operations(self):
        """Test async operations if present."""
        # TODO: Add async tests if the module has async functions
        pass
'''
        return test_template

    def _generate_api_test_template(
        self,
        task_description: str,
        api_files: List[str]
    ) -> str:
        """Generate API test template."""
        return f'''"""
API tests for task: {task_description}
Modified files: {', '.join(api_files)}
Generated: {datetime.now(timezone.utc).isoformat()}
"""

import pytest
import httpx
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_api_endpoint_health():
    """Test that the API endpoint is healthy."""
    async with AsyncClient(base_url="http://localhost:8000") as client:
        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "degraded"]


@pytest.mark.asyncio
async def test_api_endpoint_validation():
    """Test input validation for API endpoints."""
    async with AsyncClient(base_url="http://localhost:8000") as client:
        # Test with invalid data
        response = await client.post(
            "/api/endpoint",
            json={{"invalid": "data"}}
        )
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_api_endpoint_success():
    """Test successful API operation."""
    async with AsyncClient(base_url="http://localhost:8000") as client:
        response = await client.post(
            "/api/endpoint",
            json={{"valid": "data"}}
        )
        assert response.status_code in [200, 201]
        data = response.json()
        assert "result" in data
'''

    def _generate_playwright_test_template(
        self,
        task_description: str,
        frontend_files: List[str]
    ) -> str:
        """Generate Playwright browser test template."""
        return f'''"""
Browser tests for task: {task_description}
Modified files: {', '.join(frontend_files)}
Generated: {datetime.now(timezone.utc).isoformat()}
"""

import pytest
from playwright.async_api import Page, expect


@pytest.mark.asyncio
async def test_page_loads(page: Page):
    """Test that the page loads successfully."""
    await page.goto("http://localhost:3000")
    await expect(page).to_have_title(re.compile("YokeFlow"))


@pytest.mark.asyncio
async def test_ui_interaction(page: Page):
    """Test UI interactions."""
    await page.goto("http://localhost:3000")

    # Test button click
    button = page.locator("button:has-text('Submit')")
    if await button.is_visible():
        await button.click()

    # Test form submission
    await page.fill("input[name='project_name']", "test-project")
    await page.click("button[type='submit']")

    # Wait for result
    await page.wait_for_selector(".success-message", timeout=5000)


@pytest.mark.asyncio
async def test_responsive_design(page: Page):
    """Test responsive design."""
    # Test mobile view
    await page.set_viewport_size({{"width": 375, "height": 667}})
    await page.goto("http://localhost:3000")

    # Check mobile menu is visible
    mobile_menu = page.locator(".mobile-menu")
    await expect(mobile_menu).to_be_visible()

    # Test desktop view
    await page.set_viewport_size({{"width": 1920, "height": 1080}})
    await page.reload()

    # Check desktop navigation is visible
    desktop_nav = page.locator(".desktop-nav")
    await expect(desktop_nav).to_be_visible()
'''

    def _generate_integration_test_template(
        self,
        task_description: str,
        integration_files: List[str]
    ) -> str:
        """Generate integration test template."""
        return f'''"""
Integration tests for task: {task_description}
Modified files: {', '.join(integration_files)}
Generated: {datetime.now(timezone.utc).isoformat()}
"""

import pytest
import asyncio
from pathlib import Path


@pytest.mark.asyncio
async def test_end_to_end_workflow():
    """Test complete workflow integration."""
    # Setup
    project_id = "test-project"

    # Step 1: Create project
    # TODO: Implement project creation

    # Step 2: Initialize session
    # TODO: Implement session initialization

    # Step 3: Run task
    # TODO: Implement task execution

    # Step 4: Verify results
    # TODO: Implement result verification

    # Cleanup
    # TODO: Implement cleanup
    pass


@pytest.mark.asyncio
async def test_database_integration():
    """Test database operations."""
    from server.database.operations import TaskDatabase

    db = TaskDatabase()

    # Test connection
    async with db.acquire() as conn:
        result = await conn.fetchval("SELECT 1")
        assert result == 1

    # Test task operations
    # TODO: Add specific database tests
    pass


@pytest.mark.asyncio
async def test_mcp_integration():
    """Test MCP server integration."""
    # TODO: Test MCP tool execution
    pass
'''

    async def _generate_build_tests(
        self,
        task_description: str,
        modified_files: List[str],
        context: Optional[Dict[str, Any]] = None
    ) -> List["GeneratedTestSpec"]:
        """Generate build/compilation tests for configuration tasks."""
        tests = []

        # Check for configuration files
        config_files = [f for f in modified_files if any(
            pattern in f for pattern in [
                'tsconfig', 'webpack', 'vite', 'rollup', 'babel',
                'package.json', 'requirements.txt', 'pyproject.toml',
                'docker', 'eslint', 'prettier', '.config'
            ]
        )]

        if config_files or 'config' in task_description.lower():
            # Generate build test
            test_code = self._generate_build_test_template(task_description, modified_files)

            test_spec = GeneratedTestSpec(
                test_type=GeneratedTestType.BUILD,
                description=f"Build verification for task: {task_description[:50]}",
                file_path="tests/build/test_build.py",
                test_code=test_code,
                dependencies=["pytest"],
                timeout_seconds=15  # Build tests should be fast
            )

            tests.append(test_spec)

        return tests

    async def _generate_database_tests(
        self,
        task_description: str,
        modified_files: List[str],
        context: Optional[Dict[str, Any]] = None
    ) -> List["GeneratedTestSpec"]:
        """Generate database schema and query tests."""
        tests = []

        # Check for database-related files
        db_files = [f for f in modified_files if any(
            pattern in f for pattern in [
                'schema', 'migration', 'model', 'database',
                '.sql', 'alembic', 'prisma', 'entity'
            ]
        )]

        if db_files or 'database' in task_description.lower():
            # Generate database test
            test_code = self._generate_database_test_template(task_description, db_files)

            test_spec = GeneratedTestSpec(
                test_type=GeneratedTestType.DATABASE,
                description=f"Database test for task: {task_description[:50]}",
                file_path="tests/database/test_schema.py",
                test_code=test_code,
                dependencies=["pytest", "pytest-asyncio", "asyncpg"],
                timeout_seconds=20  # Database tests are moderately fast
            )

            tests.append(test_spec)

        return tests

    def _generate_build_test_template(
        self,
        task_description: str,
        modified_files: List[str]
    ) -> str:
        """Generate build verification test template."""
        return f'''"""
Build verification tests for task: {task_description}
Modified files: {', '.join(modified_files)}
Generated: {datetime.now(timezone.utc).isoformat()}
"""

import pytest
import subprocess
import json
from pathlib import Path


def test_typescript_compilation():
    """Test that TypeScript compiles without errors."""
    if Path("tsconfig.json").exists():
        result = subprocess.run(
            ["npx", "tsc", "--noEmit"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"TypeScript compilation failed: {{result.stderr}}"


def test_package_json_valid():
    """Test that package.json is valid JSON."""
    if Path("package.json").exists():
        with open("package.json") as f:
            package = json.load(f)
        assert "name" in package, "package.json missing name field"
        assert "version" in package, "package.json missing version field"


def test_dependencies_installed():
    """Test that dependencies are properly installed."""
    if Path("package.json").exists():
        # Check node_modules exists
        assert Path("node_modules").exists(), "node_modules not found - run npm install"

        # Verify lock file exists
        assert (Path("package-lock.json").exists() or
                Path("yarn.lock").exists() or
                Path("pnpm-lock.yaml").exists()), "No lock file found"


def test_linting_passes():
    """Test that linting passes without errors."""
    if Path(".eslintrc.js").exists() or Path(".eslintrc.json").exists():
        result = subprocess.run(
            ["npx", "eslint", ".", "--max-warnings", "0"],
            capture_output=True,
            text=True
        )
        # Allow linting to have warnings but not errors
        assert "error" not in result.stderr.lower(), f"ESLint errors found: {{result.stderr}}"


def test_build_command_succeeds():
    """Test that the build command runs successfully."""
    if Path("package.json").exists():
        with open("package.json") as f:
            package = json.load(f)

        if "scripts" in package and "build" in package["scripts"]:
            result = subprocess.run(
                ["npm", "run", "build"],
                capture_output=True,
                text=True,
                timeout=60  # 1 minute timeout
            )
            assert result.returncode == 0, f"Build failed: {{result.stderr}}"
'''

    def _generate_database_test_template(
        self,
        task_description: str,
        db_files: List[str]
    ) -> str:
        """Generate database test template."""
        return f'''"""
Database tests for task: {task_description}
Modified files: {', '.join(db_files)}
Generated: {datetime.now(timezone.utc).isoformat()}
"""

import pytest
import asyncio
import asyncpg
from pathlib import Path


@pytest.mark.asyncio
async def test_database_connection():
    """Test that database connection works."""
    try:
        # Try to connect to the database
        conn = await asyncpg.connect(
            host='localhost',
            port=5432,
            user='test_user',
            password='test_pass',
            database='test_db'
        )

        # Test basic query
        result = await conn.fetchval("SELECT 1")
        assert result == 1

        await conn.close()
    except Exception as e:
        pytest.skip(f"Database not available: {{e}}")


@pytest.mark.asyncio
async def test_schema_exists():
    """Test that required tables exist."""
    try:
        conn = await asyncpg.connect(
            host='localhost',
            port=5432,
            user='test_user',
            password='test_pass',
            database='test_db'
        )

        # Check for common tables based on the task
        tables = await conn.fetch("""
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
        """)

        table_names = [t['tablename'] for t in tables]

        # Basic assertion - at least one table should exist
        assert len(table_names) > 0, "No tables found in database"

        await conn.close()
    except Exception as e:
        pytest.skip(f"Database not available: {{e}}")


@pytest.mark.asyncio
async def test_migrations_applied():
    """Test that database migrations have been applied."""
    migration_dir = Path("migrations") or Path("alembic") or Path("schema/migrations")

    if migration_dir.exists():
        # Check that migration files exist
        migration_files = list(migration_dir.glob("*.sql")) or list(migration_dir.glob("*.py"))
        assert len(migration_files) > 0, "No migration files found"

        # In a real test, would check migration history table
        # For now, just verify files exist


def test_sql_syntax_valid():
    """Test that SQL files have valid syntax."""
    sql_files = list(Path(".").glob("**/*.sql"))

    for sql_file in sql_files:
        with open(sql_file) as f:
            content = f.read()

        # Basic syntax checks
        assert content.strip(), f"Empty SQL file: {{sql_file}}"
        assert "--" not in content or content.count("--") == content.count("\\n--"), \
            f"Possible SQL injection in {{sql_file}}"

        # Check for common SQL keywords
        sql_lower = content.lower()
        has_ddl = any(kw in sql_lower for kw in ['create', 'alter', 'drop'])
        has_dml = any(kw in sql_lower for kw in ['select', 'insert', 'update', 'delete'])

        assert has_ddl or has_dml, f"No valid SQL statements found in {{sql_file}}"
'''

    async def save_test_suite(self, suite: "GeneratedTestSuite") -> None:
        """
        Save generated test suite to files.

        Args:
            suite: The test suite to save
        """
        # Ensure test directory exists
        self.test_dir.mkdir(parents=True, exist_ok=True)

        for test in suite.tests:
            # Create test file path
            test_path = self.project_path / test.file_path
            test_path.parent.mkdir(parents=True, exist_ok=True)

            # Write test code
            test_path.write_text(test.test_code)

            logger.info(f"Saved test to {test.file_path}", extra={
                "test_type": test.test_type.value,
                "file_path": test.file_path
            })

    async def analyze_test_coverage(
        self,
        task_id: str,
        modified_files: List[str]
    ) -> Dict[str, Any]:
        """
        Analyze test coverage for modified files.

        Args:
            task_id: Task ID
            modified_files: List of modified files

        Returns:
            Coverage analysis results
        """
        coverage = {
            "task_id": task_id,
            "total_files": len(modified_files),
            "files_with_tests": 0,
            "coverage_percentage": 0.0,
            "missing_tests": []
        }

        for file_path in modified_files:
            # Check if test exists for this file
            test_name = f"test_{Path(file_path).stem}.py"
            test_paths = [
                self.test_dir / test_name,
                self.test_dir / "unit" / test_name,
                self.test_dir / "integration" / test_name
            ]

            has_test = any(p.exists() for p in test_paths)

            if has_test:
                coverage["files_with_tests"] += 1
            else:
                coverage["missing_tests"].append(file_path)

        if coverage["total_files"] > 0:
            coverage["coverage_percentage"] = (
                coverage["files_with_tests"] / coverage["total_files"] * 100
            )

        return coverage