"""
Tests for verification CLI module.

Verifies that the CLI entry point works correctly.
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from uuid import uuid4

# Mock the database operations before importing cli
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.mark.asyncio
async def test_cli_module_can_be_imported():
    """Test that CLI module can be imported without errors."""
    from server.verification import cli
    assert hasattr(cli, 'main')
    assert hasattr(cli, 'run_verification')


@pytest.mark.asyncio
async def test_run_verification_with_disabled_config():
    """Test that verification exits with code 2 when disabled in config."""
    from server.verification.cli import run_verification
    from server.utils.config import VerificationConfig

    with patch('server.verification.cli.Config.load_default') as mock_config:
        # Mock config with verification disabled
        mock_cfg = Mock()
        mock_cfg.verification = VerificationConfig(enabled=False)
        mock_config.return_value = mock_cfg

        # Should return exit code 2 (config error, don't block)
        exit_code = await run_verification(
            task_id=str(uuid4()),
            project_path='/tmp/test',
            session_id=str(uuid4())
        )

        assert exit_code == 2


@pytest.mark.asyncio
async def test_run_verification_with_invalid_uuid():
    """Test that verification exits with code 2 for invalid UUID."""
    from server.verification.cli import run_verification
    from server.utils.config import VerificationConfig

    with patch('server.verification.cli.Config.load_default') as mock_config:
        # Mock config with verification enabled
        mock_cfg = Mock()
        mock_cfg.verification = VerificationConfig(enabled=True)
        mock_config.return_value = mock_cfg

        # Should return exit code 2 for invalid UUID
        exit_code = await run_verification(
            task_id='not-a-uuid',
            project_path='/tmp/test',
            session_id=None
        )

        assert exit_code == 2


@pytest.mark.asyncio
async def test_run_verification_success():
    """Test successful verification flow."""
    from server.verification.cli import run_verification
    from server.utils.config import VerificationConfig

    with patch('server.verification.cli.Config.load_default') as mock_config, \
         patch('server.verification.cli.DatabaseManager') as mock_db_mgr, \
         patch('server.verification.cli.TaskVerifier') as mock_verifier_cls:

        # Mock config
        mock_cfg = Mock()
        mock_cfg.verification = VerificationConfig(enabled=True)
        mock_config.return_value = mock_cfg

        # Mock database manager
        mock_db = AsyncMock()
        mock_db_mgr.return_value.__aenter__.return_value = mock_db

        # Mock verifier
        mock_verifier = AsyncMock()
        mock_verifier_cls.return_value = mock_verifier

        # Mock successful verification result
        mock_result = Mock()
        mock_result.status = "passed"
        mock_result.tests_run = 5
        mock_result.tests_passed = 5
        mock_result.tests_failed = 0
        mock_result.generated_tests = []
        mock_verifier.verify_task.return_value = mock_result

        # Run verification
        exit_code = await run_verification(
            task_id=str(uuid4()),
            project_path='/tmp/test',
            session_id=str(uuid4())
        )

        # Should return exit code 0 (success)
        assert exit_code == 0


@pytest.mark.asyncio
async def test_run_verification_failure():
    """Test failed verification flow."""
    from server.verification.cli import run_verification
    from server.utils.config import VerificationConfig

    with patch('server.verification.cli.Config.load_default') as mock_config, \
         patch('server.verification.cli.DatabaseManager') as mock_db_mgr, \
         patch('server.verification.cli.TaskVerifier') as mock_verifier_cls:

        # Mock config
        mock_cfg = Mock()
        mock_cfg.verification = VerificationConfig(enabled=True)
        mock_config.return_value = mock_cfg

        # Mock database manager
        mock_db = AsyncMock()
        mock_db_mgr.return_value.__aenter__.return_value = mock_db

        # Mock verifier
        mock_verifier = AsyncMock()
        mock_verifier_cls.return_value = mock_verifier

        # Mock failed verification result
        mock_result = Mock()
        mock_result.status = "failed"
        mock_result.tests_run = 5
        mock_result.tests_passed = 3
        mock_result.tests_failed = 2
        mock_result.failure_reason = "Some tests failed"
        mock_result.retry_count = 0
        mock_verifier.verify_task.return_value = mock_result

        # Run verification
        exit_code = await run_verification(
            task_id=str(uuid4()),
            project_path='/tmp/test',
            session_id=None
        )

        # Should return exit code 1 (verification failed)
        assert exit_code == 1


def test_main_function_exists():
    """Test that main() function is defined."""
    from server.verification import cli
    assert callable(cli.main)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
