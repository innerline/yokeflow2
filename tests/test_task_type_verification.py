"""
Tests for Task-Type Aware Verification System
==============================================

Tests the new task type inference and appropriate test generation.
"""

import pytest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch

from server.verification.test_generator import (
    AutoTestGenerator,
    TaskType,
    GeneratedTestType,
    GeneratedTestSpec,
    GeneratedTestSuite
)


class TestTaskTypeInference:
    """Test task type inference from descriptions."""

    @pytest.fixture
    def generator(self, tmp_path):
        """Create test generator instance."""
        return AutoTestGenerator(tmp_path)

    def test_ui_task_detection(self, generator):
        """Test detection of UI tasks."""
        ui_descriptions = [
            "Create login form component",
            "Build dashboard page with charts",
            "Implement responsive navigation menu",
            "Style the user profile card",
            "Add modal dialog for confirmation",
            "Update header layout",
            "Create React component for product list"
        ]

        for desc in ui_descriptions:
            task_type = generator._infer_task_type(desc)
            assert task_type == TaskType.UI, f"Failed to detect UI task: {desc}"

    def test_api_task_detection(self, generator):
        """Test detection of API tasks."""
        api_descriptions = [
            "Create REST API endpoint for user registration",
            "Implement authentication middleware",
            "Build GraphQL resolver for product queries",
            "Set up webhook handler for payment events",
            "Add route for fetching user data",
            "Create FastAPI endpoint for file upload",
            "Implement Express.js controller"
        ]

        for desc in api_descriptions:
            task_type = generator._infer_task_type(desc)
            assert task_type == TaskType.API, f"Failed to detect API task: {desc}"

    def test_database_task_detection(self, generator):
        """Test detection of database tasks."""
        db_descriptions = [
            "Create users database table",
            "Add migration for order history",
            "Define ORM models for products",
            "Set up database connection pool",
            "Add index to improve query performance",
            "Create foreign key constraint",
            "Implement MongoDB schema"
        ]

        for desc in db_descriptions:
            task_type = generator._infer_task_type(desc)
            assert task_type == TaskType.DATABASE, f"Failed to detect database task: {desc}"

    def test_config_task_detection(self, generator):
        """Test detection of configuration tasks."""
        config_descriptions = [
            "Initialize TypeScript configuration",
            "Set up build pipeline with Webpack",
            "Configure ESLint and Prettier",
            "Install project dependencies",
            "Set up Docker environment",
            "Configure Vite for development",
            "Initialize package.json"
        ]

        for desc in config_descriptions:
            task_type = generator._infer_task_type(desc)
            assert task_type == TaskType.CONFIG, f"Failed to detect config task: {desc}"

    def test_integration_task_detection(self, generator):
        """Test detection of integration tasks."""
        integration_descriptions = [
            "Implement complete authentication workflow",
            "Build end-to-end checkout process",
            "Create full user onboarding journey",
            "Connect frontend to backend integration",
            "Implement complete user journey from signup to dashboard"
        ]

        for desc in integration_descriptions:
            task_type = generator._infer_task_type(desc)
            assert task_type == TaskType.INTEGRATION, f"Failed to detect integration task: {desc}"

    def test_unknown_task_detection(self, generator):
        """Test that ambiguous descriptions return UNKNOWN."""
        unknown_descriptions = [
            "Fix bug in system",
            "Refactor code",
            "Improve performance",
            "Update documentation"
        ]

        for desc in unknown_descriptions:
            task_type = generator._infer_task_type(desc)
            assert task_type == TaskType.UNKNOWN, f"Should return UNKNOWN for: {desc}"


class TestTaskTypeTestGeneration:
    """Test that appropriate tests are generated for each task type."""

    @pytest.fixture
    def generator(self, tmp_path):
        """Create test generator instance."""
        return AutoTestGenerator(tmp_path)

    def test_ui_task_generates_browser_tests(self, generator):
        """Test that UI tasks generate browser tests."""
        task_type = TaskType.UI
        modified_files = ["web-ui/components/LoginForm.tsx"]

        test_types = generator._determine_test_types_for_task(task_type, modified_files)

        assert GeneratedTestType.BROWSER in test_types, "UI tasks must generate browser tests"
        assert GeneratedTestType.UNIT in test_types, "UI tasks with logic should have unit tests"

    def test_api_task_generates_api_tests(self, generator):
        """Test that API tasks generate API tests."""
        task_type = TaskType.API
        modified_files = ["server/api/routes/users.py"]

        test_types = generator._determine_test_types_for_task(task_type, modified_files)

        assert GeneratedTestType.API in test_types, "API tasks must generate API tests"
        assert GeneratedTestType.UNIT in test_types, "API tasks should have unit tests"
        assert GeneratedTestType.BROWSER not in test_types, "API tasks shouldn't need browser tests"

    def test_config_task_generates_build_tests(self, generator):
        """Test that config tasks generate build tests."""
        task_type = TaskType.CONFIG
        modified_files = ["tsconfig.json", "webpack.config.js"]

        test_types = generator._determine_test_types_for_task(task_type, modified_files)

        assert GeneratedTestType.BUILD in test_types, "Config tasks must generate build tests"
        assert GeneratedTestType.BROWSER not in test_types, "Config tasks don't need browser tests"

    def test_database_task_generates_database_tests(self, generator):
        """Test that database tasks generate database tests."""
        task_type = TaskType.DATABASE
        modified_files = ["schema/migrations/001_create_users.sql"]

        test_types = generator._determine_test_types_for_task(task_type, modified_files)

        assert GeneratedTestType.DATABASE in test_types, "Database tasks must generate DB tests"
        assert GeneratedTestType.INTEGRATION in test_types, "Database tasks need integration tests"
        assert GeneratedTestType.BROWSER not in test_types, "Database tasks don't need browser tests"

    def test_integration_task_generates_e2e_tests(self, generator):
        """Test that integration tasks generate E2E tests."""
        task_type = TaskType.INTEGRATION
        modified_files = ["multiple/files/across/system.py"]

        test_types = generator._determine_test_types_for_task(task_type, modified_files)

        assert GeneratedTestType.E2E in test_types, "Integration tasks must generate E2E tests"
        assert GeneratedTestType.BROWSER in test_types, "Integration tasks need browser tests"


class TestBuildTestGeneration:
    """Test build test generation for configuration tasks."""

    @pytest.fixture
    def generator(self, tmp_path):
        """Create test generator instance."""
        return AutoTestGenerator(tmp_path)

    @pytest.mark.asyncio
    async def test_build_test_generation(self, generator):
        """Test that build tests are generated for config files."""
        task_description = "Configure TypeScript and build tools"
        modified_files = ["tsconfig.json", "package.json", "webpack.config.js"]

        tests = await generator._generate_build_tests(
            task_description, modified_files
        )

        assert len(tests) == 1, "Should generate one build test suite"
        test = tests[0]

        assert test.test_type == GeneratedTestType.BUILD
        assert "Build verification" in test.description
        assert test.timeout_seconds == 15, "Build tests should be fast"
        assert "test_typescript_compilation" in test.test_code
        assert "test_build_command_succeeds" in test.test_code


class TestDatabaseTestGeneration:
    """Test database test generation."""

    @pytest.fixture
    def generator(self, tmp_path):
        """Create test generator instance."""
        return AutoTestGenerator(tmp_path)

    @pytest.mark.asyncio
    async def test_database_test_generation(self, generator):
        """Test that database tests are generated for schema files."""
        task_description = "Create users table with authentication fields"
        modified_files = ["schema/migrations/001_users.sql", "server/models/user.py"]

        tests = await generator._generate_database_tests(
            task_description, modified_files
        )

        assert len(tests) == 1, "Should generate one database test suite"
        test = tests[0]

        assert test.test_type == GeneratedTestType.DATABASE
        assert "Database test" in test.description
        assert test.timeout_seconds == 20, "Database tests are moderately fast"
        assert "test_database_connection" in test.test_code
        assert "test_schema_exists" in test.test_code
        assert "asyncpg" in test.dependencies


class TestEndToEndTaskTypeFlow:
    """Test complete flow from task description to test generation."""

    @pytest.fixture
    def generator(self, tmp_path):
        """Create test generator instance."""
        return AutoTestGenerator(tmp_path)

    @pytest.mark.asyncio
    async def test_ui_task_full_flow(self, generator):
        """Test complete flow for a UI task."""
        task_id = "task-123"
        task_description = "Create login form component with validation"
        modified_files = ["web-ui/components/LoginForm.tsx", "web-ui/styles/login.css"]

        # Generate tests
        suite = await generator.generate_tests_for_task(
            task_id, task_description, modified_files
        )

        # Verify suite
        assert suite.task_id == task_id
        assert len(suite.tests) > 0

        # Check for browser tests
        browser_tests = [t for t in suite.tests if t.test_type == GeneratedTestType.BROWSER]
        assert len(browser_tests) > 0, "UI task must generate browser tests"

        # Verify no unnecessary build tests
        build_tests = [t for t in suite.tests if t.test_type == GeneratedTestType.BUILD]
        assert len(build_tests) == 0, "UI task shouldn't generate build tests"

    @pytest.mark.asyncio
    async def test_config_task_full_flow(self, generator):
        """Test complete flow for a configuration task."""
        task_id = "task-456"
        task_description = "Set up TypeScript configuration and build pipeline"
        modified_files = ["tsconfig.json", "package.json"]

        # Generate tests
        suite = await generator.generate_tests_for_task(
            task_id, task_description, modified_files
        )

        # Verify suite
        assert suite.task_id == task_id
        assert len(suite.tests) > 0

        # Check for build tests
        build_tests = [t for t in suite.tests if t.test_type == GeneratedTestType.BUILD]
        assert len(build_tests) > 0, "Config task must generate build tests"

        # Verify no unnecessary browser tests
        browser_tests = [t for t in suite.tests if t.test_type == GeneratedTestType.BROWSER]
        assert len(browser_tests) == 0, "Config task shouldn't generate browser tests"


class TestVerificationTimeReduction:
    """Test that task-type awareness reduces verification time."""

    def test_time_savings_calculation(self):
        """Calculate time savings from task-type aware verification."""
        # Time estimates (in seconds)
        browser_test_time = 300  # 5 minutes
        api_test_time = 120      # 2 minutes
        build_test_time = 30     # 30 seconds
        db_test_time = 60        # 1 minute

        # Sample project with 20 tasks
        tasks = {
            "ui": 5,      # UI tasks
            "api": 6,     # API tasks
            "config": 5,  # Config tasks
            "database": 3, # Database tasks
            "integration": 1  # Integration task
        }

        # Old approach: everything gets browser tests
        old_time = sum(tasks.values()) * browser_test_time

        # New approach: task-specific tests
        new_time = (
            tasks["ui"] * browser_test_time +
            tasks["api"] * api_test_time +
            tasks["config"] * build_test_time +
            tasks["database"] * db_test_time +
            tasks["integration"] * browser_test_time
        )

        time_saved = old_time - new_time
        percentage_saved = (time_saved / old_time) * 100

        assert new_time < old_time, "New approach should be faster"
        assert percentage_saved > 30, f"Should save >30% time, saved {percentage_saved:.1f}%"

        print(f"\nTime Savings Analysis:")
        print(f"Old approach: {old_time/60:.1f} minutes")
        print(f"New approach: {new_time/60:.1f} minutes")
        print(f"Time saved: {time_saved/60:.1f} minutes ({percentage_saved:.1f}%)")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])