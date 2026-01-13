# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## What This Is

**YokeFlow 2** - An autonomous AI development platform that uses Claude to build complete applications over multiple sessions.

**Status**: Production Ready - v2.0.0 (January 2026) ✅ **Complete Platform**

**Architecture**: API-first platform with FastAPI + Next.js Web UI + PostgreSQL + MCP task management

**Workflow**: Opus plans roadmap (Session 0) → Sonnet implements features (Sessions 1+)

**Latest Updates** (January 2026):
- ✅ **REST API Complete**: 17 endpoints with comprehensive validation (89% coverage)
- ✅ **Input Validation**: Pydantic-based validation framework (52 tests, 100% passing)
- ✅ **Verification System**: Automated test generation & epic validation (fully integrated)
- ✅ **Folder Reorganization**: All server code under `server/` with clear module separation
- ✅ **Production Hardening**: Database retry logic, intervention system, session checkpointing
- ✅ **Structured Logging**: JSON + development formatters with context tracking
- 🚀 **Clean Architecture**: No circular dependencies, clear module boundaries
- ✅ **Quality Improvements** (Jan 12): Pattern detection, task-type verification, 30-40% faster testing

## Core Workflow

**Session 0 (Initialization)**: Reads `app_spec.txt` → Creates epics/tasks/tests in PostgreSQL → Runs `init.sh`

**Sessions 1+ (Coding)**: Get next task → Implement → Browser verify (with Playwright) → Update database → Git commit → Auto-continue

**Key Files** (New Paths):
- `server/agent/orchestrator.py` - Session lifecycle management
- `server/agent/agent.py` - Agent loop and session logic
- `server/database/operations.py` - PostgreSQL abstraction (async) + retry logic
- `server/database/retry.py` - Retry logic with exponential backoff (30 tests)
- `server/agent/checkpoint.py` - Session checkpointing and recovery (19 tests)
- `server/agent/session_manager.py` - Intervention system with DB persistence (15 tests)
- `server/utils/logging.py` - Structured logging with JSON/dev formatters (19 tests)
- `server/utils/errors.py` - Error hierarchy with 30+ error types (36 tests)
- `server/api/app.py` - REST API + WebSocket
- `server/utils/observability.py` - Session logging (JSONL + TXT)
- `server/utils/security.py` - Blocklist validation
- `prompts/` - Agent instructions


## Database

**Schema**: PostgreSQL with 3-tier hierarchy: `epics` → `tasks` → `tests`

**Key tables**:
- Core: `projects`, `epics`, `tasks`, `tests`, `sessions`, `session_quality_checks`
- ✅ **Production Hardening**: `paused_sessions`, `intervention_actions`, `session_checkpoints` (011-012)
- ✅ **Verification System**: `task_verifications`, `epic_validations`, `generated_tests` (013-016)

**Key views**:
- Core: `v_next_task`, `v_progress`, `v_epic_progress`
- Production: `v_active_interventions`, `v_latest_checkpoints`, `v_resumable_checkpoints`
- Verification: `v_latest_task_verifications`, `v_verification_statistics`

**Access**: Use `server/database/operations.py` abstraction (async/await). See `schema/postgresql/` for DDL.

**Retry Logic**: All database operations automatically retry on transient failures (exponential backoff)

## MCP Tools

The `mcp-task-manager/` provides 15+ tools (prefix: `mcp__task-manager__`):

**Query**: `task_status`, `get_next_task`, `list_epics`, `get_epic`, `list_tasks`, `get_task`, `list_tests`

**Update**: `update_task_status`, `start_task`, `update_test_result`

**Create**: `create_epic`, `create_task`, `create_test`, `expand_epic`, `log_session`

Must build before use: `cd mcp-task-manager && npm run build`

## Configuration

**Priority**: Web UI settings > Config file (`.yokeflow.yaml`) > Defaults

**Key settings**:
- `models.initializer` / `models.coding` - Override default Opus/Sonnet models
- `timing.auto_continue_delay` - Seconds between sessions (default 3)
- `project.max_iterations` - Limit session count (null = unlimited)

## REST API

**Endpoints**: 17+ RESTful endpoints for complete platform control

**Key endpoints**:
- Health: `/health`, `/health/detailed` - System health monitoring
- Sessions: `/api/sessions/{id}/logs`, `/api/sessions/{id}/pause`, `/api/sessions/{id}/resume`
- Tasks: `/api/tasks/{id}`, `/api/tasks/{id}/status` - Task management
- Epics: `/api/epics/{id}/progress` - Epic tracking
- Quality: `/api/sessions/{id}/quality-review`, `/api/projects/{id}/quality-metrics`

**Documentation**: Interactive docs at `/docs` (Swagger UI) when API server running

**Test Coverage**: 17/19 tests passing (2 auth tests deferred - auth not yet implemented)

See [docs/api-usage.md](docs/api-usage.md) for complete endpoint reference and examples.

## Input Validation

**Framework**: Pydantic-based validation with 19 models and 52 tests (100% passing)

**What's validated**:
- API requests: Project names, spec content, session parameters, environment variables
- Configuration: Model names, timing settings, Docker limits, database URLs
- Sandbox: Memory/CPU limits, port mappings, E2B configuration
- Verification: Test timeouts, coverage thresholds, webhook URLs

**Benefits**:
- Type safety with runtime validation
- Clear error messages for invalid inputs
- Sensible defaults for configuration
- Automatic OpenAPI schema generation

See [docs/input-validation.md](docs/input-validation.md) for usage examples.

## Security

**Blocklist approach**: Allows dev tools (npm, git, curl), blocks dangerous commands (rm, sudo, apt)

Edit `server/utils/security.py` `BLOCKED_COMMANDS` to modify. Safe in Docker containers.

## Project Structure

```
yokeflow2/
├── server/                  # All server code (reorganized)
│   ├── agent/               # Session orchestration & lifecycle
│   │   ├── agent.py         # Agent loop and session logic
│   │   ├── orchestrator.py  # Session lifecycle management
│   │   ├── session_manager.py  # Intervention system (DB persistence)
│   │   ├── checkpoint.py    # Session checkpointing and recovery
│   │   ├── intervention.py  # Blocker detection and retry tracking
│   │   └── models.py        # Orchestrator data models
│   ├── api/                 # REST API & WebSocket
│   │   ├── app.py           # Main FastAPI application
│   │   ├── auth.py          # API authentication
│   │   ├── start.py         # API startup wrapper
│   │   └── routes/          # API route modules
│   ├── database/            # Database layer
│   │   ├── operations.py    # PostgreSQL operations (async)
│   │   ├── connection.py    # Connection pooling
│   │   └── retry.py         # Retry logic with exponential backoff
│   ├── client/              # External service clients
│   │   ├── claude.py        # Claude SDK client
│   │   ├── playwright.py    # Playwright Docker client
│   │   └── prompts.py       # Prompt loading
│   ├── quality/             # Quality & review system
│   │   ├── metrics.py       # Quality metrics (Phase 1)
│   │   ├── reviews.py       # Deep reviews (Phase 2)
│   │   ├── gates.py         # Quality gates
│   │   ├── integration.py   # Quality integration
│   │   └── prompt_analyzer.py  # Prompt improvements (Phase 4)
│   ├── verification/        # Testing & validation
│   │   ├── task_verifier.py  # Task verification
│   │   ├── epic_validator.py  # Epic validation
│   │   ├── epic_manager.py  # Epic management
│   │   └── test_generator.py  # Test generation
│   ├── sandbox/             # Docker management
│   │   ├── manager.py       # Docker sandbox management
│   │   └── hooks.py         # Sandbox hooks
│   ├── utils/               # Shared utilities
│   │   ├── config.py        # Configuration management
│   │   ├── logging.py       # Structured logging
│   │   ├── errors.py        # Error hierarchy
│   │   ├── security.py      # Blocklist validation
│   │   ├── observability.py # Session logging
│   │   └── reset.py         # Project reset logic
│   └── coverage/            # Test coverage
│       └── analyzer.py      # Coverage analysis
├── web-ui/                  # Next.js Web UI
├── mcp-task-manager/        # MCP server (TypeScript)
├── scripts/                 # Utility scripts
├── prompts/                 # Agent instructions
├── schema/postgresql/       # Database DDL
├── tests/                   # Test suites
├── docs/                    # Documentation
└── generations/             # Generated projects
```

## Key Design Decisions

**PostgreSQL**: Production-ready, async operations, JSONB metadata, UUID-based IDs

**Orchestrator**: Decouples session management, enables API control, foundation for job queues

**MCP over Shell**: Protocol-based, structured I/O, no injection risks, language-agnostic

**Tasks Upfront**: Complete visibility from day 1, accurate progress tracking, user can review roadmap

**Dual Models**: Opus for planning (comprehensive), Sonnet for coding (fast + cheap)

**Blocklist Security**: Agent autonomy with safety, designed for containers

## Troubleshooting

**MCP server failed**: Run `cd mcp-task-manager && npm run build`

**Database error**: Ensure PostgreSQL running (`docker-compose up -d`), check DATABASE_URL in `.env`

**Command blocked**: Check `server/utils/security.py` BLOCKED_COMMANDS list

**Agent stuck**: Check logs in `generations/[project]/logs/`, run with `--verbose`

**Web UI no projects**: Ensure PostgreSQL running, verify API connection

**Import errors**: Update imports to new structure:
```python
# Old: from core.agent import
# New: from server.agent.agent import

# Old: from api.main import
# New: from server.api.app import

# Old: from review.review_client import
# New: from server.quality.reviews import
```

## Testing

**Test Suite Status** (January 8, 2026):
- ✅ **72 core tests passing** (100% pass rate, < 30 seconds)
- ✅ **70% coverage achieved** (target met)
- ✅ **Production ready** with comprehensive test infrastructure
- 📋 **~212 total tests** across all test files
- ⏳ **29 tests skipped** (pending REST API implementation)

**Quick Start**:
```bash
# Run fast tests (recommended for development)
python scripts/test_quick.py

# Or use pytest directly
pytest -m "not slow"

# Run with coverage
pytest --cov=server --cov-report=html --cov-report=term-missing
```

**Key Test Files**:
```bash
pytest tests/test_orchestrator.py        # Session lifecycle (17 tests)
pytest tests/test_quality_integration.py # Quality system (10 tests)
pytest tests/test_sandbox_manager.py     # Docker sandbox (17 tests)
pytest tests/test_security.py            # Security validation (2 tests, 64 assertions)
pytest tests/test_task_verifier.py       # Task verification (11 tests)
pytest tests/test_test_generator.py      # Test generation (15 tests)
```

**Documentation**:
- [docs/testing-guide.md](docs/testing-guide.md) - Comprehensive developer guide
- [tests/README.md](tests/README.md) - Test descriptions and status
- [TEST_SUITE_REPORT.md](TEST_SUITE_REPORT.md) - Coverage report and gaps

## Verification System

**Purpose**: Automated test generation and validation for task completion and epic acceptance

**Components**:
- `server/verification/task_verifier.py` - Automatic test generation & execution (580 lines, 11 tests)
- `server/verification/test_generator.py` - Context-aware test creation (480 lines, 15 tests)
- `server/verification/epic_validator.py` - Epic-level validation (700 lines, 14 tests)
- `server/verification/integration.py` - MCP tool interception (413 lines, verified)
- `server/verification/epic_manager.py` - Epic lifecycle management (390 lines)

**Features**:
- **Automatic test generation**: 5 test types (unit, API, browser, integration, E2E)
- **Retry logic**: Up to 3 attempts with failure analysis
- **Epic validation**: Integration testing across task boundaries
- **Rework tasks**: Automatic creation for failed validations
- **File tracking**: Monitor modifications during task execution

**Configuration** (`.yokeflow.yaml`):
```yaml
verification:
  enabled: true              # Enable/disable verification
  auto_retry: true           # Retry failed tests automatically
  max_retries: 3             # Maximum retry attempts
  test_timeout: 30           # Test timeout in seconds
  generate_unit_tests: true  # Generate unit tests
  generate_api_tests: true   # Generate API tests
  generate_browser_tests: true  # Generate browser tests
  track_file_modifications: true  # Track file changes
  min_test_coverage: 0.7     # Minimum test coverage (70%)
```

**Database tables**: `task_verifications`, `epic_validations`, `generated_tests`

**Test coverage**: 40 tests passing (task_verifier: 11, test_generator: 15, epic_validator: 14)

See [docs/verification-system.md](docs/verification-system.md) for complete guide (850+ lines).

## Important Files

**Agent Core**:
- `server/agent/orchestrator.py` - Session lifecycle
- `server/agent/agent.py` - Agent loop
- `server/agent/session_manager.py` - Session management

**Database**:
- `server/database/operations.py` - PostgreSQL operations
- `server/database/retry.py` - Retry logic

**API**:
- `server/api/app.py` - FastAPI application (17+ endpoints)
- `server/api/validation.py` - Pydantic validation models (19 models, 52 tests)
- `web-ui/src/lib/api.ts` - Frontend API client

**Verification**:
- `server/verification/task_verifier.py` - Task verification (11 tests)
- `server/verification/test_generator.py` - Test generation (15 tests)
- `server/verification/epic_validator.py` - Epic validation (14 tests)

**Utilities**:
- `server/utils/config.py` - Configuration
- `server/utils/logging.py` - Structured logging
- `server/utils/security.py` - Security validation

**Quality System**:
- Phase 1: `server/quality/metrics.py` - Quick checks (zero-cost) ✅
- Phase 2: `server/quality/reviews.py` - Deep reviews (AI-powered) ✅
- Phase 3: `web-ui/src/components/QualityDashboard.tsx` - UI dashboard ✅
- Phase 4: `server/quality/prompt_analyzer.py` - Prompt improvements ✅

**Other Key Files**:
- `mcp-task-manager/src/index.ts` - MCP server
- `schema/postgresql/schema.sql` - Database schema
- `prompts/` - Agent instruction templates
- `docs/` - Documentation

## Logging & Observability

**Structured Logging** (v1.4.0):
- **Terminal**: Development-friendly colored output
- **File**: `logs/yokeflow.log` - JSON format for analysis
- **Per-Session**: `generations/<project>/logs/session_*.jsonl` - Session details

**Configuration** (via environment variables):
```bash
export LOG_LEVEL=INFO          # DEBUG, INFO, WARNING, ERROR, CRITICAL
export LOG_FORMAT=dev           # 'dev' (colored) or 'json' (production)
```

**Log Locations**:
- Application logs: `logs/yokeflow.log` (JSON format)
- Session logs: `generations/<project>/logs/session_NNN_TIMESTAMP.jsonl`
- Session summaries: `generations/<project>/logs/session_NNN_TIMESTAMP.txt`

**Features**:
- Automatic session_id and project_id context injection
- Performance logging for slow operations
- Exception tracking with stack traces
- Ready for ELK/Datadog/CloudWatch integration

## Production Hardening (January 2026)

**✅ P0 Critical Improvements Complete (v1.3.0)**

All three critical gaps have been addressed with production-ready implementations:

### 1. Database Retry Logic ✅
**File**: `server/database/retry.py` (350+ lines, 30 tests)
- Exponential backoff with configurable jitter
- 20+ PostgreSQL error codes covered
- Transient error detection (connection failures, deadlocks, resource exhaustion)
- Retry statistics tracking for observability
- Applied to all database operations in `server/database/operations.py`

**Usage**:
```python
from server.database.retry import with_retry, RetryConfig

@with_retry(RetryConfig(max_retries=5, base_delay=2.0))
async def my_database_operation():
    async with db.acquire() as conn:
        return await conn.fetchval("SELECT 1")
```

### 2. Intervention System ✅
**Files**: `server/agent/session_manager.py`, `server/database/operations.py` (9 new methods, 15 tests)
- Full database persistence for paused sessions
- Intervention action tracking and audit trail
- Pause/resume session operations
- Integration with existing `server/agent/intervention.py` blocker detection
- Web UI ready (`web-ui/src/components/InterventionDashboard.tsx`)

**Database**: `schema/postgresql/011_paused_sessions.sql`
- Tables: `paused_sessions`, `intervention_actions`, `notification_preferences`
- Views: `v_active_interventions`, `v_intervention_history`
- Functions: `pause_session()`, `resume_session()`

### 3. Session Checkpointing ✅
**Files**: `server/agent/checkpoint.py` (420+ lines, 19 tests), `server/database/operations.py` (9 new methods)
- Complete session state preservation at key points
- Full conversation history capture for resume
- State validation before resumption
- Recovery attempt tracking
- Context-aware resume prompt generation

**Database**: `schema/postgresql/012_session_checkpoints.sql`
- Tables: `session_checkpoints`, `checkpoint_recoveries`
- Views: `v_latest_checkpoints`, `v_resumable_checkpoints`, `v_checkpoint_recovery_history`
- Functions: `create_checkpoint()`, `start_checkpoint_recovery()`, `complete_checkpoint_recovery()`

**Usage**:
```python
from server.agent.checkpoint import CheckpointManager

manager = CheckpointManager(session_id, project_id)

# Create checkpoint after task completion
checkpoint_id = await manager.create_checkpoint(
    checkpoint_type="task_completion",
    conversation_history=messages,
    current_task_id=task.id,
    completed_tasks=completed_task_ids
)

# Resume from checkpoint after failure
from server.agent.checkpoint import CheckpointRecoveryManager

recovery = CheckpointRecoveryManager()
state = await recovery.restore_from_checkpoint(checkpoint_id)
# Continue with restored conversation_history, task state, etc.
```

---

## Recent Changes

**January 8-9, 2026 - v2.0.0 Feature Completion**:
- ✅ **REST API Complete**: 17 endpoints implemented with comprehensive validation
- ✅ **Input Validation Framework**: Pydantic models with 52 tests (100% passing)
- ✅ **Verification System Tested**: 40 tests added for task/epic validation
- ✅ **Documentation Updates**: 11 docs updated, verification-system.md created (850+ lines)
- ✅ **Database Schema**: Migrations 013-016 for verification system
- ✅ **Test Suite**: ~212 total tests, 72 core tests passing, 70% coverage achieved

**January 7, 2026 - v2.0.0 Architecture Reorganization**:
- ✅ **Complete folder reorganization**: All server code moved to `server/`
- ✅ **44 Python files** reorganized into 11 clean modules
- ✅ **61 files updated** with new import paths
- ✅ **No circular dependencies**: Clear module boundaries established
- ✅ **Git history preserved**: Used git mv for all tracked files

**January 5, 2026 - v1.4.0 Production Hardening**:
- ✅ Database retry logic with exponential backoff (30 tests)
- ✅ Complete intervention system with database persistence (15 tests)
- ✅ Session checkpointing and recovery system (19 tests)
- ✅ Structured logging with JSON/dev formatters (19 tests)
- ✅ Error hierarchy with 30+ error types (36 tests)
- ✅ 119 new tests (100% pass rate)

**December 29, 2025 - v1.2.0 Release**:
- ✅ **Playwright Browser Automation**: Full browser testing within Docker containers
- ✅ **Docker Integration**: Headless Chromium runs inside containers without port forwarding
- ✅ **Visual Verification**: Screenshots and page snapshots for testing web applications
- ✅ **Codebase Cleanup**: Removed experimental files from Playwright development
- ✅ **Documentation Update**: Consolidated Playwright docs into main Docker guide

**December 27, 2025 - v1.1.0 Release**:
- ✅ **Version 1.1.0**: Database schema improvements, migration scripts removed
- ✅ **Fresh Install Required**: Schema changes require clean database installation
- ✅ **Migration Scripts Removed**: All migration-related scripts and directories cleaned up
- ⚠️ **Breaking Change**: Existing v1.0.0 databases cannot be migrated - fresh install required

**December 24, 2025**:
- ✅ **Prompt Improvements Restored**: Phase 4 of Review System re-enabled in feature branch
- ✅ **Backend Components**: Restored `prompt_improvement_analyzer.py` and API routes
- ✅ **Web UI Pages**: Restored `/prompt-improvements` dashboard and detail views
- ✅ **Integration Complete**: Connected with existing Review System (Phases 1-3)

**December 2025**:
- ✅ Review system Phases 1-3 complete (quick checks, deep reviews, UI dashboard)
- ✅ Prompt Improvement System (Phase 4) - Archived for post-release refactoring
- ✅ PostgreSQL migration complete (UUID-based, async, connection pooling)
- ✅ API-first platform with Next.js Web UI
- ✅ Project completion tracking with celebration UI
- ✅ Coding prompt improvements (browser verification enforcement, bash_docker mandate)
- 🚀 **YokeFlow Transition**: Rebranding and repository migration in progress
- ✅ **Code Organization**: Refactored to `core/` and `review/` modules for better structure
- ✅ **Pre-Release Cleanup**: Experimental features archived, TODO split into pre/post-release

**Key Evolution**:
- Shell scripts → MCP (protocol-based task management)
- JSONL + TXT dual logging (human + machine readable)
- Autonomous Coding → **YokeFlow** (production-ready platform)

## Philosophy

**Greenfield Development**: Builds new applications from scratch, not modifying existing codebases.

**Workflow**: Create `app_spec.txt` → Initialize roadmap → Review → Autonomous coding → Completion verification

**Core Principle**: One-shot success. Improve the agent system itself rather than fixing generated apps.

## Release Status

**Current State**: Production Ready - v2.0.0

**v2.0 Release Highlights**:
- ✅ **REST API Complete**: 17 endpoints with 89% test coverage (17/19 passing)
- ✅ **Input Validation**: Comprehensive Pydantic framework (52 tests, 100% passing)
- ✅ **Verification System**: Automated test generation & epic validation (40 tests)
- ✅ **Production Hardening**: Database retry logic, intervention system, session checkpointing
- ✅ **Test Suite**: ~212 tests total, 70% coverage achieved (72 core tests, 100% pass rate)
- ✅ **Clean Architecture**: All server code under `server/` with clear module separation
- ✅ **Complete Documentation**: 11 docs updated, verification guide created (850+ lines)
- ✅ **Database Schema**: Migrations 011-016 for all v2.0 features
- ✅ **Quality System**: Automated reviews, dashboard, trend tracking
- ✅ **Enterprise Ready**: Structured logging, error hierarchy, observability, Playwright integration

**Post-Release Roadmap**:
- See `TODO-FUTURE.md` for planned enhancements
- Per-user authentication, prompt improvements, E2B integration, and more
- See `YOKEFLOW_REFACTORING_PLAN.md` for remaining P1/P2 improvements (59-69 hours)

---

**For detailed documentation, see `docs/` directory. Originally forked from Anthropic's autonomous coding demo, now evolved into YokeFlow with extensive enhancements.**
