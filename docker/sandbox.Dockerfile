# AgentForge Sandbox Image
# Pre-built image with Python, Node.js, and common test runners
#
# Build: docker build -f docker/sandbox.Dockerfile -t agentforge-sandbox:latest .
#
# This image is used by the QA agent to run generated tests in isolation.

FROM python:3.11-slim AS base

# Install Node.js 20
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# Common Python test deps (cached, fast install for generated code)
RUN pip install --no-cache-dir \
    pytest pytest-asyncio pytest-cov httpx \
    fastapi uvicorn flask sqlalchemy pydantic \
    python-jose passlib bcrypt python-multipart

# Common Node test deps in a global location
RUN npm install -g vitest jest supertest
RUN mkdir -p /opt/node_modules && cd /opt && \
    npm install --prefix /opt express cors better-sqlite3 jsonwebtoken bcryptjs zod \
                       react react-dom @vitejs/plugin-react vite

# Non-root user for safety
RUN useradd -m -s /bin/bash sandbox
USER sandbox
WORKDIR /workspace

CMD ["bash"]
