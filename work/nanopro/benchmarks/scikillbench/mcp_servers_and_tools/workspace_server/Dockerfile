# Start with a Node.js base image
FROM node:18-alpine AS builder
# Create a directory for the app
WORKDIR /app
# Copy package.json and package-lock.json for installing dependencies
COPY package.json package-lock.json ./
# Install dependencies
RUN npm install --ignore-scripts
# Copy the rest of the application source code
COPY . .
# Build the project
RUN npm run build

# Use the same Node.js base image for the final container
FROM node:18-alpine
# Set the working directory
WORKDIR /app
# Copy the build output and necessary files from the builder stage
COPY --from=builder /app/build /app/build
COPY --from=builder /app/package.json /app/package.json
COPY --from=builder /app/package-lock.json /app/package-lock.json
COPY --from=builder /app/node_modules /app/node_modules

# Install Python and required tools
RUN apk add --no-cache python3 py3-pip curl bash

# Download and install uv using the official installer
ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh

# Ensure the installed binary is on the PATH
ENV PATH="/root/.local/bin:$PATH"

# Create required directories
RUN mkdir -p /app/generated_code
RUN mkdir -p /app/saved_files
RUN mkdir -p /app/.venvs/ai
RUN mkdir -p /app/forbidden

# Create a virtual environment
RUN uv venv /app/.venvs/ai

# Set the environment variables
ENV CODE_STORAGE_DIR=/app/generated_code
ENV SAVED_FILES_DIR=/app/saved_files
ENV ENV_TYPE=venv-uv
ENV UV_VENV_PATH=/app/.venvs/ai
ENV PROJECT_ROOT=/app
ENV FORBIDDEN_PATH=/app/forbidden
ENV PATH="/app/.venvs/ai/bin:$PATH"

# Specify the command to run the Workspace Server
ENTRYPOINT ["node", "build/index.js"]
