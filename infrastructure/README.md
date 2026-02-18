# YokeFlow Infrastructure

Unified Docker infrastructure combining YokeFlow2 with local-ai-packaged services.

## Quick Start

### Minimal Setup (Development)

Just the core services - YokeFlow API and PostgreSQL:

```bash
cd infrastructure
docker compose up -d
```

This starts:
- YokeFlow API on port 8000
- PostgreSQL on port 5432

### With AI Services

Add vector database, knowledge graph, and workflow automation:

```bash
docker compose --profile ai up -d
```

This adds:
- Qdrant (vector database) on port 6333
- Neo4j (knowledge graph) on ports 7474, 7687
- n8n (workflows) on port 5678

### Full Stack

All services including Flowise and SearXNG:

```bash
docker compose --profile full up -d
```

### Production

With reverse proxy and observability:

```bash
docker compose --profile production up -d
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     YokeFlow Platform                        │
├─────────────────────────────────────────────────────────────┤
│  yokeflow-api    │ yokeflow-web  │   postgres   │  pgadmin  │
│  (port 8000)     │ (port 3000)   │  (port 5432) │(port 5050)│
├─────────────────────────────────────────────────────────────┤
│  AI Services (--profile ai/full)                            │
│  qdrant │ neo4j │ n8n │ flowise │ searxng │ langfuse       │
├─────────────────────────────────────────────────────────────┤
│  Reverse Proxy (--profile production)                        │
│  caddy (ports 80, 443)                                       │
└─────────────────────────────────────────────────────────────┘
```

## LLM Configuration

### Provider Priority

| Provider | Status | Use Case |
|----------|--------|----------|
| **Claude** | PRIMARY | Default for all operations |
| **LMStudio** | MANDATORY | Personal Obsidian Vault (privacy) |
| **llama.cpp** | Future | Alternative local inference |

### LMStudio Setup

1. Download from https://lmstudio.ai/
2. Open LMStudio and download a model
3. Go to Local Server tab → Start Server (port 1234)
4. Set environment variable:
   ```bash
   LMSTUDIO_API_BASE=http://localhost:1234/v1
   ```

### Vault Routing

The LLM router automatically selects providers based on vault path:

- **Personal Vault** → LMStudio (mandatory for privacy)
- **Agents Vault** → Claude (quality)
- **Other/None** → Claude (default)

Configure vault paths in `.env`:

```bash
PERSONAL_VAULT_PATH=/path/to/personal/obsidian
AGENTS_VAULT_PATH=/path/to/agents/vault
```

## Service Endpoints

| Service | Port | URL |
|---------|------|-----|
| YokeFlow API | 8000 | http://localhost:8000 |
| API Docs | 8000 | http://localhost:8000/docs |
| Web UI | 3000 | http://localhost:3000 |
| pgAdmin | 5050 | http://localhost:5050 |
| n8n | 5678 | http://localhost:5678 |
| Neo4j Browser | 7474 | http://localhost:7474 |
| Flowise | 3001 | http://localhost:3001 |
| SearXNG | 8080 | http://localhost:8080 |
| Langfuse | 3002 | http://localhost:3002 |

## Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
# Core
DATABASE_URL=postgresql://yokeflow:yokeflow_dev_password@postgres:5432/yokeflow
CLAUDE_API_KEY=your_key

# LLM Providers
LLM_PROVIDER=claude
LMSTUDIO_API_BASE=http://host.docker.internal:1234/v1

# Vaults
PERSONAL_VAULT_PATH=/path/to/personal/vault
AGENTS_VAULT_PATH=/path/to/agents/vault
```

## Volumes

| Volume | Purpose |
|--------|---------|
| yokeflow_postgres_data | PostgreSQL data |
| yokeflow_qdrant_storage | Vector embeddings |
| yokeflow_neo4j_data | Knowledge graph |
| yokeflow_n8n_storage | n8n workflows |

## Common Commands

```bash
# Start services
docker compose up -d

# View logs
docker compose logs -f yokeflow-api

# Stop services
docker compose down

# Stop and remove volumes
docker compose down -v

# Rebuild after code changes
docker compose up -d --build

# Check service health
docker compose ps
```

## Troubleshooting

### LMStudio Connection Failed

- Ensure LMStudio is running on the host
- Check port 1234 is accessible
- Use `host.docker.internal` in Docker config

### Database Migration Issues

```bash
# Reset database
docker compose down -v
docker compose up -d
```

### Port Conflicts

Check what's using a port:
```bash
lsof -i :8000
```

Change port in `.env`:
```bash
YOKEFLOW_PORT=8001
```

## Next Steps

1. Configure your `.env` file
2. Set up LMStudio for Personal Vault access
3. Start with `docker compose up -d`
4. Access the API at http://localhost:8000/docs
5. Access Web UI at http://localhost:3000
