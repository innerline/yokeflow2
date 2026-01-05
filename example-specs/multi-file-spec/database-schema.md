# Database Schema Specification

Complete PostgreSQL database schema using Prisma ORM.

## Schema Overview

The database follows a multi-tenant architecture with workspaces as the top-level container.

```
Workspaces
  └─ Projects
      └─ Tasks
          ├─ Comments
          └─ Attachments
```

## Prisma Schema

```prisma
// User model
model User {
  id            String   @id @default(uuid())
  email         String   @unique
  passwordHash  String
  name          String
  avatarUrl     String?
  createdAt     DateTime @default(now())
  updatedAt     DateTime @updatedAt

  // Relations
  workspaceMembers WorkspaceMember[]
  assignedTasks    Task[]            @relation("TaskAssignee")
  createdTasks     Task[]            @relation("TaskCreator")
  comments         Comment[]
  refreshTokens    RefreshToken[]

  @@index([email])
}

// Refresh tokens for JWT authentication
model RefreshToken {
  id        String   @id @default(uuid())
  token     String   @unique
  userId    String
  expiresAt DateTime
  createdAt DateTime @default(now())

  user User @relation(fields: [userId], references: [id], onDelete: Cascade)

  @@index([userId])
  @@index([token])
}

// Workspace (multi-tenant container)
model Workspace {
  id          String   @id @default(uuid())
  name        String
  slug        String   @unique
  description String?
  createdAt   DateTime @default(now())
  updatedAt   DateTime @updatedAt

  // Relations
  members  WorkspaceMember[]
  projects Project[]

  @@index([slug])
}

// Workspace membership with roles
model WorkspaceMember {
  id          String   @id @default(uuid())
  userId      String
  workspaceId String
  role        Role     @default(MEMBER)
  joinedAt    DateTime @default(now())

  user      User      @relation(fields: [userId], references: [id], onDelete: Cascade)
  workspace Workspace @relation(fields: [workspaceId], references: [id], onDelete: Cascade)

  @@unique([userId, workspaceId])
  @@index([userId])
  @@index([workspaceId])
}

enum Role {
  ADMIN
  MANAGER
  MEMBER
}

// Project within a workspace
model Project {
  id          String        @id @default(uuid())
  workspaceId String
  name        String
  description String?
  color       String        @default("#3B82F6")
  status      ProjectStatus @default(ACTIVE)
  createdAt   DateTime      @default(now())
  updatedAt   DateTime      @updatedAt

  workspace Workspace @relation(fields: [workspaceId], references: [id], onDelete: Cascade)
  tasks     Task[]

  @@index([workspaceId])
  @@index([status])
}

enum ProjectStatus {
  ACTIVE
  ARCHIVED
}

// Task within a project
model Task {
  id          String       @id @default(uuid())
  projectId   String
  title       String
  description String?
  status      TaskStatus   @default(TODO)
  priority    TaskPriority @default(MEDIUM)
  assigneeId  String?
  creatorId   String
  dueDate     DateTime?
  position    Int          @default(0) // For ordering
  createdAt   DateTime     @default(now())
  updatedAt   DateTime     @updatedAt

  project     Project      @relation(fields: [projectId], references: [id], onDelete: Cascade)
  assignee    User?        @relation("TaskAssignee", fields: [assigneeId], references: [id], onDelete: SetNull)
  creator     User         @relation("TaskCreator", fields: [creatorId], references: [id])
  comments    Comment[]
  attachments Attachment[]
  labels      TaskLabel[]

  @@index([projectId])
  @@index([assigneeId])
  @@index([status])
  @@index([priority])
  @@index([dueDate])
}

enum TaskStatus {
  TODO
  IN_PROGRESS
  REVIEW
  DONE
}

enum TaskPriority {
  LOW
  MEDIUM
  HIGH
  URGENT
}

// Labels/tags for tasks
model Label {
  id          String   @id @default(uuid())
  workspaceId String
  name        String
  color       String   @default("#6B7280")
  createdAt   DateTime @default(now())

  tasks TaskLabel[]

  @@unique([workspaceId, name])
  @@index([workspaceId])
}

// Many-to-many relationship between tasks and labels
model TaskLabel {
  taskId  String
  labelId String

  task  Task  @relation(fields: [taskId], references: [id], onDelete: Cascade)
  label Label @relation(fields: [labelId], references: [id], onDelete: Cascade)

  @@id([taskId, labelId])
  @@index([taskId])
  @@index([labelId])
}

// Comments on tasks
model Comment {
  id        String   @id @default(uuid())
  taskId    String
  authorId  String
  content   String
  mentions  String[] // Array of mentioned user IDs
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt

  task   Task @relation(fields: [taskId], references: [id], onDelete: Cascade)
  author User @relation(fields: [authorId], references: [id])

  @@index([taskId])
  @@index([authorId])
}

// File attachments on tasks
model Attachment {
  id        String   @id @default(uuid())
  taskId    String
  filename  String
  filesize  Int
  mimetype  String
  path      String // Storage path
  url       String // Public URL
  createdAt DateTime @default(now())

  task Task @relation(fields: [taskId], references: [id], onDelete: Cascade)

  @@index([taskId])
}
```

## Relationships

### User ↔ Workspace (Many-to-Many)
- Users can belong to multiple workspaces
- Each membership has a role (ADMIN, MANAGER, MEMBER)
- Implemented via `WorkspaceMember` join table

### Workspace → Projects (One-to-Many)
- Each workspace contains multiple projects
- Projects are deleted when workspace is deleted (CASCADE)

### Project → Tasks (One-to-Many)
- Each project contains multiple tasks
- Tasks are deleted when project is deleted (CASCADE)

### User ↔ Task (Many-to-Many)
- Users can be assigned to multiple tasks
- Tasks track both assignee and creator
- Assignment is optional (can be NULL)

### Task → Comments (One-to-Many)
- Each task can have multiple comments
- Comments are deleted when task is deleted (CASCADE)

### Task → Attachments (One-to-Many)
- Each task can have multiple file attachments
- Attachments are deleted when task is deleted (CASCADE)

### Task ↔ Label (Many-to-Many)
- Tasks can have multiple labels
- Labels can be applied to multiple tasks
- Implemented via `TaskLabel` join table

## Indexes

Performance indexes are created on:
- Foreign keys for all relationships
- Status and priority fields for filtering
- Due date for sorting
- Email for user lookups
- Workspace slug for URL routing
- Unique constraints on critical fields

## Migrations

Use Prisma Migrate for database migrations:

```bash
# Create migration
npx prisma migrate dev --name init

# Apply migrations in production
npx prisma migrate deploy

# Generate Prisma Client
npx prisma generate
```

## Seed Data

For development, seed the database with:
- 1 admin user
- 1 test workspace
- 2 projects with sample tasks
- Various labels

```typescript
// prisma/seed.ts
import { PrismaClient, Role } from '@prisma/client';

const prisma = new PrismaClient();

async function main() {
  // Create admin user
  const admin = await prisma.user.create({
    data: {
      email: 'admin@example.com',
      passwordHash: 'hashed_password',
      name: 'Admin User',
    },
  });

  // Create workspace
  const workspace = await prisma.workspace.create({
    data: {
      name: 'Demo Workspace',
      slug: 'demo',
      members: {
        create: {
          userId: admin.id,
          role: Role.ADMIN,
        },
      },
    },
  });

  // ... seed projects, tasks, etc.
}

main();
```

## Data Validation

Use Prisma + Zod for comprehensive validation:
- Email format validation
- Password strength requirements (min 8 chars)
- Workspace slug format (lowercase, alphanumeric, hyphens)
- File size limits for attachments (max 10MB)
- Content length limits (title max 200 chars, description max 5000 chars)

## Performance Considerations

- Use connection pooling (max 10 connections)
- Implement database query caching for frequently accessed data
- Use SELECT only required fields (avoid SELECT *)
- Paginate large result sets (default 50 items per page)
- Use database transactions for multi-step operations

---

**Implementation Notes:**
- All timestamps use UTC timezone
- UUIDs for all primary keys for security and distribution
- Soft deletes not implemented (use status fields where needed)
- Audit logs can be added later as a separate feature
