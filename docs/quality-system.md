# YokeFlow Quality System

**Last Updated:** January 12, 2026
**Version:** 2.0.1

---

## Overview

YokeFlow's quality system ensures high-quality code generation through four integrated subsystems that work together throughout the development lifecycle:

1. **Intervention System** - Real-time monitoring and error prevention during sessions
2. **Verification System** - Test-driven task completion validation
3. **Review System** - Quality assessment and recommendation generation
4. **Prompt Improvement** - Aggregation and application of improvements

Each subsystem addresses specific quality concerns while feeding information to the others, creating a comprehensive quality assurance pipeline.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Agent Coding Session                         │
└────────────┬────────────────────────┬────────────────────┬─────────┘
             │                        │                      │
             ▼                        ▼                      ▼
┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────┐
│  Intervention       │  │  Verification        │  │  Task Tracking   │
│  (Real-time)        │  │  (Task completion)   │  │  (Progress)      │
│  - Retry tracking   │  │  - Test generation   │  │  - File changes  │
│  - Error detection  │  │  - Test execution    │  │  - Tool usage    │
│  - Pattern analysis │  │  - Retry logic       │  │  - Metrics       │
└─────────┬───────────┘  └──────────┬──────────┘  └────────┬────────┘
          │                         │                       │
          └─────────────────────────┼───────────────────────┘
                                   │
                           Session Complete
                                   │
                                   ▼
                    ┌──────────────────────────┐
                    │   Review System          │
                    │   Phase 1: Quick Check   │
                    │   (Every session)        │
                    └──────────┬───────────────┘
                               │
                               ▼
                    ┌──────────────────────────┐
                    │   Review System          │
                    │   Phase 2: Deep Review   │
                    │   (Triggered by quality) │
                    └──────────┬───────────────┘
                               │
                               ▼
                    ┌──────────────────────────┐
                    │   Prompt Improvement     │
                    │   (Aggregate & Apply)    │
                    └──────────────────────────┘
```

---

## 1. Intervention System

**Purpose:** Prevent infinite loops, detect critical errors, and pause sessions when human intervention is needed.

### Features

- **Retry Tracking** - Monitors repeated command executions, blocks after threshold
- **Critical Error Detection** - Identifies infrastructure blockers (DB failures, missing deps)
- **Quality Pattern Detection** - Catches verification mismatches and tool misuse
- **Webhook Notifications** - Alerts via Slack/Discord when intervention needed
- **Pause/Resume** - Sessions can be paused for fixes and resumed later

### Configuration

```yaml
intervention:
  enabled: true
  max_retries: 3
  error_rate_threshold: 0.15
  session_duration_limit: 600
  detect_infrastructure_errors: true
  webhook_url: "https://hooks.slack.com/..."
```

### Database Tables

- `paused_sessions` - Tracks paused session state
- `intervention_actions` - Audit trail of intervention actions
- `notification_preferences` - Per-project notification settings

### When It Triggers

1. Command attempted >3 times (configurable)
2. Error rate exceeds 15%
3. Session duration >10 minutes on same task
4. Critical infrastructure errors detected
5. Quality violations (UI task without browser verification)

### Quality Pattern Detection (New in v2.0.1)

The intervention system now includes advanced quality pattern detection through the `QualityPatternDetector` class:

**Features:**
- **Task Type Inference** - Automatically detects UI, API, Database, Config, or Integration tasks
- **Tool Misuse Detection** - Catches incorrect tool usage (e.g., bash for file operations)
- **Verification Tracking** - Monitors verification attempts and detects abandonment
- **Quality Scoring** - Real-time quality score (0-10) with intervention at <3
- **Error Recovery Analysis** - Tracks how errors are handled

**Quality Rules Enforced:**
- UI tasks MUST have browser verification before completion
- Config tasks should use build verification, not browser tests
- Tool misuse triggers intervention after 10 incorrect uses
- Verification abandonment blocked after 5 failed attempts

**Configuration:**
```yaml
quality_detection:
  enabled: true
  ui_browser_required: true
  tool_misuse_threshold: 10
  verification_abandonment_limit: 5
  min_quality_score: 3
```

---

## 2. Verification System

**Purpose:** Ensure every completed task passes automated tests before being marked as done.

### Features

- **Automatic Test Generation** - Creates appropriate tests based on task type
- **Smart Task-Type Matching** - Analyzes task descriptions to select optimal test types
- **Retry Logic** - Up to 3 attempts with failure analysis
- **Epic Validation** - Integration testing across completed tasks
- **File Tracking** - Monitors which files were modified
- **Time Optimization** - 30-40% reduction in verification time through smart test selection

### Test Types by Task Category

| Task Type | Test Method | Time | Tools |
|-----------|------------|------|-------|
| UI | Browser (Playwright) | 3-5 min | Navigate, screenshot, interact |
| API | curl/fetch | 1-2 min | HTTP requests, status codes |
| Config | Build verification | 30 sec | Compilation, linting |
| Database | SQL queries | 1 min | Schema verification, CRUD |
| Integration | E2E Browser | 5-10 min | Complete workflows |

### Configuration

```yaml
verification:
  enabled: true
  auto_retry: true
  max_retries: 3
  test_timeout: 30
  generate_unit_tests: true
  generate_api_tests: true
  generate_browser_tests: true
  track_file_modifications: true
```

### Database Tables

- `task_verifications` - Verification results for each task
- `epic_validations` - Epic-level validation results
- `generated_tests` - Catalog of all generated tests
- `verification_history` - Audit trail

### Verification Flow

1. Agent completes task implementation
2. Verification intercepts before marking complete
3. Test generator analyzes task and creates appropriate tests
4. Tests execute with timeout
5. If passed → Task marked complete
6. If failed → Retry with failure analysis (up to 3x)
7. If still failing → Manual review required

---

## 3. Review System

**Purpose:** Assess session quality, identify patterns, and generate improvement recommendations.

### Phase 1: Quick Checks (Every Session)

**Cost:** $0 (no API calls)

Extracts metrics from session logs:
- Tool use count and error rate
- Browser verification usage
- Screenshot count
- Critical issues

Calculates quality rating (1-10) based on:
- Browser verification presence (critical for UI tasks)
- Error rate (<10% expected)
- Tool call presence

### Phase 2: Deep Reviews (Triggered)

**Cost:** ~$0.10 per review

Triggers when:
- Every 5th session (5, 10, 15, 20...)
- Quality drops below 7/10
- 5+ sessions since last review
- Project completion

Analyzes:
- Task verification compliance
- Error patterns and recovery
- Tool usage correctness
- Prompt adherence

Outputs:
- Overall rating with justification
- Structured recommendations (stored in JSONB)
- Human-readable markdown review

### Phase 3: Web UI Dashboard

Displays:
- Quality trends over time
- Session metrics and ratings
- Deep review reports
- Download options for reviews

### Phase 4: Prompt Improvement Analyzer

Aggregates recommendations across sessions:
- Groups by theme (browser_verification, docker_mode, testing, etc.)
- Deduplicates similar suggestions
- Calculates confidence scores
- Links evidence to specific sessions

### Database Tables

- `session_quality_checks` - Quick check metrics (Phase 1)
- `session_deep_reviews` - Deep review results with structured recommendations (Phase 2)
- `prompt_improvement_analyses` - Cross-project analyses (Phase 4)
- `prompt_proposals` - Individual improvement proposals (Phase 4)

---

## 4. Prompt Improvement System

**Purpose:** Aggregate recommendations from deep reviews and present actionable improvements.

### Current Architecture

```sql
-- Deep reviews store both human-readable and structured data
CREATE TABLE session_deep_reviews (
    review_text TEXT,                      -- Markdown for humans
    prompt_improvements JSONB DEFAULT '[]', -- Structured for aggregation
    ...
);
```

### Structured Recommendation Format

```json
{
  "title": "Add Task-Type Classification",
  "priority": "HIGH",
  "theme": "testing",
  "problem": "Agent used browser testing for config tasks",
  "current_text": "[Current prompt section...]",
  "proposed_text": "[Complete improved section...]",
  "impact": "Reduces wasted time by 50%",
  "confidence": 8
}
```

### Aggregation Process

1. Load structured recommendations from `prompt_improvements` JSONB
2. Group by theme using predefined categories
3. Calculate confidence based on frequency and session quality
4. Deduplicate identical proposals
5. Present prioritized list with evidence

### Themes for Categorization

- `browser_verification` - UI testing compliance
- `docker_mode` - Correct tool usage in containers
- `error_handling` - Recovery strategies
- `git_commits` - Version control practices
- `testing` - Test generation and execution
- `parallel_execution` - Concurrent operations
- `task_management` - Task/epic handling
- `prompt_adherence` - Following instructions

---

## Quality Metrics and Monitoring

### Key Performance Indicators

**Session Quality:**
- Average quality rating (target: 7+/10)
- Browser verification compliance (target: 100% for UI tasks)
- Error rate (target: <10%)

**Verification Success:**
- First-attempt pass rate (target: 80%+)
- Average retry count (target: <1.5)
- Manual review rate (target: <5%)

**Intervention Effectiveness:**
- Sessions paused for quality issues
- Average time to resolution
- Auto-resume success rate

### Database Views for Monitoring

```sql
-- Overall project quality
SELECT * FROM v_project_quality;

-- Recent quality issues
SELECT * FROM v_recent_quality_issues;

-- Verification statistics
SELECT * FROM v_verification_statistics;

-- Active interventions
SELECT * FROM v_active_interventions;
```

---

## Configuration Best Practices

### For Development/Prototyping

```yaml
intervention:
  enabled: true
  max_retries: 5  # More lenient

verification:
  enabled: false  # Speed over quality

review:
  deep_review_interval: 10  # Less frequent
```

### For Production Quality

```yaml
intervention:
  enabled: true
  max_retries: 3
  error_rate_threshold: 0.10  # Stricter

verification:
  enabled: true
  require_all_tests_pass: true
  min_test_coverage: 0.8

review:
  deep_review_interval: 5
  quality_threshold: 7
```

---

## Troubleshooting Guide

### Common Issues and Solutions

**Verification always fails:**
- Check test timeout settings
- Verify Docker sandbox configuration
- Ensure dependencies installed

**No deep reviews triggering:**
- Verify CLAUDE_CODE_OAUTH_TOKEN set
- Check trigger conditions in logs
- Confirm sessions completing successfully

**Prompt improvements empty:**
- Check `prompt_improvements` JSONB field populated
- Verify deep reviews generating recommendations
- Ensure structured format being used

**Too many false interventions:**
- Increase max_retries threshold
- Adjust error_rate_threshold
- Review blocked command patterns

---

## Future Enhancements

### Planned Improvements

1. **ML-based pattern detection** - Learn from historical data
2. **Automated prompt application** - Apply high-confidence changes automatically
3. **Cross-project analysis** - Learn from multiple projects
4. **A/B testing** - Compare prompt versions
5. **Real-time quality dashboard** - Live monitoring during sessions

### Integration Opportunities

- GitHub Actions for CI/CD integration
- Datadog/CloudWatch for metrics
- PagerDuty for critical alerts
- Jira for issue tracking

---

## Related Documentation

- [Configuration Guide](configuration.md) - Detailed configuration options
- [Database Schema](../schema/postgresql/) - Complete schema definitions
- [API Reference](api-usage.md) - REST API endpoints
- [Verification System](verification-system.md) - Detailed verification guide

---

**Key Insight:** Quality isn't just the absence of errors - it's using the right approach for each task type, following best practices, and continuously improving based on systematic analysis of outcomes.