# API Usage Guide

YokeFlow provides a RESTful API for managing projects and sessions programmatically. The Web UI uses this API, and you can use it directly for automation or integration.

**Version**: 2.0.0

---

## Quick Start

### Start the API Server

```bash
# Start PostgreSQL (required)
docker-compose up -d

# Start API server
uvicorn server.api.app:app --host 0.0.0.0 --port 8000 --reload
```

Server runs at: http://localhost:8000

### Interactive Documentation

- **Swagger UI**: http://localhost:8000/docs (try endpoints interactively)
- **ReDoc**: http://localhost:8000/redoc (reference documentation)
- **Health Check**: http://localhost:8000/api/health

---

## Common API Workflows

### 1. Create a New Project

```bash
curl -X POST http://localhost:8000/api/projects \
  -F "name=my-todo-app" \
  -F "spec_file=@app_spec.txt" \
  -F "sandbox_type=docker"
```

**Response:**
```json
{
  "project_id": "550e8400-...",
  "name": "my-todo-app",
  "is_initialized": false
}
```

### 2. Initialize Project (Session 0)

```bash
curl -X POST http://localhost:8000/api/projects/550e8400-.../initialize
```

**Response:**
```json
{
  "session_id": "abc123...",
  "status": "running",
  "type": "initializer"
}
```

This creates the complete roadmap (epics → tasks → tests).

### 3. Check Progress

```bash
curl http://localhost:8000/api/projects/550e8400-.../progress
```

**Response:**
```json
{
  "total_epics": 20,
  "completed_epics": 0,
  "total_tasks": 150,
  "completed_tasks": 0,
  "task_completion_pct": 0.0
}
```

### 4. Start Coding Session

```bash
curl -X POST http://localhost:8000/api/projects/550e8400-.../coding/start
```

**Response:**
```json
{
  "session_id": "def456...",
  "status": "running",
  "type": "coding"
}
```

### 5. Monitor Real-Time Progress (WebSocket)

```javascript
// JavaScript example
const ws = new WebSocket('ws://localhost:8000/api/ws/550e8400-...');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Progress:', data.progress);
  console.log('Current task:', data.current_task);
};
```

---

## API Endpoints Reference

### Health & Status

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Basic health check |
| `GET` | `/health/detailed` | Detailed component status ⭐ NEW v2.0 |

### Projects

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/projects` | List all projects |
| `POST` | `/api/projects` | Create new project |
| `GET` | `/api/projects/{id}` | Get project details |
| `GET` | `/api/projects/{id}/progress` | Get progress stats |
| `DELETE` | `/api/projects/{id}` | Delete project |

### Sessions

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/projects/{id}/initialize` | Start initialization |
| `POST` | `/api/projects/{id}/coding/start` | Start coding session |
| `POST` | `/api/projects/{id}/coding/stop` | Stop current session |
| `GET` | `/api/projects/{id}/sessions` | List all sessions |
| `GET` | `/api/projects/{id}/sessions/{sid}` | Get session details |
| `GET` | `/api/sessions/{sid}/logs` | Get session logs ⭐ NEW v2.0 |
| `POST` | `/api/sessions/{sid}/pause` | Pause active session ⭐ NEW v2.0 |
| `POST` | `/api/sessions/{sid}/resume` | Resume paused session ⭐ NEW v2.0 |

### Tasks & Epics

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/tasks/{task_id}` | Get task details ⭐ NEW v2.0 |
| `PATCH` | `/api/tasks/{task_id}` | Update task status ⭐ NEW v2.0 |
| `GET` | `/api/epics/{epic_id}/progress` | Get epic progress ⭐ NEW v2.0 |

### Quality & Verification

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/sessions/{sid}/quality-review` | Trigger quality review ⭐ NEW v2.0 |
| `GET` | `/api/projects/{id}/quality-metrics` | Get quality metrics ⭐ NEW v2.0 |

### Real-Time

| Method | Endpoint | Description |
|--------|----------|-------------|
| `WS` | `/api/ws/{id}` | WebSocket for live updates |

⭐ **v2.0 New Endpoints** - See sections below for usage examples

**See interactive documentation at http://localhost:8000/docs for complete endpoint details**

---

## Authentication

### Development Mode (Default)

No authentication required when `UI_PASSWORD` is not set:

```bash
# Just call the API directly
curl http://localhost:8000/api/projects
```

### Production Mode

When `UI_PASSWORD` is set, you need a JWT token:

**1. Login:**
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"password": "your-password"}'
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

**2. Use Token:**
```bash
curl http://localhost:8000/api/projects \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."
```

**See [authentication.md](authentication.md) for details**

---

## WebSocket Events

Subscribe to project updates:

```javascript
const ws = new WebSocket('ws://localhost:8000/api/ws/PROJECT_ID');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);

  switch (data.type) {
    case 'session_update':
      console.log('Session:', data.status);
      break;
    case 'progress_update':
      console.log('Progress:', data.progress.task_completion_pct + '%');
      break;
    case 'tool_use':
      console.log('Tool:', data.tool_name);
      break;
    case 'session_complete':
      console.log('Session finished:', data.session_id);
      break;
  }
};
```

**Event Types:**
- `session_update` - Session status changed
- `progress_update` - Task/test progress updated
- `tool_use` - Agent used a tool
- `tool_result` - Tool execution result
- `session_complete` - Session finished
- `error` - Error occurred

---

## Example: Automated Project Creation

```python
import requests

API_URL = "http://localhost:8000"

# 1. Create project
with open('app_spec.txt', 'rb') as f:
    response = requests.post(
        f"{API_URL}/api/projects",
        files={'spec_file': f},
        data={
            'name': 'automated-project',
            'sandbox_type': 'docker'
        }
    )
    project = response.json()
    project_id = project['project_id']

# 2. Initialize (creates roadmap)
response = requests.post(
    f"{API_URL}/api/projects/{project_id}/initialize"
)
session = response.json()
print(f"Initialization started: {session['session_id']}")

# 3. Poll until initialization complete
import time
while True:
    response = requests.get(
        f"{API_URL}/api/projects/{project_id}/sessions/{session['session_id']}"
    )
    status = response.json()

    if status['status'] == 'completed':
        print("Initialization complete!")
        break
    elif status['status'] == 'error':
        print("Error:", status.get('error_message'))
        break

    time.sleep(5)

# 4. Start coding sessions
response = requests.post(
    f"{API_URL}/api/projects/{project_id}/coding/start"
)
print("Coding session started")
```

---

## Example: Monitor Progress

```python
import requests

API_URL = "http://localhost:8000"
PROJECT_ID = "550e8400-..."

# Get current progress
response = requests.get(f"{API_URL}/api/projects/{PROJECT_ID}/progress")
progress = response.json()

print(f"Tasks: {progress['completed_tasks']}/{progress['total_tasks']}")
print(f"Tests: {progress['passing_tests']}/{progress['total_tests']}")
print(f"Completion: {progress['task_completion_pct']:.1f}%")
```

---

## Example: WebSocket with Python

```python
import asyncio
import websockets
import json

async def monitor_project(project_id):
    uri = f"ws://localhost:8000/api/ws/{project_id}"

    async with websockets.connect(uri) as websocket:
        while True:
            message = await websocket.recv()
            data = json.loads(message)

            if data['type'] == 'progress_update':
                progress = data['progress']
                print(f"Progress: {progress['task_completion_pct']:.1f}%")

            elif data['type'] == 'session_complete':
                print("Session finished!")
                break

# Run
asyncio.run(monitor_project("550e8400-..."))
```

---

## CORS Configuration

The API supports CORS for web applications:

**Default allowed origins:**
- `http://localhost:3000` (Next.js dev server)
- `http://localhost:5173` (Vite dev server)

**To add custom origins:**

Set `CORS_ORIGINS` in `.env`:
```bash
CORS_ORIGINS=http://localhost:3000,https://my-domain.com
```

---

## Error Handling

**Common HTTP Status Codes:**

| Code | Meaning | Example |
|------|---------|---------|
| `200` | Success | Project retrieved |
| `201` | Created | Project created |
| `400` | Bad Request | Missing spec file |
| `401` | Unauthorized | Invalid/missing token |
| `404` | Not Found | Project doesn't exist |
| `409` | Conflict | Session already running |
| `500` | Server Error | Database connection failed |

**Error Response Format:**
```json
{
  "detail": "Project with name 'my-project' already exists"
}
```

---

## Rate Limiting

Currently no rate limiting is implemented. For production deployment, consider adding:
- Nginx rate limiting
- API gateway (Kong, AWS API Gateway)
- Application-level rate limiting

---

## Troubleshooting

### Cannot connect to API

**Check server is running:**
```bash
curl http://localhost:8000/api/health
```

**Should return:**
```json
{"status": "healthy", "timestamp": "..."}
```

### 401 Unauthorized

**Development mode:** Ensure `UI_PASSWORD` is not set in `.env`

**Production mode:** Get a token via `/api/auth/login` and use it in requests

### 500 Database errors

**Ensure PostgreSQL is running:**
```bash
docker ps | grep postgres
```

**Check connection:**
```bash
psql $DATABASE_URL -c "SELECT 1;"
```

### WebSocket disconnects

**Check project exists:**
```bash
curl http://localhost:8000/api/projects/PROJECT_ID
```

**Check firewall/proxy settings** - WebSocket needs persistent connection

---

## v2.0 New Endpoints

### Session Management

#### Get Session Logs

Retrieve structured logs for a session with pagination and filtering:

```bash
# Get latest 100 log entries
curl "http://localhost:8000/api/sessions/SESSION_ID/logs?offset=0&limit=100"

# Filter by log level
curl "http://localhost:8000/api/sessions/SESSION_ID/logs?level=error"
```

**Response:**
```json
{
  "logs": [
    {
      "timestamp": "2026-01-08T15:30:45Z",
      "level": "info",
      "message": "Task completed successfully",
      "task_id": "123"
    }
  ],
  "total": 1250,
  "offset": 0,
  "limit": 100
}
```

#### Pause/Resume Sessions

```bash
# Pause an active session
curl -X POST http://localhost:8000/api/sessions/SESSION_ID/pause

# Resume a paused session
curl -X POST http://localhost:8000/api/sessions/SESSION_ID/resume
```

Both return `204 No Content` on success.

### Task & Epic Management

#### Get Task Details

```bash
curl http://localhost:8000/api/tasks/42
```

**Response:**
```json
{
  "id": 42,
  "name": "Implement user authentication",
  "status": "in_progress",
  "description": "Add JWT-based authentication",
  "epic_id": 5
}
```

#### Update Task Status

```bash
curl -X PATCH http://localhost:8000/api/tasks/42 \
  -H "Content-Type: application/json" \
  -d '{"status": "completed"}'
```

#### Get Epic Progress

```bash
curl http://localhost:8000/api/epics/5/progress
```

**Response:**
```json
{
  "epic_id": 5,
  "name": "User Management",
  "total_tasks": 15,
  "completed_tasks": 8,
  "in_progress_tasks": 2,
  "pending_tasks": 5,
  "progress_percentage": 53.3,
  "status": "in_progress"
}
```

### Quality & Verification

#### Trigger Quality Review

```bash
curl -X POST http://localhost:8000/api/sessions/SESSION_ID/quality-review \
  -H "Content-Type: application/json" \
  -d '{"review_type": "comprehensive"}'
```

**Response:**
```json
{
  "id": "review-abc123",
  "session_id": "SESSION_ID",
  "review_type": "comprehensive",
  "status": "pending"
}
```

#### Get Quality Metrics

```bash
curl http://localhost:8000/api/projects/PROJECT_ID/quality-metrics
```

**Response:**
```json
{
  "project_id": "PROJECT_ID",
  "code_quality_score": 8.5,
  "test_coverage": 85.3,
  "issues_found": 12,
  "issues_resolved": 8,
  "last_review": "2026-01-08T15:30:45Z"
}
```

### Health Check

#### Detailed Health Status

Get component-level health information:

```bash
curl http://localhost:8000/health/detailed
```

**Response:**
```json
{
  "status": "healthy",
  "database": {
    "status": "healthy",
    "pool_size": 10,
    "active_connections": 2
  },
  "mcp_server": {
    "status": "healthy",
    "version": "1.0.0"
  },
  "disk": {
    "status": "healthy",
    "free_space_gb": 150.5
  },
  "sessions": {
    "active": 2,
    "paused": 1
  }
}
```

---

## Related Documentation

- **[authentication.md](authentication.md)** - Authentication system details
- **[deployment-guide.md](deployment-guide.md)** - Production deployment
- **[developer-guide.md](developer-guide.md)** - Platform architecture
- **[verification-system.md](verification-system.md)** - Automatic verification system

---

## Need Help?

- **Interactive docs:** http://localhost:8000/docs
- **API reference:** http://localhost:8000/redoc
- **GitHub issues:** Report bugs or request features

The Swagger UI at `/docs` is the best place to explore and test the API interactively!
