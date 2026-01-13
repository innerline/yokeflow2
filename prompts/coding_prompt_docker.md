# 🐳 DOCKER MODE - CODING AGENT

**⚠️ CRITICAL: You are in DOCKER MODE. Every command MUST use `mcp__task-manager__bash_docker`, NOT `Bash`.**

## 📋 Core Rules (MEMORIZE)

1. **File Operations**: Use `Read`/`Write`/`Edit` tools (run on host, use relative paths)
2. **Commands**: Use `mcp__task-manager__bash_docker` ONLY (runs in container at /workspace/)
3. **NEVER use heredocs**: `cat > file << EOF` FAILS. Always use `Write` tool for files
4. **File extensions matter**: `.cjs` for CommonJS, `.js`/`.mjs` for ES modules
5. **Browser verification = WORKFLOW testing**: Test interactions, not just screenshots

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
mcp__task-manager__bash_docker({
  command: "curl -s http://localhost:3000 > /dev/null 2>&1 && echo '✅ Server running' || echo '❌ Need to start'"
})

# If not running, start in background
mcp__task-manager__bash_docker({
  command: "nohup npm run dev > /dev/null 2>&1 &"
})

# Health check
mcp__task-manager__bash_docker({
  command: "for i in {1..15}; do curl -s http://localhost:3000 > /dev/null 2>&1 && echo 'Ready' && break; sleep 1; done"
})
```

### 2. Task Implementation Loop

```
1. Get next task: mcp__task-manager__get_next_task
2. Start task: mcp__task-manager__start_task
3. Implement (using appropriate tools)
4. Verify based on task type (see verification section)
5. Update status: mcp__task-manager__update_task_status
6. Mark tests: mcp__task-manager__update_test_result
```

### 3. Task Completion Requirements

**CRITICAL**: Confirm success before marking complete:
- Tests must show explicit success (not "Running..." or timeout)
- Quote success output in completion message
- Verify console has no errors for UI tasks
- Check compilation for TypeScript tasks

## 🔍 Verification by Task Type

### UI Tasks (components, pages, forms)
**Use Browser with Playwright - Test workflows, not just screenshots**

```javascript
// Create test file
Write({
  file_path: "verify_task.cjs",
  content: `const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage();
  await page.goto('http://localhost:3000/path');

  // TEST INTERACTIONS - Click, type, verify
  await page.click('button.submit');
  await page.fill('input#email', 'test@example.com');

  // CHECK CONSOLE ERRORS (MANDATORY)
  const errors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push(msg.text());
  });

  // Verify results
  const title = await page.title();
  console.log('✅ Page loads:', title);
  console.log(errors.length ? '❌ Console errors:' + errors : '✅ No console errors');

  await page.screenshot({ path: 'verification.png' });
  await browser.close();
})();`
})

mcp__task-manager__bash_docker({ command: "node verify_task.cjs" })
```

### API Tasks (endpoints, middleware)
**Use curl or fetch - No browser needed**

```bash
mcp__task-manager__bash_docker({
  command: "curl -X POST http://localhost:3001/api/endpoint -H 'Content-Type: application/json' -d '{\"test\":\"data\"}'"
})
```

### Config Tasks (TypeScript, build, packages)
**Check compilation - No browser needed**

```bash
mcp__task-manager__bash_docker({ command: "npx tsc --noEmit" })
mcp__task-manager__bash_docker({ command: "npm run build" })
```

### Database Tasks (schemas, migrations)
**Query verification - No browser needed**

```bash
mcp__task-manager__bash_docker({ command: "sqlite3 database.db 'SELECT * FROM users LIMIT 1;'" })
```

## ⚠️ Common Pitfalls to Avoid

### ❌ NEVER Do This:
```bash
# Heredocs fail
bash_docker({ command: "cat > file.js << 'EOF'\\ncode\\nEOF" })  # FAILS

# Wrong tool
Bash({ command: "npm install" })  # WRONG - Use bash_docker

# Wrong extension
Write({ file_path: "verify.js", content: "const fs = require('fs')" })  # Use .cjs

# Screenshot-only verification
await page.screenshot()  # Insufficient - test interactions too!
```

### ✅ ALWAYS Do This:
```javascript
// File creation
Write({ file_path: "server/index.js", content: "..." })

// Commands
mcp__task-manager__bash_docker({ command: "npm install express" })

// CommonJS files
Write({ file_path: "verify.cjs", content: "require('fs')" })

// Full verification
// Click buttons, check console, verify state changes
```

## 🔧 Troubleshooting

### Verification Failures

1. **Check server health**:
   ```bash
   mcp__task-manager__bash_docker({ command: "curl -s http://localhost:3000/health" })
   ```

2. **If server down, restart**:
   ```bash
   mcp__task-manager__bash_docker({ command: "pkill -f 'npm run dev' || true" })
   mcp__task-manager__bash_docker({ command: "nohup npm run dev > /dev/null 2>&1 &" })
   ```

3. **Retry verification** (up to 3 attempts)

### Playwright Issues

```bash
# If "Executable doesn't exist"
mcp__task-manager__bash_docker({ command: "npx playwright install chromium --with-deps" })

# If browser won't launch
mcp__task-manager__bash_docker({ command: "pkill -f chromium || true" })
```

## 💡 Performance Tips

1. **Parallel tool calls**: When independent, call multiple tools in one message
2. **Smart waiting**: Use health checks, not fixed sleeps
3. **Skip unnecessary restarts**: Server persists across sessions
4. **Appropriate verification**: Browser for UI, curl for API, build for config

## 📝 Session End

Before context fills (check with "context" command):

1. Complete current task
2. Update status: `mcp__task-manager__task_status`
3. Create session summary in claude-progress.md
4. Commit work: `mcp__task-manager__bash_docker({ command: "git add . && git commit -m 'Session X complete'" })`

---

**Remember**: Docker mode is about using the right tool for the right job. File ops with Read/Write/Edit, commands with bash_docker, appropriate verification for each task type.