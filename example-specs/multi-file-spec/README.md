# Multi-File Specification Example

This directory demonstrates how to structure a complex project specification using multiple files.

## Files in this Specification

**Specification Files:**
- **main.md** - The primary specification file (start here)
- **api-design.md** - Complete REST API and WebSocket event specifications
- **database-schema.md** - PostgreSQL schema with Prisma ORM
- **ui-design.md** - UI/UX guidelines and component specifications

**Code Examples:**
- **example-auth.py** - Reference implementation for authentication (FastAPI/JWT pattern)

## How to Use This Spec

### For YokeFlow Users

When creating a new project in YokeFlow:

1. Upload all files in this directory (using the Web UI's multi-file upload)
2. The agent will automatically detect `main.md` as the primary file
3. During initialization, the agent will read `main.md` first
4. The agent will lazy-load other files only when needed for specific tasks

### File Organization Best Practices

**Name your primary file:**
- `main.md` (recommended)
- `spec.md`
- `specification.md`
- `readme.md`

**Reference other files clearly:**
```markdown
## Authentication
For detailed authentication flows, see `api-design.md#authentication`

## Database Design
Complete schema is in `database-schema.md`
```

**Keep related content together:**
- API endpoints → `api-design.md`
- Database models → `database-schema.md`
- UI components → `ui-design.md`
- Technical architecture → `technical-architecture.md`

## Benefits of Multi-File Specs

**Organization:**
- Separate concerns (API, DB, UI, etc.)
- Easier to maintain and update
- Better for large/complex projects

**Collaboration:**
- Different team members can own different files
- Easier to review changes
- Clear separation of responsibilities

**Agent Performance:**
- Lazy-loading saves tokens
- Agent reads only what it needs
- Faster initialization
- Better context management

## Example Project

This specification describes a **Task Management SaaS** application with:
- User authentication
- Multi-tenant workspaces
- Project and task management
- Real-time collaboration
- Comments and attachments

Estimated implementation:
- 15-20 epics
- 120-180 tasks
- 300-500 tests
- 8-12 hours of agent time

## Converting Existing Specs

If you have a single large specification file, consider splitting it into:

1. **main.md** - Overview, features, tech stack, getting started
2. **api-design.md** - All API endpoints and data contracts
3. **database-schema.md** - Data models and relationships
4. **ui-design.md** - Component patterns and layouts
5. **technical-architecture.md** - System design, deployment, infrastructure

---

**Tip:** Use this structure as a template for your own complex projects!
