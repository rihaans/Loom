# Loom Sandbox Image
# Pre-built image with Python, Node.js, and common test runners
#
# Build: docker build -f docker/sandbox.Dockerfile -t loom-sandbox:latest .
# Run:   docker run --rm -it loom-sandbox:latest
#
# This image is used by the QA agent to run generated tests in isolation.
# Security: runs as non-root, minimal attack surface, no network by default.

FROM python:3.12-slim AS base

# Metadata
LABEL org.opencontainers.image.title="Loom Sandbox"
LABEL org.opencontainers.image.description="Isolated environment for running generated code and tests"
LABEL org.opencontainers.image.version="1.0.0"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 20 LTS
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

# ============================================
# Python dependencies (cached layer)
# ============================================
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    # Testing
    pytest==8.* \
    pytest-asyncio==0.24.* \
    pytest-cov==5.* \
    pytest-timeout==2.* \
    httpx==0.27.* \
    respx==0.21.* \
    # Web frameworks
    fastapi==0.115.* \
    uvicorn[standard]==0.32.* \
    flask==3.* \
    starlette==0.41.* \
    # Database
    sqlalchemy==2.* \
    alembic==1.* \
    # Data validation
    pydantic==2.* \
    pydantic-settings==2.* \
    # Auth
    python-jose[cryptography]==3.* \
    passlib[bcrypt]==1.* \
    python-multipart==0.* \
    # Utilities
    python-dotenv==1.* \
    aiofiles==24.* \
    jinja2==3.*

# ============================================
# Node.js dependencies (cached layer)
# ============================================
# Global test runners
RUN npm install -g \
    vitest@2.* \
    jest@29.* \
    typescript@5.* \
    ts-node@10.* \
    @types/node@20.*

# Pre-install common packages in /opt for faster project setup
RUN mkdir -p /opt/node_modules && cd /opt && \
    npm install --prefix /opt \
    # Testing
    supertest@7.* \
    @testing-library/react@16.* \
    @testing-library/jest-dom@6.* \
    @testing-library/user-event@14.* \
    jsdom@25.* \
    # Backend
    express@4.* \
    cors@2.* \
    helmet@8.* \
    better-sqlite3@11.* \
    jsonwebtoken@9.* \
    bcryptjs@2.* \
    zod@3.* \
    dotenv@16.* \
    # Frontend
    react@18.* \
    react-dom@18.* \
    vite@6.* \
    @vitejs/plugin-react@4.* \
    tailwindcss@3.* \
    axios@1.*

# Set NODE_PATH so projects can find pre-installed modules
ENV NODE_PATH=/opt/node_modules

# ============================================
# Security setup
# ============================================
# Create non-root user with minimal privileges
RUN useradd -m -s /bin/bash -u 1000 sandbox && \
    mkdir -p /workspace && \
    chown -R sandbox:sandbox /workspace

# Create output directories
RUN mkdir -p /workspace/output /workspace/tests && \
    chown -R sandbox:sandbox /workspace

# Switch to non-root user
USER sandbox
WORKDIR /workspace

# ============================================
# Runtime configuration
# ============================================
# Default timeout for test execution (in seconds)
ENV SANDBOX_TIMEOUT=60

# Disable pip warnings about running as non-root
ENV PIP_ROOT_USER_ACTION=ignore

# Python: unbuffered output for real-time logging
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Default command
CMD ["bash"]

# ============================================
# Health check
# ============================================
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python --version && node --version || exit 1
