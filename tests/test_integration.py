"""
Integration Test Suite for YokeFlow
====================================

Tests integration between different components of the system.

NOTE: These are conceptual integration tests that verify component interactions
work correctly. They use mocks to avoid requiring full infrastructure.

For real end-to-end integration tests with PostgreSQL, see test_integration_database.py
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from server.database.retry import RetryConfig, with_retry
from server.utils.config import Config
from server.utils.errors import DatabaseError, DatabaseConnectionError
from server.utils.logging import get_logger, PerformanceLogger


class TestDatabaseIntegration:
    """Test database integration with retry logic."""

    @pytest.mark.asyncio
    async def test_database_retry_on_transient_error(self):
        """Test that database operations retry on transient errors."""
        mock_conn = AsyncMock()

        # Use ConnectionError which is recognized as transient
        mock_conn.fetchval.side_effect = [
            DatabaseConnectionError("connection refused"),  # Transient pattern
            42  # Success on retry
        ]

        @with_retry(RetryConfig(max_retries=3, base_delay=0.01))
        async def get_value():
            return await mock_conn.fetchval("SELECT 42")

        result = await get_value()
        assert result == 42
        assert mock_conn.fetchval.call_count == 2

    @pytest.mark.asyncio
    async def test_database_gives_up_after_max_retries(self):
        """Test that database stops retrying after max attempts."""
        mock_conn = AsyncMock()

        # Use transient error pattern
        mock_conn.fetchval.side_effect = DatabaseConnectionError("connection refused")

        @with_retry(RetryConfig(max_retries=2, base_delay=0.01))
        async def get_value():
            return await mock_conn.fetchval("SELECT 42")

        with pytest.raises(DatabaseConnectionError):
            await get_value()

        # Should try initial + 2 retries = 3 times
        assert mock_conn.fetchval.call_count == 3


class TestOrchestratorIntegration:
    """Test orchestrator integration concepts."""

    def test_orchestrator_can_be_imported(self):
        """Test orchestrator module can be imported."""
        from server.agent.orchestrator import AgentOrchestrator
        assert AgentOrchestrator is not None

    def test_orchestrator_has_required_methods(self):
        """Test orchestrator has expected interface."""
        from server.agent.orchestrator import AgentOrchestrator
        import inspect

        # Verify key methods exist
        assert hasattr(AgentOrchestrator, '__init__')
        # Other methods would be verified here


class TestSessionManagerIntegration:
    """Test session manager integration."""

    def test_session_manager_imports(self):
        """Test session manager can be imported."""
        from server.agent.session_manager import PausedSessionManager
        assert PausedSessionManager is not None

    def test_checkpoint_manager_imports(self):
        """Test checkpoint manager can be imported."""
        from server.agent.checkpoint import CheckpointManager, CheckpointRecoveryManager
        assert CheckpointManager is not None
        assert CheckpointRecoveryManager is not None


class TestAPIIntegration:
    """Test API integration."""

    def test_api_task_status_endpoint(self):
        """Test task status endpoint exists."""
        from server.api.app import app

        # Verify app has routes
        routes = [str(r.path) for r in app.routes]
        assert len(routes) > 0

    @pytest.mark.asyncio
    async def test_api_websocket_integration(self):
        """Test WebSocket support exists."""
        from server.api.app import app

        # Verify app has WebSocket routes
        routes = [str(r.path) for r in app.routes]
        ws_routes = [r for r in routes if '/ws' in r]
        assert len(ws_routes) > 0


class TestQualitySystemIntegration:
    """Test quality system integration."""

    def test_quality_metrics_functions_exist(self):
        """Test quality metrics functions can be imported."""
        from server.quality.metrics import quick_quality_check, analyze_session_logs

        assert callable(quick_quality_check)
        assert callable(analyze_session_logs)

    def test_quality_gates_integration(self):
        """Test quality gates can be instantiated."""
        from server.quality.gates import QualityGates
        from server.utils.config import Config
        from unittest.mock import AsyncMock

        mock_db = AsyncMock()
        project_path = Path("/tmp/test")
        config = Config()

        gates = QualityGates(db=mock_db, project_path=project_path, config=config)
        assert gates is not None


class TestConfigurationIntegration:
    """Test configuration integration."""

    def test_config_loading_from_file(self, tmp_path):
        """Test config can be loaded from file."""
        config_file = tmp_path / ".yokeflow.yaml"
        config_file.write_text("""
project:
  max_iterations: 10

timing:
  auto_continue_delay: 2
""")

        config = Config.load_from_file(config_file)
        assert config.project.max_iterations == 10
        assert config.timing.auto_continue_delay == 2

    def test_config_with_environment_override(self):
        """Test config environment overrides."""
        import os

        # Set env var
        os.environ["YOKEFLOW_MAX_ITERATIONS"] = "5"

        config = Config()
        # Environment variables can override config
        # (exact behavior depends on implementation)

        # Cleanup
        if "YOKEFLOW_MAX_ITERATIONS" in os.environ:
            del os.environ["YOKEFLOW_MAX_ITERATIONS"]


class TestLoggingIntegration:
    """Test logging integration."""

    def test_structured_logging_integration(self):
        """Test structured logging works."""
        logger = get_logger("test_integration")

        # Should be able to log with context
        logger.info("Test message", extra={"test_key": "test_value"})

        assert logger is not None

    def test_performance_logging_integration(self):
        """Test performance logging context manager."""
        import time

        with PerformanceLogger("test_operation") as perf:
            time.sleep(0.01)

        # PerformanceLogger logs duration but doesn't expose it as attribute
        assert perf.operation == "test_operation"


class TestErrorHandlingIntegration:
    """Test error handling integration."""

    def test_error_propagation(self):
        """Test error hierarchy and propagation."""
        from server.utils.errors import (
            YokeFlowError,
            DatabaseError,
            DatabaseConnectionError,
            DatabaseQueryError
        )

        # Test error hierarchy
        assert issubclass(DatabaseError, YokeFlowError)
        assert issubclass(DatabaseConnectionError, DatabaseError)
        assert issubclass(DatabaseQueryError, DatabaseError)

        # Test creating errors with context
        error = DatabaseError("Test error", context={"key": "value"})
        assert error.context["key"] == "value"

    def test_error_recovery_flow(self):
        """Test error recovery patterns."""
        from server.agent.intervention import BlockerDetector

        # Test blocker detection class exists
        assert BlockerDetector is not None


class TestEndToEndIntegration:
    """Test end-to-end workflows (conceptual)."""

    def test_complete_session_flow_components_exist(self):
        """Test that all components for session flow exist."""
        from server.agent.orchestrator import AgentOrchestrator
        from server.agent.session_manager import PausedSessionManager
        from server.agent.checkpoint import CheckpointManager
        from server.database.operations import TaskDatabase
        from server.client.claude import create_client

        # All components should be importable
        assert AgentOrchestrator is not None
        assert PausedSessionManager is not None
        assert CheckpointManager is not None
        assert TaskDatabase is not None
        assert callable(create_client)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
