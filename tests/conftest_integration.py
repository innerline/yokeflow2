"""
Integration test configuration with real test database.

This module provides fixtures for integration tests that need a real database
instead of mocks. It sets up and tears down a test database for each test session.

Usage:
    To use in integration tests, import fixtures from here:

    from tests.conftest_integration import test_db, db_session

    @pytest.mark.integration
    async def test_something(test_db):
        async with test_db.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            assert result == 1
"""

import asyncio
import os
from typing import AsyncGenerator
import asyncpg
import pytest
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.database.connection import DatabaseManager


# Test database configuration
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://agent:agent_dev_password@localhost:5432/yokeflow_test"
)


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def test_db_pool(event_loop):
    """
    Create a test database connection pool for the session.

    This is a sync fixture that uses the event loop to run async operations.
    It will skip if PostgreSQL is not available.
    """
    import urllib.parse

    # Check if integration tests should run
    run_integration = os.getenv("RUN_INTEGRATION", "false").lower() == "true"
    if not run_integration:
        pytest.skip("Integration tests disabled. Set RUN_INTEGRATION=true to enable.")

    # Parse the database URL to get connection params
    parsed = urllib.parse.urlparse(TEST_DATABASE_URL)

    db_config = {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "database": parsed.path.lstrip("/"),
        "user": parsed.username,
        "password": parsed.password,
    }

    async def setup_db():
        """Async setup function."""
        # Create the test database if it doesn't exist
        try:
            # Connect to postgres database to create test database
            admin_config = db_config.copy()
            admin_config["database"] = "postgres"

            admin_conn = await asyncpg.connect(**admin_config)

            # Check if test database exists
            exists = await admin_conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1",
                db_config["database"]
            )

            if not exists:
                # Create test database
                await admin_conn.execute(f'CREATE DATABASE {db_config["database"]}')
                print(f"Created test database: {db_config['database']}")

            await admin_conn.close()
        except Exception as e:
            pytest.skip(f"Could not connect to PostgreSQL: {e}")

        # Create connection pool for tests
        try:
            pool = await asyncpg.create_pool(
                dsn=TEST_DATABASE_URL,
                min_size=2,
                max_size=10,
                timeout=10,
                command_timeout=10
            )
        except Exception as e:
            pytest.skip(f"Could not create connection pool: {e}")

        # Initialize schema if needed
        async with pool.acquire() as conn:
            # Check if tables exist
            table_exists = await conn.fetchval(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'projects')"
            )

            if not table_exists:
                # Load and execute schema
                schema_path = Path(__file__).parent.parent / "schema" / "postgresql" / "schema.sql"
                if schema_path.exists():
                    schema_sql = schema_path.read_text()
                    # Execute schema creation
                    try:
                        await conn.execute(schema_sql)
                        print("Initialized test database schema")
                    except Exception as e:
                        print(f"Warning: Could not initialize schema: {e}")

        return pool

    # Run setup in event loop
    pool = event_loop.run_until_complete(setup_db())

    yield pool

    # Cleanup
    async def cleanup():
        await pool.close()

    event_loop.run_until_complete(cleanup())


@pytest.fixture
async def test_db(test_db_pool):
    """Provide a test database connection pool for individual tests."""
    # Clear all data before each test
    async with test_db_pool.acquire() as conn:
        # Get all table names (excluding system tables)
        tables = await conn.fetch("""
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
            AND tablename NOT LIKE 'pg_%'
        """)

        # Truncate all tables
        for table in tables:
            await conn.execute(f'TRUNCATE TABLE {table["tablename"]} CASCADE')

    yield test_db_pool


@pytest.fixture
async def db_session(test_db):
    """Provide a database session (TaskDatabase instance) for tests."""
    # TaskDatabase expects connection_url, not pool
    # We'll use the pool directly for these integration tests
    # since TaskDatabase is designed for production use
    yield test_db


@pytest.fixture
async def db_manager(test_db):
    """Provide a DatabaseManager instance for tests."""
    # Temporarily set the TEST_DATABASE_URL as DATABASE_URL
    original_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL

    manager = DatabaseManager()
    await manager.initialize()

    yield manager

    await manager.close()

    # Restore original DATABASE_URL
    if original_url:
        os.environ["DATABASE_URL"] = original_url
    elif "DATABASE_URL" in os.environ:
        del os.environ["DATABASE_URL"]


@pytest.fixture
async def sample_project(test_db):
    """Create a sample project for testing."""
    async with test_db.acquire() as conn:
        project_id = await conn.fetchval("""
            INSERT INTO projects (
                name, app_spec_path, project_path, status, created_at
            ) VALUES (
                'test_project', '/tmp/test_spec.txt', '/tmp/test_project',
                'in_progress', NOW()
            )
            RETURNING id
        """)

        # Create sample epic
        epic_id = await conn.fetchval("""
            INSERT INTO epics (
                project_id, name, description, status, created_at
            ) VALUES (
                $1, 'Test Epic', 'Test epic description', 'pending', NOW()
            )
            RETURNING id
        """, project_id)

        # Create sample task
        task_id = await conn.fetchval("""
            INSERT INTO tasks (
                epic_id, name, description, status, created_at
            ) VALUES (
                $1, 'Test Task', 'Test task description', 'pending', NOW()
            )
            RETURNING id
        """, epic_id)

        # Create sample test
        test_id = await conn.fetchval("""
            INSERT INTO tests (
                task_id, name, test_type, test_code, status, created_at
            ) VALUES (
                $1, 'Test Case', 'unit', 'assert True', 'pending', NOW()
            )
            RETURNING id
        """, task_id)

        return {
            "project_id": project_id,
            "epic_id": epic_id,
            "task_id": task_id,
            "test_id": test_id
        }


# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration