-- =============================================================================
-- YokeFlow (Autonomous Coding Agent) - Complete PostgreSQL Schema
-- =============================================================================
-- Version: 2.0.0
-- Date: January 9, 2026
--
-- This is the consolidated schema file that reflects the current database state.
-- All migrations have been applied and consolidated into this single file.
--
-- Changelog:
--   2.0.0 (Jan 9, 2026): Consolidated with all migrations (011-016) - Production ready
--   2.2.0 (Dec 25, 2025): Added total_time_seconds, removed budget_usd, updated trigger
--   2.1.0 (Dec 23, 2025): Added session heartbeat tracking
--   2.0.0 (Dec 2025): Initial consolidated schema
--
-- To initialize a fresh database, run:
--   python scripts/init_database.py
-- =============================================================================

-- =============================================================================
-- EXTENSIONS
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";  -- For UUID generation

-- =============================================================================
-- CUSTOM TYPES
-- =============================================================================

-- Project status enum
CREATE TYPE project_status AS ENUM (
    'active',
    'paused',
    'completed',
    'archived'
);

-- Session types
CREATE TYPE session_type AS ENUM (
    'initializer',
    'coding',
    'review'
);

-- Session status
CREATE TYPE session_status AS ENUM (
    'pending',
    'running',
    'completed',
    'error',
    'interrupted'
);

-- Deployment status
CREATE TYPE deployment_status AS ENUM (
    'local',
    'sandbox',
    'production'
);

-- Task status
CREATE TYPE task_status AS ENUM (
    'pending',
    'in_progress',
    'completed',
    'blocked'
);

-- =============================================================================
-- MAIN TABLES
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Projects Table - Central metadata for all projects
-- -----------------------------------------------------------------------------
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) UNIQUE NOT NULL,
    user_id UUID,  -- Ready for multi-user support

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,  -- Project completion tracking

    -- Environment configuration
    env_configured BOOLEAN DEFAULT FALSE,
    env_configured_at TIMESTAMPTZ,

    -- Specification tracking
    spec_file_path TEXT,
    spec_hash VARCHAR(64),  -- SHA256 hash to detect changes

    -- GitHub integration
    github_repo_url TEXT,
    github_branch VARCHAR(100) DEFAULT 'main',
    github_default_branch VARCHAR(100) DEFAULT 'main',

    -- Deployment configuration
    deployment_status deployment_status DEFAULT 'local',
    sandbox_config JSONB DEFAULT '{}',
    api_endpoint TEXT,

    -- Project status and metrics
    status project_status DEFAULT 'active',
    total_cost_usd DECIMAL(10,4) DEFAULT 0,
    total_time_seconds INTEGER DEFAULT 0,

    -- Flexible metadata storage
    metadata JSONB DEFAULT '{}',

    -- Constraints
    CONSTRAINT valid_total_cost CHECK (total_cost_usd >= 0),
    CONSTRAINT valid_total_time CHECK (total_time_seconds >= 0)
);

CREATE INDEX idx_projects_user_id ON projects(user_id) WHERE user_id IS NOT NULL;
CREATE INDEX idx_projects_status ON projects(status);
CREATE INDEX idx_projects_name ON projects(name);
CREATE INDEX idx_projects_metadata ON projects USING GIN (metadata);
CREATE INDEX idx_projects_completed_at ON projects(completed_at);
CREATE INDEX idx_projects_total_time ON projects(total_time_seconds);

COMMENT ON COLUMN projects.completed_at IS 'Timestamp when all epics/tasks/tests were completed. NULL means project is still in progress.';
COMMENT ON COLUMN projects.total_time_seconds IS 'Total time spent on project in seconds, automatically aggregated from session durations';

-- -----------------------------------------------------------------------------
-- Sessions Table - Track all agent sessions
-- -----------------------------------------------------------------------------
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    session_number INTEGER NOT NULL,
    type session_type NOT NULL,

    -- Model configuration
    model TEXT NOT NULL,
    max_iterations INTEGER,

    -- Session status
    status session_status DEFAULT 'pending',

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    last_heartbeat TIMESTAMPTZ,  -- Track active sessions to prevent false-positive stale detection

    -- Session outcome
    error_message TEXT,
    interruption_reason TEXT,

    -- Session metrics stored as JSONB for flexibility
    metrics JSONB DEFAULT '{
        "duration_seconds": 0,
        "tool_calls_count": 0,
        "tokens_input": 0,
        "tokens_output": 0,
        "cost_usd": 0,
        "tasks_completed": 0,
        "tests_passed": 0,
        "errors_count": 0,
        "browser_verifications": 0
    }',

    -- Log file references
    log_path TEXT,

    UNIQUE(project_id, session_number)
);

CREATE INDEX idx_sessions_project_status ON sessions(project_id, status);
CREATE INDEX idx_sessions_type ON sessions(type);
CREATE INDEX idx_sessions_created_at ON sessions(created_at DESC);
CREATE INDEX idx_sessions_metrics ON sessions USING GIN (metrics);
CREATE INDEX idx_sessions_stale_detection ON sessions (status, last_heartbeat) WHERE status = 'running';

COMMENT ON COLUMN sessions.last_heartbeat IS 'Timestamp of last heartbeat update during session execution. Used to detect truly stale sessions vs. long-running active sessions.';

-- -----------------------------------------------------------------------------
-- Hierarchical Task Management Tables
-- -----------------------------------------------------------------------------

-- Epics Table - High-level feature areas
CREATE TABLE epics (
    id SERIAL PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    priority INTEGER DEFAULT 0,
    status task_status DEFAULT 'pending',

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    -- Metadata
    metadata JSONB DEFAULT '{}',

    UNIQUE(project_id, name)
);

CREATE INDEX idx_epics_project_id ON epics(project_id);
CREATE INDEX idx_epics_status ON epics(status);
CREATE INDEX idx_epics_priority ON epics(priority);

-- Tasks Table - Individual implementation steps
CREATE TABLE tasks (
    id SERIAL PRIMARY KEY,
    epic_id INTEGER NOT NULL REFERENCES epics(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    description TEXT NOT NULL,
    action TEXT,
    priority INTEGER DEFAULT 0,
    done BOOLEAN DEFAULT FALSE,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,

    -- Session tracking
    session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,
    session_notes TEXT,

    -- Metadata
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_tasks_epic_id ON tasks(epic_id);
CREATE INDEX idx_tasks_project_id ON tasks(project_id);
CREATE INDEX idx_tasks_done ON tasks(done);
CREATE INDEX idx_tasks_priority ON tasks(priority);
CREATE INDEX idx_tasks_session_id ON tasks(session_id);

-- Tests Table - Verification steps for tasks
CREATE TABLE tests (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    category VARCHAR(50) NOT NULL,
    description TEXT NOT NULL,
    steps JSONB DEFAULT '[]',
    passes BOOLEAN DEFAULT FALSE,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    verified_at TIMESTAMPTZ,

    -- Session tracking
    session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,

    -- Test results
    result JSONB DEFAULT '{}',

    CONSTRAINT valid_category CHECK (category IN ('functional', 'style', 'accessibility', 'performance', 'security'))
);

CREATE INDEX idx_tests_task_id ON tests(task_id);
CREATE INDEX idx_tests_project_id ON tests(project_id);
CREATE INDEX idx_tests_passes ON tests(passes);
CREATE INDEX idx_tests_category ON tests(category);

-- -----------------------------------------------------------------------------
-- Session Quality Checks Table - Phase 1 Review System
-- -----------------------------------------------------------------------------
-- Note: The old 'reviews' table was removed in Migration 007 (never used)
-- Note: Deep review fields removed after Migration 003 created session_deep_reviews
CREATE TABLE session_quality_checks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,

    -- Timing and version
    check_version VARCHAR(20),
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Overall scores
    overall_rating INTEGER,  -- 1-10 quality score

    -- Critical quality metrics (from quick check)
    playwright_count INTEGER DEFAULT 0,
    playwright_screenshot_count INTEGER DEFAULT 0,
    total_tool_uses INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    error_rate DECIMAL(5,4),

    -- Issue tracking
    critical_issues JSONB DEFAULT '[]',
    warnings JSONB DEFAULT '[]',

    -- Full metrics (from review_metrics.analyze_session_logs)
    metrics JSONB DEFAULT '{}',

    -- Constraints
    CONSTRAINT valid_rating CHECK (overall_rating IS NULL OR (overall_rating >= 1 AND overall_rating <= 10))
);

CREATE INDEX idx_quality_checks_session ON session_quality_checks(session_id);
CREATE INDEX idx_quality_checks_rating ON session_quality_checks(overall_rating) WHERE overall_rating IS NOT NULL;
CREATE INDEX idx_quality_checks_playwright ON session_quality_checks(playwright_count);
CREATE INDEX idx_quality_checks_created ON session_quality_checks(created_at DESC);
CREATE INDEX idx_quality_checks_critical_issues ON session_quality_checks USING GIN (critical_issues);
CREATE INDEX idx_quality_checks_metrics ON session_quality_checks USING GIN (metrics);

COMMENT ON TABLE session_quality_checks IS 'Quick quality check results for coding sessions (Phase 1 Review System). Zero-cost metrics analysis from session logs. Runs after every coding session. For deep reviews (Phase 2), see session_deep_reviews table.';
COMMENT ON COLUMN session_quality_checks.playwright_count IS 'Total Playwright browser automation calls. Critical quality metric with r=0.98 correlation to session quality. 0 = critical issue, 1-9 = minimal, 10-49 = good, 50+ = excellent';
COMMENT ON COLUMN session_quality_checks.overall_rating IS '1-10 quality score. Based on browser verification, error rate, and critical issues.';

-- -----------------------------------------------------------------------------
-- Deep Review Results (Phase 2 Review System)
-- -----------------------------------------------------------------------------
-- Note: Added via Migration 003 (separate_deep_reviews.sql)
-- Separated from session_quality_checks for cleaner architecture

CREATE TABLE session_deep_reviews (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,

    -- Review version and timing
    review_version VARCHAR(20),
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Overall score (1-10)
    overall_rating INTEGER,

    -- Deep review results
    review_text TEXT,
    review_summary JSONB DEFAULT '{}',
    prompt_improvements JSONB DEFAULT '[]',

    -- Model used for review
    model VARCHAR(100),

    -- Constraints
    CONSTRAINT valid_deep_review_rating CHECK (overall_rating IS NULL OR (overall_rating >= 1 AND overall_rating <= 10)),
    CONSTRAINT unique_session_deep_review UNIQUE (session_id)  -- Each session can have at most one deep review
);

CREATE INDEX idx_deep_reviews_session ON session_deep_reviews(session_id);
CREATE INDEX idx_deep_reviews_created ON session_deep_reviews(created_at DESC);
CREATE INDEX idx_deep_reviews_rating ON session_deep_reviews(overall_rating) WHERE overall_rating IS NOT NULL;
CREATE INDEX idx_deep_reviews_improvements ON session_deep_reviews USING GIN (prompt_improvements);

COMMENT ON TABLE session_deep_reviews IS 'Deep review results for coding sessions. Automated or on-demand Claude-powered reviews for prompt improvement analysis.';
COMMENT ON COLUMN session_deep_reviews.overall_rating IS '1-10 quality score from deep review analysis. May differ from quick check rating.';
COMMENT ON COLUMN session_deep_reviews.review_text IS 'Full markdown review text from Claude, including analysis and recommendations.';
COMMENT ON COLUMN session_deep_reviews.prompt_improvements IS 'Structured list of recommendation strings extracted from review text for aggregation across sessions.';
COMMENT ON CONSTRAINT unique_session_deep_review ON session_deep_reviews IS 'Ensures each session has at most one deep review. If a session needs to be re-reviewed, the existing review should be updated rather than creating a new one.';

-- -----------------------------------------------------------------------------
-- Prompt Improvement System Tables (Phase 4)
-- -----------------------------------------------------------------------------

-- Prompt Improvement Analyses
CREATE TABLE prompt_improvement_analyses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'pending',

    -- Analysis scope
    projects_analyzed UUID[] NOT NULL,
    sessions_analyzed INTEGER NOT NULL DEFAULT 0,
    date_range_start TIMESTAMPTZ,
    date_range_end TIMESTAMPTZ,

    -- Configuration
    analysis_model VARCHAR(100) DEFAULT 'claude-sonnet-4-5-20250929',
    sandbox_type VARCHAR(20),

    -- Results
    overall_findings TEXT,
    patterns_identified JSONB DEFAULT '{}',
    proposed_changes JSONB DEFAULT '[]',
    quality_impact_estimate DECIMAL(3,1),

    -- Metadata
    triggered_by VARCHAR(50),
    user_id UUID,
    notes TEXT,

    CONSTRAINT status_valid CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    CONSTRAINT sandbox_type_valid CHECK (sandbox_type IN ('docker', 'local'))
);

CREATE INDEX idx_prompt_analyses_status ON prompt_improvement_analyses(status);
CREATE INDEX idx_prompt_analyses_created ON prompt_improvement_analyses(created_at DESC);
CREATE INDEX idx_prompt_analyses_sandbox ON prompt_improvement_analyses(sandbox_type);

-- Prompt Proposals
CREATE TABLE prompt_proposals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    analysis_id UUID REFERENCES prompt_improvement_analyses(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Change details
    prompt_file VARCHAR(100) NOT NULL,
    section_name VARCHAR(200),
    line_start INTEGER,
    line_end INTEGER,

    -- The actual change
    original_text TEXT NOT NULL,
    proposed_text TEXT NOT NULL,
    change_type VARCHAR(50),

    -- Justification
    rationale TEXT NOT NULL,
    evidence JSONB DEFAULT '[]',
    confidence_level INTEGER,

    -- Implementation status
    status VARCHAR(20) DEFAULT 'proposed',
    applied_at TIMESTAMPTZ,
    applied_to_version VARCHAR(50),
    applied_by VARCHAR(100),

    -- Impact tracking
    sessions_before_change INTEGER,
    quality_before DECIMAL(3,1),
    sessions_after_change INTEGER,
    quality_after DECIMAL(3,1),

    -- Additional metadata (diff details, etc.)
    metadata JSONB DEFAULT '{}',

    CONSTRAINT change_type_valid CHECK (change_type IN ('addition', 'modification', 'deletion', 'reorganization')),
    CONSTRAINT status_valid CHECK (status IN ('proposed', 'accepted', 'rejected', 'implemented')),
    CONSTRAINT confidence_valid CHECK (confidence_level BETWEEN 1 AND 10)
);

CREATE INDEX idx_proposals_analysis ON prompt_proposals(analysis_id);
CREATE INDEX idx_proposals_status ON prompt_proposals(status);
CREATE INDEX idx_proposals_file ON prompt_proposals(prompt_file);

COMMENT ON TABLE prompt_improvement_analyses IS 'Stores cross-project prompt improvement analyses';
COMMENT ON TABLE prompt_proposals IS 'Individual prompt change proposals from analyses';

-- Note: github_commits and project_preferences tables removed in Migration 007
-- (GitHub integration never implemented, preferences handled by config files)

-- =============================================================================
-- VIEWS
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Progress View
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_progress AS
SELECT
    p.id as project_id,
    p.name as project_name,
    COUNT(DISTINCT e.id) as total_epics,
    COUNT(DISTINCT CASE WHEN e.status = 'completed' THEN e.id END) as completed_epics,
    COUNT(DISTINCT t.id) as total_tasks,
    COUNT(DISTINCT CASE WHEN t.done = true THEN t.id END) as completed_tasks,
    COUNT(DISTINCT test.id) as total_tests,
    COUNT(DISTINCT CASE WHEN test.passes = true THEN test.id END) as passing_tests,
    ROUND(
        CASE
            WHEN COUNT(DISTINCT t.id) > 0
            THEN (COUNT(DISTINCT CASE WHEN t.done = true THEN t.id END)::DECIMAL / COUNT(DISTINCT t.id) * 100)
            ELSE 0
        END, 2
    ) as task_completion_pct,
    ROUND(
        CASE
            WHEN COUNT(DISTINCT test.id) > 0
            THEN (COUNT(DISTINCT CASE WHEN test.passes = true THEN test.id END)::DECIMAL / COUNT(DISTINCT test.id) * 100)
            ELSE 0
        END, 2
    ) as test_pass_pct
FROM projects p
LEFT JOIN epics e ON p.id = e.project_id
LEFT JOIN tasks t ON p.id = t.project_id
LEFT JOIN tests test ON p.id = test.project_id
GROUP BY p.id, p.name;

-- -----------------------------------------------------------------------------
-- Next Task View
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_next_task AS
SELECT DISTINCT ON (p.id)
    t.id as task_id,
    t.description,
    t.action,
    e.id as epic_id,
    e.name as epic_name,
    e.description as epic_description,
    p.id as project_id,
    p.name as project_name
FROM projects p
JOIN epics e ON p.id = e.project_id
JOIN tasks t ON e.id = t.epic_id
WHERE t.done = false
    AND e.status != 'completed'
    AND p.status = 'active'
ORDER BY p.id, e.priority, t.priority, t.id;

-- -----------------------------------------------------------------------------
-- Epic Progress View
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_epic_progress AS
SELECT
    e.id as epic_id,
    e.project_id,
    e.name,
    e.status,
    COUNT(t.id) as total_tasks,
    SUM(CASE WHEN t.done = true THEN 1 ELSE 0 END) as completed_tasks,
    ROUND(
        CASE
            WHEN COUNT(t.id) > 0
            THEN (SUM(CASE WHEN t.done = true THEN 1 ELSE 0 END)::DECIMAL / COUNT(t.id) * 100)
            ELSE 0
        END, 2
    ) as completion_percentage
FROM epics e
LEFT JOIN tasks t ON e.id = t.epic_id
GROUP BY e.id;

-- -----------------------------------------------------------------------------
-- Active Sessions View
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_active_sessions AS
SELECT
    s.id,
    s.project_id,
    p.name as project_name,
    s.session_number,
    s.type,
    s.model,
    s.status,
    s.started_at,
    EXTRACT(EPOCH FROM (NOW() - s.started_at)) as duration_seconds
FROM sessions s
JOIN projects p ON s.project_id = p.id
WHERE s.status = 'running';

-- -----------------------------------------------------------------------------
-- Project Quality View (excludes Session 0/initializer)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_project_quality AS
SELECT
    s.project_id,
    p.name as project_name,
    COUNT(DISTINCT s.id) as total_sessions,
    COUNT(DISTINCT q.id) as checked_sessions,
    ROUND(AVG(q.overall_rating), 1) as avg_quality_rating,
    SUM(CASE WHEN q.playwright_count = 0 THEN 1 ELSE 0 END) as sessions_without_browser_verification,
    ROUND(AVG(q.error_rate) * 100, 1) as avg_error_rate_percent,
    ROUND(AVG(q.playwright_count), 1) as avg_playwright_calls_per_session
FROM sessions s
LEFT JOIN session_quality_checks q ON s.id = q.session_id
LEFT JOIN projects p ON s.project_id = p.id
WHERE s.type = 'coding'  -- Only coding sessions (excludes Session 0/initializer)
GROUP BY s.project_id, p.name;

COMMENT ON VIEW v_project_quality IS 'Project-level quality summary with average ratings, error rates, and browser verification statistics (coding sessions only, excludes Session 0)';

-- -----------------------------------------------------------------------------
-- Recent Quality Issues View
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_recent_quality_issues AS
SELECT
    q.id as check_id,
    s.id as session_id,
    s.session_number,
    s.type as session_type,
    s.project_id,
    p.name as project_name,
    q.overall_rating,
    q.playwright_count,
    q.error_rate,
    q.critical_issues,
    q.warnings,
    q.created_at
FROM session_quality_checks q
JOIN sessions s ON q.session_id = s.id
JOIN projects p ON s.project_id = p.id
WHERE
    s.type != 'initializer'  -- Exclude initializer sessions
    AND (
        jsonb_array_length(q.critical_issues) > 0
        OR q.overall_rating < 6
    )
ORDER BY q.created_at DESC;

-- -----------------------------------------------------------------------------
-- Browser Verification Compliance View
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_browser_verification_compliance AS
SELECT
    s.project_id,
    p.name as project_name,
    COUNT(*) as total_sessions,
    SUM(CASE WHEN q.playwright_count > 0 THEN 1 ELSE 0 END) as sessions_with_verification,
    SUM(CASE WHEN q.playwright_count >= 50 THEN 1 ELSE 0 END) as sessions_excellent_verification,
    SUM(CASE WHEN q.playwright_count BETWEEN 10 AND 49 THEN 1 ELSE 0 END) as sessions_good_verification,
    SUM(CASE WHEN q.playwright_count BETWEEN 1 AND 9 THEN 1 ELSE 0 END) as sessions_minimal_verification,
    SUM(CASE WHEN q.playwright_count = 0 THEN 1 ELSE 0 END) as sessions_no_verification,
    ROUND(100.0 * SUM(CASE WHEN q.playwright_count > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as verification_rate_percent
FROM sessions s
JOIN projects p ON s.project_id = p.id
LEFT JOIN session_quality_checks q ON s.id = q.session_id
WHERE s.type = 'coding'  -- Only coding sessions
GROUP BY s.project_id, p.name;

COMMENT ON VIEW v_browser_verification_compliance IS 'Browser verification compliance tracking. Shows % of coding sessions with Playwright usage (target: 100%)';

-- -----------------------------------------------------------------------------
-- Prompt Improvement Views
-- -----------------------------------------------------------------------------

-- Recent Analyses with Summary Stats
CREATE OR REPLACE VIEW v_recent_analyses AS
SELECT
    a.id,
    a.created_at,
    a.completed_at,
    a.status,
    a.sandbox_type,
    CARDINALITY(a.projects_analyzed) as num_projects,
    a.sessions_analyzed,
    a.quality_impact_estimate,
    COUNT(p.id) as total_proposals,
    COUNT(CASE WHEN p.status = 'proposed' THEN 1 END) as pending_proposals,
    COUNT(CASE WHEN p.status = 'accepted' THEN 1 END) as accepted_proposals,
    COUNT(CASE WHEN p.status = 'implemented' THEN 1 END) as implemented_proposals
FROM prompt_improvement_analyses a
LEFT JOIN prompt_proposals p ON a.id = p.analysis_id
GROUP BY a.id
ORDER BY a.created_at DESC;

-- Pending Proposals with Analysis Info
CREATE OR REPLACE VIEW v_pending_proposals AS
SELECT
    p.id,
    p.created_at,
    p.prompt_file,
    p.section_name,
    p.change_type,
    p.confidence_level,
    p.rationale,
    a.sandbox_type,
    a.sessions_analyzed,
    CARDINALITY(a.projects_analyzed) as num_projects_analyzed
FROM prompt_proposals p
JOIN prompt_improvement_analyses a ON p.analysis_id = a.id
WHERE p.status = 'proposed'
ORDER BY p.confidence_level DESC, p.created_at DESC;

-- =============================================================================
-- FUNCTIONS AND TRIGGERS
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Update updated_at Timestamp
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_projects_updated_at
    BEFORE UPDATE ON projects
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- -----------------------------------------------------------------------------
-- Update Project Metrics (Cost and Time) on Session Complete
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_project_metrics()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'completed' AND OLD.status != 'completed' THEN
        UPDATE projects
        SET
            total_cost_usd = total_cost_usd + COALESCE((NEW.metrics->>'cost_usd')::DECIMAL, 0),
            total_time_seconds = total_time_seconds + COALESCE(ROUND((NEW.metrics->>'duration_seconds')::NUMERIC)::INTEGER, 0)
        WHERE id = NEW.project_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_project_metrics_on_session_complete
    AFTER UPDATE ON sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_project_metrics();

-- -----------------------------------------------------------------------------
-- Validate Session Type Consistency (0-based session numbering)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION validate_session_type()
RETURNS TRIGGER AS $$
DECLARE
    epic_count INTEGER;
BEGIN
    -- Count existing epics for the project
    SELECT COUNT(*) INTO epic_count
    FROM epics
    WHERE project_id = NEW.project_id;

    -- First session (session_number = 0) must be initializer if no epics exist
    IF NEW.session_number = 0 AND epic_count = 0 AND NEW.type != 'initializer' THEN
        RAISE EXCEPTION 'First session (session_number = 0) must be initializer type when no epics exist';
    END IF;

    -- Can't run initializer if epics already exist
    IF NEW.type = 'initializer' AND epic_count > 0 THEN
        RAISE EXCEPTION 'Cannot run initializer session when epics already exist (% epics found)', epic_count;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER validate_session_type_consistency
    BEFORE INSERT ON sessions
    FOR EACH ROW
    EXECUTE FUNCTION validate_session_type();

COMMENT ON FUNCTION validate_session_type() IS 'Validates session type consistency: First session (session_number=0) must be initializer when no epics exist, and initializer cannot run when epics exist';

-- =============================================================================
-- END OF SCHEMA
-- =============================================================================
-- Paused Sessions and Intervention Management
-- ============================================
-- Stores session state when paused due to blockers

-- Table for paused sessions
CREATE TABLE IF NOT EXISTS paused_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    -- Pause information
    paused_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    pause_reason TEXT NOT NULL,
    pause_type VARCHAR(50) NOT NULL, -- 'retry_limit', 'critical_error', 'manual', 'timeout'

    -- Current state when paused
    current_task_id INTEGER REFERENCES tasks(id),
    current_task_description TEXT,
    message_count INTEGER,

    -- Blocker details
    blocker_info JSONB NOT NULL DEFAULT '{}',
    retry_stats JSONB NOT NULL DEFAULT '{}',
    error_messages TEXT[],

    -- Resolution tracking
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMPTZ,
    resolution_notes TEXT,
    resolved_by VARCHAR(255),

    -- Resume information
    can_auto_resume BOOLEAN DEFAULT FALSE,
    resume_prompt TEXT, -- Custom prompt to use when resuming
    resume_context JSONB DEFAULT '{}', -- Additional context for resume

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_active_pause_per_session UNIQUE (session_id, resolved)
);

-- Table for intervention actions taken
CREATE TABLE IF NOT EXISTS intervention_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    paused_session_id UUID NOT NULL REFERENCES paused_sessions(id) ON DELETE CASCADE,

    -- Action details
    action_type VARCHAR(50) NOT NULL, -- 'notification_sent', 'auto_recovery', 'manual_fix', 'resumed'
    action_status VARCHAR(20) NOT NULL, -- 'pending', 'success', 'failed'
    action_details JSONB NOT NULL DEFAULT '{}',

    -- Timing
    initiated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,

    -- Results
    result_message TEXT,
    error_message TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Table for notification preferences per project
CREATE TABLE IF NOT EXISTS notification_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    -- Notification channels
    webhook_enabled BOOLEAN DEFAULT FALSE,
    webhook_url TEXT,

    email_enabled BOOLEAN DEFAULT FALSE,
    email_addresses TEXT[],

    sms_enabled BOOLEAN DEFAULT FALSE,
    sms_numbers TEXT[],

    -- Notification triggers
    notify_on_retry_limit BOOLEAN DEFAULT TRUE,
    notify_on_critical_error BOOLEAN DEFAULT TRUE,
    notify_on_timeout BOOLEAN DEFAULT TRUE,
    notify_on_manual_pause BOOLEAN DEFAULT FALSE,

    -- Rate limiting
    min_notification_interval INTEGER DEFAULT 300, -- Minimum seconds between notifications
    last_notification_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_preferences_per_project UNIQUE (project_id)
);

-- Indexes for performance
CREATE INDEX idx_paused_sessions_project ON paused_sessions(project_id);
CREATE INDEX idx_paused_sessions_resolved ON paused_sessions(resolved);
CREATE INDEX idx_paused_sessions_paused_at ON paused_sessions(paused_at DESC);
CREATE INDEX idx_intervention_actions_paused_session ON intervention_actions(paused_session_id);
CREATE INDEX idx_intervention_actions_initiated_at ON intervention_actions(initiated_at DESC);

-- Views for dashboard
CREATE OR REPLACE VIEW v_active_interventions AS
SELECT
    ps.id,
    ps.session_id,
    ps.project_id,
    p.name as project_name,
    ps.paused_at,
    ps.pause_reason,
    ps.pause_type,
    ps.current_task_description,
    ps.blocker_info,
    ps.retry_stats,
    ps.can_auto_resume,
    COALESCE(
        (SELECT COUNT(*)
         FROM intervention_actions ia
         WHERE ia.paused_session_id = ps.id
         AND ia.action_type = 'notification_sent'
         AND ia.action_status = 'success'),
        0
    ) as notifications_sent,
    NOW() - ps.paused_at as time_paused
FROM paused_sessions ps
JOIN projects p ON ps.project_id = p.id
WHERE ps.resolved = FALSE
ORDER BY ps.paused_at DESC;

CREATE OR REPLACE VIEW v_intervention_history AS
SELECT
    ps.id,
    ps.project_id,
    p.name as project_name,
    ps.paused_at,
    ps.pause_type,
    ps.resolved_at,
    ps.resolution_notes,
    ps.resolved_by,
    ps.resolved_at - ps.paused_at as resolution_time,
    array_agg(
        DISTINCT jsonb_build_object(
            'type', ia.action_type,
            'status', ia.action_status,
            'initiated_at', ia.initiated_at
        )
    ) as actions_taken
FROM paused_sessions ps
JOIN projects p ON ps.project_id = p.id
LEFT JOIN intervention_actions ia ON ps.id = ia.paused_session_id
WHERE ps.resolved = TRUE
GROUP BY ps.id, p.id, p.name
ORDER BY ps.resolved_at DESC;

-- Function to pause a session
CREATE OR REPLACE FUNCTION pause_session(
    p_session_id UUID,
    p_project_id UUID,
    p_reason TEXT,
    p_pause_type VARCHAR(50),
    p_blocker_info JSONB DEFAULT '{}',
    p_retry_stats JSONB DEFAULT '{}',
    p_current_task_id INTEGER DEFAULT NULL,
    p_current_task_description TEXT DEFAULT NULL
) RETURNS UUID AS $$
DECLARE
    v_paused_session_id UUID;
BEGIN
    INSERT INTO paused_sessions (
        session_id,
        project_id,
        pause_reason,
        pause_type,
        blocker_info,
        retry_stats,
        current_task_id,
        current_task_description
    ) VALUES (
        p_session_id,
        p_project_id,
        p_reason,
        p_pause_type,
        p_blocker_info,
        p_retry_stats,
        p_current_task_id,
        p_current_task_description
    )
    RETURNING id INTO v_paused_session_id;

    -- Update session status
    UPDATE sessions
    SET status = 'paused',
        updated_at = NOW()
    WHERE id = p_session_id;

    RETURN v_paused_session_id;
END;
$$ LANGUAGE plpgsql;

-- Function to resume a session
CREATE OR REPLACE FUNCTION resume_session(
    p_paused_session_id UUID,
    p_resolved_by VARCHAR(255) DEFAULT 'system',
    p_resolution_notes TEXT DEFAULT NULL
) RETURNS BOOLEAN AS $$
BEGIN
    -- Mark as resolved
    UPDATE paused_sessions
    SET resolved = TRUE,
        resolved_at = NOW(),
        resolved_by = p_resolved_by,
        resolution_notes = p_resolution_notes,
        updated_at = NOW()
    WHERE id = p_paused_session_id
    AND resolved = FALSE;

    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    -- Update session status
    UPDATE sessions
    SET status = 'resumed',
        updated_at = NOW()
    WHERE id = (
        SELECT session_id
        FROM paused_sessions
        WHERE id = p_paused_session_id
    );

    -- Log the resume action
    INSERT INTO intervention_actions (
        paused_session_id,
        action_type,
        action_status,
        action_details,
        completed_at
    ) VALUES (
        p_paused_session_id,
        'resumed',
        'success',
        jsonb_build_object('resolved_by', p_resolved_by),
        NOW()
    );

    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;-- Session Checkpoints for Resume Capability
-- ============================================
-- Stores session state at key points for recovery and resumption

-- Checkpoint table - stores session state snapshots
CREATE TABLE IF NOT EXISTS session_checkpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    -- Checkpoint metadata
    checkpoint_number INTEGER NOT NULL, -- Sequential within session (1, 2, 3...)
    checkpoint_type VARCHAR(50) NOT NULL, -- 'task_completion', 'epic_completion', 'manual', 'error'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Session state at checkpoint
    current_task_id INTEGER REFERENCES tasks(id),
    current_epic_id INTEGER REFERENCES epics(id),
    message_count INTEGER NOT NULL DEFAULT 0,
    iteration_count INTEGER NOT NULL DEFAULT 0,

    -- Agent conversation state
    conversation_history JSONB NOT NULL DEFAULT '[]', -- Array of messages
    tool_results_cache JSONB NOT NULL DEFAULT '{}', -- Recent tool results for context

    -- Task progress state
    completed_tasks INTEGER[] DEFAULT '{}', -- Array of completed task IDs
    in_progress_tasks INTEGER[] DEFAULT '{}', -- Array of in-progress task IDs
    blocked_tasks INTEGER[] DEFAULT '{}', -- Array of blocked task IDs

    -- Session metrics snapshot
    metrics_snapshot JSONB NOT NULL DEFAULT '{}',

    -- File system state (for verification)
    files_modified TEXT[], -- List of files modified in this session
    git_commit_sha VARCHAR(40), -- Last git commit at checkpoint

    -- Resumption info
    can_resume_from BOOLEAN DEFAULT TRUE,
    resume_notes TEXT, -- Notes about how to resume from this checkpoint
    invalidated BOOLEAN DEFAULT FALSE, -- Set to true if checkpoint is no longer valid
    invalidation_reason TEXT,

    -- Recovery metadata
    recovery_count INTEGER DEFAULT 0, -- How many times resumed from this checkpoint
    last_resumed_at TIMESTAMPTZ,

    CONSTRAINT unique_checkpoint_per_session UNIQUE (session_id, checkpoint_number),
    CONSTRAINT valid_checkpoint_number CHECK (checkpoint_number > 0),
    CONSTRAINT valid_message_count CHECK (message_count >= 0),
    CONSTRAINT valid_iteration_count CHECK (iteration_count >= 0)
);

-- Table for checkpoint recovery attempts
CREATE TABLE IF NOT EXISTS checkpoint_recoveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    checkpoint_id UUID NOT NULL REFERENCES session_checkpoints(id) ON DELETE CASCADE,

    -- Recovery attempt info
    recovery_initiated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    recovery_completed_at TIMESTAMPTZ,
    recovery_status VARCHAR(20) NOT NULL, -- 'in_progress', 'success', 'failed'

    -- New session created for recovery
    new_session_id UUID REFERENCES sessions(id),

    -- Recovery details
    recovery_method VARCHAR(50) NOT NULL, -- 'automatic', 'manual', 'partial'
    recovery_notes TEXT,
    error_message TEXT,

    -- State comparison
    state_differences JSONB DEFAULT '{}', -- Differences between checkpoint and actual state

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_checkpoints_session ON session_checkpoints(session_id);
CREATE INDEX idx_checkpoints_project ON session_checkpoints(project_id);
CREATE INDEX idx_checkpoints_created_at ON session_checkpoints(created_at DESC);
CREATE INDEX idx_checkpoints_type ON session_checkpoints(checkpoint_type);
CREATE INDEX idx_checkpoints_can_resume ON session_checkpoints(can_resume_from) WHERE can_resume_from = TRUE;
CREATE INDEX idx_checkpoints_task ON session_checkpoints(current_task_id) WHERE current_task_id IS NOT NULL;

CREATE INDEX idx_recoveries_checkpoint ON checkpoint_recoveries(checkpoint_id);
CREATE INDEX idx_recoveries_status ON checkpoint_recoveries(recovery_status);
CREATE INDEX idx_recoveries_initiated_at ON checkpoint_recoveries(recovery_initiated_at DESC);

-- Views for checkpoint management

-- View: Latest checkpoint for each session
CREATE OR REPLACE VIEW v_latest_checkpoints AS
SELECT DISTINCT ON (session_id)
    cp.id,
    cp.session_id,
    cp.project_id,
    p.name as project_name,
    cp.checkpoint_number,
    cp.checkpoint_type,
    cp.created_at,
    cp.current_task_id,
    t.description as current_task_description,
    cp.message_count,
    cp.iteration_count,
    cp.can_resume_from,
    cp.invalidated,
    cp.recovery_count,
    cp.last_resumed_at,
    s.status as session_status,
    s.session_number
FROM session_checkpoints cp
JOIN sessions s ON cp.session_id = s.id
JOIN projects p ON cp.project_id = p.id
LEFT JOIN tasks t ON cp.current_task_id = t.id
ORDER BY session_id, checkpoint_number DESC;

-- View: Resumable checkpoints (valid and not invalidated)
CREATE OR REPLACE VIEW v_resumable_checkpoints AS
SELECT
    cp.id,
    cp.session_id,
    cp.project_id,
    p.name as project_name,
    cp.checkpoint_number,
    cp.checkpoint_type,
    cp.created_at,
    cp.current_task_id,
    t.description as current_task_description,
    cp.message_count,
    cp.recovery_count,
    cp.last_resumed_at,
    s.session_number,
    s.type as session_type,
    s.status as session_status,
    NOW() - cp.created_at as age
FROM session_checkpoints cp
JOIN sessions s ON cp.session_id = s.id
JOIN projects p ON cp.project_id = p.id
LEFT JOIN tasks t ON cp.current_task_id = t.id
WHERE cp.can_resume_from = TRUE
  AND cp.invalidated = FALSE
  AND s.status IN ('error', 'interrupted')
ORDER BY cp.created_at DESC;

-- View: Checkpoint recovery history
CREATE OR REPLACE VIEW v_checkpoint_recovery_history AS
SELECT
    cr.id,
    cr.checkpoint_id,
    cp.session_id as original_session_id,
    s1.session_number as original_session_number,
    cr.new_session_id,
    s2.session_number as new_session_number,
    cp.project_id,
    p.name as project_name,
    cr.recovery_initiated_at,
    cr.recovery_completed_at,
    cr.recovery_status,
    cr.recovery_method,
    cr.error_message,
    EXTRACT(EPOCH FROM (cr.recovery_completed_at - cr.recovery_initiated_at)) as recovery_duration_seconds,
    cp.checkpoint_type,
    cp.checkpoint_number
FROM checkpoint_recoveries cr
JOIN session_checkpoints cp ON cr.checkpoint_id = cp.id
JOIN sessions s1 ON cp.session_id = s1.id
LEFT JOIN sessions s2 ON cr.new_session_id = s2.id
JOIN projects p ON cp.project_id = p.id
ORDER BY cr.recovery_initiated_at DESC;

-- Function to create a checkpoint
CREATE OR REPLACE FUNCTION create_checkpoint(
    p_session_id UUID,
    p_project_id UUID,
    p_checkpoint_type VARCHAR(50),
    p_current_task_id INTEGER DEFAULT NULL,
    p_current_epic_id INTEGER DEFAULT NULL,
    p_message_count INTEGER DEFAULT 0,
    p_iteration_count INTEGER DEFAULT 0,
    p_conversation_history JSONB DEFAULT '[]',
    p_tool_results_cache JSONB DEFAULT '{}',
    p_completed_tasks INTEGER[] DEFAULT '{}',
    p_in_progress_tasks INTEGER[] DEFAULT '{}',
    p_blocked_tasks INTEGER[] DEFAULT '{}',
    p_metrics_snapshot JSONB DEFAULT '{}',
    p_files_modified TEXT[] DEFAULT '{}',
    p_git_commit_sha VARCHAR(40) DEFAULT NULL,
    p_resume_notes TEXT DEFAULT NULL
) RETURNS UUID AS $$
DECLARE
    v_checkpoint_id UUID;
    v_checkpoint_number INTEGER;
BEGIN
    -- Get next checkpoint number for this session
    SELECT COALESCE(MAX(checkpoint_number), 0) + 1
    INTO v_checkpoint_number
    FROM session_checkpoints
    WHERE session_id = p_session_id;

    -- Create the checkpoint
    INSERT INTO session_checkpoints (
        session_id,
        project_id,
        checkpoint_number,
        checkpoint_type,
        current_task_id,
        current_epic_id,
        message_count,
        iteration_count,
        conversation_history,
        tool_results_cache,
        completed_tasks,
        in_progress_tasks,
        blocked_tasks,
        metrics_snapshot,
        files_modified,
        git_commit_sha,
        resume_notes
    ) VALUES (
        p_session_id,
        p_project_id,
        v_checkpoint_number,
        p_checkpoint_type,
        p_current_task_id,
        p_current_epic_id,
        p_message_count,
        p_iteration_count,
        p_conversation_history,
        p_tool_results_cache,
        p_completed_tasks,
        p_in_progress_tasks,
        p_blocked_tasks,
        p_metrics_snapshot,
        p_files_modified,
        p_git_commit_sha,
        p_resume_notes
    )
    RETURNING id INTO v_checkpoint_id;

    RETURN v_checkpoint_id;
END;
$$ LANGUAGE plpgsql;

-- Function to invalidate checkpoints (when state has changed)
CREATE OR REPLACE FUNCTION invalidate_checkpoints(
    p_session_id UUID,
    p_reason TEXT
) RETURNS INTEGER AS $$
DECLARE
    v_count INTEGER;
BEGIN
    UPDATE session_checkpoints
    SET invalidated = TRUE,
        invalidation_reason = p_reason
    WHERE session_id = p_session_id
      AND invalidated = FALSE
      AND can_resume_from = TRUE;

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;

-- Function to start checkpoint recovery
CREATE OR REPLACE FUNCTION start_checkpoint_recovery(
    p_checkpoint_id UUID,
    p_recovery_method VARCHAR(50),
    p_new_session_id UUID DEFAULT NULL
) RETURNS UUID AS $$
DECLARE
    v_recovery_id UUID;
BEGIN
    -- Create recovery record
    INSERT INTO checkpoint_recoveries (
        checkpoint_id,
        recovery_status,
        recovery_method,
        new_session_id
    ) VALUES (
        p_checkpoint_id,
        'in_progress',
        p_recovery_method,
        p_new_session_id
    )
    RETURNING id INTO v_recovery_id;

    -- Update checkpoint recovery count
    UPDATE session_checkpoints
    SET recovery_count = recovery_count + 1,
        last_resumed_at = NOW()
    WHERE id = p_checkpoint_id;

    RETURN v_recovery_id;
END;
$$ LANGUAGE plpgsql;

-- Function to complete checkpoint recovery
CREATE OR REPLACE FUNCTION complete_checkpoint_recovery(
    p_recovery_id UUID,
    p_status VARCHAR(20),
    p_recovery_notes TEXT DEFAULT NULL,
    p_error_message TEXT DEFAULT NULL,
    p_state_differences JSONB DEFAULT '{}'
) RETURNS BOOLEAN AS $$
BEGIN
    UPDATE checkpoint_recoveries
    SET recovery_status = p_status,
        recovery_completed_at = NOW(),
        recovery_notes = p_recovery_notes,
        error_message = p_error_message,
        state_differences = p_state_differences
    WHERE id = p_recovery_id;

    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

-- Function to get latest resumable checkpoint for a session
CREATE OR REPLACE FUNCTION get_latest_resumable_checkpoint(
    p_session_id UUID
) RETURNS UUID AS $$
DECLARE
    v_checkpoint_id UUID;
BEGIN
    SELECT id INTO v_checkpoint_id
    FROM session_checkpoints
    WHERE session_id = p_session_id
      AND can_resume_from = TRUE
      AND invalidated = FALSE
    ORDER BY checkpoint_number DESC
    LIMIT 1;

    RETURN v_checkpoint_id;
END;
$$ LANGUAGE plpgsql;

-- Trigger to update session status enum to include checkpointing states
-- Note: We're adding 'paused' and 'resumed' to the session_status enum if needed
DO $$
BEGIN
    -- Add 'paused' status if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'paused' AND enumtypid = 'session_status'::regtype) THEN
        ALTER TYPE session_status ADD VALUE 'paused';
    END IF;

    -- Add 'resumed' status if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'resumed' AND enumtypid = 'session_status'::regtype) THEN
        ALTER TYPE session_status ADD VALUE 'resumed';
    END IF;
EXCEPTION
    WHEN duplicate_object THEN
        -- Ignore if values already exist
        NULL;
END$$;

COMMENT ON TABLE session_checkpoints IS 'Stores session state snapshots at key points for recovery and resumption';
COMMENT ON TABLE checkpoint_recoveries IS 'Tracks attempts to recover sessions from checkpoints';
COMMENT ON COLUMN session_checkpoints.conversation_history IS 'Full conversation history at checkpoint for context restoration';
COMMENT ON COLUMN session_checkpoints.tool_results_cache IS 'Recent tool results to avoid re-execution';
COMMENT ON COLUMN session_checkpoints.invalidated IS 'Set to true if state has diverged and checkpoint is no longer safe to resume from';
COMMENT ON COLUMN checkpoint_recoveries.state_differences IS 'JSON object documenting differences between checkpoint state and actual state';
-- Task Verification System Tables
-- ================================
-- Adds support for automated task verification and testing

-- Table: task_verification_results
-- Stores results of task verification attempts
CREATE TABLE IF NOT EXISTS task_verification_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,

    -- Verification status
    status VARCHAR(50) NOT NULL CHECK (status IN (
        'pending', 'running', 'passed', 'failed', 'retry', 'manual_review'
    )),

    -- Test results
    tests_run INTEGER NOT NULL DEFAULT 0,
    tests_passed INTEGER NOT NULL DEFAULT 0,
    tests_failed INTEGER NOT NULL DEFAULT 0,

    -- Failure analysis (JSON)
    failure_analysis JSONB,

    -- Retry information
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,

    -- Performance
    duration_seconds NUMERIC(10, 2),

    -- Timestamps
    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Index for quick lookups
CREATE INDEX idx_task_verification_task_id ON task_verification_results(task_id);
CREATE INDEX idx_task_verification_session_id ON task_verification_results(session_id);
CREATE INDEX idx_task_verification_status ON task_verification_results(status);
CREATE INDEX idx_task_verification_started_at ON task_verification_results(started_at DESC);

-- Table: generated_tests
-- Stores tests generated for each task
CREATE TABLE IF NOT EXISTS generated_tests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    verification_id UUID REFERENCES task_verification_results(id) ON DELETE CASCADE,

    -- Test information
    test_type VARCHAR(50) NOT NULL CHECK (test_type IN (
        'unit', 'integration', 'e2e', 'browser', 'api', 'validation'
    )),
    test_name VARCHAR(255) NOT NULL,
    test_description TEXT,
    file_path TEXT NOT NULL,

    -- Test code
    test_code TEXT NOT NULL,

    -- Dependencies
    dependencies TEXT[],

    -- Configuration
    timeout_seconds INTEGER DEFAULT 30,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Index for quick lookups
CREATE INDEX idx_generated_tests_task_id ON generated_tests(task_id);
CREATE INDEX idx_generated_tests_verification_id ON generated_tests(verification_id);
CREATE INDEX idx_generated_tests_type ON generated_tests(test_type);

-- Table: test_execution_results
-- Stores individual test execution results
CREATE TABLE IF NOT EXISTS test_execution_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    verification_id UUID NOT NULL REFERENCES task_verification_results(id) ON DELETE CASCADE,
    test_id UUID REFERENCES generated_tests(id) ON DELETE CASCADE,

    -- Test identification
    test_name VARCHAR(255) NOT NULL,
    test_type VARCHAR(50) NOT NULL,

    -- Result
    passed BOOLEAN NOT NULL,

    -- Output and errors
    output TEXT,
    error TEXT,

    -- Performance
    duration_seconds NUMERIC(10, 3),

    -- Retry information
    retry_number INTEGER DEFAULT 0,

    -- Timestamps
    executed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Index for quick lookups
CREATE INDEX idx_test_execution_verification_id ON test_execution_results(verification_id);
CREATE INDEX idx_test_execution_test_id ON test_execution_results(test_id);
CREATE INDEX idx_test_execution_passed ON test_execution_results(passed);

-- Table: task_file_modifications
-- Tracks files modified during task implementation
CREATE TABLE IF NOT EXISTS task_file_modifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,

    -- File information
    file_path TEXT NOT NULL,
    file_type VARCHAR(50),  -- 'python', 'typescript', 'javascript', etc.

    -- Modification type
    modification_type VARCHAR(50) CHECK (modification_type IN (
        'created', 'modified', 'deleted', 'renamed'
    )),

    -- Lines changed (for modified files)
    lines_added INTEGER DEFAULT 0,
    lines_removed INTEGER DEFAULT 0,

    -- Timestamps
    modified_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Index for quick lookups
CREATE INDEX idx_file_modifications_task_id ON task_file_modifications(task_id);
CREATE INDEX idx_file_modifications_session_id ON task_file_modifications(session_id);
CREATE INDEX idx_file_modifications_file_path ON task_file_modifications(file_path);

-- Add verification columns to tasks table
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS verified BOOLEAN DEFAULT FALSE;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS needs_review BOOLEAN DEFAULT FALSE;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS review_reason TEXT;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS verification_attempts INTEGER DEFAULT 0;

-- View: Current verification status for all tasks
CREATE OR REPLACE VIEW v_task_verification_status AS
SELECT
    t.id AS task_id,
    t.description AS task_description,
    t.done AS task_completed,
    t.verified AS task_verified,
    t.needs_review,
    tvr.status AS latest_verification_status,
    tvr.tests_run,
    tvr.tests_passed,
    tvr.tests_failed,
    tvr.retry_count,
    tvr.duration_seconds,
    tvr.started_at AS last_verification_at,
    COUNT(DISTINCT tfm.file_path) AS files_modified
FROM tasks t
LEFT JOIN LATERAL (
    SELECT * FROM task_verification_results
    WHERE task_id = t.id
    ORDER BY started_at DESC
    LIMIT 1
) tvr ON true
LEFT JOIN task_file_modifications tfm ON tfm.task_id = t.id
GROUP BY t.id, t.description, t.done, t.verified, t.needs_review,
         tvr.status, tvr.tests_run, tvr.tests_passed, tvr.tests_failed,
         tvr.retry_count, tvr.duration_seconds, tvr.started_at;

-- View: Verification success rate by epic
CREATE OR REPLACE VIEW v_epic_verification_stats AS
SELECT
    e.id AS epic_id,
    e.name AS epic_name,
    COUNT(t.id) AS total_tasks,
    COUNT(t.id) FILTER (WHERE t.done) AS completed_tasks,
    COUNT(t.id) FILTER (WHERE t.verified) AS verified_tasks,
    COUNT(t.id) FILTER (WHERE t.needs_review) AS needs_review_tasks,
    AVG(tvr.tests_passed::NUMERIC / NULLIF(tvr.tests_run, 0)) * 100 AS avg_test_pass_rate,
    AVG(tvr.retry_count) AS avg_retry_count,
    AVG(tvr.duration_seconds) AS avg_verification_duration
FROM epics e
LEFT JOIN tasks t ON t.epic_id = e.id
LEFT JOIN LATERAL (
    SELECT * FROM task_verification_results
    WHERE task_id = t.id AND status = 'passed'
    ORDER BY started_at DESC
    LIMIT 1
) tvr ON true
GROUP BY e.id, e.name;

-- View: Test failure patterns
CREATE OR REPLACE VIEW v_test_failure_patterns AS
SELECT
    ter.test_type,
    ter.error,
    COUNT(*) AS failure_count,
    COUNT(DISTINCT ter.verification_id) AS affected_verifications,
    COUNT(DISTINCT tvr.task_id) AS affected_tasks,
    AVG(ter.duration_seconds) AS avg_duration,
    MAX(ter.executed_at) AS last_occurrence
FROM test_execution_results ter
JOIN task_verification_results tvr ON tvr.id = ter.verification_id
WHERE ter.passed = false
GROUP BY ter.test_type, ter.error
ORDER BY failure_count DESC;

-- Function: Get verification summary for a project
CREATE OR REPLACE FUNCTION get_project_verification_summary(p_project_id UUID)
RETURNS TABLE (
    total_tasks INTEGER,
    verified_tasks INTEGER,
    tasks_needing_review INTEGER,
    total_tests_run INTEGER,
    total_tests_passed INTEGER,
    average_pass_rate NUMERIC,
    average_verification_time NUMERIC,
    most_common_failure TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(DISTINCT t.id)::INTEGER AS total_tasks,
        COUNT(DISTINCT t.id) FILTER (WHERE t.verified)::INTEGER AS verified_tasks,
        COUNT(DISTINCT t.id) FILTER (WHERE t.needs_review)::INTEGER AS tasks_needing_review,
        SUM(tvr.tests_run)::INTEGER AS total_tests_run,
        SUM(tvr.tests_passed)::INTEGER AS total_tests_passed,
        AVG(CASE WHEN tvr.tests_run > 0
            THEN tvr.tests_passed::NUMERIC / tvr.tests_run * 100
            ELSE 0 END) AS average_pass_rate,
        AVG(tvr.duration_seconds) AS average_verification_time,
        (SELECT ter.error FROM test_execution_results ter
         JOIN task_verification_results tvr2 ON tvr2.id = ter.verification_id
         JOIN tasks t2 ON t2.id = tvr2.task_id
         JOIN epics e2 ON e2.id = t2.epic_id
         WHERE e2.project_id = p_project_id AND NOT ter.passed
         GROUP BY ter.error
         ORDER BY COUNT(*) DESC
         LIMIT 1) AS most_common_failure
    FROM tasks t
    JOIN epics e ON e.id = t.epic_id
    LEFT JOIN task_verification_results tvr ON tvr.task_id = t.id
    WHERE e.project_id = p_project_id;
END;
$$ LANGUAGE plpgsql;

-- Function: Mark task as verified
CREATE OR REPLACE FUNCTION mark_task_verified(
    p_task_id INTEGER,
    p_session_id UUID DEFAULT NULL
)
RETURNS BOOLEAN AS $$
BEGIN
    UPDATE tasks
    SET verified = true,
        verified_at = CURRENT_TIMESTAMP,
        needs_review = false,
        review_reason = NULL,
        session_id = COALESCE(p_session_id, session_id)
    WHERE id = p_task_id;

    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

-- Comments for documentation
COMMENT ON TABLE task_verification_results IS 'Stores results of automated task verification attempts';
COMMENT ON TABLE generated_tests IS 'Stores tests automatically generated for each task';
COMMENT ON TABLE test_execution_results IS 'Individual test execution results within a verification';
COMMENT ON TABLE task_file_modifications IS 'Tracks files modified during task implementation';
COMMENT ON VIEW v_task_verification_status IS 'Current verification status for all tasks';
COMMENT ON VIEW v_epic_verification_stats IS 'Verification statistics aggregated by epic';
COMMENT ON VIEW v_test_failure_patterns IS 'Common test failure patterns for analysis';-- Epic Validation System Tables
-- ===============================
-- Adds support for epic-level validation and integration testing

-- Table: epic_validation_results
-- Stores results of epic validation attempts
CREATE TABLE IF NOT EXISTS epic_validation_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    epic_id INTEGER NOT NULL REFERENCES epics(id) ON DELETE CASCADE,
    session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,

    -- Validation status
    status VARCHAR(50) NOT NULL CHECK (status IN (
        'pending', 'running', 'passed', 'failed', 'partial', 'manual_review'
    )),

    -- Task validation summary
    total_tasks INTEGER NOT NULL DEFAULT 0,
    tasks_verified INTEGER NOT NULL DEFAULT 0,
    tasks_failed INTEGER NOT NULL DEFAULT 0,
    tasks_skipped INTEGER NOT NULL DEFAULT 0,

    -- Integration test results
    integration_tests_run INTEGER NOT NULL DEFAULT 0,
    integration_tests_passed INTEGER NOT NULL DEFAULT 0,
    integration_tests_failed INTEGER NOT NULL DEFAULT 0,

    -- Acceptance criteria
    acceptance_criteria_met BOOLEAN DEFAULT FALSE,
    acceptance_criteria_details JSONB,

    -- Failure analysis
    failure_analysis JSONB,
    rework_tasks_created INTEGER DEFAULT 0,

    -- Performance
    duration_seconds NUMERIC(10, 2),

    -- Timestamps
    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Index for quick lookups
CREATE INDEX idx_epic_validation_epic_id ON epic_validation_results(epic_id);
CREATE INDEX idx_epic_validation_session_id ON epic_validation_results(session_id);
CREATE INDEX idx_epic_validation_status ON epic_validation_results(status);
CREATE INDEX idx_epic_validation_started_at ON epic_validation_results(started_at DESC);

-- Table: epic_integration_tests
-- Stores integration tests generated for epic validation
CREATE TABLE IF NOT EXISTS epic_integration_tests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    epic_id INTEGER NOT NULL REFERENCES epics(id) ON DELETE CASCADE,
    validation_id UUID REFERENCES epic_validation_results(id) ON DELETE CASCADE,

    -- Test information
    test_name VARCHAR(255) NOT NULL,
    test_description TEXT,
    test_scope VARCHAR(50) CHECK (test_scope IN (
        'data_flow', 'api_integration', 'ui_integration', 'system_behavior', 'performance'
    )),

    -- Tasks involved
    task_ids INTEGER[],

    -- Test code
    test_code TEXT NOT NULL,
    file_path TEXT,

    -- Dependencies and configuration
    dependencies TEXT[],
    timeout_seconds INTEGER DEFAULT 60,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Index for quick lookups
CREATE INDEX idx_epic_integration_tests_epic_id ON epic_integration_tests(epic_id);
CREATE INDEX idx_epic_integration_tests_validation_id ON epic_integration_tests(validation_id);

-- Table: epic_rework_tasks
-- Stores rework tasks created when epic validation fails
CREATE TABLE IF NOT EXISTS epic_rework_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    epic_id INTEGER NOT NULL REFERENCES epics(id) ON DELETE CASCADE,
    validation_id UUID NOT NULL REFERENCES epic_validation_results(id) ON DELETE CASCADE,
    original_task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    rework_task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,

    -- Rework information
    failure_reason TEXT NOT NULL,
    rework_type VARCHAR(50) CHECK (rework_type IN (
        'bug_fix', 'missing_functionality', 'integration_issue', 'performance_issue', 'test_fix'
    )),
    priority INTEGER NOT NULL DEFAULT 1,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Index for quick lookups
CREATE INDEX idx_epic_rework_epic_id ON epic_rework_tasks(epic_id);
CREATE INDEX idx_epic_rework_validation_id ON epic_rework_tasks(validation_id);
CREATE INDEX idx_epic_rework_task_id ON epic_rework_tasks(rework_task_id);

-- Table: epic_dependencies
-- Tracks dependencies between epics for validation ordering
CREATE TABLE IF NOT EXISTS epic_dependencies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    epic_id INTEGER NOT NULL REFERENCES epics(id) ON DELETE CASCADE,
    depends_on_epic_id INTEGER NOT NULL REFERENCES epics(id) ON DELETE CASCADE,
    dependency_type VARCHAR(50) CHECK (dependency_type IN (
        'data', 'api', 'functionality', 'infrastructure'
    )),

    -- Validation requirements
    must_validate_first BOOLEAN DEFAULT TRUE,
    validation_order INTEGER,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    UNIQUE(epic_id, depends_on_epic_id),
    CHECK(epic_id != depends_on_epic_id),

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Index for dependency lookups
CREATE INDEX idx_epic_dependencies_epic_id ON epic_dependencies(epic_id);
CREATE INDEX idx_epic_dependencies_depends_on ON epic_dependencies(depends_on_epic_id);

-- Add validation columns to epics table
ALTER TABLE epics ADD COLUMN IF NOT EXISTS validated BOOLEAN DEFAULT FALSE;
ALTER TABLE epics ADD COLUMN IF NOT EXISTS validated_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE epics ADD COLUMN IF NOT EXISTS validation_status VARCHAR(50);
ALTER TABLE epics ADD COLUMN IF NOT EXISTS acceptance_criteria JSONB DEFAULT '[]'::jsonb;

-- View: Current epic validation status
CREATE OR REPLACE VIEW v_epic_validation_status AS
SELECT
    e.id AS epic_id,
    e.name AS epic_name,
    e.validated,
    e.validation_status,
    evr.status AS latest_validation_status,
    evr.total_tasks,
    evr.tasks_verified,
    evr.tasks_failed,
    evr.integration_tests_passed,
    evr.integration_tests_failed,
    evr.acceptance_criteria_met,
    evr.rework_tasks_created,
    evr.duration_seconds,
    evr.started_at AS last_validation_at,
    COUNT(DISTINCT ert.id) AS total_rework_tasks,
    array_agg(DISTINCT ed.depends_on_epic_id) FILTER (WHERE ed.depends_on_epic_id IS NOT NULL) AS depends_on_epics
FROM epics e
LEFT JOIN LATERAL (
    SELECT * FROM epic_validation_results
    WHERE epic_id = e.id
    ORDER BY started_at DESC
    LIMIT 1
) evr ON true
LEFT JOIN epic_rework_tasks ert ON ert.epic_id = e.id
LEFT JOIN epic_dependencies ed ON ed.epic_id = e.id
GROUP BY e.id, e.name, e.validated, e.validation_status,
         evr.status, evr.total_tasks, evr.tasks_verified, evr.tasks_failed,
         evr.integration_tests_passed, evr.integration_tests_failed,
         evr.acceptance_criteria_met, evr.rework_tasks_created,
         evr.duration_seconds, evr.started_at;

-- View: Epic validation dependency order
CREATE OR REPLACE VIEW v_epic_validation_order AS
WITH RECURSIVE epic_hierarchy AS (
    -- Base case: epics with no dependencies
    SELECT
        e.id,
        e.name,
        0 AS level,
        ARRAY[e.id] AS path,
        FALSE AS has_cycle
    FROM epics e
    WHERE NOT EXISTS (
        SELECT 1 FROM epic_dependencies ed
        WHERE ed.epic_id = e.id AND ed.must_validate_first = true
    )

    UNION ALL

    -- Recursive case: epics that depend on others
    SELECT
        e.id,
        e.name,
        eh.level + 1,
        eh.path || e.id,
        e.id = ANY(eh.path) AS has_cycle
    FROM epics e
    JOIN epic_dependencies ed ON ed.epic_id = e.id
    JOIN epic_hierarchy eh ON eh.id = ed.depends_on_epic_id
    WHERE ed.must_validate_first = true
        AND NOT eh.has_cycle
)
SELECT
    id AS epic_id,
    name AS epic_name,
    MAX(level) AS validation_level,
    array_agg(DISTINCT path ORDER BY array_length(path, 1) DESC) AS dependency_paths,
    bool_or(has_cycle) AS has_circular_dependency
FROM epic_hierarchy
GROUP BY id, name
ORDER BY MAX(level), id;

-- View: Epic validation success metrics
CREATE OR REPLACE VIEW v_epic_validation_metrics AS
SELECT
    e.project_id,
    COUNT(DISTINCT e.id) AS total_epics,
    COUNT(DISTINCT e.id) FILTER (WHERE e.validated) AS validated_epics,
    COUNT(DISTINCT evr.id) AS total_validations,
    COUNT(DISTINCT evr.id) FILTER (WHERE evr.status = 'passed') AS passed_validations,
    COUNT(DISTINCT evr.id) FILTER (WHERE evr.status = 'failed') AS failed_validations,
    AVG(evr.tasks_verified::NUMERIC / NULLIF(evr.total_tasks, 0)) * 100 AS avg_task_verification_rate,
    AVG(evr.integration_tests_passed::NUMERIC / NULLIF(evr.integration_tests_run, 0)) * 100 AS avg_integration_pass_rate,
    SUM(evr.rework_tasks_created) AS total_rework_tasks,
    AVG(evr.duration_seconds) AS avg_validation_duration
FROM epics e
LEFT JOIN epic_validation_results evr ON evr.epic_id = e.id
GROUP BY e.project_id;

-- Function: Get next epic to validate
CREATE OR REPLACE FUNCTION get_next_epic_to_validate(p_project_id UUID)
RETURNS TABLE (
    epic_id INTEGER,
    epic_name VARCHAR,
    validation_level INTEGER,
    dependencies_validated BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    WITH epic_status AS (
        SELECT
            e.id,
            e.name,
            e.validated,
            evo.validation_level,
            -- Check if all dependencies are validated
            COALESCE(
                bool_and(dep_e.validated) FILTER (WHERE ed.must_validate_first),
                true
            ) AS dependencies_validated
        FROM epics e
        LEFT JOIN v_epic_validation_order evo ON evo.epic_id = e.id
        LEFT JOIN epic_dependencies ed ON ed.epic_id = e.id
        LEFT JOIN epics dep_e ON dep_e.id = ed.depends_on_epic_id
        WHERE e.project_id = p_project_id
            AND NOT e.validated
            AND NOT COALESCE(evo.has_circular_dependency, false)
        GROUP BY e.id, e.name, e.validated, evo.validation_level
    )
    SELECT
        es.id AS epic_id,
        es.name AS epic_name,
        COALESCE(es.validation_level, 0) AS validation_level,
        es.dependencies_validated
    FROM epic_status es
    WHERE es.dependencies_validated
    ORDER BY COALESCE(es.validation_level, 0), es.id
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- Function: Mark epic as validated
CREATE OR REPLACE FUNCTION mark_epic_validated(
    p_epic_id INTEGER,
    p_validation_id UUID,
    p_session_id UUID DEFAULT NULL
)
RETURNS BOOLEAN AS $$
DECLARE
    v_status VARCHAR(50);
    v_criteria_met BOOLEAN;
BEGIN
    -- Get validation results
    SELECT status, acceptance_criteria_met
    INTO v_status, v_criteria_met
    FROM epic_validation_results
    WHERE id = p_validation_id AND epic_id = p_epic_id;

    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    -- Update epic
    UPDATE epics
    SET validated = (v_status = 'passed' AND v_criteria_met),
        validated_at = CASE
            WHEN v_status = 'passed' AND v_criteria_met THEN CURRENT_TIMESTAMP
            ELSE NULL
        END,
        validation_status = v_status
    WHERE id = p_epic_id;

    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

-- Function: Create epic rework tasks
CREATE OR REPLACE FUNCTION create_epic_rework_task(
    p_epic_id INTEGER,
    p_validation_id UUID,
    p_original_task_id INTEGER,
    p_description TEXT,
    p_action TEXT,
    p_failure_reason TEXT,
    p_rework_type VARCHAR(50),
    p_priority INTEGER DEFAULT 1
)
RETURNS INTEGER AS $$
DECLARE
    v_new_task_id INTEGER;
BEGIN
    -- Create new task
    INSERT INTO tasks (
        epic_id,
        description,
        action,
        priority,
        done,
        verified,
        needs_review,
        review_reason
    ) VALUES (
        p_epic_id,
        'REWORK: ' || p_description,
        p_action,
        p_priority,
        FALSE,
        FALSE,
        TRUE,
        'Auto-generated rework task from epic validation failure: ' || p_failure_reason
    ) RETURNING id INTO v_new_task_id;

    -- Record rework task
    INSERT INTO epic_rework_tasks (
        epic_id,
        validation_id,
        original_task_id,
        rework_task_id,
        failure_reason,
        rework_type,
        priority
    ) VALUES (
        p_epic_id,
        p_validation_id,
        p_original_task_id,
        v_new_task_id,
        p_failure_reason,
        p_rework_type,
        p_priority
    );

    RETURN v_new_task_id;
END;
$$ LANGUAGE plpgsql;

-- Comments for documentation
COMMENT ON TABLE epic_validation_results IS 'Stores results of epic-level validation and integration testing';
COMMENT ON TABLE epic_integration_tests IS 'Integration tests generated for epic validation';
COMMENT ON TABLE epic_rework_tasks IS 'Tracks rework tasks created from epic validation failures';
COMMENT ON TABLE epic_dependencies IS 'Dependencies between epics for validation ordering';
COMMENT ON VIEW v_epic_validation_status IS 'Current validation status for all epics';
COMMENT ON VIEW v_epic_validation_order IS 'Optimal order for validating epics based on dependencies';
COMMENT ON VIEW v_epic_validation_metrics IS 'Aggregate metrics for epic validation';
COMMENT ON FUNCTION get_next_epic_to_validate IS 'Returns the next epic that should be validated';
COMMENT ON FUNCTION mark_epic_validated IS 'Marks an epic as validated based on validation results';
COMMENT ON FUNCTION create_epic_rework_task IS 'Creates a new rework task when epic validation fails';-- Quality Gates System Tables
-- ============================
-- Adds support for quality gate enforcement and automatic rework creation

-- Table: quality_gate_results
-- Stores results of quality gate checks
CREATE TABLE IF NOT EXISTS quality_gate_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id VARCHAR(50) NOT NULL,  -- Task/Epic ID
    entity_type VARCHAR(20) NOT NULL CHECK (entity_type IN ('task', 'epic', 'project')),
    gate_type VARCHAR(20) NOT NULL CHECK (gate_type IN (
        'task', 'epic', 'review', 'integration', 'performance'
    )),

    -- Gate results
    status VARCHAR(20) NOT NULL CHECK (status IN (
        'passed', 'failed', 'warning', 'manual_review', 'skipped'
    )),
    score NUMERIC(3, 2) CHECK (score >= 0 AND score <= 1),

    -- Check details (JSON arrays)
    passed_checks JSONB DEFAULT '[]'::jsonb,
    failed_checks JSONB DEFAULT '[]'::jsonb,
    warnings JSONB DEFAULT '[]'::jsonb,
    improvements JSONB DEFAULT '[]'::jsonb,

    -- Session tracking
    session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Index for quick lookups
CREATE INDEX idx_quality_gate_entity ON quality_gate_results(entity_id, entity_type);
CREATE INDEX idx_quality_gate_session ON quality_gate_results(session_id);
CREATE INDEX idx_quality_gate_status ON quality_gate_results(status);
CREATE INDEX idx_quality_gate_created ON quality_gate_results(created_at DESC);

-- Table: quality_gate_tasks
-- Links quality gate failures to rework tasks
CREATE TABLE IF NOT EXISTS quality_gate_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    original_entity_id VARCHAR(50) NOT NULL,
    entity_type VARCHAR(20) NOT NULL,
    gate_type VARCHAR(50) NOT NULL,

    -- Issue details
    issue TEXT NOT NULL,
    priority INTEGER DEFAULT 3,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP WITH TIME ZONE,

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Index for relationships
CREATE INDEX idx_quality_gate_tasks_task ON quality_gate_tasks(task_id);
CREATE INDEX idx_quality_gate_tasks_entity ON quality_gate_tasks(original_entity_id);

-- Table: improvement_suggestions
-- Auto-generated improvement suggestions
CREATE TABLE IF NOT EXISTS improvement_suggestions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id VARCHAR(50) NOT NULL,
    entity_type VARCHAR(20) NOT NULL,
    session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,

    -- Suggestion details
    category VARCHAR(50) CHECK (category IN (
        'code_quality', 'testing', 'documentation', 'performance', 'security', 'architecture'
    )),
    priority INTEGER CHECK (priority >= 1 AND priority <= 5),
    issue TEXT NOT NULL,
    suggestion TEXT NOT NULL,
    action TEXT NOT NULL,
    example TEXT,
    reference_links TEXT[],
    estimated_effort VARCHAR(50),

    -- Implementation tracking
    implemented BOOLEAN DEFAULT FALSE,
    implemented_at TIMESTAMP WITH TIME ZONE,
    implementation_task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Index for lookups
CREATE INDEX idx_improvement_entity ON improvement_suggestions(entity_id, entity_type);
CREATE INDEX idx_improvement_category ON improvement_suggestions(category);
CREATE INDEX idx_improvement_priority ON improvement_suggestions(priority);
CREATE INDEX idx_improvement_implemented ON improvement_suggestions(implemented);

-- View: Current quality gate status for all tasks
CREATE OR REPLACE VIEW v_quality_gate_status AS
SELECT
    t.id AS task_id,
    t.description AS task_description,
    t.epic_id,
    e.name AS epic_name,
    t.verified,
    qg.status AS latest_gate_status,
    qg.score AS latest_gate_score,
    qg.gate_type,
    qg.failed_checks,
    qg.warnings,
    COUNT(qgt.id) AS rework_tasks_created,
    qg.created_at AS last_checked_at
FROM tasks t
JOIN epics e ON e.id = t.epic_id
LEFT JOIN LATERAL (
    SELECT * FROM quality_gate_results
    WHERE entity_id = t.id::text AND entity_type = 'task'
    ORDER BY created_at DESC
    LIMIT 1
) qg ON true
LEFT JOIN quality_gate_tasks qgt ON qgt.original_entity_id = t.id::text
GROUP BY t.id, t.description, t.epic_id, e.name, t.verified,
         qg.status, qg.score, qg.gate_type, qg.failed_checks,
         qg.warnings, qg.created_at;

-- View: Quality metrics by epic
CREATE OR REPLACE VIEW v_epic_quality_metrics AS
SELECT
    e.id AS epic_id,
    e.name AS epic_name,
    COUNT(DISTINCT t.id) AS total_tasks,
    COUNT(DISTINCT t.id) FILTER (WHERE t.verified) AS verified_tasks,
    COUNT(DISTINCT qg.id) AS quality_checks_run,
    COUNT(DISTINCT qg.id) FILTER (WHERE qg.status = 'passed') AS checks_passed,
    COUNT(DISTINCT qg.id) FILTER (WHERE qg.status = 'failed') AS checks_failed,
    AVG(qg.score) AS avg_quality_score,
    COUNT(DISTINCT qgt.id) AS total_rework_tasks,
    COUNT(DISTINCT is_imp.id) AS improvement_suggestions,
    COUNT(DISTINCT is_imp.id) FILTER (WHERE is_imp.implemented) AS improvements_implemented
FROM epics e
LEFT JOIN tasks t ON t.epic_id = e.id
LEFT JOIN quality_gate_results qg ON qg.entity_id = t.id::text AND qg.entity_type = 'task'
LEFT JOIN quality_gate_tasks qgt ON qgt.original_entity_id = e.id::text
LEFT JOIN improvement_suggestions is_imp ON is_imp.entity_id = e.id::text
GROUP BY e.id, e.name;

-- View: Top improvement suggestions
CREATE OR REPLACE VIEW v_top_improvement_suggestions AS
SELECT
    category,
    priority,
    issue,
    suggestion,
    action,
    estimated_effort,
    COUNT(*) AS occurrence_count,
    COUNT(*) FILTER (WHERE implemented) AS times_implemented,
    CASE
        WHEN COUNT(*) FILTER (WHERE implemented) > 0 THEN
            COUNT(*) FILTER (WHERE implemented)::FLOAT / COUNT(*)
        ELSE 0
    END AS implementation_rate
FROM improvement_suggestions
GROUP BY category, priority, issue, suggestion, action, estimated_effort
ORDER BY priority, occurrence_count DESC;

-- Function: Get quality gate summary for a project
CREATE OR REPLACE FUNCTION get_project_quality_summary(p_project_id UUID)
RETURNS TABLE (
    total_gates_run INTEGER,
    gates_passed INTEGER,
    gates_failed INTEGER,
    avg_quality_score NUMERIC,
    total_rework_tasks INTEGER,
    total_improvements INTEGER,
    improvements_implemented INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(DISTINCT qg.id)::INTEGER AS total_gates_run,
        COUNT(DISTINCT qg.id) FILTER (WHERE qg.status = 'passed')::INTEGER AS gates_passed,
        COUNT(DISTINCT qg.id) FILTER (WHERE qg.status = 'failed')::INTEGER AS gates_failed,
        ROUND(AVG(qg.score), 2) AS avg_quality_score,
        COUNT(DISTINCT qgt.id)::INTEGER AS total_rework_tasks,
        COUNT(DISTINCT is_imp.id)::INTEGER AS total_improvements,
        COUNT(DISTINCT is_imp.id) FILTER (WHERE is_imp.implemented)::INTEGER AS improvements_implemented
    FROM sessions s
    JOIN quality_gate_results qg ON qg.session_id = s.id
    LEFT JOIN quality_gate_tasks qgt ON qgt.created_at >= s.started_at
    LEFT JOIN improvement_suggestions is_imp ON is_imp.session_id = s.id
    WHERE s.project_id = p_project_id;
END;
$$ LANGUAGE plpgsql;

-- Function: Create rework task from quality gate
CREATE OR REPLACE FUNCTION create_quality_rework_task(
    p_epic_id INTEGER,
    p_original_entity_id VARCHAR(50),
    p_entity_type VARCHAR(20),
    p_issue TEXT,
    p_action TEXT,
    p_priority INTEGER DEFAULT 3
)
RETURNS INTEGER AS $$
DECLARE
    v_task_id INTEGER;
BEGIN
    -- Create the rework task
    INSERT INTO tasks (
        epic_id,
        description,
        action,
        priority,
        done,
        verified,
        needs_review,
        review_reason
    ) VALUES (
        p_epic_id,
        'QUALITY: ' || p_issue,
        p_action,
        p_priority,
        FALSE,
        FALSE,
        TRUE,
        'Auto-generated from quality gate failure: ' || p_issue
    ) RETURNING id INTO v_task_id;

    -- Link to quality gate
    INSERT INTO quality_gate_tasks (
        task_id,
        original_entity_id,
        entity_type,
        gate_type,
        issue,
        priority
    ) VALUES (
        v_task_id,
        p_original_entity_id,
        p_entity_type,
        'quality_gate',
        p_issue,
        p_priority
    );

    RETURN v_task_id;
END;
$$ LANGUAGE plpgsql;

-- Function: Check if entity passes quality gates
CREATE OR REPLACE FUNCTION check_quality_gates(
    p_entity_id VARCHAR(50),
    p_entity_type VARCHAR(20),
    p_min_score NUMERIC DEFAULT 0.7
)
RETURNS BOOLEAN AS $$
DECLARE
    v_latest_score NUMERIC;
    v_latest_status VARCHAR(20);
BEGIN
    SELECT score, status
    INTO v_latest_score, v_latest_status
    FROM quality_gate_results
    WHERE entity_id = p_entity_id
      AND entity_type = p_entity_type
    ORDER BY created_at DESC
    LIMIT 1;

    IF NOT FOUND THEN
        RETURN FALSE; -- No quality check run
    END IF;

    RETURN v_latest_status IN ('passed', 'warning') AND v_latest_score >= p_min_score;
END;
$$ LANGUAGE plpgsql;

-- Comments for documentation
COMMENT ON TABLE quality_gate_results IS 'Stores results of quality gate checks for tasks, epics, and projects';
COMMENT ON TABLE quality_gate_tasks IS 'Links quality gate failures to automatically created rework tasks';
COMMENT ON TABLE improvement_suggestions IS 'Auto-generated improvement suggestions from quality analysis';
COMMENT ON VIEW v_quality_gate_status IS 'Current quality gate status for all tasks';
COMMENT ON VIEW v_epic_quality_metrics IS 'Aggregated quality metrics by epic';
COMMENT ON VIEW v_top_improvement_suggestions IS 'Most common improvement suggestions across the project';
COMMENT ON FUNCTION get_project_quality_summary IS 'Returns quality gate summary statistics for a project';
COMMENT ON FUNCTION create_quality_rework_task IS 'Creates a rework task when quality gates fail';
COMMENT ON FUNCTION check_quality_gates IS 'Checks if an entity passes quality gate requirements';-- ============================================================================
-- YokeFlow Task Verification System Schema
-- ============================================================================
-- Description: Database schema for storing task and epic verification results
-- Created: January 8, 2026
-- Version: 1.0.0
-- ============================================================================

-- Task verification results
-- Stores results of automated task verification including tests run, failures, and retry attempts
CREATE TABLE IF NOT EXISTS task_verifications (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,
    status VARCHAR(50) NOT NULL,  -- pending, running, passed, failed, retry, manual_review
    tests_run INTEGER NOT NULL DEFAULT 0,
    tests_passed INTEGER NOT NULL DEFAULT 0,
    tests_failed INTEGER NOT NULL DEFAULT 0,
    test_results JSONB,  -- Array of GeneratedTestResult objects
    failure_analysis JSONB,  -- FailureAnalysis data (root cause, suggested fix, etc.)
    retry_count INTEGER NOT NULL DEFAULT 0,
    duration_seconds FLOAT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    metadata JSONB,  -- Additional metadata (environment, config, etc.)
    CONSTRAINT valid_verification_status CHECK (status IN ('pending', 'running', 'passed', 'failed', 'retry', 'manual_review')),
    CONSTRAINT valid_test_counts CHECK (tests_run >= 0 AND tests_passed >= 0 AND tests_failed >= 0),
    CONSTRAINT valid_retry_count CHECK (retry_count >= 0)
);

-- Epic validation results
-- Stores results of epic-level validation including integration tests and acceptance criteria
CREATE TABLE IF NOT EXISTS epic_validations (
    id SERIAL PRIMARY KEY,
    epic_id INTEGER NOT NULL REFERENCES epics(id) ON DELETE CASCADE,
    session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,
    status VARCHAR(50) NOT NULL,  -- pending, running, passed, failed, partial, needs_rework
    total_tasks INTEGER NOT NULL DEFAULT 0,
    tasks_validated INTEGER NOT NULL DEFAULT 0,
    tasks_passed INTEGER NOT NULL DEFAULT 0,
    tasks_failed INTEGER NOT NULL DEFAULT 0,
    integration_tests_run INTEGER NOT NULL DEFAULT 0,
    integration_tests_passed INTEGER NOT NULL DEFAULT 0,
    integration_tests_failed INTEGER NOT NULL DEFAULT 0,
    acceptance_criteria_met BOOLEAN DEFAULT FALSE,
    acceptance_criteria JSONB,  -- Array of acceptance criteria strings
    failure_analysis JSONB,  -- Detailed failure analysis
    rework_tasks JSONB,  -- Array of tasks needing rework
    duration_seconds FLOAT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    metadata JSONB,  -- Additional metadata
    CONSTRAINT valid_epic_validation_status CHECK (status IN ('pending', 'running', 'passed', 'failed', 'partial', 'needs_rework')),
    CONSTRAINT valid_task_counts CHECK (total_tasks >= 0 AND tasks_validated >= 0 AND tasks_passed >= 0 AND tasks_failed >= 0),
    CONSTRAINT valid_integration_test_counts CHECK (integration_tests_run >= 0 AND integration_tests_passed >= 0 AND integration_tests_failed >= 0)
);

-- Generated tests catalog
-- Stores all tests that have been automatically generated for tasks
CREATE TABLE IF NOT EXISTS generated_tests (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    verification_id INTEGER REFERENCES task_verifications(id) ON DELETE SET NULL,
    test_type VARCHAR(50) NOT NULL,  -- unit, integration, e2e, browser, api, validation
    description TEXT NOT NULL,
    file_path TEXT NOT NULL,
    test_code TEXT NOT NULL,
    dependencies JSONB,  -- Array of dependency strings (e.g., ["pytest", "playwright"])
    timeout_seconds INTEGER DEFAULT 30,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_run TIMESTAMP WITH TIME ZONE,
    last_result BOOLEAN,  -- True if passed, False if failed, NULL if not run
    last_error TEXT,  -- Error message from last failed run
    run_count INTEGER DEFAULT 0,  -- Number of times this test has been run
    success_count INTEGER DEFAULT 0,  -- Number of successful runs
    metadata JSONB,  -- Additional metadata
    CONSTRAINT valid_test_type CHECK (test_type IN ('unit', 'integration', 'e2e', 'browser', 'api', 'validation')),
    CONSTRAINT valid_timeout CHECK (timeout_seconds > 0),
    CONSTRAINT valid_run_counts CHECK (run_count >= 0 AND success_count >= 0 AND success_count <= run_count)
);

-- Verification history for tracking changes over time
-- Useful for analyzing verification trends and identifying patterns
CREATE TABLE IF NOT EXISTS verification_history (
    id SERIAL PRIMARY KEY,
    verification_id INTEGER NOT NULL REFERENCES task_verifications(id) ON DELETE CASCADE,
    action VARCHAR(50) NOT NULL,  -- created, started, completed, retry_attempted, failed, passed
    status_before VARCHAR(50),
    status_after VARCHAR(50),
    details JSONB,  -- Additional details about the action
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT valid_verification_action CHECK (action IN ('created', 'started', 'completed', 'retry_attempted', 'failed', 'passed', 'manual_review_requested'))
);

-- ============================================================================
-- Indexes for Performance
-- ============================================================================

-- Task verifications indexes
CREATE INDEX IF NOT EXISTS idx_task_verifications_task_id ON task_verifications(task_id);
CREATE INDEX IF NOT EXISTS idx_task_verifications_session_id ON task_verifications(session_id);
CREATE INDEX IF NOT EXISTS idx_task_verifications_status ON task_verifications(status);
CREATE INDEX IF NOT EXISTS idx_task_verifications_created_at ON task_verifications(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_task_verifications_completed_at ON task_verifications(completed_at DESC) WHERE completed_at IS NOT NULL;

-- Epic validations indexes
CREATE INDEX IF NOT EXISTS idx_epic_validations_epic_id ON epic_validations(epic_id);
CREATE INDEX IF NOT EXISTS idx_epic_validations_session_id ON epic_validations(session_id);
CREATE INDEX IF NOT EXISTS idx_epic_validations_status ON epic_validations(status);
CREATE INDEX IF NOT EXISTS idx_epic_validations_created_at ON epic_validations(created_at DESC);

-- Generated tests indexes
CREATE INDEX IF NOT EXISTS idx_generated_tests_task_id ON generated_tests(task_id);
CREATE INDEX IF NOT EXISTS idx_generated_tests_verification_id ON generated_tests(verification_id);
CREATE INDEX IF NOT EXISTS idx_generated_tests_test_type ON generated_tests(test_type);
CREATE INDEX IF NOT EXISTS idx_generated_tests_last_run ON generated_tests(last_run DESC) WHERE last_run IS NOT NULL;

-- Verification history indexes
CREATE INDEX IF NOT EXISTS idx_verification_history_verification_id ON verification_history(verification_id);
CREATE INDEX IF NOT EXISTS idx_verification_history_created_at ON verification_history(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_verification_history_action ON verification_history(action);

-- ============================================================================
-- Views for Common Queries
-- ============================================================================

-- Latest verification result for each task
CREATE OR REPLACE VIEW v_latest_task_verifications AS
SELECT DISTINCT ON (task_id)
    tv.id,
    tv.task_id,
    t.name as task_name,
    tv.session_id,
    tv.status,
    tv.tests_run,
    tv.tests_passed,
    tv.tests_failed,
    tv.retry_count,
    tv.duration_seconds,
    tv.created_at,
    tv.completed_at,
    tv.failure_analysis
FROM task_verifications tv
JOIN tasks t ON tv.task_id = t.id
ORDER BY tv.task_id, tv.created_at DESC;

-- Overall verification statistics
CREATE OR REPLACE VIEW v_verification_statistics AS
SELECT
    COUNT(*) as total_verifications,
    SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as passed,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
    SUM(CASE WHEN status = 'manual_review' THEN 1 ELSE 0 END) as manual_review,
    AVG(tests_run) as avg_tests_per_task,
    AVG(CASE WHEN tests_run > 0 THEN tests_passed::float / tests_run ELSE 0 END) as avg_pass_rate,
    AVG(duration_seconds) as avg_duration_seconds,
    AVG(retry_count) as avg_retry_count,
    MAX(retry_count) as max_retry_count
FROM task_verifications
WHERE completed_at IS NOT NULL;

-- Epic validation summary
CREATE OR REPLACE VIEW v_epic_validation_summary AS
SELECT
    ev.id,
    ev.epic_id,
    e.name as epic_name,
    ev.status,
    ev.total_tasks,
    ev.tasks_validated,
    ev.tasks_passed,
    ev.tasks_failed,
    ev.integration_tests_run,
    ev.integration_tests_passed,
    ev.integration_tests_failed,
    ev.acceptance_criteria_met,
    ev.duration_seconds,
    ev.created_at,
    ev.completed_at,
    CASE
        WHEN ev.total_tasks > 0 THEN (ev.tasks_passed::float / ev.total_tasks * 100)
        ELSE 0
    END as task_pass_percentage,
    CASE
        WHEN ev.integration_tests_run > 0 THEN (ev.integration_tests_passed::float / ev.integration_tests_run * 100)
        ELSE 0
    END as integration_test_pass_percentage
FROM epic_validations ev
JOIN epics e ON ev.epic_id = e.id
ORDER BY ev.created_at DESC;

-- Test generation statistics by type
CREATE OR REPLACE VIEW v_test_generation_stats AS
SELECT
    test_type,
    COUNT(*) as total_tests,
    COUNT(CASE WHEN last_result = true THEN 1 END) as successful_tests,
    COUNT(CASE WHEN last_result = false THEN 1 END) as failed_tests,
    COUNT(CASE WHEN last_result IS NULL THEN 1 END) as not_run_tests,
    AVG(run_count) as avg_run_count,
    SUM(run_count) as total_runs,
    SUM(success_count) as total_successes,
    CASE
        WHEN SUM(run_count) > 0 THEN (SUM(success_count)::float / SUM(run_count) * 100)
        ELSE 0
    END as overall_success_rate
FROM generated_tests
GROUP BY test_type
ORDER BY test_type;

-- Recent verification activity (last 7 days)
CREATE OR REPLACE VIEW v_recent_verification_activity AS
SELECT
    DATE(tv.created_at) as date,
    COUNT(*) as total_verifications,
    SUM(CASE WHEN tv.status = 'passed' THEN 1 ELSE 0 END) as passed,
    SUM(CASE WHEN tv.status = 'failed' THEN 1 ELSE 0 END) as failed,
    AVG(tv.tests_run) as avg_tests_run,
    AVG(tv.duration_seconds) as avg_duration_seconds
FROM task_verifications tv
WHERE tv.created_at >= NOW() - INTERVAL '7 days'
GROUP BY DATE(tv.created_at)
ORDER BY DATE(tv.created_at) DESC;

-- Tasks requiring manual review
CREATE OR REPLACE VIEW v_tasks_requiring_review AS
SELECT
    t.id as task_id,
    t.name as task_name,
    t.epic_id,
    e.name as epic_name,
    tv.id as verification_id,
    tv.status,
    tv.retry_count,
    tv.tests_run,
    tv.tests_passed,
    tv.tests_failed,
    tv.failure_analysis,
    tv.created_at as verification_created_at,
    tv.completed_at as verification_completed_at
FROM task_verifications tv
JOIN tasks t ON tv.task_id = t.id
LEFT JOIN epics e ON t.epic_id = e.id
WHERE tv.status = 'manual_review'
    AND tv.id = (
        SELECT id
        FROM task_verifications tv2
        WHERE tv2.task_id = tv.task_id
        ORDER BY created_at DESC
        LIMIT 1
    )
ORDER BY tv.created_at DESC;

-- ============================================================================
-- Helper Functions
-- ============================================================================

-- Function to get verification pass rate for a project
CREATE OR REPLACE FUNCTION get_verification_pass_rate(p_project_id UUID)
RETURNS FLOAT AS $$
DECLARE
    pass_rate FLOAT;
BEGIN
    SELECT
        CASE
            WHEN COUNT(*) > 0 THEN
                (COUNT(CASE WHEN tv.status = 'passed' THEN 1 END)::float / COUNT(*) * 100)
            ELSE 0
        END
    INTO pass_rate
    FROM task_verifications tv
    JOIN tasks t ON tv.task_id = t.id
    WHERE t.project_id = p_project_id
        AND tv.completed_at IS NOT NULL;

    RETURN pass_rate;
END;
$$ LANGUAGE plpgsql;

-- Function to get average retry count for a project
CREATE OR REPLACE FUNCTION get_avg_retry_count(p_project_id UUID)
RETURNS FLOAT AS $$
DECLARE
    avg_retries FLOAT;
BEGIN
    SELECT AVG(tv.retry_count)
    INTO avg_retries
    FROM task_verifications tv
    JOIN tasks t ON tv.task_id = t.id
    WHERE t.project_id = p_project_id
        AND tv.completed_at IS NOT NULL;

    RETURN COALESCE(avg_retries, 0);
END;
$$ LANGUAGE plpgsql;

-- Function to mark verification as requiring manual review
CREATE OR REPLACE FUNCTION mark_verification_for_manual_review(p_verification_id INTEGER, p_reason TEXT)
RETURNS VOID AS $$
BEGIN
    UPDATE task_verifications
    SET status = 'manual_review',
        metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object('manual_review_reason', p_reason, 'manual_review_requested_at', NOW())
    WHERE id = p_verification_id;

    -- Log to history
    INSERT INTO verification_history (verification_id, action, status_before, status_after, details)
    VALUES (
        p_verification_id,
        'manual_review_requested',
        (SELECT status FROM task_verifications WHERE id = p_verification_id),
        'manual_review',
        jsonb_build_object('reason', p_reason)
    );
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Comments for Documentation
-- ============================================================================

COMMENT ON TABLE task_verifications IS 'Stores results of automated task verification including tests run, pass/fail status, and retry attempts';
COMMENT ON TABLE epic_validations IS 'Stores results of epic-level validation including integration tests and acceptance criteria checks';
COMMENT ON TABLE generated_tests IS 'Catalog of all automatically generated tests with execution history';
COMMENT ON TABLE verification_history IS 'Audit trail of verification status changes and actions';

COMMENT ON VIEW v_latest_task_verifications IS 'Shows the most recent verification result for each task';
COMMENT ON VIEW v_verification_statistics IS 'Aggregated statistics across all verifications';
COMMENT ON VIEW v_epic_validation_summary IS 'Summary of epic validation results with pass percentages';
COMMENT ON VIEW v_test_generation_stats IS 'Statistics on generated tests by type';
COMMENT ON VIEW v_recent_verification_activity IS 'Verification activity over the last 7 days';
COMMENT ON VIEW v_tasks_requiring_review IS 'Tasks that have been marked for manual review';

COMMENT ON FUNCTION get_verification_pass_rate IS 'Calculates the verification pass rate for a given project';
COMMENT ON FUNCTION get_avg_retry_count IS 'Calculates the average retry count for verifications in a project';
COMMENT ON FUNCTION mark_verification_for_manual_review IS 'Marks a verification as requiring manual review with a reason';

-- ============================================================================
-- Grants (adjust as needed for your security model)
-- ============================================================================

-- Grant permissions to application role (adjust role name as needed)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON task_verifications TO yokeflow_app;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON epic_validations TO yokeflow_app;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON generated_tests TO yokeflow_app;
-- GRANT SELECT, INSERT ON verification_history TO yokeflow_app;
-- GRANT SELECT ON v_latest_task_verifications TO yokeflow_app;
-- GRANT SELECT ON v_verification_statistics TO yokeflow_app;
-- GRANT SELECT ON v_epic_validation_summary TO yokeflow_app;
-- GRANT SELECT ON v_test_generation_stats TO yokeflow_app;
-- GRANT SELECT ON v_recent_verification_activity TO yokeflow_app;
-- GRANT SELECT ON v_tasks_requiring_review TO yokeflow_app;
-- GRANT EXECUTE ON FUNCTION get_verification_pass_rate TO yokeflow_app;
-- GRANT EXECUTE ON FUNCTION get_avg_retry_count TO yokeflow_app;
-- GRANT EXECUTE ON FUNCTION mark_verification_for_manual_review TO yokeflow_app;

-- ============================================================================
-- End of Schema
-- ============================================================================
