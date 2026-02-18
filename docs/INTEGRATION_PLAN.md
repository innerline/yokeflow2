# YokeFlow Integration Plan

**Goal**: Combine YokeFlow2, local-ai-packaged, obsidian-ai-agent, and Remote agent into a unified autonomous AI development platform with local LLM support, remote control, and knowledge management.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           UNIFIED PLATFORM                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  REMOTE CONTROL LAYER (from Remote Agent)                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                       │
│  │   Slack      │  │  Telegram    │  │   GitHub     │  ← Control from anywhere │
│  │   Adapter    │  │   Adapter    │  │   Webhooks   │                       │
│  └──────────────┘  └──────────────┘  └──────────────┘                       │
├─────────────────────────────────────────────────────────────────────────────┤
│  YOKEFLOW CORE (Autonomous Development Engine)                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Session Orchestrator │ MCP Task Manager │ Quality System │ API      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────────────┤
│  KNOWLEDGE LAYER (from Obsidian AI Agent)                                   │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐          │
│  │  Vault Query     │  │  Context Engine  │  │  Note Manager    │          │
│  │  Tools (MCP)     │  │  (RAG)           │  │  (Auto-docs)     │          │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘          │
├─────────────────────────────────────────────────────────────────────────────┤
│  AI INFRASTRUCTURE (from local-ai-packaged)                                 │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐│
│  │  LMStudio  │ │  Supabase  │ │    n8n     │ │  Flowise   │ │  Neo4j     ││
│  │ (Local LLM)│ │ (DB+Auth)  │ │(Workflows) │ │(Agent Dev) │ │(Knowledge) ││
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘ └────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Integration Components

### 1. Infrastructure Layer (local-ai-packaged)

**What we use:**
- **Claude API**: Default LLM for all operations (primary)
- **LMStudio**: Local LLM inference - **MANDATORY for Personal Obsidian Vault**, backup for other tasks
- **llama.cpp**: Alternative local inference (future support)
- **Supabase**: Replace raw PostgreSQL + add Auth + Realtime + Storage
- **n8n**: Workflow automation for complex multi-step operations
- **Flowise**: Visual agent builder for prototyping
- **Neo4j**: Knowledge graph for project relationships
- **SearXNG**: Private web search for research tasks
- **Langfuse**: Observability for LLM calls

**LLM Routing Rules:**
| Vault Type | LLM Provider | Reason |
|------------|--------------|--------|
| Personal Obsidian Vault | **LMStudio** (mandatory) | Privacy - no data leaves local |
| Agents (Local) Vault | **Claude** (with agent models) | Quality - use Claude's selected models |
| Generated Projects | **Claude** (default) | Quality + reliability |
| Fallback/Backup | **LMStudio** | When Claude unavailable |

**Integration points:**
```yaml
# docker-compose.yml additions
services:
  yokeflow-api:
    build: ./server
    environment:
      - CLAUDE_API_KEY=${CLAUDE_API_KEY}  # Primary
      - LMSTUDIO_API_BASE=http://host.docker.internal:1234/v1  # For Personal Vault
      - LLAMACPP_API_BASE=http://host.docker.internal:8080/v1  # Future
      - DATABASE_URL=postgresql://...
      - SUPABASE_URL=http://kong:8000
      - PERSONAL_VAULT_PATH=/vaults/personal  # Must use LMStudio
      - AGENTS_VAULT_PATH=/vaults/agents      # Uses Claude
    depends_on:
      - db  # Supabase Postgres
    extra_hosts:
      - "host.docker.internal:host-gateway"  # Access host LMStudio
    volumes:
      - ${PERSONAL_VAULT_PATH}:/vaults/personal:ro
      - ${AGENTS_VAULT_PATH}:/vaults/agents:rw
```

**Note on Local LLM Setup:**
- LMStudio runs on the host machine (not in Docker) for GPU access
- llama.cpp also runs on host for direct hardware access
- Both expose OpenAI-compatible APIs that YokeFlow can use
- **Personal Vault queries ALWAYS use LMStudio** for privacy

### 2. Remote Control Layer (Remote Agent)

**What we use:**
- Platform adapters (Slack, Telegram, GitHub)
- Command handler system
- Session orchestration for remote control
- Streaming response patterns

**Integration points:**
```python
# New file: server/remote/adapters/__init__.py
from abc import ABC, abstractmethod
from typing import AsyncIterator

class IPlatformAdapter(ABC):
    @abstractmethod
    async def send_message(self, conversation_id: str, message: str) -> None: ...

    @abstractmethod
    async def stream_message(self, conversation_id: str, stream: AsyncIterator[str]) -> None: ...

# New file: server/remote/command_handler.py
class RemoteCommandHandler:
    """Process remote commands from Slack/Telegram/GitHub"""

    async def handle_command(self, platform: str, conversation_id: str, command: str) -> None:
        # Commands: /status, /pause, /resume, /review, /deploy
        pass
```

**API endpoints to add:**
```
POST /api/remote/slack/events     # Slack events
POST /api/remote/telegram/webhook # Telegram webhook
POST /api/remote/github/webhook   # GitHub webhooks
GET  /api/remote/status           # Remote session status
```

### 3. Knowledge Layer (obsidian-ai-agent)

**What we use:**
- Vault query tools (search, list, find_related)
- Context engine for semantic search
- Note manager for auto-documentation
- OpenAI-compatible API for integration

**Integration points:**
```python
# New MCP tools: mcp-task-manager/src/tools/knowledge.ts

export async function queryProjectKnowledge(
  project_id: string,
  query: string,
  operation: 'search' | 'find_related' | 'recent_changes'
): Promise<QueryResult> {
  // Query the project's Obsidian vault
}

export async function createProjectDoc(
  project_id: string,
  path: string,
  content: string
): Promise<void> {
  // Auto-document generated code
}

export async function getContextForTask(
  task_id: string
): Promise<string[]> {
  // Get relevant context from knowledge base
}
```

---

## New Directory Structure

```
yokeflow2/
├── server/
│   ├── agent/              # Existing - Core agent logic
│   ├── api/                # Existing - REST API
│   ├── database/           # Existing - DB operations
│   ├── remote/             # NEW - Remote control layer
│   │   ├── adapters/
│   │   │   ├── slack.py
│   │   │   ├── telegram.py
│   │   │   ├── github.py
│   │   │   └── base.py
│   │   ├── commands.py
│   │   └── session_sync.py
│   ├── knowledge/          # NEW - Knowledge management
│   │   ├── vault_manager.py
│   │   ├── context_engine.py
│   │   └── auto_docs.py
│   ├── llm/                # NEW - LLM abstraction
│   │   ├── claude_client.py
│   │   ├── openai_compatible.py  # LMStudio/llama.cpp
│   │   └── provider_router.py
│   └── utils/
├── infrastructure/         # NEW - Docker infra
│   ├── docker-compose.yml  # Unified compose
│   ├── supabase/
│   └── n8n/
├── web-ui/                 # Existing
├── mcp-task-manager/       # Existing + new tools
└── docs/
```

---

## Implementation Phases

### Phase 1: Infrastructure Foundation (Priority: High)
**Goal**: Set up local-ai-packaged as the infrastructure backbone with smart LLM routing

**Tasks:**
1. Create unified `docker-compose.yml` combining YokeFlow + local-ai-packaged
2. Keep Claude as default LLM provider
3. Add LMStudio provider for Personal Vault (mandatory) + backup
4. Add llama.cpp support as future alternative provider
5. Implement LLM router that routes by vault type
6. Configure Supabase connection for auth + realtime
7. Set up Neo4j for project knowledge graphs
8. Add Langfuse for observability

**Files to create/modify:**
- `infrastructure/docker-compose.yml` (new)
- `server/llm/provider_router.py` (new - smart routing by vault type)
- `server/llm/claude_client.py` (existing Claude integration)
- `server/llm/openai_compatible.py` (LMStudio/llama.cpp client)
- `server/utils/config.py` (add vault paths + LMStudio settings)
- `.env.example` (add all new services)

### Phase 2: Remote Control Layer (Priority: High)
**Goal**: Control YokeFlow from Slack/Telegram/GitHub

**Tasks:**
1. Port Remote Agent's adapter interfaces to Python
2. Implement Slack adapter with Socket Mode
3. Implement Telegram adapter with polling
4. Implement GitHub adapter with webhooks
5. Create command handler for YokeFlow operations
6. Add streaming response support

**Files to create:**
- `server/remote/adapters/base.py`
- `server/remote/adapters/slack.py`
- `server/remote/adapters/telegram.py`
- `server/remote/adapters/github.py`
- `server/remote/commands.py`
- `server/api/routes/remote.py`

### Phase 3: Knowledge Integration (Priority: Medium)
**Goal**: Auto-document projects and provide context-aware assistance

**Tasks:**
1. Port obsidian-ai-agent's vault tools to YokeFlow MCP
2. Create per-project vault in `generations/{project}/knowledge/`
3. Auto-generate documentation during coding sessions
4. Build context engine for task-relevant knowledge retrieval
5. Add knowledge search to agent prompts

**Files to create:**
- `server/knowledge/vault_manager.py`
- `server/knowledge/context_engine.py`
- `server/knowledge/auto_docs.py`
- `mcp-task-manager/src/tools/knowledge.ts`

### Phase 4: Unified Experience (Priority: Medium)
**Goal**: Seamless integration of all components

**Tasks:**
1. Update Web UI with remote control dashboard
2. Add LLM provider switcher (Claude vs Ollama)
3. Create project knowledge browser
4. Add n8n workflow templates for YokeFlow
5. Build Flowise agent components for YokeFlow

### Phase 5: Polish & Production (Priority: Low)
**Goal**: Production-ready unified platform

**Tasks:**
1. Comprehensive integration tests
2. Performance optimization
3. Security hardening
4. Documentation
5. CI/CD pipeline

---

## Configuration

### Environment Variables (Unified)

```bash
# Core YokeFlow
YOKEFLOW_PORT=8000
DATABASE_URL=postgresql://...

# LLM Providers
CLAUDE_API_KEY=sk-ant-...           # PRIMARY - Default for everything
LMSTUDIO_API_BASE=http://localhost:1234/v1   # MANDATORY for Personal Vault
LMSTUDIO_MODEL=local-model          # Model name as shown in LMStudio
LLAMACPP_API_BASE=http://localhost:8080/v1   # llama.cpp server (future)
LLM_PROVIDER=claude                 # Default: claude (lmstudio for Personal Vault auto)

# Vault Configuration
PERSONAL_VAULT_PATH=/path/to/personal/obsidian  # Uses LMStudio (mandatory)
AGENTS_VAULT_PATH=/path/to/agents/vault         # Uses Claude with agent models

# Remote Control (choose platforms)
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
TELEGRAM_BOT_TOKEN=...
GITHUB_TOKEN=ghp_...
GITHUB_APP_ID=...
GITHUB_PRIVATE_KEY=-----

# Knowledge
OBSIDIAN_VAULT_PATH=/path/to/vault   # Optional - for personal vault
AUTO_DOCS_ENABLED=true

# Infrastructure (from local-ai-packaged)
SUPABASE_URL=http://localhost:8000
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
```

---

## API Additions

### Remote Control Endpoints

```yaml
# New endpoints in server/api/app.py

POST /api/remote/slack/events:
  description: Handle Slack events (Socket Mode or webhooks)
  body: { type: string, ... }

POST /api/remote/telegram/webhook:
  description: Handle Telegram webhook updates
  body: { update_id: int, message: {...} }

POST /api/remote/github/webhook:
  headers: { X-Hub-Signature-256: string }
  body: { action: string, ... }

GET /api/remote/sessions:
  description: List active remote sessions
  response: [{ id, platform, conversation_id, project_id, status }]

POST /api/remote/sessions/{id}/command:
  description: Execute command on remote session
  body: { command: string, args: [...] }
```

### Knowledge Endpoints

```yaml
GET /api/projects/{id}/knowledge:
  description: Get project knowledge vault status
  response: { vault_path, notes_count, last_indexed }

POST /api/projects/{id}/knowledge/search:
  description: Search project knowledge
  body: { query: string, limit: int }
  response: { results: [...] }

POST /api/projects/{id}/knowledge/sync:
  description: Sync generated docs to knowledge vault
  response: { synced: int, errors: [...] }
```

---

## Benefits of Integration

1. **Cost Savings**: Use LMStudio/llama.cpp with local LLMs instead of Claude API
2. **Remote Control**: Manage projects from Slack/Telegram/GitHub
3. **Auto-Documentation**: Every project gets a knowledge base
4. **Visual Workflows**: n8n + Flowise for complex automations
5. **Knowledge Graphs**: Neo4j for project relationships
6. **Full Stack Auth**: Supabase Auth for multi-user support
7. **Observability**: Langfuse for LLM debugging
8. **Private Search**: SearXNG for research without tracking
9. **Flexibility**: Switch between Claude, LMStudio, and llama.cpp seamlessly

---

## Migration Strategy

### For Existing YokeFlow Users

1. **No breaking changes** - all existing functionality preserved
2. **Opt-in features** - remote control and knowledge are optional
3. **Backward compatible** - Claude API still works alongside Ollama
4. **Gradual adoption** - can enable features one at a time

### Recommended Setup Order

1. Start with infrastructure (Phase 1)
2. Add remote control (Phase 2)
3. Enable knowledge management (Phase 3)
4. Polish and productionize (Phases 4-5)

---

## Questions to Resolve

1. ~~**LLM Strategy**~~: ✅ RESOLVED - Claude is default, LMStudio mandatory for Personal Vault
2. **Multi-tenancy**: Single-user (current) or add Supabase Auth for teams?
3. **Knowledge Scope**: Per-project vaults only, or shared knowledge base?
4. **Remote Defaults**: Which platforms to support out of the box?
5. **Vault Paths**: Confirm exact paths for Personal Vault and Agents Vault

---

## Next Steps

1. Review and approve this integration plan
2. Set up development environment with all services
3. Begin Phase 1 implementation
4. Create feature branches for each phase
5. Test integration thoroughly before merging

---

*Generated: February 2026*
*Version: 1.0*
