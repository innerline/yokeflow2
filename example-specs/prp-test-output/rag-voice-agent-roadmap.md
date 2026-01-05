# rag-voice-agent - Project Roadmap

**Generated:** 12/23/2025, 6:49:29 PM

## Summary

- **Epics:** 0/18 complete
- **Tasks:** 0/129 complete
- **Tests:** 0/129 passing

---

## 1. ⏳ Project Foundation & Environment Setup

**Priority:** 1 | **Status:** In Progress | **Tasks:** 0/8

Initialize project structure, configure Python/UV environment, set up dependencies for LiveKit, PostgreSQL, and OpenAI integrations. Create .env configuration and init.sh scripts.

### Tasks

1. ⬜ **Create project directory structure**
   - Tests: 1

2. ⬜ **Initialize Python project with UV**
   - Tests: 1

3. ⬜ **Create .env.example template**
   - Tests: 1

4. ⬜ **Create init.sh startup script**
   - Tests: 1

5. ⬜ **Create livekit.toml configuration**
   - Tests: 1

6. ⬜ **Create .gitignore file**
   - Tests: 1

7. ⬜ **Create utils/providers.py for flexible API clients**
   - Tests: 1

8. ⬜ **Create utils/models.py for data models**
   - Tests: 1

---

## 2. ⏳ Database Setup & Schema

**Priority:** 2 | **Status:** In Progress | **Tasks:** 0/7

Set up PostgreSQL with PGVector extension, apply schema.sql, create documents and chunks tables, implement match_chunks function for vector similarity search.

### Tasks

1. ⬜ **Create schema.sql with PGVector extensions**
   - Tests: 1

2. ⬜ **Create documents table schema**
   - Tests: 1

3. ⬜ **Create chunks table schema**
   - Tests: 1

4. ⬜ **Create match_chunks function**
   - Tests: 1

5. ⬜ **Create update_updated_at trigger function**
   - Tests: 1

6. ⬜ **Create document_summaries view**
   - Tests: 1

7. ⬜ **Create database initialization script**
   - Tests: 1

---

## 3. ⏳ Database Connection Pool & Utilities

**Priority:** 3 | **Status:** In Progress | **Tasks:** 0/7

Implement database connection pool using asyncpg, create db_utils module with connection management, query helpers, and error handling.

### Tasks

1. ⬜ **Create DatabasePool class**
   - Tests: 1

2. ⬜ **Create global database pool instance**
   - Tests: 1

3. ⬜ **Implement get_document function**
   - Tests: 1

4. ⬜ **Implement list_documents function**
   - Tests: 1

5. ⬜ **Implement execute_query helper**
   - Tests: 1

6. ⬜ **Implement test_connection function**
   - Tests: 1

7. ⬜ **Add proper logging to db_utils**
   - Tests: 1

---

## 4. ⏳ Document Chunking System

**Priority:** 4 | **Status:** In Progress | **Tasks:** 0/8

Implement document chunking module with configurable chunk sizes, overlap handling, and semantic splitting support for preparing documents for embedding.

### Tasks

1. ⬜ **Create DocumentChunk dataclass**
   - Tests: 1

2. ⬜ **Create ChunkingConfig dataclass**
   - Tests: 1

3. ⬜ **Create DocumentChunker class**
   - Tests: 1

4. ⬜ **Implement paragraph splitting**
   - Tests: 1

5. ⬜ **Implement sentence splitting**
   - Tests: 1

6. ⬜ **Implement token counting**
   - Tests: 1

7. ⬜ **Implement chunk_document method**
   - Tests: 1

8. ⬜ **Create chunker factory function**
   - Tests: 1

---

## 5. ⏳ Embedding Generation Pipeline

**Priority:** 5 | **Status:** In Progress | **Tasks:** 0/8

Create embedder.py module using OpenAI text-embedding-3-small model, implement batch embedding generation, caching, and retry logic with rate limit handling.

### Tasks

1. ⬜ **Create EmbeddingGenerator class**
   - Tests: 1

2. ⬜ **Implement single embedding generation**
   - Tests: 1

3. ⬜ **Implement batch embedding generation**
   - Tests: 1

4. ⬜ **Implement individual fallback processing**
   - Tests: 1

5. ⬜ **Implement embed_chunks method**
   - Tests: 1

6. ⬜ **Implement embed_query method**
   - Tests: 1

7. ⬜ **Create EmbeddingCache class**
   - Tests: 1

8. ⬜ **Create embedder factory function**
   - Tests: 1

---

## 6. ⏳ Document Ingestion Pipeline

**Priority:** 6 | **Status:** In Progress | **Tasks:** 0/9

Build ingest.py pipeline to process markdown documents, chunk content, generate embeddings, and store in PostgreSQL with vector embeddings for RAG retrieval.

### Tasks

1. ⬜ **Create DocumentIngestionPipeline class**
   - Tests: 1

2. ⬜ **Implement pipeline initialization**
   - Tests: 1

3. ⬜ **Implement markdown file discovery**
   - Tests: 1

4. ⬜ **Implement document reading and parsing**
   - Tests: 1

5. ⬜ **Implement metadata extraction**
   - Tests: 1

6. ⬜ **Implement PostgreSQL save function**
   - Tests: 1

7. ⬜ **Implement single document ingestion**
   - Tests: 1

8. ⬜ **Implement batch document ingestion**
   - Tests: 1

9. ⬜ **Create CLI main function**
   - Tests: 1

---

## 7. ⏳ Core Voice Agent Structure

**Priority:** 7 | **Status:** In Progress | **Tasks:** 0/6

Implement RAGKnowledgeAgent class extending livekit.agents.Agent with proper initialization, instructions configuration, and lifecycle management (on_enter, on_exit).

### Tasks

1. ⬜ **Create RAGKnowledgeAgent class skeleton**
   - Tests: 1

2. ⬜ **Define agent instructions**
   - Tests: 1

3. ⬜ **Implement database initialization method**
   - Tests: 1

4. ⬜ **Implement on_enter lifecycle method**
   - Tests: 1

5. ⬜ **Implement on_exit lifecycle method**
   - Tests: 1

6. ⬜ **Add required imports**
   - Tests: 1

---

## 8. ⏳ Voice Pipeline Configuration

**Priority:** 8 | **Status:** In Progress | **Tasks:** 0/7

Configure AgentSession with Deepgram Nova-3 STT, OpenAI GPT-4.1-mini LLM, OpenAI TTS with echo voice, Silero VAD, and multilingual turn detection.

### Tasks

1. ⬜ **Configure Deepgram STT**
   - Tests: 1

2. ⬜ **Configure OpenAI LLM**
   - Tests: 1

3. ⬜ **Configure OpenAI TTS**
   - Tests: 1

4. ⬜ **Configure Silero VAD**
   - Tests: 1

5. ⬜ **Configure turn detection**
   - Tests: 1

6. ⬜ **Create AgentSession with full configuration**
   - Tests: 1

7. ⬜ **Configure noise cancellation**
   - Tests: 1

---

## 9. ⏳ Knowledge Base Search Tool

**Priority:** 9 | **Status:** In Progress | **Tasks:** 0/7

Implement search_knowledge_base function_tool using PGVector match_chunks function, with query embedding generation, similarity filtering, and source attribution.

### Tasks

1. ⬜ **Create search_knowledge_base function_tool decorator**
   - Tests: 1

2. ⬜ **Implement query embedding generation**
   - Tests: 1

3. ⬜ **Implement vector similarity search**
   - Tests: 1

4. ⬜ **Implement similarity threshold filtering**
   - Tests: 1

5. ⬜ **Implement no results handling**
   - Tests: 1

6. ⬜ **Track search history**
   - Tests: 1

7. ⬜ **Implement error handling for search**
   - Tests: 1

---

## 10. ⏳ RAG Response Formatting

**Priority:** 10 | **Status:** In Progress | **Tasks:** 0/6

Create response formatting logic for RAG results including source citations, relevance filtering (similarity > 0.7), and user-friendly output synthesis.

### Tasks

1. ⬜ **Format search results with sources**
   - Tests: 1

2. ⬜ **Create result summary header**
   - Tests: 1

3. ⬜ **Implement content truncation for long results**
   - Tests: 1

4. ⬜ **Add similarity score to response**
   - Tests: 1

5. ⬜ **Create response formatter utility**
   - Tests: 1

6. ⬜ **Optimize response for voice output**
   - Tests: 1

---

## 11. ⏳ Agent Session Management

**Priority:** 11 | **Status:** In Progress | **Tasks:** 0/6

Implement entrypoint function, session event handlers (state_changed, error), noise cancellation configuration, and room input options management.

### Tasks

1. ⬜ **Create entrypoint function**
   - Tests: 1

2. ⬜ **Implement state change event handler**
   - Tests: 1

3. ⬜ **Implement error event handler**
   - Tests: 1

4. ⬜ **Create main entry point with CLI**
   - Tests: 1

5. ⬜ **Add session logging**
   - Tests: 1

6. ⬜ **Configure room input options**
   - Tests: 1

---

## 12. ⏳ Error Handling & Recovery

**Priority:** 12 | **Status:** In Progress | **Tasks:** 0/7

Implement graceful error handling for database failures, API errors, embedding issues, and session disconnections with user-friendly error messages.

### Tasks

1. ⬜ **Implement database connection error handling**
   - Tests: 1

2. ⬜ **Implement embedding API error handling**
   - Tests: 1

3. ⬜ **Implement query execution error handling**
   - Tests: 1

4. ⬜ **Implement session disconnection handling**
   - Tests: 1

5. ⬜ **Create user-friendly error messages**
   - Tests: 1

6. ⬜ **Implement graceful degradation**
   - Tests: 1

7. ⬜ **Add connection retry logic**
   - Tests: 1

---

## 13. ⏳ Context & State Management

**Priority:** 13 | **Status:** In Progress | **Tasks:** 0/6

Implement search history tracking, conversation context preservation, and retrieved chunks caching for maintaining context across dialogue turns.

### Tasks

1. ⬜ **Implement search history tracking**
   - Tests: 1

2. ⬜ **Implement conversation context tracking**
   - Tests: 1

3. ⬜ **Implement retrieved chunks caching**
   - Tests: 1

4. ⬜ **Implement context-enhanced queries**
   - Tests: 1

5. ⬜ **Implement session state cleanup**
   - Tests: 1

6. ⬜ **Add state persistence for long sessions**
   - Tests: 1

---

## 14. ⏳ Unit Testing Suite

**Priority:** 14 | **Status:** In Progress | **Tasks:** 0/8

Create comprehensive unit tests for RAG agent initialization, search tool functionality, embedding generation, and database operations using pytest with mocking.

### Tasks

1. ⬜ **Set up pytest configuration**
   - Tests: 1

2. ⬜ **Create agent initialization tests**
   - Tests: 1

3. ⬜ **Create search tool unit tests**
   - Tests: 1

4. ⬜ **Create no results handling tests**
   - Tests: 1

5. ⬜ **Create embedding generator tests**
   - Tests: 1

6. ⬜ **Create database utility tests**
   - Tests: 1

7. ⬜ **Create chunker unit tests**
   - Tests: 1

8. ⬜ **Create error handling tests**
   - Tests: 1

---

## 15. ⏳ Integration Testing

**Priority:** 15 | **Status:** In Progress | **Tasks:** 0/6

Build integration tests for PostgreSQL/PGVector connectivity, end-to-end RAG pipeline, and voice agent session management with test fixtures.

### Tasks

1. ⬜ **Create PostgreSQL test fixtures**

2. ⬜ **Create PGVector integration tests**

3. ⬜ **Create end-to-end RAG pipeline tests**

4. ⬜ **Create test document fixtures**

5. ⬜ **Create ingestion pipeline integration tests**

6. ⬜ **Create agent session integration tests**

---

## 16. ⏳ Behavioral Testing

**Priority:** 16 | **Status:** In Progress | **Tasks:** 0/7

Implement behavioral tests using LiveKit AgentTestSuite for greeting behavior, knowledge query handling, out-of-scope responses, and conversation flow.

### Tasks

1. ⬜ **Set up LiveKit AgentTestSuite**

2. ⬜ **Create greeting behavior tests**

3. ⬜ **Create knowledge query behavior tests**

4. ⬜ **Create out-of-scope response tests**

5. ⬜ **Create conversation flow tests**

6. ⬜ **Create clarification request tests**

7. ⬜ **Create farewell behavior tests**

---

## 17. ⏳ Logging & Observability

**Priority:** 17 | **Status:** In Progress | **Tasks:** 0/8

Set up structured logging with structlog, implement RAG operation metrics, search latency tracking, and monitoring for similarity scores and token usage.

### Tasks

1. ⬜ **Set up structlog for structured logging**

2. ⬜ **Implement RAG search metrics logging**

3. ⬜ **Implement similarity score logging**

4. ⬜ **Implement embedding generation metrics**

5. ⬜ **Implement error logging with context**

6. ⬜ **Create metrics collection utility**

7. ⬜ **Add session metrics to agent**

8. ⬜ **Implement performance monitoring targets**

---

## 18. ⏳ Deployment & Configuration

**Priority:** 18 | **Status:** In Progress | **Tasks:** 0/8

Create Dockerfile for containerized deployment, configure livekit.toml for agent workers, set up production environment configuration and health checks.

### Tasks

1. ⬜ **Create Dockerfile**

2. ⬜ **Create docker-compose.yml**

3. ⬜ **Configure livekit.toml for production**

4. ⬜ **Create production environment configuration**

5. ⬜ **Create health check endpoint**

6. ⬜ **Create deployment documentation**

7. ⬜ **Create .dockerignore file**

8. ⬜ **Create startup validation script**

---

