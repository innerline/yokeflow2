# YokeFlow 2 - Brownfield Support Plan

*Created: February 10, 2026*
*Target: v2.2*

## Executive Summary

This plan adds **brownfield support** to YokeFlow — the ability to load an existing codebase and create epics/tasks for improvements, bug fixes, refactoring, or new features on top of it. Today YokeFlow is greenfield-only: Session 0 creates a project from scratch, assumes an empty directory, and the initializer prompt is designed for new applications.

Brownfield support means:
1. Import an existing codebase (from local path or GitHub)
2. Analyze its structure, dependencies, and patterns
3. Accept a "change spec" describing desired improvements/fixes
4. Generate epics/tasks/tests scoped to modifying existing code (not building from scratch)
5. Run coding sessions that understand and safely modify the existing codebase

---

## Current Architecture (What Assumes Greenfield)

### 1. Project Creation (`server/agent/orchestrator.py:101-197`)
- `create_project()` creates an empty directory under `generations/`
- Copies spec files into the empty directory
- No support for pointing to an existing codebase outside `generations/`

### 2. Initializer Prompt (`prompts/initializer_prompt.md`)
- Entirely greenfield-oriented: "initializing a new software project"
- Creates epics from scratch assuming nothing exists
- TASK 4 creates basic directory structure (`mkdir -p src/...`)
- TASK 5 initializes a new Git repo
- Epic patterns are greenfield ("Project foundation & database setup", etc.)

### 3. Coding Prompts (`prompts/coding_prompt_docker.md`, `coding_prompt_local.md`)
- Session start checks if server is running, starts it if not
- No concept of "understanding existing code before modifying"
- No guidance on regression safety, existing test suites, or merge strategies

### 4. Database Schema (`schema/postgresql/schema.sql`)
- `projects` table has `spec_file_path` and `spec_content` but no `source_repo_url`, `project_type` (greenfield/brownfield), or `codebase_analysis` fields
- No way to store codebase metadata (framework, language, dependencies detected)

### 5. Docker Sandbox (`server/sandbox/manager.py`)
- Container named `yokeflow-{project_dir.name}` based on `generations/` path
- Initializer sessions always recreate container (clean slate)
- No mechanism to clone a repo into the container or mount an external codebase

### 6. Prompt Loading (`server/client/prompts.py`)
- `get_initializer_prompt()` returns a single prompt — no variant for brownfield
- `get_coding_prompt()` varies only by sandbox type (docker/local), not project type

### 7. Configuration (`server/utils/config.py`)
- No brownfield-specific config (analysis depth, safety level, existing test handling)

### 8. Web UI (`web-ui/src/app/create/page.tsx`)
- Only supports "upload spec file" or "generate spec with AI"
- No option to import from GitHub URL or local path

---

## Implementation Plan

### Phase 1: Data Model & Project Import (8-10h)

The foundation — allow projects to be created from existing codebases.

#### 1.1 Database Schema Changes

**New migration: `schema/postgresql/017_brownfield_support.sql`**

```sql
-- Add project_type to distinguish greenfield vs brownfield
ALTER TABLE projects ADD COLUMN project_type VARCHAR(20) DEFAULT 'greenfield'
    CHECK (project_type IN ('greenfield', 'brownfield'));

-- Source repository info (for brownfield)
ALTER TABLE projects ADD COLUMN source_repo_url TEXT;
ALTER TABLE projects ADD COLUMN source_branch VARCHAR(100) DEFAULT 'main';
ALTER TABLE projects ADD COLUMN source_commit_sha VARCHAR(40);

-- Codebase analysis results (populated during brownfield init)
ALTER TABLE projects ADD COLUMN codebase_analysis JSONB DEFAULT '{}';

-- Comment the new columns
COMMENT ON COLUMN projects.project_type IS 'greenfield = new project, brownfield = existing codebase';
COMMENT ON COLUMN projects.source_repo_url IS 'Git URL of the source repository for brownfield projects';
COMMENT ON COLUMN projects.source_branch IS 'Branch to work on for brownfield projects';
COMMENT ON COLUMN projects.source_commit_sha IS 'Commit SHA at import time for tracking drift';
COMMENT ON COLUMN projects.codebase_analysis IS 'Structured analysis: languages, frameworks, deps, structure';
```

The `codebase_analysis` JSONB will store:
```json
{
  "languages": ["typescript", "python"],
  "frameworks": ["next.js", "fastapi"],
  "package_managers": ["npm", "pip"],
  "has_tests": true,
  "test_framework": "jest",
  "has_ci": true,
  "ci_platform": "github-actions",
  "entry_points": ["src/index.ts", "server/main.py"],
  "loc_estimate": 15000,
  "directory_structure_summary": "...",
  "key_config_files": ["package.json", "tsconfig.json", ".env.example"],
  "detected_patterns": ["monorepo", "api-first", "docker-compose"]
}
```

#### 1.2 Orchestrator Changes (`server/agent/orchestrator.py`)

Add a new method `create_brownfield_project()`:

```python
async def create_brownfield_project(
    self,
    project_name: str,
    source: str,  # Git URL or local path
    branch: str = "main",
    change_spec_content: Optional[str] = None,
    change_spec_source: Optional[Path] = None,
    user_id: Optional[UUID] = None,
    sandbox_type: str = "docker",
    initializer_model: Optional[str] = None,
    coding_model: Optional[str] = None,
) -> Dict[str, Any]:
```

This method will:
1. Create project directory under `generations/`
2. Clone/copy the existing codebase into it
3. Store the change spec (what to improve/fix) as `change_spec.md` alongside `app_spec.txt`
4. Record source metadata in DB (`source_repo_url`, `source_branch`, `source_commit_sha`)
5. Set `project_type = 'brownfield'`
6. Create the project in the database

**Key difference from `create_project()`**: The project directory is pre-populated with existing code, not empty. The spec describes *changes* to make, not a complete application.

#### 1.3 Codebase Import Logic (`server/agent/codebase_import.py` — new file)

Create a focused module for importing codebases:

```python
class CodebaseImporter:
    """Import existing codebases for brownfield projects."""

    async def import_from_github(
        self, repo_url: str, branch: str, target_dir: Path
    ) -> ImportResult:
        """Clone a GitHub repo into the project directory."""
        # git clone --depth=1 --branch=<branch> <url> <target>
        # Record commit SHA
        # Return ImportResult with metadata

    async def import_from_local(
        self, source_path: Path, target_dir: Path
    ) -> ImportResult:
        """Copy a local codebase into the project directory."""
        # Copy files (respecting .gitignore patterns)
        # Initialize git if not already a repo
        # Return ImportResult with metadata

    async def analyze_codebase(self, project_dir: Path) -> dict:
        """Analyze the imported codebase structure."""
        # Detect languages (by file extensions)
        # Detect frameworks (package.json, requirements.txt, Cargo.toml, etc.)
        # Detect test frameworks (jest.config, pytest.ini, etc.)
        # Detect CI (github/workflows, .gitlab-ci.yml, etc.)
        # Count LOC estimate
        # Map directory structure
        # Return structured analysis dict
```

The analysis is lightweight (file-system inspection, not LLM-based) and runs before the initializer session. The heavy understanding happens in Session 0 via Claude.

#### 1.4 API Endpoint (`server/api/app.py`)

Add a new endpoint for brownfield project creation:

```python
@app.post("/api/projects/import")
async def import_project(
    name: str = Form(...),
    source_url: str = Form(None),          # GitHub URL
    source_path: str = Form(None),          # Local path
    branch: str = Form("main"),
    change_spec: UploadFile = File(None),   # What to change
    change_spec_content: str = Form(None),  # Or as text
    sandbox_type: str = Form("docker"),
    initializer_model: str = Form(None),
    coding_model: str = Form(None),
):
```

#### 1.5 Validation Models (`server/api/validation.py`)

Add Pydantic models:

```python
class ImportProjectRequest(BaseModel):
    name: str  # Project name (reuse existing validation)
    source_url: Optional[str] = None  # Must be valid git URL
    source_path: Optional[str] = None  # Must be valid local path
    branch: str = "main"
    change_spec_content: Optional[str] = None
    sandbox_type: str = "docker"

    @validator('source_url', 'source_path')
    def at_least_one_source(cls, v, values):
        # Ensure exactly one source is provided
        ...
```

#### 1.6 Web UI Import Page (`web-ui/src/app/create/page.tsx`)

Extend the existing create page with a third mode:

- **Upload Spec** (existing) — greenfield
- **Generate with AI** (existing) — greenfield
- **Import Existing Codebase** (new) — brownfield

The import mode UI:
1. Source selector: GitHub URL input OR local path input
2. Branch selector (default: main)
3. Change spec: text area or file upload describing what to improve
4. Same model/sandbox options as greenfield
5. "Import & Analyze" button

---

### Phase 2: Brownfield Initializer Prompt (8-10h)

The core intelligence — a new initializer prompt that understands existing code.

#### 2.1 New Prompt: `prompts/initializer_prompt_brownfield.md`

This prompt replaces the greenfield initializer for brownfield projects. Key differences:

**TASK 1: Understand the Existing Codebase**
- Read the codebase analysis (injected into prompt from DB)
- Explore key files: entry points, config files, README
- Understand the architecture, patterns, and conventions
- Identify the tech stack and dependencies
- Map the directory structure
- Find existing tests and CI configuration
- Document understanding in `claude-progress.md`

**TASK 2: Read the Change Specification**
- Read `change_spec.md` (what the user wants improved/fixed)
- Cross-reference with codebase understanding
- Identify which parts of the codebase are affected
- Assess complexity and risk of each change

**TASK 3: Create Epics and Tasks for Changes**
- Create epics scoped to the requested changes (not the whole app)
- Each epic represents a cohesive area of change
- Tasks describe specific modifications to existing files
- Task descriptions include:
  - Which files to modify
  - What the current behavior is
  - What the new behavior should be
  - Potential regression risks
- Order by dependency and risk (safest changes first)

**TASK 4: Create Test Requirements**
- For each task, create tests that verify the change works
- Include regression tests for existing functionality that might break
- Reference existing test patterns in the codebase
- If the project has a test framework, tasks should add tests in the same style

**TASK 5: Verify Git State**
- Create a feature branch for the changes
- Do NOT reinitialize git or modify `.gitignore` unless specifically requested
- First commit should be empty (or just `change_spec.md`) to mark the starting point

**Key prompt differences from greenfield:**

| Aspect | Greenfield | Brownfield |
|--------|-----------|------------|
| First action | Read spec | Explore existing codebase |
| Epic scope | Entire application | Only requested changes |
| Task descriptions | "Create X from scratch" | "Modify X to add/fix Y" |
| Test strategy | All new tests | New tests + regression tests |
| Git setup | `git init` | Create feature branch |
| Directory structure | Create from scratch | Preserve existing |
| Dependencies | Install everything | Only add what's needed |
| Task count | 100-400 | 20-100 (scoped to changes) |

#### 2.2 Prompt Loading Changes (`server/client/prompts.py`)

```python
def get_initializer_prompt(project_type: str = "greenfield") -> str:
    if project_type == "brownfield":
        return load_prompt("initializer_prompt_brownfield")
    return load_prompt("initializer_prompt")
```

#### 2.3 Orchestrator Integration

In `start_session()`, inject codebase analysis into the brownfield initializer prompt:

```python
if is_initializer:
    project_type = project.get('project_type', 'greenfield')
    base_prompt = get_initializer_prompt(project_type=project_type)
    prompt = f"PROJECT_ID: {project_id}\n\n{base_prompt}"

    # For brownfield, inject codebase analysis
    if project_type == 'brownfield':
        analysis = project.get('codebase_analysis', {})
        analysis_str = json.dumps(analysis, indent=2)
        prompt += f"\n\n## Codebase Analysis (Pre-computed)\n```json\n{analysis_str}\n```"
```

#### 2.4 Context Injection for Coding Sessions

The coding prompts need a small addition for brownfield projects. Rather than creating entirely new coding prompts, add a brownfield preamble that gets prepended:

**`prompts/coding_preamble_brownfield.md`** (new, short):
```markdown
## Brownfield Project Context

You are modifying an EXISTING codebase, not building from scratch.

**Critical Rules:**
1. **Understand before changing** — Read relevant existing code before modifying
2. **Preserve conventions** — Match the existing code style, patterns, and naming
3. **Minimize blast radius** — Change only what's necessary for the task
4. **Run existing tests** — After changes, run the project's existing test suite
5. **No unnecessary refactoring** — Fix/improve what's asked, nothing else
6. **Feature branch** — All work happens on the feature branch, not main
```

This preamble is prepended to the standard coding prompt in `start_session()`:

```python
else:
    base_prompt = get_coding_prompt(sandbox_type=sandbox_type)
    if project.get('project_type') == 'brownfield':
        preamble = load_prompt("coding_preamble_brownfield")
        prompt = f"{preamble}\n\n{base_prompt}"
    else:
        prompt = base_prompt
```

---

### Phase 3: Sandbox & Git Integration (6-8h)

Safe modification of existing codebases with rollback support.

#### 3.1 Docker Sandbox Changes (`server/sandbox/manager.py`)

For brownfield projects, the Docker container needs the full existing codebase:

- **Current behavior**: Mounts `generations/<project>/` as `/workspace/`
- **Brownfield behavior**: Same — the imported codebase is already in `generations/<project>/` from Phase 1

No fundamental change needed to the volume mounting. The key difference is the initializer session should NOT recreate the container from a clean slate if the codebase is already imported. Update the session type logic:

```python
# In DockerSandbox.start():
if self.session_type == "initializer" and existing_container:
    if self.config.get("project_type") == "brownfield":
        # Brownfield: reuse container (codebase already present)
        if existing_container.status == "running":
            self.container_id = existing_container.id
            self.is_running = True
            return
        else:
            existing_container.start()
            self.container_id = existing_container.id
            self.is_running = True
            return
    else:
        # Greenfield: clean slate
        existing_container.remove(force=True)
        existing_container = None
```

#### 3.2 Git Branch Management

During brownfield project import (`codebase_import.py`):

```python
async def setup_brownfield_git(self, project_dir: Path, branch_name: str = None):
    """Set up git branch for brownfield modifications."""
    # Ensure we're on the source branch
    # Create a feature branch: yokeflow/<change-description>
    # Record the base commit SHA for later diff/PR creation
```

After coding sessions complete, the orchestrator can optionally:
- Create a diff of all changes
- Generate a PR description summarizing what was changed
- Push to a remote and create a PR (future Phase 4)

#### 3.3 Rollback Support

Add a method to the orchestrator:

```python
async def rollback_brownfield_changes(self, project_id: UUID) -> bool:
    """Reset the project to the original imported state."""
    # git checkout <source_branch>
    # git branch -D yokeflow/<feature-branch>
    # Reset task statuses in DB
```

This is important for brownfield since users may want to retry with different specs.

---

### Phase 4: Verification & Testing Enhancements (4-5h)

#### 4.1 Existing Test Suite Detection

During codebase analysis (Phase 1), detect:
- Test framework (jest, pytest, mocha, vitest, etc.)
- Test runner command (`npm test`, `pytest`, etc.)
- Test directory structure
- Current test count and pass rate

Store in `codebase_analysis.testing`:
```json
{
  "testing": {
    "framework": "jest",
    "runner_command": "npm test",
    "test_dirs": ["__tests__", "src/**/*.test.ts"],
    "test_count_estimate": 45,
    "config_file": "jest.config.ts"
  }
}
```

#### 4.2 Regression Test Integration

The brownfield coding prompt instructs the agent to:
1. Run existing tests BEFORE making changes (baseline)
2. Make changes
3. Run existing tests AFTER changes (regression check)
4. Run new tests for the specific change

The task verification flow adds a step:

```
Existing workflow:
  get_task_tests → verify requirements → update_task_status

Brownfield workflow:
  run_existing_tests (baseline) →
  implement changes →
  run_existing_tests (regression) →
  get_task_tests → verify requirements →
  update_task_status
```

This doesn't require new MCP tools — the agent simply runs the test command via `bash_docker` as an additional verification step. The prompt instructs this behavior.

#### 4.3 Impact Analysis in Task Descriptions

The brownfield initializer creates tasks with richer metadata:

```json
{
  "description": "Add pagination to user list API",
  "action": "Modify src/api/users.ts to add offset/limit parameters...",
  "metadata": {
    "files_to_modify": ["src/api/users.ts", "src/types/api.ts"],
    "files_affected": ["src/pages/users.tsx", "src/hooks/useUsers.ts"],
    "risk_level": "medium",
    "regression_areas": ["user listing", "search results", "admin dashboard"]
  }
}
```

This metadata is stored in the existing task `metadata` JSONB column and surfaced to the coding agent via task descriptions.

---

### Phase 5: GitHub Integration (6-8h)

#### 5.1 Clone from GitHub

In `codebase_import.py`:

```python
async def import_from_github(self, repo_url: str, branch: str, target_dir: Path) -> ImportResult:
    """Clone a GitHub repository."""
    # Validate URL (GitHub, GitLab, Bitbucket)
    # git clone --depth=1 --branch=<branch> <url> <target>
    # For private repos: use GITHUB_TOKEN from env
    # Record commit SHA
    # Run codebase analysis
```

Support for:
- Public repos (no auth needed)
- Private repos (via `GITHUB_TOKEN` env var or GitHub CLI auth)
- Specific branches or tags
- Shallow clones for faster import

#### 5.2 Push Changes Back

After brownfield coding sessions complete:

```python
async def push_changes(self, project_id: UUID, remote: str = "origin") -> dict:
    """Push brownfield changes to remote."""
    # git push -u origin yokeflow/<feature-branch>
    # Return push result
```

#### 5.3 Create Pull Request

```python
async def create_pull_request(
    self, project_id: UUID, title: str = None, body: str = None
) -> dict:
    """Create a PR for brownfield changes using gh CLI."""
    # Auto-generate title from change spec if not provided
    # Auto-generate body from completed tasks/epics
    # gh pr create --title "..." --body "..."
    # Return PR URL
```

#### 5.4 API Endpoints

```python
@app.post("/api/projects/{project_id}/push")
async def push_project_changes(project_id: UUID):
    """Push brownfield changes to remote."""

@app.post("/api/projects/{project_id}/create-pr")
async def create_project_pr(project_id: UUID, title: str = None):
    """Create a GitHub PR for brownfield changes."""
```

#### 5.5 Web UI

Add to the project detail page:
- "Push Changes" button (visible for brownfield projects)
- "Create PR" button with title/description editor
- PR link display after creation

---

## Configuration

### `.yokeflow.yaml` additions

```yaml
brownfield:
  # Default branch for feature work
  default_feature_branch_prefix: "yokeflow/"

  # Codebase analysis depth
  analysis_depth: "standard"  # "quick", "standard", "deep"

  # Safety settings
  run_existing_tests_before_changes: true
  run_existing_tests_after_changes: true
  max_files_modified_per_task: 10
  require_feature_branch: true

  # GitHub integration
  auto_push: false
  auto_create_pr: false
  pr_draft: true  # Create PRs as draft by default
```

### Environment Variables

```bash
# Optional: GitHub token for private repos
GITHUB_TOKEN=ghp_xxx

# Optional: Default GitHub org for repos
GITHUB_DEFAULT_ORG=myorg
```

---

## MCP Tool Changes

### Existing tools that work as-is:
- `create_epic`, `expand_epic`, `create_task_test`, `create_epic_test` — all work unchanged
- `get_next_task`, `start_task`, `update_task_status` — all work unchanged
- `bash_docker` — works unchanged (codebase is in /workspace/)
- `task_status`, `list_epics`, `list_tasks` — all work unchanged

### New tools (optional, Phase 5):
- `push_changes` — Push current branch to remote
- `create_pr` — Create a GitHub pull request

### No existing MCP tools need modification.

The brownfield workflow uses the same task management tools. The difference is entirely in:
1. How the project directory is populated (existing code vs empty)
2. What the initializer prompt instructs (analyze & plan changes vs create from scratch)
3. What the coding prompt instructs (modify carefully vs build freely)

---

## Implementation Order & Dependencies

```
Phase 1 (Foundation)          Phase 2 (Intelligence)
├─ 1.1 DB Schema              ├─ 2.1 Brownfield Init Prompt
├─ 1.2 Orchestrator           ├─ 2.2 Prompt Loading
├─ 1.3 Import Logic           ├─ 2.3 Orchestrator Integration
├─ 1.4 API Endpoint           └─ 2.4 Coding Preamble
├─ 1.5 Validation
└─ 1.6 Web UI                 Phase 3 (Safety)
                               ├─ 3.1 Sandbox Changes
Phase 4 (Testing)              ├─ 3.2 Git Branch Mgmt
├─ 4.1 Test Detection          └─ 3.3 Rollback Support
├─ 4.2 Regression Tests
└─ 4.3 Impact Analysis        Phase 5 (GitHub)
                               ├─ 5.1 Clone from GitHub
                               ├─ 5.2 Push Changes
                               ├─ 5.3 Create PR
                               ├─ 5.4 API Endpoints
                               └─ 5.5 Web UI
```

**Critical path**: Phase 1 → Phase 2 → Phase 3 (minimum viable brownfield)
**Can be parallelized**: Phase 4 alongside Phase 3; Phase 5 after Phase 3

---

## Testing Plan

### Unit Tests
- `tests/test_codebase_import.py` — Import from local path, mock GitHub clone, analysis detection
- `tests/test_brownfield_orchestrator.py` — Project creation, session type detection
- `tests/test_brownfield_validation.py` — API validation models for import

### Integration Tests
- Import a sample codebase (checked into `tests/fixtures/sample_project/`)
- Run brownfield initialization with mock Claude client
- Verify epics/tasks created reference existing files
- Verify feature branch created correctly
- Verify rollback works

### End-to-End Tests
- Import a small real project (e.g., a simple Express app)
- Run full brownfield flow: import → analyze → init → code → verify
- Validate changes are correct and existing tests still pass

---

## Estimated Effort

| Phase | Description | Hours |
|-------|-------------|-------|
| 1 | Data Model & Project Import | 8-10h |
| 2 | Brownfield Initializer Prompt | 8-10h |
| 3 | Sandbox & Git Integration | 6-8h |
| 4 | Verification & Testing | 4-5h |
| 5 | GitHub Integration | 6-8h |
| **Total** | | **32-41h** |

**Minimum Viable Brownfield** (Phases 1-3): **22-28h**
- Can import local codebases
- Generates appropriate brownfield epics/tasks
- Safely modifies code on feature branch
- No GitHub push/PR (manual git operations work)

---

## Success Criteria

- [ ] Import a React/Next.js project from a local directory
- [ ] Import a Python project from a GitHub URL
- [ ] Brownfield initializer creates epics/tasks scoped to requested changes
- [ ] Tasks reference specific existing files to modify
- [ ] Coding sessions modify existing code without breaking unrelated functionality
- [ ] Existing test suites continue to pass after modifications
- [ ] Changes are on a feature branch, original code preserved on main
- [ ] User can rollback all changes with one action
- [ ] User can push changes and create a PR (Phase 5)
- [ ] Web UI supports the full brownfield workflow

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Large codebases overwhelm Claude's context | Agent can't understand enough of the codebase | Codebase analysis pre-computes structure; prompt instructs lazy exploration; tasks reference specific files |
| Existing tests break from changes | User loses trust in the tool | Mandatory regression test runs before/after; prompt emphasizes minimal changes |
| Git conflicts with upstream changes | Feature branch becomes stale | Record base commit SHA; warn user if upstream has diverged; support rebase |
| Private repo auth complexity | Import fails for private repos | Support GitHub CLI auth, PAT tokens, SSH keys; clear error messages |
| Brownfield tasks are too vague | Agent doesn't know what to change | Require change spec; initializer prompt emphasizes specific file references in tasks |

---

## Open Questions

1. **Should brownfield projects live in `generations/` or alongside the source repo?**
   - Recommendation: Keep in `generations/` for consistency. The imported code is a copy.
   - Alternative: Work directly in the source repo (riskier, but avoids copy overhead)

2. **How deep should automatic codebase analysis go?**
   - Recommendation: File-system level only (fast, no LLM cost). Let Session 0 do the deep understanding.
   - Alternative: Use a quick LLM pass for framework/pattern detection (adds cost)

3. **Should we support incremental change specs (multiple rounds of brownfield)?**
   - Recommendation: v1 supports one change spec per project. Future: allow adding more change specs to existing brownfield projects.

4. **How to handle monorepos?**
   - Recommendation: Allow specifying a subdirectory as the working root. Analysis runs on the subdirectory.
