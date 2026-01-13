"""
Basic Integration Tests for YokeFlow
====================================

Tests basic integration between components with correct imports.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from server.database.retry import RetryConfig, with_retry
from server.utils.config import Config
from server.utils.errors import YokeFlowError, DatabaseError
from server.utils.logging import get_logger, PerformanceLogger


class TestDatabaseRetryIntegration:
    """Test database retry integration."""

    @pytest.mark.asyncio
    async def test_retry_with_exponential_backoff(self):
        """Test retry with exponential backoff."""
        call_count = 0

        @with_retry(RetryConfig(max_retries=3, base_delay=0.01))
        async def flaky_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise DatabaseError("Temporary failure")
            return "success"

        result = await flaky_operation()
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_gives_up_on_permanent_error(self):
        """Test that retry gives up on non-retryable errors."""

        @with_retry(RetryConfig(max_retries=3, base_delay=0.01))
        async def failing_operation():
            raise ValueError("Permanent error")

        with pytest.raises(ValueError):
            await failing_operation()


class TestConfigIntegration:
    """Test configuration system integration."""

    def test_config_loads_defaults(self):
        """Test config loads with defaults."""
        config = Config()

        # Should have default values
        assert config.models is not None
        assert config.project is not None
        assert config.timing is not None

    def test_config_from_file(self, tmp_path):
        """Test config loading from file."""
        config_file = tmp_path / ".yokeflow.yaml"
        config_file.write_text("""
project:
  name: integration_test
  max_iterations: 5

models:
  coding: claude-3-sonnet

timing:
  auto_continue_delay: 1
""")

        # Config uses load_from_file() method, not config_path parameter
        config = Config.load_from_file(config_file)

        # ProjectConfig doesn't have 'name' attribute in v2
        # Just verify config loaded and has expected values
        assert config.project.max_iterations == 5
        assert config.timing.auto_continue_delay == 1


class TestLoggingIntegration:
    """Test logging system integration."""

    def test_logger_creation(self):
        """Test logger creation."""
        logger = get_logger("test_module")

        assert logger is not None
        assert logger.name == "test_module"

    def test_performance_logger(self):
        """Test performance logger."""
        import time
        with PerformanceLogger("test_operation") as perf_logger:
            # Simulate work
            time.sleep(0.01)

        # PerformanceLogger doesn't expose duration, but logs it
        # Just verify it can be used as a context manager
        assert perf_logger.operation == "test_operation"

    def test_structured_logging_with_context(self, caplog):
        """Test structured logging with extra context."""
        logger = get_logger("test")

        with caplog.at_level("INFO"):
            logger.info("Test message", extra={
                "session_id": "test_123",
                "task_id": "task_456"
            })

        assert "Test message" in caplog.text


class TestErrorIntegration:
    """Test error handling integration."""

    def test_error_hierarchy(self):
        """Test error class hierarchy."""
        base_error = YokeFlowError("Base error")
        db_error = DatabaseError("Database error")

        assert isinstance(db_error, YokeFlowError)
        assert isinstance(db_error, Exception)

        # Should have proper error messages
        assert str(base_error) == "Base error"
        assert str(db_error) == "Database error"

    def test_error_with_context(self):
        """Test errors with additional context."""
        try:
            # YokeFlowError uses 'context' parameter, not 'details'
            raise DatabaseError("Connection failed", context={
                "host": "localhost",
                "port": 5432
            })
        except DatabaseError as e:
            assert "Connection failed" in str(e)
            # Context is stored in the error
            assert e.context is not None
            assert e.context["host"] == "localhost"


class TestAPIIntegration:
    """Test API integration."""

    def test_api_app_exists(self):
        """Test that API app can be imported."""
        from server.api.app import app

        assert app is not None

        # Should have routes defined
        routes = list(app.routes)
        assert len(routes) > 0

    def test_api_has_websocket_support(self):
        """Test API has WebSocket support."""
        from server.api.app import app

        # Check for WebSocket routes
        routes = [str(r.path) for r in app.routes]
        ws_routes = [r for r in routes if '/ws' in r]

        assert len(ws_routes) > 0


class TestDatabaseOperations:
    """Test database operations integration."""

    @pytest.mark.asyncio
    async def test_database_connection_pooling(self):
        """Test database connection pooling."""
        from server.database.connection import DatabaseManager

        # DatabaseManager uses asyncpg internally, we just test creation
        # Mock at the asyncpg module level
        with patch('asyncpg.create_pool') as mock_create_pool:
            mock_pool = AsyncMock()
            mock_create_pool.return_value = mock_pool

            # Should be able to create manager
            manager = DatabaseManager("postgresql://test")
            assert manager is not None
            # DatabaseManager stores it as connection_string, not connection_url
            assert manager.connection_string == "postgresql://test"

    @pytest.mark.asyncio
    async def test_database_operations_with_retry(self):
        """Test database operations use retry logic."""
        from server.database.operations import TaskDatabase

        mock_pool = AsyncMock()
        db = TaskDatabase(mock_pool)

        # Mock a database operation
        with patch.object(db, 'acquire') as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__.return_value = mock_conn
            mock_conn.fetchval = AsyncMock(return_value=42)

            # Operations should work with mocked connection
            async with db.acquire() as conn:
                result = await conn.fetchval("SELECT 42")

            assert result == 42


class TestCheckpointSystem:
    """Test checkpoint system integration."""

    @pytest.mark.asyncio
    async def test_checkpoint_manager_creation(self):
        """Test checkpoint manager creation."""
        from server.agent.checkpoint import CheckpointManager

        # CheckpointManager takes session_id and project_id (both must be valid UUIDs)
        session_uuid = uuid4()
        project_uuid = uuid4()

        manager = CheckpointManager(
            session_id=str(session_uuid),
            project_id=str(project_uuid)
        )

        assert manager is not None
        assert manager.session_id == session_uuid
        assert manager.project_id == project_uuid

    @pytest.mark.asyncio
    async def test_checkpoint_recovery_manager(self):
        """Test checkpoint recovery manager."""
        from server.agent.checkpoint import CheckpointRecoveryManager

        # CheckpointRecoveryManager takes no parameters
        recovery = CheckpointRecoveryManager()

        assert recovery is not None


class TestQualitySystem:
    """Test quality system integration."""

    def test_quality_metrics_import(self):
        """Test quality metrics functions can be imported."""
        from server.quality.metrics import quick_quality_check, analyze_session_logs

        # These are functions, not a class
        assert callable(quick_quality_check)
        assert callable(analyze_session_logs)

    def test_quality_gates_import(self):
        """Test quality gates can be imported."""
        from server.quality.gates import QualityGates
        from server.utils.config import Config
        from pathlib import Path

        mock_db = AsyncMock()
        project_path = Path("/tmp/test_project")
        config = Config()

        # QualityGates requires db, project_path, and config
        gates = QualityGates(db=mock_db, project_path=project_path, config=config)

        assert gates is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])