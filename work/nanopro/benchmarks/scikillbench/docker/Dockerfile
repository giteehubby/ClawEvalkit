# Dockerfile for CASCADE Conversational System
# This provides an isolated environment for running the materials science assistant

FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    build-essential \
    ca-certificates \
    gnupg \
    procps \
    # For Selenium/Playwright browser
    chromium \
    chromium-driver \
    libxrender1 \
    libxext6 \
    libsm6 \
    libice6 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    # Install Node.js for workspace server
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install UV package manager (faster than pip)
RUN pip install uv

# Copy requirements first for better caching
COPY docker/requirements-docker.txt /tmp/requirements.txt

# Create virtual environment at /app/.venv (tools expect this path)
RUN uv venv /app/.venv \
    && . /app/.venv/bin/activate \
    && uv pip install -r /tmp/requirements.txt

# Copy the application code
COPY . /app

# Build workspace server (Node.js MCP server)
WORKDIR /app/mcp_servers_and_tools/workspace_server
RUN npm install && npm run build

# Back to app directory
WORKDIR /app

# Create directories for temp files, saved code, and data persistence
RUN mkdir -p /app/temp_code /app/saved_code /app/data /app/.home

# Copy startup script and set permissions (before switching to non-root user)
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 755 /usr/local/bin/entrypoint.sh

# Create non-root user for security
RUN useradd -m -u 1000 cascade_user \
    && chown -R cascade_user:cascade_user /app \
    && chmod -R a+rX /app

# Make specific directories world-writable for any UID (AFTER chown/chmod)
# These directories need write access regardless of which user runs the container
RUN chmod 777 /app/temp_code /app/saved_code /app/data /app/.home

# Switch to non-root user (can be overridden by docker-compose user:)
USER cascade_user

# Install Playwright browsers as cascade_user
RUN /app/.venv/bin/playwright install chromium

# Switch back to root to fix permissions, then back to cascade_user
USER root
# Make cascade_user's home and playwright cache accessible to any UID
# (needed when container runs with user: "${UID}:${GID}" override)
RUN chmod a+rx /home/cascade_user && chmod -R a+rX /home/cascade_user/.cache
USER cascade_user

# Environment variables (can be overridden)
ENV PROJECT_ROOT=/app
ENV CODE_STORAGE_DIR=/app/temp_code
ENV SAVED_FILES_DIR=/app/saved_code
ENV PYTHONUNBUFFERED=1
# Ensure virtual environment is used
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Expose Streamlit port
EXPOSE 8501

# Default command
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["streamlit", "run", "conversational_system/frontend/streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501"]
