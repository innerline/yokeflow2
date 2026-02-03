# Configuration File Guide

YokeFlow supports YAML configuration files for managing default settings. Configuration is primarily managed through the Web UI, but YAML files provide defaults.

**Version**: 2.1.0

## What's New in v2.1

YokeFlow 2.1 adds extensive configuration options for the quality system:

- **Review System**: Configure minimum reviews for prompt improvement analysis
- **Epic Testing**: Strict vs autonomous modes with critical epic patterns
- **Epic Re-testing**: Automated regression detection every N epics
- **Sandbox Configuration**: Docker and E2B cloud sandbox support
- **Testing Configuration**: Test execution tracking with error details and timing
- **Model Selection**: Separate models for reviews and prompt improvements

See [QUALITY_SYSTEM_SUMMARY.md](../QUALITY_SYSTEM_SUMMARY.md) for implementation details.

## Quick Start

1. **Copy the example config:**
   ```bash
   cp .yokeflow.yaml.example .yokeflow.yaml
   ```

2. **Edit settings** in `.yokeflow.yaml`

3. **Settings are used by:**
   - Web UI (for default model selections)
   - API endpoints
   - Utility scripts

## Configuration File Locations

The system looks for configuration files in this order:

1. **Current directory**: `.yokeflow.yaml`
   - Project-specific settings
   - Checked first

2. **Home directory**: `~/.yokeflow.yaml`
   - Global defaults for all projects
   - Checked if no local config exists

3. **Built-in defaults**
   - Used if no config file found
   - See [server/utils/config.py](../server/utils/config.py) for default values

**Note**: Web UI settings (selected during project creation) override config file defaults.

## Configuration Options

### Models

Control which Claude models are used for different session types:

```yaml
models:
  initializer: claude-opus-4-5-20251101        # For planning/initialization
  coding: claude-sonnet-4-5-20250929           # For implementation
  review: claude-sonnet-4-5-20250929           # For quality reviews (v2.1)
  prompt_improvement: claude-opus-4-5-20251101 # For prompt analysis (v2.1)
```

**Recommended:**
- **Opus** for initialization (better planning capabilities)
- **Sonnet** for coding (faster, more cost-effective)
- **Sonnet** for reviews (good analysis at lower cost)
- **Opus** for prompt improvements (critical reasoning task)

### Timing

Control delays and intervals:

```yaml
timing:
  auto_continue_delay: 3      # Seconds between sessions
  web_ui_poll_interval: 5     # Web UI refresh interval
  web_ui_port: 3000           # Web dashboard port (Next.js default)
```

### Security

Add custom blocked commands:

```yaml
security:
  additional_blocked_commands:
    - my-dangerous-script
    - custom-deploy-tool
```

These are added to the built-in blocklist in [server/utils/security.py](../server/utils/security.py).

### Review System (v2.1)

Configure the quality review and prompt improvement system:

```yaml
review:
  # Minimum deep reviews before running prompt improvement analysis
  min_reviews_for_analysis: 5  # Balance between speed and statistical significance
```

**Recommendations:**
- **3-5 reviews**: Faster insights, less statistical significance
- **10-15 reviews**: More robust patterns, requires more sessions

See [docs/quality-system.md](quality-system.md) for complete quality system documentation.

### Epic Testing (v2.1 - Phase 3)

Control how epic tests are handled when they fail:

```yaml
epic_testing:
  # Testing mode: "strict" or "autonomous"
  mode: autonomous  # Default: autonomous (recommended)

  # Critical epic patterns (block immediately in autonomous mode)
  critical_epics:
    - Authentication
    - Database
    - Payment
    - Security
    - Core API

  # Maximum failures before blocking (non-critical epics)
  auto_failure_tolerance: 3

  # Auto-create fix tasks for failures
  auto_create_fix_tasks: true

  # Send notification when blocked (strict mode)
  strict_notify_on_block: true
```

**Modes:**
- **Strict**: Block immediately on any epic test failure, require human intervention
- **Autonomous**: Continue on minor failures, block only on critical epics or >3 failures

**Critical Epics:**
- Epic names containing these substrings are considered critical
- Critical epics block immediately even in autonomous mode
- Customize based on your project's priorities

### Epic Re-testing (v2.1 - Phase 5)

Periodically re-test completed epics to catch regressions:

```yaml
epic_retesting:
  # Enable/disable epic re-testing system
  enabled: true

  # Trigger frequency: Re-test after every N completed epics
  trigger_frequency: 2  # After epic 3, 5, 7, 9, etc.

  # Foundation re-test interval (days)
  foundation_retest_days: 7  # Foundation epics tested more frequently

  # Maximum epics to re-test per trigger
  max_retests_per_trigger: 2

  # Prioritize foundation epics (database, auth, core API)
  prioritize_foundation: true

  # Prioritize epics with many dependents
  prioritize_dependents: true

  # Auto-pause session on critical regression
  pause_on_regression: false

  # Create rework tasks for failed re-tests
  auto_create_rework_tasks: true
```

**Strategy:**
- **Foundation epics**: Database, auth, core API - tested most frequently
- **High-dependency epics**: Epics with many dependents - tested regularly
- **Standard epics**: Tested less frequently
- **Smart selection**: Algorithm picks most important epics based on age, dependencies, and type

**Benefits:**
- Catches regressions within 2 epics of breaking change (instead of 10+ sessions)
- Stability scoring (0.00-1.00 scale) for reliability tracking
- Automatic regression detection comparing new vs previous results

See [QUALITY_SYSTEM_SUMMARY.md](../QUALITY_SYSTEM_SUMMARY.md) Phase 5 for implementation details.

### Verification (v2.0+)

**Note**: As of v2.1 (Phase 2), tests are created during initialization with executable `test_code` and run by the coding agent using MCP's `run_task_tests` before marking tasks complete. The configuration below represents future extensibility options.

Current behavior:
- Tests created during Session 0 (initialization)
- Tests executed automatically before task completion
- Test results tracked with error messages, execution time, and retry counts
- Epic test failure tracking for pattern analysis

Future configuration options (placeholders):
```yaml
testing:
  test_timeout: 30                    # Test timeout in seconds
  test_parallelization: true          # Run tests in parallel
  test_output_verbosity: normal       # normal, verbose, or quiet
```

**Test Execution System** (v2.1):
- Last error message captured for debugging
- Execution time tracked for performance analysis
- Retry count incremented automatically on failures
- Performance indexes for detecting slow/flaky tests

See [docs/quality-system.md](quality-system.md) for Phase 1-2 details.

### Project

Project-level settings:

```yaml
project:
  default_generations_dir: generations   # Where to store projects
  max_iterations: null                    # Default iteration limit (null = unlimited)
```

### Sandbox (v2.1)

Configure isolated execution environments for agent sessions:

```yaml
sandbox:
  # Sandbox type: "none", "docker", or "e2b"
  type: none  # Default: none (runs on host)

  # Docker-specific settings (when type: docker)
  docker_image: yokeflow-playwright:latest
  docker_network: bridge
  docker_memory_limit: 3g    # Increased for browser operations
  docker_cpu_limit: "2.0"

  # Port forwarding (optional - not needed if Playwright runs inside container)
  # docker_ports:
  #   - "5173:5173"  # Only for manual browser access during debugging

  # E2B-specific settings (when type: e2b)
  # e2b_api_key: ${E2B_API_KEY}  # Or set E2B_API_KEY environment variable
  # e2b_tier: pro                # "free" (1-hour) or "pro" (24-hour, $150/month)

docker:
  enabled: true
  image: yokeflow-playwright:latest
```

**Sandbox Types:**
- **none**: Runs directly on host (faster but can leak environment variables)
- **docker**: Local containers (good isolation, zero cost, unlimited duration)
- **e2b**: Cloud sandbox (production-ready, requires paid tier for long sessions)

**Docker with Playwright:**
- Use `yokeflow-playwright:latest` image for browser testing support
- Memory increased to 3g for headless Chromium
- Playwright runs inside container - no port forwarding needed
- See [docs/docker-sandbox-implementation.md](docker-sandbox-implementation.md) for setup

**E2B Cloud Sandbox:**
- Free tier: 1-hour session limit
- Pro tier: 24-hour limit, $150/month
- Good for production deployments
- Automatic cleanup and resource management

## Priority Order

Settings are applied in this order (highest priority first):

1. **Web UI selections** (when creating/initializing projects)
   - Model selection dropdowns
   - Project-specific settings

2. **Configuration file** (provides defaults)
   ```yaml
   models:
     initializer: claude-opus-4-5-20251101
     coding: claude-sonnet-4-5-20250929
   ```

3. **Built-in defaults** (fallback)
   ```python
   # From core/config.py
   initializer: "claude-opus-4-5-20251101"
   coding: "claude-sonnet-4-5-20250929"
   ```

## Examples

### Example 1: Basic Config

Create `.yokeflow.yaml` in current directory:

```yaml
models:
  initializer: claude-opus-4-5-20251101
  coding: claude-sonnet-4-5-20250929

timing:
  auto_continue_delay: 5  # Slower pace between sessions

project:
  default_generations_dir: generations
```

The Web UI will use these as defaults when creating new projects.

### Example 2: Global Config

Create `~/.yokeflow.yaml` for global defaults:

```yaml
models:
  initializer: claude-opus-4-5-20251101
  coding: claude-sonnet-4-5-20250929
```

These defaults apply to all projects on this machine.

### Example 3: Development vs Production

You can use different configs for different scenarios by placing them in different directories:

**Development** (`.yokeflow.yaml`):
```yaml
models:
  initializer: claude-opus-4-5-20251101
  coding: claude-sonnet-4-5-20250929  # Fast, cost-effective

timing:
  auto_continue_delay: 1  # Quick iteration
```

**Production** (`~/.yokeflow.yaml`):
```yaml
models:
  initializer: claude-opus-4-5-20251101
  coding: claude-opus-4-5-20251101  # Higher quality

timing:
  auto_continue_delay: 5  # Slower, more stable
```

### Example 4: Enable Quality System (v2.1)

Enable comprehensive quality monitoring with epic testing and re-testing:

```yaml
models:
  review: claude-sonnet-4-5-20250929
  prompt_improvement: claude-opus-4-5-20251101

review:
  min_reviews_for_analysis: 5

epic_testing:
  mode: autonomous
  critical_epics:
    - Authentication
    - Payment
  auto_failure_tolerance: 3
  auto_create_fix_tasks: true

epic_retesting:
  enabled: true
  trigger_frequency: 2
  foundation_retest_days: 7
  max_retests_per_trigger: 2
  auto_create_rework_tasks: true
```

This provides automated quality checks, regression detection, and intelligent test blocking.

### Example 5: Docker Sandbox with Playwright (v2.1)

Enable Docker isolation with browser testing support:

```yaml
sandbox:
  type: docker
  docker_image: yokeflow-playwright:latest
  docker_memory_limit: 3g
  docker_cpu_limit: "2.0"

docker:
  enabled: true
  image: yokeflow-playwright:latest
```

This runs all sessions in isolated Docker containers with full Playwright support.

### Example 6: Complete v2.1 Configuration

A comprehensive configuration using all v2.1 features:

```yaml
# Model Configuration
models:
  initializer: claude-opus-4-5-20251101
  coding: claude-sonnet-4-5-20250929
  review: claude-sonnet-4-5-20250929
  prompt_improvement: claude-opus-4-5-20251101

# Timing Configuration
timing:
  auto_continue_delay: 3
  web_ui_poll_interval: 5
  web_ui_port: 3000

# Security Configuration
security:
  additional_blocked_commands:
    # Add project-specific dangerous commands here

# Project Configuration
project:
  default_generations_dir: generations
  max_iterations: null  # unlimited

# Review Configuration
review:
  min_reviews_for_analysis: 5

# Epic Testing Configuration (Phase 3)
epic_testing:
  mode: autonomous
  critical_epics:
    - Authentication
    - Database
    - Payment
    - Security
    - Core API
  auto_failure_tolerance: 3
  auto_create_fix_tasks: true
  strict_notify_on_block: true

# Epic Re-testing Configuration (Phase 5)
epic_retesting:
  enabled: true
  trigger_frequency: 2
  foundation_retest_days: 7
  max_retests_per_trigger: 2
  prioritize_foundation: true
  prioritize_dependents: true
  pause_on_regression: false
  auto_create_rework_tasks: true

# Sandbox Configuration
sandbox:
  type: docker
  docker_image: yokeflow-playwright:latest
  docker_network: bridge
  docker_memory_limit: 3g
  docker_cpu_limit: "2.0"

docker:
  enabled: true
  image: yokeflow-playwright:latest
```

This configuration enables:
- ✅ Opus for planning, Sonnet for implementation
- ✅ Intelligent epic test blocking (autonomous mode)
- ✅ Regression detection every 2 epics
- ✅ Foundation epic re-testing every 7 days
- ✅ Docker isolation with Playwright support
- ✅ Automatic fix task creation
- ✅ Quality reviews with prompt improvements

## Validation

The config system validates settings on load:

- Invalid YAML → error message shown in Web UI/API logs
- Missing file (auto-detect) → use built-in defaults
- Invalid model names → passed through (API will validate)

## Complete Example

See [.yokeflow.yaml.example](../.yokeflow.yaml.example) for a complete configuration file with all available options and comments.

## Best Practices

1. **Use global config** (`~/.yokeflow.yaml`) for personal defaults
2. **Use local config** (`.yokeflow.yaml`) for project-specific needs
3. **Add to .gitignore** if config contains sensitive paths
4. **Version control** `.yokeflow.yaml.example` as a template
5. **Document** any non-standard settings in project README

## See Also

### Configuration
- [server/utils/config.py](../server/utils/config.py) - Configuration implementation
- [.yokeflow.yaml.example](../.yokeflow.yaml.example) - Full example with comments

### Quality System (v2.1)
- [docs/quality-system.md](quality-system.md) - Complete quality system documentation (Phases 0-8)
- [QUALITY_SYSTEM_SUMMARY.md](../QUALITY_SYSTEM_SUMMARY.md) - Phase-by-phase implementation summary
- [docs/testing-guide.md](testing-guide.md) - Testing practices and tools

### Related Documentation
- [docs/api-usage.md](api-usage.md) - API endpoint reference (60+ endpoints)
- [docs/docker-sandbox-implementation.md](docker-sandbox-implementation.md) - Docker setup guide
- [docs/developer-guide.md](developer-guide.md) - Platform architecture

