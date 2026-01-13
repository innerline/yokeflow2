"""
Test suite for Quality & Review Integration.

Tests the quality integration module including:
- Quality checks after sessions
- Deep review triggers
- Test coverage analysis
- Metrics collection and rating
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch, call
import pytest
import sys
from datetime import datetime
from uuid import uuid4

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from server.quality.integration import QualityIntegration
from server.agent.models import SessionType
from server.utils.config import Config


class TestQualityIntegration:
    """Test suite for QualityIntegration class."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock config object."""
        config = Mock()
        config.models = Mock()
        config.models.review = "claude-3-sonnet"
        config.docker = Mock()
        config.docker.enabled = False
        return config

    @pytest.fixture
    def quality_integration(self, mock_config):
        """Create a QualityIntegration instance."""
        return QualityIntegration(mock_config)

    @pytest.fixture
    def mock_session_logger(self, tmp_path):
        """Create a mock session logger."""
        logger = Mock()
        logger.jsonl_file = tmp_path / "session.jsonl"
        # Create dummy JSONL file
        logger.jsonl_file.write_text(json.dumps({
            "timestamp": "2024-01-01T00:00:00",
            "type": "tool_use",
            "tool_name": "Bash",
            "tool_input": {"command": "npm install"}
        }) + "\n")
        return logger

    @pytest.mark.asyncio
    async def test_run_quality_check_success(self, quality_integration, mock_session_logger, tmp_path):
        """Test successful quality check run."""
        session_id = uuid4()
        project_path = tmp_path / "test_project"
        project_path.mkdir()

        with patch('server.quality.integration.analyze_session_logs') as mock_analyze:
            with patch('server.quality.integration.quick_quality_check') as mock_check:
                with patch('server.quality.integration.get_quality_rating') as mock_rating:
                    with patch('server.quality.integration.DatabaseManager') as mock_db_manager:
                        # Setup mocks
                        mock_analyze.return_value = {
                            'files_created': 5,
                            'tests_written': 3,
                            'browser_checks': 2
                        }
                        mock_check.return_value = []  # No issues
                        mock_rating.return_value = "high"

                        mock_db = AsyncMock()
                        mock_db.store_quality_check = AsyncMock(return_value=uuid4())
                        mock_db_manager.return_value.__aenter__.return_value = mock_db

                        # Run quality check
                        await quality_integration.run_quality_check(
                            session_id=session_id,
                            project_path=project_path,
                            session_logger=mock_session_logger,
                            session_status="continue",
                            session_type=SessionType.CODING
                        )

                        # Verify calls
                        mock_analyze.assert_called_once_with(mock_session_logger.jsonl_file)
                        mock_check.assert_called_once()
                        mock_rating.assert_called_once()
                        mock_db.store_quality_check.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_quality_check_with_issues(self, quality_integration, mock_session_logger, tmp_path):
        """Test quality check with critical issues."""
        session_id = uuid4()
        project_path = tmp_path / "test_project"
        project_path.mkdir()

        with patch('server.quality.integration.analyze_session_logs') as mock_analyze:
            with patch('server.quality.integration.quick_quality_check') as mock_check:
                with patch('server.quality.integration.get_quality_rating') as mock_rating:
                    with patch('server.quality.integration.DatabaseManager') as mock_db_manager:
                        # Setup mocks with issues
                        mock_analyze.return_value = {
                            'files_created': 0,  # No files created
                            'tests_written': 0,  # No tests
                            'browser_checks': 0  # No browser verification
                        }
                        mock_check.return_value = [
                            "❌ No files created",
                            "❌ No tests written",
                            "⚠️ No browser verification"
                        ]
                        mock_rating.return_value = "low"

                        mock_db = AsyncMock()
                        mock_db.store_quality_check = AsyncMock(return_value=uuid4())
                        mock_db_manager.return_value.__aenter__.return_value = mock_db

                        # Run quality check
                        await quality_integration.run_quality_check(
                            session_id=session_id,
                            project_path=project_path,
                            session_logger=mock_session_logger,
                            session_status="continue",
                            session_type=SessionType.CODING
                        )

                        # Should still store results even with issues
                        mock_db.store_quality_check.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_quality_check_initializer_session(self, quality_integration, mock_session_logger, tmp_path):
        """Test quality check for initializer session (no browser verification required)."""
        session_id = uuid4()
        project_path = tmp_path / "test_project"
        project_path.mkdir()

        with patch('server.quality.integration.analyze_session_logs') as mock_analyze:
            with patch('server.quality.integration.quick_quality_check') as mock_check:
                with patch('server.quality.integration.DatabaseManager') as mock_db_manager:
                    mock_analyze.return_value = {
                        'files_created': 1,
                        'epics_created': 5,
                        'tasks_created': 20
                    }
                    mock_check.return_value = []

                    mock_db = AsyncMock()
                    mock_db.store_quality_check = AsyncMock(return_value=uuid4())
                    mock_db_manager.return_value.__aenter__.return_value = mock_db

                    await quality_integration.run_quality_check(
                        session_id=session_id,
                        project_path=project_path,
                        session_logger=mock_session_logger,
                        session_status="continue",
                        session_type=SessionType.INITIALIZER
                    )

                    # Check that is_initializer flag was passed
                    call_args = mock_check.call_args
                    assert call_args.kwargs.get('is_initializer') == True

    @pytest.mark.asyncio
    async def test_run_quality_check_missing_jsonl(self, quality_integration, tmp_path):
        """Test quality check when JSONL log is missing."""
        session_id = uuid4()
        project_path = tmp_path / "test_project"
        project_path.mkdir()

        # Create logger with non-existent JSONL file
        mock_logger = Mock()
        mock_logger.jsonl_file = tmp_path / "missing.jsonl"

        with patch('server.quality.integration.DatabaseManager') as mock_db_manager:
            mock_db = AsyncMock()
            mock_db_manager.return_value.__aenter__.return_value = mock_db

            # Should handle gracefully
            await quality_integration.run_quality_check(
                session_id=session_id,
                project_path=project_path,
                session_logger=mock_logger,
                session_status="continue",
                session_type=SessionType.CODING
            )

            # Should not call store_quality_check
            mock_db.store_quality_check.assert_not_called()

    @pytest.mark.asyncio
    async def test_trigger_deep_review(self, quality_integration):
        """Test triggering deep review for low-quality sessions."""
        session_id = uuid4()
        project_id = uuid4()

        with patch('server.quality.integration.DatabaseManager') as mock_db_manager:
            # Create a mock for the connection object
            mock_conn = MagicMock()
            mock_conn.fetchrow = AsyncMock(return_value={
                'project_id': project_id,
                'session_number': 5
            })
            mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn.__aexit__ = AsyncMock(return_value=None)

            # Create a mock for db.acquire() that returns the connection
            mock_acquire = MagicMock(return_value=mock_conn)

            # Create a mock for the database manager
            mock_db = MagicMock()
            mock_db.acquire = mock_acquire
            mock_db.get_session = AsyncMock(return_value={
                'id': session_id,
                'project_id': project_id
            })
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=None)

            mock_db_manager.return_value = mock_db

            # Mock deep review functions
            with patch('server.quality.reviews.should_trigger_deep_review') as mock_should_trigger:
                with patch('server.quality.reviews.run_deep_review') as mock_run_review:
                    mock_should_trigger.return_value = True  # Will be awaited
                    mock_run_review.return_value = {
                        'review_id': str(uuid4()),
                        'status': 'completed',
                        'rating': 3,
                        'summary': 'Test review'
                    }

                    # Low quality should trigger review
                    rating = 3  # Low quality
                    await quality_integration.maybe_trigger_deep_review(
                        session_id=session_id,
                        project_path=Path('/tmp/test_project'),
                        session_quality=rating
                    )

                    # Should check if review should be triggered
                    mock_should_trigger.assert_called_once()

    @pytest.mark.asyncio
    async def test_test_coverage_analysis(self, quality_integration, tmp_path):
        """Test analyzing test coverage during quality check."""
        project_path = tmp_path / "test_project"
        project_path.mkdir()

        # Create some test files
        (project_path / "test.py").write_text("def test_example(): pass")
        (project_path / "test_another.py").write_text("def test_another(): pass")

        with patch('server.coverage.analyzer.analyze_test_coverage') as mock_coverage:
            mock_coverage.return_value = {
                'test_files': 2,
                'test_functions': 2,
                'estimated_coverage': 45
            }

            # Quality check should include coverage analysis
            # Implementation depends on actual integration

    @pytest.mark.asyncio
    async def test_event_callback_triggered(self, mock_config):
        """Test that event callbacks are triggered during quality checks."""
        events = []

        async def event_callback(project_id, event_type, data):
            events.append((project_id, event_type, data))

        quality_integration = QualityIntegration(mock_config, event_callback)

        # Mock a quality check that should trigger events
        # Implementation depends on actual event system

    def test_quality_rating_calculation(self, quality_integration):
        """Test quality rating calculation based on metrics."""
        from server.quality.metrics import get_quality_rating

        # Test various metrics scenarios
        high_quality_metrics = {
            'files_created': 10,
            'tests_written': 8,
            'playwright_count': 5,  # Using correct key
            'error_rate': 0
        }
        rating = get_quality_rating(high_quality_metrics)
        assert rating >= 7  # High quality should be 7 or higher

        low_quality_metrics = {
            'files_created': 1,
            'tests_written': 0,
            'playwright_count': 0,  # Using correct key
            'error_rate': 0.3  # 30% error rate
        }
        rating = get_quality_rating(low_quality_metrics)
        assert rating <= 4  # Low quality should be 4 or lower


class TestQualityGates:
    """Test quality gates and enforcement."""

    @pytest.mark.asyncio
    async def test_quality_gate_blocks_low_quality(self, tmp_path):
        """Test that quality gates block low-quality sessions."""
        from server.quality.gates import QualityGates, GateType, GateStatus
        from server.utils.config import Config

        # Mock database and config
        mock_db = AsyncMock()
        config = Config.load_default()

        gates = QualityGates(
            db=mock_db,
            project_path=tmp_path,
            config=config
        )

        # Mock internal check methods to simulate low quality
        with patch.object(gates, '_check_test_results', return_value=0.3):  # Low test score
            with patch.object(gates, '_check_code_quality', return_value=(0.4, ['Low code quality'])):
                with patch.object(gates, '_check_documentation', return_value=0.2):
                    with patch.object(gates, '_check_security', return_value=['Security issue found']):
                        # Check the task gate - should fail with low quality
                        task_id = str(uuid4())
                        result = await gates.task_gate(
                            task_id=task_id,
                            session_id=uuid4()
                        )

                        # Low scores should result in FAILED or MANUAL_REVIEW status
                        assert result.status in [GateStatus.FAILED, GateStatus.MANUAL_REVIEW]
                        assert result.score < 0.5  # Low overall score

    @pytest.mark.asyncio
    async def test_quality_gate_allows_high_quality(self, tmp_path):
        """Test that quality gates allow high-quality sessions."""
        from server.quality.gates import QualityGates, GateType, GateStatus
        from server.utils.config import Config

        # Mock database and config
        mock_db = AsyncMock()
        config = Config.load_default()

        gates = QualityGates(
            db=mock_db,
            project_path=tmp_path,
            config=config
        )

        # Mock internal check methods to simulate high quality
        with patch.object(gates, '_check_test_results', return_value=1.0):  # Perfect test score
            with patch.object(gates, '_check_code_quality', return_value=(1.0, [])):  # No quality issues
                with patch.object(gates, '_check_documentation', return_value=0.95):  # Good docs
                    with patch.object(gates, '_check_security', return_value=[]):  # No security issues
                        # Check the task gate - should pass with high quality
                        task_id = str(uuid4())
                        result = await gates.task_gate(
                            task_id=task_id,
                            session_id=uuid4()
                        )

                        # High scores should result in PASSED or WARNING status
                        assert result.status in [GateStatus.PASSED, GateStatus.WARNING]
                        assert result.score > 0.8  # High overall score


def run_tests():
    """Run the test suite."""
    pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    run_tests()