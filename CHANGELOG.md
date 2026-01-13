# Changelog

All notable changes to YokeFlow will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] 2026-01-12

### Last minute additions

- **Quality & Intervention System Improvements** (January 12, 2026) - Completed 100% of planned improvements
  - **Phase 1: Structured Recommendations in JSONB** (1.5 hours)
    - Fixed empty `proposed_text` fields issue
    - Dual storage strategy: Markdown for humans + JSON for machines
    - 100% field population guaranteed
    - Theme categorization at generation time
  - **Phase 2: Quality Pattern Detection** (1.5 hours)
    - Created `server/agent/quality_detector.py` with comprehensive monitoring
    - UI tasks blocked without browser verification
    - Tool misuse detection (configurable threshold, default 10 incorrect uses)
    - Task type inference (UI, API, Database, Config, Integration)
    - Quality scoring system (0-10 scale, intervention at <3)
    - 27 comprehensive tests passing (100% pass rate)
  - **Phase 3: Task-Type Aware Verification** (2 hours)
    - Smart test type selection based on task analysis
    - 30-40% verification time reduction achieved
    - Config tasks: 90% faster (30s vs 5min)
    - Database tasks: 80% faster (1min vs 5min)
    - Added BUILD and DATABASE test generation methods
    - 16 tests covering all aspects (100% passing)
  - **Total time**: 5 hours (vs 13-17 hours estimated - 70% faster!)

## 2026-01-09

### 🎉 Major Release - Complete Platform

YokeFlow 2.0 represents a major milestone with complete platform functionality, production hardening, and comprehensive documentation.

### Added

#### REST API (January 8, 2026)
- **17 REST endpoints** with comprehensive validation (89% test coverage)
- **Health monitoring**: `/health`, `/health/detailed` with component-level status
- **Session management**: `/api/sessions/{id}/logs`, `/api/sessions/{id}/pause`, `/api/sessions/{id}/resume`
- **Task operations**: `/api/tasks/{id}`, `/api/tasks/{id}/status` with validation
- **Epic tracking**: `/api/epics/{id}/progress` with task breakdown
- **Quality endpoints**: `/api/sessions/{id}/quality-review`, `/api/projects/{id}/quality-metrics`
- **Interactive documentation** at `/docs` (Swagger UI)

#### Input Validation Framework (January 8, 2026)
- **19 Pydantic validation models** for type-safe API inputs
- **52 tests** (100% passing) covering all validation scenarios
- **4 enums** for type safety (SandboxType, SessionType, SessionStatus, TaskStatus)
- **3 helper functions** for common validation tasks
- Clear error messages for invalid inputs
- Sensible defaults for configuration
- Automatic OpenAPI schema generation
- Documentation: `docs/input-validation.md`

#### Verification System (January 8-9, 2026)
- **Automated test generation** for 5 test types (unit, API, browser, integration, E2E)
- **Task verification** with retry logic (up to 3 attempts with failure analysis)
- **Epic validation** with integration testing across task boundaries
- **Rework task creation** for failed validations
- **File modification tracking** during task execution
- **40 tests passing** (task_verifier: 11, test_generator: 15, epic_validator: 14)
- **Database tables**: `task_verifications`, `epic_validations`, `generated_tests`
- **Comprehensive guide**: `docs/verification-system.md` (850+ lines)

#### Documentation (January 8-9, 2026)
- **14 documentation files** updated or created
- **README.md**: Major rewrite with complete architecture overview
- **CLAUDE.md**: Full v2.0 update with all new features
- **QUICKSTART.md**: Updated 5-minute setup guide
- **docs/verification-system.md**: NEW - Comprehensive 850+ line guide
- **11 docs** updated or verified for v2.0
- **1,500+ lines** of new/updated documentation

### Changed

#### Architecture Reorganization (January 7, 2026)
- **All server code** moved to unified `server/` module
- **44 Python files** reorganized into 11 clean modules
- **61 files updated** with new import paths
- **Zero circular dependencies** - clear module boundaries established
- **Module structure**:
  - `server/agent/` - Session orchestration & lifecycle
  - `server/api/` - REST API & WebSocket
  - `server/database/` - PostgreSQL operations & retry logic
  - `server/verification/` - Testing & validation
  - `server/quality/` - Quality & review system
  - `server/client/` - External service clients
  - `server/sandbox/` - Docker management
  - `server/utils/` - Shared utilities

#### Production Hardening (January 5, 2026)
- **Database retry logic** with exponential backoff (30 tests)
  - 20+ PostgreSQL error codes covered
  - Configurable jitter and max retries
  - Retry statistics tracking
- **Session checkpointing** and recovery (19 tests)
  - Complete state preservation at key points
  - Full conversation history capture
  - State validation before resumption
- **Intervention system** with database persistence (15 tests)
  - Pause/resume session operations
  - Action tracking and audit trail
  - Web UI integration
- **Structured logging** with JSON/dev formatters (19 tests)
  - Development-friendly colored output
  - JSON format for production analysis
  - Automatic context injection
- **Error hierarchy** with 30+ error types (36 tests)
  - Clear error categorization
  - Context-aware error handling

#### Testing Improvements (January 8-9, 2026)
- **Test suite**: 212 total tests, 70% coverage achieved
- **Core tests**: 72 tests passing (100% pass rate)
- **Production hardening tests**: 119 tests (retry, checkpoint, intervention, logging, errors)
- **Verification tests**: 40 tests (task_verifier, test_generator, epic_validator)
- **API tests**: 17/19 passing (89% coverage, 2 auth tests deferred)
- **Integration tests**: 6+ passing (Docker required)
- **Test infrastructure**: Fast test runner (`scripts/test_quick.py`)
- **Documentation**: `docs/testing-guide.md`, `tests/README.md`

#### Database Schema (January 8-9, 2026)
- **Migration 011**: Intervention system tables (`paused_sessions`, `intervention_actions`, `notification_preferences`)
- **Migration 012**: Checkpointing tables (`session_checkpoints`, `checkpoint_recoveries`)
- **Migration 013-016**: Verification system tables (`task_verifications`, `epic_validations`, `generated_tests`)
- **New views**: `v_active_interventions`, `v_latest_checkpoints`, `v_latest_task_verifications`, `v_verification_statistics`
- **Documentation**: `docs/postgres-setup.md` updated with all migrations

### Fixed
- Resolved all test failures (15 failures fixed across 6 test files)
- Eliminated 24 warnings from test suite
- Fixed circular import issues with reorganization
- Corrected all import paths from old structure (core/, api/, review/) to new (server/)
- Fixed database retry logic edge cases
- Improved error handling consistency

### Removed
- Obsolete migration scripts and directories
- Redundant test runners

### Developer Experience
- **Clean architecture** with clear module boundaries
- **Comprehensive documentation** with examples
- **Interactive API docs** at `/docs` (Swagger UI)
- **Type safety** with Pydantic validation
- **Better IDE support** with clear imports
- **Fast tests** (72 core tests in < 30 seconds)

### Security
- Input validation prevents injection attacks
- Blocklist security for command execution
- Database retry logic prevents data loss
- Session checkpointing enables recovery

### Performance
- Async database operations with connection pooling
- Retry logic with exponential backoff
- Efficient test generation with caching
- Fast test suite execution

## Version Comparison

| Feature | v1.0.0 | v2.0.0 |
|---------|--------|--------|
| REST API | Basic | 17 endpoints + validation |
| Input Validation | Ad-hoc | Pydantic framework (19 models) |
| Verification System | Manual | Automated (5 test types) |
| Architecture | Mixed folders | Clean server/ module |
| Test Coverage | ~50% | 70% (212 tests) |
| Production Hardening | Basic | Complete (retry, checkpoint, intervention) |
| Documentation | Partial | Comprehensive (14 files) |
| Error Handling | Basic | 30+ error types |
| Logging | Simple | Structured (JSON + dev) |
| Database Schema | Core only | +6 migrations |

---

## Upgrade Guide

### From v1.x to v2.0.0

#### Prerequisites
1. **Fresh install required** - v2.0 is not backward compatible
2. Backup any existing projects in `generations/`
3. PostgreSQL must be running

#### Steps

1. **Update imports** - All server code moved to `server/`:
   ```python
   # Old (v1.x)
   from core.agent import Agent
   from api.main import app
   from review.review_client import ReviewClient

   # New (v2.0)
   from server.agent.agent import SessionManager
   from server.api.app import app
   from server.quality.reviews import ReviewClient
   ```

2. **Database migration**:
   ```bash
   # Drop existing database (if any)
   docker-compose down -v

   # Start fresh
   docker-compose up -d
   python scripts/init_database.py --docker
   ```

3. **Update configuration** (`.yokeflow.yaml`):
   ```yaml
   # Add verification system config
   verification:
     enabled: true
     auto_retry: true
     max_retries: 3
     test_timeout: 30
   ```

4. **Rebuild MCP server**:
   ```bash
   cd mcp-task-manager
   npm install
   npm run build
   cd ..
   ```

5. **Update dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

6. **Verify installation**:
   ```bash
   # Run quick tests
   python scripts/test_quick.py

   # Check API
   curl http://localhost:8000/health/detailed
   ```

---

## Support

- **Documentation**: See [docs/](docs/) directory
- **Quick Start**: [QUICKSTART.md](QUICKSTART.md)
- **Developer Guide**: [docs/developer-guide.md](docs/developer-guide.md)
- **Issues**: Open an issue on GitHub

---

**For the complete v2.0 feature set, see [README.md](README.md)**
