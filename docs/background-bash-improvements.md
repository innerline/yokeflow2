# Background Bash Process Improvements

**Date**: December 23, 2025
**Issue**: Background bash timeouts fail silently, causing sessions to continue without awareness of process failures

## Problem Summary

When a background bash process exceeds its timeout, Claude Code's internal process manager aborts it but fails to return a `tool_result` error event to the agent. This causes:

1. ❌ Session continues without knowing background process failed
2. ❌ No `tool_result` event in session logs
3. ❌ Repeated `AbortError` messages in Claude Code server logs (20+ times)
4. ❌ No opportunity for agent to handle error or retry

**Real-world impact**: Session #27 attempted to start dev server with 10s timeout, process was aborted silently, session continued for 4.5 hours without awareness.

## Improvements Implemented

### 1. GitHub Issue Drafted

**File**: [docs/claude-code-background-bash-bug.md](claude-code-background-bash-bug.md)

Comprehensive bug report for Claude Code team including:
- Reproduction steps
- Expected vs actual behavior
- Session log evidence
- Server error logs
- Impact assessment
- Proposed fixes (3 options)

**Action Required**: Submit to https://github.com/anthropics/claude-code/issues

### 2. Updated Coding Prompts

**Files Modified**:
- `prompts/coding_prompt_docker.md`
- `prompts/coding_prompt_local.md`

**New Section**: "⚠️ Background Bash Processes - CRITICAL"

**Content**:
- Explains known timeout issue (errors are silent)
- When to use background bash (quick tasks only)
- When NOT to use (servers, long-running processes)
- Correct approach (start servers via init.sh before session)
- Safety checklist if background bash must be used

**Example Guidance**:
```bash
# ❌ WRONG - Will timeout silently after 10-30 seconds
Bash({
  command: "npm run dev",
  run_in_background: true,
  timeout: 10000
})

# ✅ CORRECT - Start servers via init.sh BEFORE session
bash_docker({ command: "./init.sh" })  # Starts servers properly
bash_docker({ command: "sleep 8" })     # Wait for startup
bash_docker({ command: "curl -s http://localhost:5173 && echo 'Ready'" })  # Verify
```

### 3. Defensive Logging in Agent

**File Modified**: `core/agent.py`

**Location**: Lines 215-241 (after tool use logging)

**Features**:
1. **Risky Pattern Detection**: Identifies server commands (npm run dev, npm start, node server, etc.)
2. **Timeout Validation**: Warns if timeout < 60 seconds for server commands
3. **Console Warning**: Prints visible warning to user/developer
4. **Session Logging**: Records warning in session JSONL/TXT logs
5. **All Background Bash Tracking**: Logs every background bash invocation for debugging

**Warning Message**:
```
⚠️  WARNING: Background bash with short timeout (10.0s) for server command.
   Command: PORT=3001 npm run dev
   Risk: Process may timeout and abort silently (known Claude Code bug).
   Recommendation: Start servers via init.sh before session, not during.
   See: prompts/coding_prompt_docker.md - Background Bash section
```

**Code Logic**:
```python
# Detect risky background bash usage
if tool_name == "Bash" and tool_input.get("run_in_background"):
    timeout_ms = tool_input.get("timeout", 120000)
    timeout_sec = timeout_ms / 1000
    command = tool_input.get("command", "")

    # Check for server commands
    risky_patterns = ["npm run dev", "npm start", "node server", "uvicorn", "flask run", "python -m"]
    is_risky = any(pattern in command for pattern in risky_patterns)

    # Warn if risky + short timeout
    if is_risky and timeout_sec < 60:
        # Log and print warning
```

## Benefits

### For Users
- **Immediate visibility**: Warning appears in console during session
- **Session logs**: Warnings recorded for post-session analysis
- **Prevents wasted time**: Catches risky patterns before 4-hour silent failures

### For Developers
- **Debugging aid**: All background bash logged with timeout/command info
- **Pattern detection**: Identifies common risky patterns automatically
- **Actionable guidance**: Provides specific fix (use init.sh instead)

### For Future Sessions
- **Prompt education**: Agents learn correct pattern from updated prompts
- **Reduced incidents**: Fewer silent failures from background bash
- **Better practices**: Encourages proper server lifecycle management

## Testing Recommendations

1. **Test Warning Detection**:
   ```python
   # This should trigger warning
   Bash({
     command: "npm run dev",
     run_in_background: true,
     timeout: 10000  # < 60s
   })
   ```

2. **Test Info Logging**:
   ```python
   # This should log but not warn (non-risky command)
   Bash({
     command: "npm run build",
     run_in_background: true,
     timeout: 30000
   })
   ```

3. **Verify Session Logs**:
   - Check JSONL for `"system_message"` events with subtype `"risky_background_bash_warning"`
   - Check TXT for readable warning messages

## Related Files

- **Bug Report**: [docs/claude-code-background-bash-bug.md](claude-code-background-bash-bug.md)
- **Prompts**: [prompts/coding_prompt_docker.md](../prompts/coding_prompt_docker.md), [prompts/coding_prompt_local.md](../prompts/coding_prompt_local.md)
- **Agent Code**: [core/agent.py](../core/agent.py) (lines 215-241)
- **Session Logger**: [core/observability.py](../core/observability.py) (log_system_message method)

## Next Steps

1. ✅ Submit GitHub issue to Claude Code repository
2. ✅ Test warning detection with example session
3. ✅ Monitor future sessions for warning frequency
4. ✅ Iterate on risky pattern detection based on real-world usage
5. ✅ Consider adding to session quality metrics (track background bash failures)

## Notes

- This is a **defense-in-depth** approach (prompt + runtime detection)
- Warning is informational only (doesn't block execution)
- Root cause fix requires Claude Code team to surface timeout errors
- Workaround (use init.sh for servers) is reliable and recommended
