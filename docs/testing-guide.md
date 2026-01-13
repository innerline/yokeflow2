# YokeFlow Testing Guide

## Overview

YokeFlow has a comprehensive test suite with **72 passing tests** across multiple test categories. Tests are organized to support both rapid development (fast unit tests) and comprehensive validation (integration tests).

## Test Suite Status

- **Total Tests**: ~212 tests across all test files
- **Core Tests**: 72 passing (100% pass rate, < 30 seconds)
- **API Tests**: 17 passing, 2 skipped (auth not yet implemented)
- **Verification Tests**: 55 passing (task verifier, epic validator, test generator)
- **Coverage**: 70% overall target achieved ✅
- **Runtime**:
  - Fast tests: < 30 seconds
  - All tests (including Docker): 5-10 minutes

## Prerequisites for Testing

### Environment Setup

1. **Unset UI_PASSWORD** - Authentication must be disabled for tests:
   ```bash
   # Temporarily unset for testing (if set in .env)
   unset UI_PASSWORD
   # OR comment out UI_PASSWORD in .env file
   ```

2. **Test Database Setup** (for integration tests):
   ```bash
   # Create test database
   docker exec yokeflow_postgres psql -U agent -d postgres -c "CREATE DATABASE yokeflow_test;"

   # Initialize schema
   docker exec -i yokeflow_postgres psql -U agent -d yokeflow_test < schema/postgresql/schema.sql

   # Set environment variable
   export TEST_DATABASE_URL="postgresql://agent:agent_dev_password@localhost:5432/yokeflow_test"
   ```

3. **MCP Server** (not required for most tests):
   - The MCP server directory doesn't exist in the current codebase
   - Tests expecting MCP server will fail or be skipped

## Quick Start

```bash
# Run fast tests (recommended for development)
python scripts/test_quick.py

# Run with coverage
pytest --cov=server --cov-report=html --cov-report=term-missing

# Run specific test file
pytest tests/test_orchestrator.py -v

# Skip slow tests (default for development)
pytest -m "not slow"
```

## Test Organization

### Core Test Files (Always Run)

| Test File | Tests | Focus | Runtime |
|-----------|-------|-------|---------|
| `test_orchestrator.py` | 17 | Session lifecycle, orchestration | < 1s |
| `test_quality_integration.py` | 10 | Quality system integration | < 1s |
| `test_sandbox_manager.py` | 17 | Docker sandbox (mocked) | < 1s |
| `test_security.py` | 2 | Security validation (64 assertions) | < 1s |
| `test_task_verifier.py` | 11 | Task verification system | < 1s |
| `test_test_generator.py` | 15 | Test generation system | < 1s |

**Total Core Tests**: 72 tests, all passing

### Integration Test Files (Slower)

| Test File | Tests | Focus | Runtime | Prerequisites |
|-----------|-------|-------|---------|---------------|
| `test_sandbox_integration.py` | 6 | Real Docker containers | 5-10 min | Docker required |
| `test_integration_*.py` | Various | Database, workflows | 1-5 min | PostgreSQL required |
| `test_api_rest.py` | 17 passing, 2 skipped | REST API endpoints | < 1s | None (test mode) |

### Additional Test Files

These test files cover specific components with full test coverage:

**Production Hardening Tests:**
- `test_checkpoint.py` (19 tests) - Session checkpointing and recovery
- `test_database_retry.py` (30 tests) - Database retry logic with exponential backoff
- `test_errors.py` (36 tests) - Error hierarchy and categorization (99% coverage)
- `test_intervention.py` (~10 tests) - Blocker detection and retry tracking
- `test_intervention_system.py` (~10 tests) - Intervention system integration
- `test_session_manager.py` (15 tests) - Session pause/resume functionality
- `test_structured_logging.py` (19 tests) - Logging system (93% coverage)

**Verification System Tests:**
- `test_task_verifier.py` (11 tests) - Task verification with retry logic
- `test_epic_validator.py` (13 tests) - Epic validation and rework tasks
- `test_test_generator.py` (15 tests) - Automatic test generation
- `test_verification_simple.py` (16 tests) - Verification data classes and initialization

**Input Validation Tests:**
- `test_validation.py` (52 tests) - Pydantic validation models for API/config/specs

## Running Tests

### For Development (Fast)

```bash
# Quick test suite - recommended for rapid development
python scripts/test_quick.py

# Run specific test file by name (omit 'test_' and '.py')
python scripts/test_quick.py orchestrator

# With verbose output
python scripts/test_quick.py --verbose

# With coverage report
python scripts/test_quick.py --coverage
```

### Using pytest Directly

```bash
# Run all fast tests (skip Docker/slow tests)
pytest -m "not slow"

# Run specific test file
pytest tests/test_orchestrator.py

# Run specific test
pytest tests/test_orchestrator.py::TestAgentOrchestrator::test_start_session_initializer

# With verbose output and show print statements
pytest tests/test_orchestrator.py -v -s

# Run tests matching pattern
pytest tests/test_orchestrator.py -k "start_session"
```

### With Coverage Reports

```bash
# Generate HTML coverage report
pytest --cov=server --cov-report=html --cov-report=term-missing

# View HTML report
open htmlcov/index.html

# Coverage for specific module
pytest tests/test_orchestrator.py --cov=server.agent.orchestrator --cov-report=term-missing

# Fail if coverage below threshold
pytest --cov=server --cov-fail-under=70
```

### Integration Tests

```bash
# Run Docker integration tests (requires Docker running)
pytest tests/test_sandbox_integration.py

# Run all integration tests
pytest -m "integration"

# Run integration tests with database (requires PostgreSQL)
RUN_INTEGRATION=true pytest tests/test_integration_*.py
```

### Filter by Test Markers

```bash
# Run only unit tests (fast, mocked)
pytest -m "unit"

# Run only integration tests
pytest -m "integration"

# Run API tests
pytest -m "api"

# Run database tests
pytest -m "database"

# Skip slow tests (default for development)
pytest -m "not slow"

# Skip both slow and Docker tests
pytest -m "not slow and not docker"
```

## Test Markers

Tests use pytest markers for categorization:

- `@pytest.mark.unit` - Unit tests (fast, mocked dependencies)
- `@pytest.mark.integration` - Integration tests (multiple components)
- `@pytest.mark.slow` - Slow tests (Docker, performance tests)
- `@pytest.mark.docker` - Requires Docker running
- `@pytest.mark.api` - API endpoint tests
- `@pytest.mark.database` - Database operation tests
- `@pytest.mark.websocket` - WebSocket communication tests
- `@pytest.mark.performance` - Performance/stress tests

## Test Structure and Patterns

### Async Testing

```python
import pytest

@pytest.mark.asyncio
async def test_async_function():
    result = await my_async_function()
    assert result == expected
```

### Mocking Database Operations

```python
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_with_database():
    # Mock connection
    mock_conn = MagicMock()
    mock_conn.fetchrow = AsyncMock(return_value={'id': '123'})
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)

    # Mock database manager
    mock_db = MagicMock()
    mock_db.acquire = MagicMock(return_value=mock_conn)
```

### Mocking Docker Operations

```python
import docker.errors

# Mock Docker client
mock_client = MagicMock()
mock_container = MagicMock()
mock_container.id = "test-container-id"
mock_container.status = "running"

# Mock containers.get to raise NotFound
mock_client.containers.get.side_effect = [
    docker.errors.NotFound("Container not found"),
    mock_container
]

# Mock exec_run with demux=True format
mock_container.exec_run.return_value = (0, (b"stdout", b"stderr"))
```

## Known Test Failures (v2.0.0)

As of January 2026, with UI_PASSWORD unset, the following tests fail:

### API Implementation Issues (5 failures in test_api_rest.py)
- `test_get_task_details` - Missing `db.get_task()` method (calls non-existent method)
- `test_update_task_status` - Missing database method implementation
- `test_get_epic_progress` - Missing `db.get_epic_progress()` method
- `test_trigger_quality_review` - Missing `db.get_session()` method
- `test_get_quality_metrics` - Database connection issues

**Root Cause**: API endpoints call database methods that don't exist in `TaskDatabase` class.
**Resolution**: Either implement the missing methods or update API to use existing methods like `get_task_with_tests()`.

### MCP Server Test (1 failure in test_claude_sdk_client.py)
- `test_create_client_requires_mcp_server` - MCP server directory doesn't exist

**Root Cause**: The mcp-task-manager directory is not present in the current codebase.
**Resolution**: Skip this test or provide the MCP server implementation.

## Skipped Tests

### Integration Tests (20 skipped)
- **test_integration_database.py** (8 tests) - Require `RUN_INTEGRATION=true` and test database
- **test_api_rest.py** (12 tests) - Test endpoints that may not be implemented

### How to Enable Integration Tests
```bash
# Set up test database (see Prerequisites)
export RUN_INTEGRATION=true
export TEST_DATABASE_URL="postgresql://agent:agent_dev_password@localhost:5432/yokeflow_test"
pytest tests/test_integration_database.py -v
```

## Known Warnings

**3 minor warnings** exist in `test_quality_integration.py`:
- Related to AsyncMock unawaited coroutines in tests that don't execute those code paths
- Non-critical and do not affect test results
- Can be resolved by improving mock setup in the test fixtures

See `TEST_SUITE_REPORT.md` for detailed analysis and resolution steps.

## Coverage Analysis

### Well-Covered Modules (>70%)

- `server/utils/errors.py` - 99% coverage
- `server/utils/logging.py` - 93% coverage
- `server/database/retry.py` - 82% coverage
- `server/agent/session_manager.py` - 56% coverage

### Modules Needing Coverage

- `server/api/app.py` - REST API endpoints (pending implementation)
- `server/agent/orchestrator.py` - Session orchestration (complex workflows)
- `server/agent/agent.py` - Agent execution logic (integration dependent)
- `server/client/claude.py` - Claude SDK integration (external service)
- `server/sandbox/manager.py` - Docker sandbox (covered by integration tests)

## Performance Tips

### 1. Use Quick Tests During Development

The `scripts/test_quick.py` script runs only fast tests (~30 seconds) vs all tests (5-10 minutes):

```bash
python scripts/test_quick.py
```

### 2. Run Integration Tests Separately

Only run Docker/database tests when specifically testing that functionality:

```bash
# Fast tests only
pytest -m "not slow"

# Docker tests only when needed
pytest tests/test_sandbox_integration.py
```

### 3. Parallel Execution

Speed up test runs with pytest-xdist:

```bash
pip install pytest-xdist
pytest -n auto -m "not slow"
```

### 4. Watch Mode for TDD

Continuous testing during development:

```bash
pip install pytest-watch
ptw -- -m "not slow"
```

### 5. Run Only Failed Tests

After fixing issues, rerun only previously failed tests:

```bash
pytest --lf  # last failed
pytest --ff  # failed first, then rest
```

## Troubleshooting

### Docker Tests Failing

**Symptoms**: Tests in `test_sandbox_integration.py` fail or hang

**Solutions**:
- Ensure Docker Desktop is running
- Check Docker has sufficient resources (2GB+ memory, 20GB+ disk)
- Clean up old containers: `docker system prune -a`
- Check container logs: `docker logs <container-id>`

### Import Errors

**Symptoms**: `ModuleNotFoundError` or import errors

**Solutions**:
- Ensure you're in the project root directory
- Verify Python path: `export PYTHONPATH=$PYTHONPATH:$(pwd)`
- Install all dependencies: `pip install -r requirements.txt`
- Check virtual environment is activated

### PostgreSQL Connection Errors

**Symptoms**: Database tests fail with connection errors

**Solutions**:
- Ensure PostgreSQL is running: `docker-compose up -d`
- Check DATABASE_URL environment variable is set
- Verify database exists: `psql $DATABASE_URL -c "SELECT 1"`
- Run schema initialization: `python scripts/init_database.py`

### Slow Test Performance

**Symptoms**: Tests take too long to run

**Solutions**:
- Use quick test script: `python scripts/test_quick.py`
- Skip slow tests: `pytest -m "not slow"`
- Run specific test files: `pytest tests/test_orchestrator.py`
- Consider running integration tests only before commits

### AsyncIO Warnings

**Symptoms**: Warnings about async fixtures or event loops

**Solutions**:
- Ensure `pytest-asyncio` is installed: `pip install pytest-asyncio`
- Check pytest.ini has `asyncio_mode = auto`
- Use `@pytest.mark.asyncio` decorator on async tests

## Continuous Integration

### Recommended CI Workflow

```yaml
# .github/workflows/test.yml
- name: Run fast tests
  run: pytest -m "not slow" --cov=server --cov-report=xml

- name: Run integration tests
  run: pytest -m "integration"

- name: Upload coverage
  uses: codecov/codecov-action@v3
```

### Pre-commit Hook

Create `.git/hooks/pre-commit`:

```bash
#!/bin/bash
python scripts/test_quick.py
if [ $? -ne 0 ]; then
    echo "Tests failed. Commit aborted."
    exit 1
fi
```

## Test Coverage Goals

- **Overall Target**: 70% coverage ✅ (currently achieved)
- **Critical Modules**: 80%+ coverage
  - Error handling: 99% ✅
  - Logging: 93% ✅
  - Database retry: 82% ✅
- **Integration Coverage**: Focus on happy paths and critical error handling
- **Next Focus**: API endpoints, orchestrator workflows, agent logic

## Writing New Tests

### Test File Naming

```
tests/
├── test_<module_name>.py       # Unit tests for server/<module_name>.py
├── test_<feature>_integration.py  # Integration tests
└── conftest.py                 # Shared fixtures
```

### Test Function Naming

```python
def test_<action>_<scenario>():
    """Test <action> when <scenario>."""
```

Examples:
- `test_start_session_with_active_session()`
- `test_execute_command_with_timeout()`
- `test_parse_invalid_json_returns_error()`

### Test Structure (AAA Pattern)

```python
@pytest.mark.asyncio
async def test_example():
    # Arrange - Set up test data and mocks
    mock_db = AsyncMock()
    mock_db.get_project.return_value = {'id': '123'}

    # Act - Execute the function being tested
    result = await my_function(mock_db)

    # Assert - Verify the results
    assert result['status'] == 'success'
    mock_db.get_project.assert_called_once()
```

### Using Fixtures

```python
@pytest.fixture
def sample_project(tmp_path):
    """Create a sample project for testing."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    return project_dir

def test_with_fixture(sample_project):
    """Test using the fixture."""
    assert sample_project.exists()
```

## Additional Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-asyncio documentation](https://pytest-asyncio.readthedocs.io/)
- [pytest-cov documentation](https://pytest-cov.readthedocs.io/)
- [unittest.mock documentation](https://docs.python.org/3/library/unittest.mock.html)

## Summary

YokeFlow's test suite provides comprehensive coverage with fast feedback loops:

- ✅ **72 tests passing** - 100% pass rate
- ✅ **Fast development cycle** - Quick tests in < 30 seconds
- ✅ **Comprehensive validation** - Integration tests for critical workflows
- ✅ **70% coverage achieved** - Focusing on critical paths
- ⏳ **29 tests skipped** - Pending API endpoint implementation

Use `python scripts/test_quick.py` for rapid development and `pytest --cov=server` for comprehensive validation before commits.
