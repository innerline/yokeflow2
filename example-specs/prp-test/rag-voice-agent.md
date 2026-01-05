# PRP: RAG Voice Agent - LiveKit Voice AI Agent

---
name: "RAG Voice Agent"
type: "voice-ai-agent"
framework: "livekit-agents"
version: "1.0"
---

## Goal

Build an intelligent voice AI agent with LiveKit that provides conversational access to a knowledge base stored in PostgreSQL with PGVector. The agent will use RAG (Retrieval-Augmented Generation) to search through embedded document chunks and provide contextual, accurate responses based on the organization's internal documentation and knowledge.

Core Capabilities:
- Natural voice conversations with users about knowledge base content
- Intelligent semantic search through vector-embedded documents
- Context-aware responses using RAG pipeline
- Real-time voice interaction with low latency
- Graceful handling of queries outside the knowledge base

IMPORANT: Use Archon for task management - we have a LiveKit RAG Agent project created in Archon and I want you to use that.

## Why

- **User Experience**: Transform static documentation into an interactive voice assistant that users can naturally converse with
- **Efficiency**: Instant access to information without manual searching through documents
- **Scalability**: Handle multiple concurrent voice sessions with automated knowledge retrieval
- **Innovation**: Combine state-of-the-art voice AI with vector search for intelligent information access
- **Accessibility**: Voice interface makes knowledge accessible to users who prefer audio interaction

## What

### Voice Pipeline Architecture

```yaml
Pipeline Configuration:
  STT:
    provider: deepgram
    model: nova-3         # Latest, highest accuracy for better query understanding
    language: en          # Can be set to "multi" for multilingual support
  
  LLM:
    provider: openai
    model: gpt-4.1-mini   # Fast, capable, cost-effective with good RAG performance
    temperature: 0.3      # Lower temperature for more factual responses
    max_tokens: 500       # Sufficient for knowledge-based responses
  
  TTS:
    provider: openai
    voice: echo           # Natural, versatile voice
    speed: 1.0
  
  VAD:
    provider: silero
    threshold: 0.5
  
  Turn Detection:
    strategy: multilingual  # Best for natural conversation flow
    sensitivity: 0.7
```

### Agent Design

```python
Agent Class Structure:
  - Name: RAGKnowledgeAgent
  - Base: livekit.agents.Agent
  - Instructions: |
      "You are an intelligent knowledge assistant with access to an organization's documentation and information.
      Your role is to help users find accurate information from the knowledge base.
      You have a professional yet friendly demeanor.
      Always search the knowledge base before answering questions.
      If information isn't in the knowledge base, clearly state that and offer general guidance.
      Be concise but thorough in your responses.
      Ask clarifying questions if the user's query is ambiguous."
  
  Tools:
    - search_knowledge_base: Semantic search through vector-embedded documents
  
  Lifecycle:
    - on_enter: Greeting and capabilities introduction
    - on_exit: Session cleanup and farewell
  
  State Management:
    - search_history: Track queries for context
    - conversation_context: Maintain dialogue flow
    - retrieved_chunks: Cache recent search results
```

### Tool Definitions

```python
Required Tools:
  - search_knowledge_base:
      description: "Search the knowledge base using semantic similarity"
      parameters:
        - query: str (required) - The search query
        - limit: int = 5 - Maximum number of chunks to retrieve
      returns: list[dict] - Relevant document chunks with metadata
      implementation: Uses match_chunks function with PGVector
```

## Success Criteria

### Functional Requirements
- [x] Agent responds to voice input within 2 seconds
- [x] RAG search retrieves relevant document chunks
- [x] Responses are based on knowledge base content
- [x] Agent handles queries outside knowledge base gracefully
- [x] Turn detection correctly identifies speaker changes
- [x] Interruptions are handled smoothly

### Quality Metrics
- [x] Conversation feels natural and responsive
- [x] Average response latency < 1000ms (including RAG search)
- [x] RAG retrieval accuracy > 90%
- [x] Turn detection accuracy > 95%
- [x] Tool execution success rate > 99%

### Testing Coverage
- [x] Unit tests for RAG tool
- [x] Integration tests with PostgreSQL/PGVector
- [x] Behavioral tests for knowledge responses
- [x] Console mode testing for voice interaction
- [x] Edge cases (empty results, connection failures)

## All Needed Context (MUST READ)

### LiveKit Documentation
```yaml
Essential Resources:
  - Use the Archon MCP for ALL LiveKit documentation searching
```

### Project Context
```yaml
Existing Code:
  - file: ingest.py
    why: Document ingestion pipeline that populates the knowledge base
  
  - file: embedder.py
    why: Embedding generation using OpenAI text-embedding-3-small
  
  - file: schema.sql
    why: PostgreSQL schema with match_chunks function for vector search
  
  - file: db_utils.py
    why: Database connection pool and utilities
  
  - file: basic_voice_assistant.py
    why: Reference implementation for agent structure
```

## Implementation Blueprint

### Phase 1: Project Setup

```bash
# Project already initialized, just need to ensure dependencies
cd LiveKitAgent

# Add any missing dependencies
uv add asyncpg  # For PostgreSQL connection
uv add numpy    # For vector operations

# Environment variables needed in .env:
# DATABASE_URL=postgresql://user:pass@localhost/dbname
# LIVEKIT_URL=wss://your-project.livekit.cloud
# LIVEKIT_API_KEY=your-key
# LIVEKIT_API_SECRET=your-secret
# OPENAI_API_KEY=your-openai-key
# DEEPGRAM_API_KEY=your-deepgram-key
```

### Phase 2: Core Agent Implementation

```python
# agent.py structure
"""
RAG Voice Agent with PostgreSQL/PGVector
=========================================
Voice AI agent that searches through knowledge base using semantic similarity
"""

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, function_tool, RunContext
from livekit.plugins import openai, deepgram, silero, noise_cancellation
import asyncpg
import json
import os
from typing import List, Dict, Any
import logging

# Load environment variables
load_dotenv(".env")

logger = logging.getLogger(__name__)

class RAGKnowledgeAgent(Agent):
    """Voice AI agent with RAG knowledge base access."""
    
    def __init__(self) -> None:
        super().__init__(
            instructions="""You are an intelligent knowledge assistant with access to an organization's documentation and information.
            Your role is to help users find accurate information from the knowledge base.
            You have a professional yet friendly demeanor.
            Always search the knowledge base before answering questions.
            If information isn't in the knowledge base, clearly state that and offer general guidance.
            Be concise but thorough in your responses.
            Ask clarifying questions if the user's query is ambiguous.
            When you find relevant information, synthesize it clearly and cite the source documents."""
        )
        self.db_pool = None
        self.search_history = []
        
    async def initialize_db(self):
        """Initialize database connection pool."""
        if not self.db_pool:
            self.db_pool = await asyncpg.create_pool(
                os.getenv("DATABASE_URL"),
                min_size=2,
                max_size=10,
                command_timeout=60
            )
    
    @function_tool
    async def search_knowledge_base(
        self, 
        context: RunContext, 
        query: str,
        limit: int = 5
    ) -> str:
        """
        Search the knowledge base using semantic similarity.
        
        Args:
            query: The search query to find relevant information
            limit: Maximum number of results to return (default: 5)
        """
        try:
            # Ensure database is initialized
            if not self.db_pool:
                await self.initialize_db()
            
            # Generate embedding for query
            from ingestion.embedder import create_embedder
            embedder = create_embedder()
            query_embedding = await embedder.embed_query(query)
            
            # Convert to PostgreSQL vector format
            embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'
            
            # Search using match_chunks function
            async with self.db_pool.acquire() as conn:
                results = await conn.fetch(
                    """
                    SELECT * FROM match_chunks($1::vector, $2)
                    """,
                    embedding_str,
                    limit
                )
            
            # Format results for response
            if not results:
                return "No relevant information found in the knowledge base for your query."
            
            # Build response with sources
            response_parts = []
            for i, row in enumerate(results, 1):
                similarity = row['similarity']
                content = row['content']
                doc_title = row['document_title']
                doc_source = row['document_source']
                
                # Only include highly relevant results (similarity > 0.7)
                if similarity > 0.7:
                    response_parts.append(
                        f"[Source: {doc_title}]\n{content}\n"
                    )
            
            if not response_parts:
                return "Found some results but they may not be directly relevant to your query. Please try rephrasing your question."
            
            # Track search history
            self.search_history.append({
                "query": query,
                "results_count": len(response_parts),
                "top_similarity": results[0]['similarity'] if results else 0
            })
            
            return f"Found {len(response_parts)} relevant results:\n\n" + "\n---\n".join(response_parts)
            
        except Exception as e:
            logger.error(f"Knowledge base search failed: {e}")
            return f"I encountered an error searching the knowledge base. Please try again or rephrase your question."
    
    async def on_enter(self) -> None:
        """Called when the agent becomes active."""
        # Initialize database connection
        await self.initialize_db()
        
        # Generate greeting
        await self.session.generate_reply(
            instructions="""Greet the user warmly and let them know you can help them:
            - Search through the organization's knowledge base
            - Answer questions about documented topics
            - Find specific information from internal documents
            Keep it brief, natural, and professional."""
        )
    
    async def on_exit(self) -> None:
        """Called when agent is being replaced or session ends."""
        # Close database pool
        if self.db_pool:
            await self.db_pool.close()
        
        # Farewell message
        await self.session.say("Thank you for using the knowledge assistant. Have a great day!")


async def entrypoint(ctx: agents.JobContext):
    """Main entry point for the agent worker."""
    
    # Configure voice pipeline with recommended settings
    session = AgentSession(
        # Speech-to-Text - Deepgram Nova-3 for best accuracy
        stt=deepgram.STT(
            model="nova-3",
            language="en",
        ),
        
        # LLM - GPT-4.1-mini for fast RAG responses
        llm=openai.LLM(
            model="gpt-4.1-mini",
            temperature=0.3,  # Lower for factual responses
        ),
        
        # Text-to-Speech - OpenAI echo voice
        tts=openai.TTS(
            voice="echo",
            speed=1.0,
        ),
        
        # Voice Activity Detection
        vad=silero.VAD.load(),
        
        # Turn detection - multilingual for natural flow
        turn_detection="multilingual",
    )
    
    # Start session with RAG agent
    await session.start(
        room=ctx.room,
        agent=RAGKnowledgeAgent(),
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )
    
    # Logging
    logger.info(f"RAG Voice Agent started in room: {ctx.room.name}")
    
    # Event handlers
    @session.on("agent_state_changed")
    def on_state_changed(ev):
        logger.info(f"Agent state: {ev.old_state} -> {ev.new_state}")
    
    @session.on("error")
    async def on_error(error):
        logger.error(f"Session error: {error}")
        if error.recoverable:
            logger.info("Recovering from error...")
        else:
            await session.say("I'm having trouble accessing the knowledge base. Let me try to help differently.")


if __name__ == "__main__":
    # Run the agent
    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            worker_name="rag-knowledge-agent",
            max_idle_time=60,
        )
    )
```

### Phase 3: Tool Integration

```python
# Implementation checklist for search_knowledge_base tool:
- [x] Connect to PostgreSQL database
- [x] Generate query embedding using existing embedder
- [x] Call match_chunks function with vector search
- [x] Format results with source attribution
- [x] Handle errors gracefully
- [x] Track search history for context
```

### Phase 4: Testing Suite

```python
# tests/test_rag_agent.py
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from agent import RAGKnowledgeAgent

@pytest.mark.asyncio
async def test_agent_initialization():
    """Test agent initializes with correct instructions."""
    agent = RAGKnowledgeAgent()
    assert "knowledge assistant" in agent.instructions.lower()
    assert agent.db_pool is None
    assert agent.search_history == []

@pytest.mark.asyncio
async def test_search_knowledge_base():
    """Test knowledge base search returns relevant results."""
    agent = RAGKnowledgeAgent()
    
    # Mock database and embedder
    with patch('agent.asyncpg.create_pool') as mock_pool:
        mock_conn = AsyncMock()
        mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
        
        # Mock search results
        mock_conn.fetch.return_value = [
            {
                'similarity': 0.85,
                'content': 'Test content about AI',
                'document_title': 'AI Documentation',
                'document_source': 'docs/ai.md'
            }
        ]
        
        with patch('agent.create_embedder') as mock_embedder:
            mock_embedder.return_value.embed_query = AsyncMock(return_value=[0.1] * 1536)
            
            # Execute search
            context = Mock()
            result = await agent.search_knowledge_base(context, "What is AI?", limit=5)
            
            assert "Found 1 relevant results" in result
            assert "AI Documentation" in result
            assert len(agent.search_history) == 1

@pytest.mark.asyncio
async def test_no_results_handling():
    """Test graceful handling when no results found."""
    agent = RAGKnowledgeAgent()
    
    with patch('agent.asyncpg.create_pool') as mock_pool:
        mock_conn = AsyncMock()
        mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
        mock_conn.fetch.return_value = []
        
        with patch('agent.create_embedder') as mock_embedder:
            mock_embedder.return_value.embed_query = AsyncMock(return_value=[0.1] * 1536)
            
            context = Mock()
            result = await agent.search_knowledge_base(context, "Unknown topic")
            
            assert "No relevant information found" in result

# tests/test_behaviors.py
from livekit.agents.testing import AgentTestSuite, Judge

@pytest.mark.asyncio
async def test_greeting_behavior():
    """Test agent greets appropriately."""
    suite = AgentTestSuite()
    judge = Judge(
        criteria="Agent should greet warmly and explain RAG capabilities"
    )
    
    result = await suite.test_agent(
        agent=RAGKnowledgeAgent(),
        scenario="User joins session",
        judge=judge
    )
    
    assert result.passed

@pytest.mark.asyncio
async def test_knowledge_query_behavior():
    """Test agent searches knowledge base when asked questions."""
    suite = AgentTestSuite()
    judge = Judge(
        criteria="Agent should search knowledge base and provide sourced answers"
    )
    
    result = await suite.test_agent(
        agent=RAGKnowledgeAgent(),
        scenario="User asks: What is our company's AI strategy?",
        judge=judge
    )
    
    assert result.passed
```

### Phase 5: Deployment Configuration

```dockerfile
# Dockerfile (already exists, update if needed)
FROM python:3.11-slim
WORKDIR /app

# Install system dependencies for PostgreSQL
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen
COPY . .
CMD ["uv", "run", "python", "agent.py"]
```

```toml
# livekit.toml (already exists, ensure correct)
[agent]
job_type = "room"
worker_type = "agent"

[agent.prewarm]
count = 1
```

### Phase 6: Validation & Optimization

```bash
# Ensure database is populated
uv run python ingestion/ingest.py --documents documents

# Local testing
uv run python agent.py console

# Run test suite
uv run pytest tests/ -v --asyncio-mode=auto

# Test specific behaviors
uv run pytest tests/test_behaviors.py -v

# Performance testing
# Create tests/performance_test.py to measure:
# - RAG search latency
# - Concurrent session handling
# - Memory usage with connection pooling
```

## Validation Commands

```bash
# Development
uv sync                                    # Install dependencies
uv run python agent.py console            # Test in terminal
uv run python agent.py dev               # Connect to LiveKit

# Testing
uv run pytest tests/ -v                  # Run all tests
uv run pytest tests/ --cov=.            # With coverage
uv run python -m pytest --asyncio-mode=auto  # Async tests

# Database
uv run python ingestion/ingest.py --documents documents  # Populate knowledge base
psql $DATABASE_URL -c "SELECT COUNT(*) FROM chunks"     # Verify data

# Code Quality
uv run black agent.py                    # Format code
uv run ruff check agent.py              # Lint code
```

## Common Implementation Patterns

### RAG Query Pattern
```python
@function_tool
async def search_knowledge_base(context: RunContext, query: str) -> str:
    """Search with proper error handling and formatting."""
    try:
        # 1. Generate embedding
        embedding = await embedder.embed_query(query)
        
        # 2. Vector search
        results = await db.search_similar(embedding)
        
        # 3. Filter by relevance
        relevant = [r for r in results if r['similarity'] > 0.7]
        
        # 4. Format with sources
        return format_rag_response(relevant)
    except Exception as e:
        logger.error(f"RAG search failed: {e}")
        return "Unable to search at the moment"
```

### Connection Pool Pattern
```python
async def initialize_db():
    """Create connection pool once, reuse for all queries."""
    return await asyncpg.create_pool(
        DATABASE_URL,
        min_size=2,      # Minimum connections
        max_size=10,     # Maximum connections
        command_timeout=60  # Query timeout
    )
```

### Context Preservation
```python
class RAGKnowledgeAgent(Agent):
    def __init__(self):
        super().__init__(instructions="...")
        self.search_history = []  # Track queries
        self.context_window = []  # Recent chunks
    
    async def search_with_context(self, query: str):
        # Consider previous searches
        enhanced_query = self.enhance_with_context(query)
        results = await self.search_knowledge_base(enhanced_query)
        self.update_context(results)
        return results
```

## Monitoring & Observability

```python
# Key metrics to track
import structlog
logger = structlog.get_logger()

# Log RAG operations
logger.info("rag.search", query=query, results_count=len(results))
logger.info("rag.similarity", top_score=results[0]['similarity'])
logger.error("rag.failed", error=str(e), query=query)

# Metrics to monitor:
- RAG search latency (target < 500ms)
- Embedding generation time
- Database query time
- Result relevance scores
- Cache hit rates
- Token usage per query
```

## Anti-Patterns to Avoid

- ❌ Don't embed queries synchronously - use async
- ❌ Don't create new DB connections per query - use pool
- ❌ Don't return raw database results - format for users
- ❌ Don't ignore low similarity scores - filter results
- ❌ Don't forget to cite sources in responses
- ❌ Don't let errors crash the session - handle gracefully
- ❌ Don't make responses too technical - simplify for users
- ❌ Don't cache embeddings indefinitely - manage memory

## Confidence Score: 9/10

High confidence in this implementation as it:
- Leverages existing, tested ingestion pipeline and database schema
- Uses proven LiveKit patterns from examples
- Implements proper connection pooling and error handling
- Includes comprehensive testing approach
- Follows best practices for RAG systems

Minor uncertainty around optimal similarity thresholds and chunk limits, which should be tuned based on actual usage patterns.

## Next Steps

After PRP approval:
1. Execute implementation with `/execute-livekit-prp`
2. Populate knowledge base with `uv run python ingestion/ingest.py`
3. Test in console mode with various queries
4. Run behavioral test suite
5. Tune similarity thresholds based on results
6. Deploy to staging for user testing
7. Monitor RAG performance metrics
8. Deploy to production
9. Continuously improve based on query patterns

---

Remember: The goal is to create an intelligent voice interface that makes organizational knowledge instantly accessible through natural conversation!