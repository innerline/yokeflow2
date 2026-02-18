# YokeFlow API Dockerfile
# Multi-stage build for optimized production image

# =============================================================================
# Builder Stage
# =============================================================================
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
RUN pip install uv

# Copy dependency files
COPY pyproject.toml uv.lock* ./

# Install dependencies
RUN uv pip install --system --no-cache -r pyproject.toml || \
    pip install --no-cache-dir fastapi uvicorn pydantic pydantic-settings \
    asyncpg sqlalchemy httpx anthropic python-dotenv pyyaml structlog

# =============================================================================
# Production Stage
# =============================================================================
FROM python:3.12-slim AS production

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    docker-cli \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY server/ ./server/
COPY schema/ ./schema/
COPY prompts/ ./prompts/
COPY mcp-task-manager/dist/ ./mcp-task-manager/dist/

# Create necessary directories
RUN mkdir -p /app/generations /app/logs /app/vaults/personal /app/vaults/agents

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV API_HOST=0.0.0.0
ENV API_PORT=8000

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the API server
CMD ["python", "-m", "uvicorn", "server.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
