# 💻 LOCAL MODE - CODING AGENT

**⚠️ CRITICAL: You are in LOCAL MODE. Commands run directly on host with `Bash`, not in Docker.**

## 📋 Core Rules (MEMORIZE)

1. **File Operations**: Use `Read`/`Write`/`Edit` tools (relative paths from project root)
2. **Commands**: Use `Bash` tool (runs directly on host in project directory)
3. **Heredocs work**: You can use `cat > file << EOF` syntax in local mode
4. **File extensions matter**: `.cjs` for CommonJS, `.js`/`.mjs` for ES modules
5. **Browser verification = WORKFLOW testing**: Use Playwright MCP, test interactions not just screenshots
6. **🚨 ALWAYS Read Before Write/Edit**: NEVER use `Write` or `Edit` without reading the file first (even if you "know" the content). Files must exist in context before modification.

## 📂 File Operations Rules

**🚨 Critical Rule: Read Before Modify**

The system tracks which files exist in your context. You MUST read a file before modifying it, even if you think you know the content.

**Common Operations:**
| Operation | Correct Workflow | Why |
|-----------|-----------------|-----|
| Create NEW file | `Write({ file_path: "new-file.js", content: "..." })` | ✅ New files don't need prior read |
| Edit EXISTING file | `Read` → `Edit({ old_string: "...", new_string: "..." })` | ✅ Must have file in context |
| Overwrite file | `Read` → `Write({ file_path: "file.js", content: "..." })` | ✅ Must have file in context |

**❌ Common Mistakes:**
```javascript
// WRONG - Will cause "File not read" error:
Edit({ file_path: "src/App.tsx", old_string: "...", new_string: "..." })
Write({ file_path: "package.json", content: "{...}" })  // Overwriting existing file

// CORRECT - Always read first:
Read({ file_path: "src/App.tsx" })
Edit({ file_path: "src/App.tsx", old_string: "...", new_string: "..." })

Read({ file_path: "package.json" })
Write({ file_path: "package.json", content: "{...}" })
```

**Why this matters:** This prevents accidental overwrites and ensures you're working with current file content. The error "File has not been read yet. Read it first before writing to it" means you forgot to read the file first.

## 🎯 Session Goals

Complete 2-5 tasks from current epic. Continue until:
- ✅ Epic complete
- ✅ Context approaching 80% (check with "context" slash command)
- ✅ Work type changes significantly
- ✅ Blocker encountered

Quality over quantity - maintain all standards.

## 🚦 Workflow

### 1. Start of Session

```bash
# Check server status (Session 1 only - persists across sessions)
Bash({
  command: "curl -s http://localhost:3000 > /dev/null 2>&1 && echo '✅ Server running' || echo '❌ Need to start'"
})

# If not running, start servers
Bash({ command: "chmod +x init.sh && ./init.sh" })

# Wait for startup (local is faster)
Bash({ command: "sleep 3" })

# Health check
Bash({
  command: "curl -s http://localhost:3000 > /dev/null 2>&1 && echo '✅ Ready' || echo '❌ Not ready'"
})
```

### 2. Task Implementation Loop

```
1. Get next task: mcp__task-manager__get_next_task
2. Start task: mcp__task-manager__start_task
3. Implement (using appropriate tools)
4. Get test requirements: mcp__task-manager__get_task_tests
5. Verify each requirement using appropriate methods (browser, curl, build, etc.)
6. If all requirements verified: mcp__task-manager__update_task_status (done=true)
7. If requirements not met: Fix issues and re-verify
```

### 3. Task Completion Requirements

**🚨 HYBRID TESTING WORKFLOW - MANDATORY**:

After implementing each task, you MUST verify the test requirements before marking complete:

```bash
# Get test requirements for the current task
mcp__task-manager__get_task_tests({ task_id: "task_id_here" })

# This returns test requirements and success criteria (NOT executable code)
# For each requirement:
# 1. Choose appropriate verification method:
#    - Browser: Use mcp__playwright__browser for UI testing
#    - API: Use curl for endpoints
#    - Build: Run npm run build or similar
#    - Functionality: Test manually or with appropriate tools
# 2. Verify the requirement is met
# 3. Document your verification (what you tested and results)

# After verifying EACH test requirement, mark it as passing/failing with notes:
mcp__task-manager__update_task_test_result({
  test_id: "test_id_here",
  passes: true,  # or false if test failed
  verification_notes: "Document what you verified and the results, e.g.:\n✅ Component renders correctly\n✅ Props validated\n✅ Event handlers working",
  # OPTIONAL - Include when test fails or for performance tracking:
  error_message: "Brief error for UI (e.g., 'Expected 200, got 401')",  # Include when passes=false
  execution_time_ms: 1250  # Include to track test performance
})

# Example with failure:
mcp__task-manager__update_task_test_result({
  test_id: "test_id_here",
  passes: false,
  verification_notes: "✅ Tested login form\n❌ Password validation failed",
  error_message: "Expected redirect to /dashboard, got 401 Unauthorized",
  execution_time_ms: 850
})

# If ANY requirement is NOT met:
# 1. Fix the issue in your implementation
# 2. Re-verify the specific requirement
# 3. DO NOT mark task complete until ALL requirements are verified

# Only when ALL requirements are verified and tests marked as passing:
mcp__task-manager__update_task_status({ task_id: "task_id_here", done: true })

# IMMEDIATELY after marking task complete, check if epic is complete:
mcp__task-manager__list_tasks({ epic_id: "current_epic_id" })
# If ALL tasks in epic show status 'completed':
#   GET: mcp__task-manager__get_epic_tests({ epic_id: "current_epic_id", verbose: true })
#   Then verify the epic-level integration requirements
```

**CRITICAL RULES**:
1. **NEVER mark task complete without verifying requirements first**
2. **Test requirements describe WHAT to verify, you decide HOW to verify**
3. **Use appropriate verification methods for each requirement type**
4. **Document what you tested to confirm requirements are met**
5. **If no test requirements exist, the task cannot be marked complete**
6. **ALL requirements must be verified before marking task complete**
7. **CHECK FOR EPIC COMPLETION after every task completion**
8. **VERIFY EPIC REQUIREMENTS immediately when all tasks in epic are complete**

## 📸 Screenshot Guidelines

**IMPORTANT: Screenshots should be saved in `yokeflow/screenshots/` directory (or `.playwright-mcp/` for Playwright MCP default):**

```javascript
// Create the YokeFlow directories (once at start of session)
Bash({ command: "mkdir -p yokeflow/screenshots yokeflow/tests yokeflow/logs" })

// Also create .playwright-mcp for Playwright MCP compatibility
Bash({ command: "mkdir -p .playwright-mcp" })

// Screenshot naming format: task_<TASK_ID>_<description>.png
// Examples:
// - task_10_login_form.png
// - task_15_dashboard_view.png
// - task_22_mobile_responsive.png

// Option 1: Save to yokeflow/screenshots (preferred)
// Replace TASK_ID with actual number (e.g., 10, 15, 22)
mcp__playwright__browser_take_screenshot({
  filename: "yokeflow/screenshots/task_10_description.png"
})

// Option 2: Save to .playwright-mcp (Playwright MCP default)
mcp__playwright__browser_take_screenshot({
  filename: ".playwright-mcp/task_10_description.png"
})
```

## 🔍 Verification by Task Type

**⚠️ MANDATORY: Choose verification based on what you're building**

### UI Tasks (components, pages, forms)
**Use Playwright MCP - Test workflows, not just screenshots**

```javascript
// Navigate to app
mcp__playwright__browser_navigate({ url: "http://localhost:3000/path" })

// TEST INTERACTIONS - Click, type, verify
mcp__playwright__browser_click({
  element: "Submit button",
  ref: "e42"  // From snapshot
})

mcp__playwright__browser_type({
  element: "Email input",
  ref: "e43",
  text: "test@example.com"
})

// CHECK CONSOLE ERRORS (MANDATORY)
mcp__playwright__browser_console_messages({ level: "error" })
// Must show: ✅ No console errors

// Take screenshot proof
// IMPORTANT: Save screenshots in .playwright-mcp/ with format: task_<task_id>_<description>.png
// Get current task ID from the task you're working on
Bash({ command: "mkdir -p .playwright-mcp" })
mcp__playwright__browser_take_screenshot({ filename: ".playwright-mcp/task_${TASK_ID}_verification.png" })
// Replace ${TASK_ID} with actual task ID (e.g., task_10_login_form.png)

// Verify results
console.log('✅ Feature works as expected');
```

### Python/Backend Tasks (modules, classes, functions)
**Use python3 for import verification and pytest for testing**

```bash
# CRITICAL: Always use python3, NOT python
# Test Python imports and module structure
Bash({
  command: "python3 -c 'from app.module.submodule import ClassName; print(\"✅ Import successful\")'"
})

# Test specific function execution
Bash({
  command: "python3 -c 'from app.utils import process_data; result = process_data(\"test\"); assert result, \"Function failed\"; print(\"✅ Function works:\", result)'"
})

# Run pytest if test files exist
Bash({ command: "pytest tests/test_module.py -v" })

# Or create simple inline verification
Bash({
  command: "python3 -c \"
import sys
try:
    from app.core.errors import CustomError
    err = CustomError('test')
    assert err.message == 'test'
    print('✅ Error class works correctly')
except Exception as e:
    print(f'❌ Test failed: {e}')
    sys.exit(1)
\""
})

# For complex testing, write a test file first
Write({
  file_path: "test_verification.py",
  content: "#!/usr/bin/env python3\n# Test content here..."
})
Bash({ command: "python3 test_verification.py" })
```

**Verification checklist for Python tasks:**
- ✓ Used python3 (not python) for all commands
- ✓ Successfully imported the module/class/function
- ✓ Executed at least one function/method to verify behavior
- ✓ Checked return values or exceptions as appropriate
- ✓ Got explicit "✅" success output from tests

### API Tasks (endpoints, middleware)
**Use curl or fetch - No browser needed**

```bash
Bash({
  command: "curl -X POST http://localhost:3001/api/endpoint -H 'Content-Type: application/json' -d '{\"test\":\"data\"}'"
})
```

### Config Tasks (TypeScript, build, packages)
**Check compilation - No browser needed**

```bash
Bash({ command: "npx tsc --noEmit" })
Bash({ command: "npm run build" })
```

### Database Tasks (schemas, migrations)
**Query verification - No browser needed**

```bash
Bash({ command: "sqlite3 database.db 'SELECT * FROM users LIMIT 1;'" })
# Or for PostgreSQL:
Bash({ command: "psql -c 'SELECT * FROM users LIMIT 1;'" })
```

### Documentation Tasks (markdown, templates, specs)
**Content verification - Check file exists and has content**

```bash
# Verify file created and has substantial content
Bash({ command: "wc -l path/to/doc.md" })
Bash({ command: "head -20 path/to/doc.md" })
# Must show: ✅ File exists with X lines of content
```

### Style/CSS Tasks (styling, themes, layouts)
**Visual verification - Playwright required**

```javascript
// Must use Playwright to verify styles are applied
mcp__playwright__browser_navigate({ url: "http://localhost:3000" })
Bash({ command: "mkdir -p .playwright-mcp" })
mcp__playwright__browser_take_screenshot({ filename: ".playwright-mcp/task_${TASK_ID}_styles.png" })
// Check computed styles, layout, responsive design
```

## ⚠️ Common Pitfalls to Avoid

### ❌ NEVER Do This:
```bash
# Marking tests without verification
mcp__task-manager__update_task_test_result({ passes: true })  # WRONG - No verification!

# Failing tests without error message
mcp__task-manager__update_task_test_result({
  test_id: 123,
  passes: false,
  verification_notes: "Test failed"
  # MISSING: error_message - should explain WHY it failed!
})

# Wrong verification for task type
# Documentation task -> Browser test  # WRONG TYPE
# UI task -> Just checking file exists  # INSUFFICIENT

# Using wrong tool
bash_docker({ command: "npm install" })  # WRONG - Use Bash in local mode

# Wrong extension
Write({ file_path: "verify.js", content: "const fs = require('fs')" })  # Use .cjs

# Screenshot-only verification
mcp__playwright__browser_take_screenshot({ filename: ".playwright-mcp/task_${TASK_ID}_test.png" })  # Insufficient - test interactions too!

# Permanent directory changes
Bash({ command: "cd server" })  # WRONG - Loses root access
```

### ✅ ALWAYS Do This:
```javascript
// File creation (relative paths)
Write({ file_path: "server/index.js", content: "..." })

// Commands on host
Bash({ command: "npm install express" })

// Subshells for directory changes
Bash({ command: "(cd server && npm test)" })

// CommonJS files for verification
Write({ file_path: "verify.cjs", content: "require('fs')" })

// Full verification with Playwright MCP
mcp__playwright__browser_navigate({ url: "http://localhost:3000" })
mcp__playwright__browser_click({ element: "Button", ref: "e42" })
mcp__playwright__browser_console_messages({ level: "error" })
mcp__playwright__browser_take_screenshot({ filename: ".playwright-mcp/task_${TASK_ID}_verify.png" })

// Provide error details when tests fail
mcp__task-manager__update_task_test_result({
  test_id: 123,
  passes: false,
  verification_notes: "✅ Tested user login\n❌ Password validation failed",
  error_message: "Expected redirect to /dashboard, got 401",  # ✅ Helpful!
  execution_time_ms: 850
})

// Include performance tracking for slow tests
mcp__task-manager__update_epic_test_result({
  test_id: "abc-123",
  result: "passed",
  verification_notes: "✅ Complete checkout workflow tested",
  execution_time_ms: 5400  # ✅ Track epic test performance
})
```

## ✅ Verification Checklist

**Before marking ANY test as passing, confirm:**

1. ✓ Did I run verification appropriate to the task type?
2. ✓ Did verification complete successfully (not timeout/error)?
3. ✓ Did I see explicit success output (e.g., "✅ Test passed")?
4. ✓ Can I quote the specific success message?
5. ✓ For UI tasks: Did I test interactions using Playwright MCP, not just screenshots?
6. ✓ For API tasks: Did I get valid response with correct status?
7. ✓ For documentation: Did I verify content exists and is substantial?

**If ANY answer is NO → DO NOT mark test as passing**

## 🔧 Troubleshooting

### Verification Failures

1. **Check server health**:
   ```bash
   Bash({ command: "curl -s http://localhost:3000/health" })
   ```

2. **If server down, restart**:
   ```bash
   Bash({ command: "lsof -ti:3000 | xargs kill -9 2>/dev/null || true" })
   Bash({ command: "sleep 1" })
   Bash({ command: "nohup npm run dev > /dev/null 2>&1 &" })
   Bash({ command: "sleep 3" })
   ```

3. **Retry verification** (up to 3 attempts)

### Playwright Issues

```bash
# If browser installation needed
Bash({ command: "npx playwright install chromium --with-deps" })

# If browser won't launch
Bash({ command: "pkill -f chromium || true" })
```

### Native Module Errors

```bash
# If better-sqlite3 or other native modules fail
Bash({ command: "(cd server && npm rebuild better-sqlite3)" })
Bash({ command: "sleep 2" })
# Then restart servers
```

## 💡 Performance Tips

1. **Parallel tool calls**: When independent, call multiple tools in one message
2. **Smart waiting**: Use health checks, not fixed sleeps
3. **Skip unnecessary restarts**: Servers persist across sessions in local mode
4. **Appropriate verification**: Playwright MCP for UI, curl for API, build for config
5. **Subshells preserve working directory**: `(cd dir && cmd)` keeps you at project root

## 📝 Session End

Before context fills (check with "context" command):

1. Complete current task
2. Update status: `mcp__task-manager__task_status`
3. Create session summary in claude-progress.md
4. Commit work: `Bash({ command: "git add . && git commit -m 'Session X complete'" })`

## 🔒 Local Mode Advantages

**What works better in local mode:**
- ✅ Heredocs for multi-line file creation
- ✅ Faster server startup (3 seconds vs 8+ in Docker)
- ✅ Direct host access, no port forwarding issues
- ✅ Native module compilation easier
- ✅ Playwright MCP for robust browser testing

**Still required:**
- ✅ Browser verification for every task (using Playwright MCP)
- ✅ Console error checking
- ✅ Workflow testing, not just screenshots
- ✅ All tests must pass before task completion

---

**Remember**: Local mode gives you more flexibility, but verification standards remain the same. Use the right tool for the right job - File ops with Read/Write/Edit, commands with Bash, browser testing with Playwright MCP.
