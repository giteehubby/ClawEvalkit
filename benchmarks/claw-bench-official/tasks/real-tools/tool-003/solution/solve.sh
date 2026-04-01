#!/usr/bin/env bash
set -euo pipefail
WORKSPACE="${1:-workspace}"

python3 << PYEOF
import json

with open("$WORKSPACE/config_spec.json") as f:
    spec = json.load(f)

env_lines = []
env_lines.append("# Database Configuration")
env_lines.append(f"DB_HOST={spec['variables']['DB_HOST']['default']}")
env_lines.append(f"DB_PORT={spec['variables']['DB_PORT']['default']}")
env_lines.append(f"DB_NAME={spec['variables']['DB_NAME']['default']}")
env_lines.append(f"DB_USER={spec['variables']['DB_USER']['default']}")
env_lines.append(f"DB_PASSWORD={spec['variables']['DB_PASSWORD']['default']}")
env_lines.append("")
env_lines.append("# Application Settings")
env_lines.append(f"APP_SECRET_KEY={spec['variables']['APP_SECRET_KEY']['default']}")
env_lines.append(f"APP_DEBUG={str(spec['variables']['APP_DEBUG']['default']).lower()}")
env_lines.append(f"APP_PORT={spec['variables']['APP_PORT']['default']}")
env_lines.append("")
env_lines.append("# External Services")
env_lines.append(f"API_KEY={spec['variables']['API_KEY']['default']}")
env_lines.append(f"REDIS_URL={spec['variables']['REDIS_URL']['default']}")

with open("$WORKSPACE/.env", "w") as f:
    f.write("\n".join(env_lines) + "\n")

docker_compose = """version: "3.8"

services:
  app:
    image: python:3.11-slim
    ports:
      - "\${APP_PORT}:8000"
    environment:
      - DB_HOST=\${DB_HOST}
      - DB_PORT=\${DB_PORT}
      - DB_NAME=\${DB_NAME}
      - DB_USER=\${DB_USER}
      - DB_PASSWORD=\${DB_PASSWORD}
      - APP_SECRET_KEY=\${APP_SECRET_KEY}
      - APP_DEBUG=\${APP_DEBUG}
      - API_KEY=\${API_KEY}
      - REDIS_URL=\${REDIS_URL}
    env_file:
      - .env
    depends_on:
      - db
      - redis

  db:
    image: postgres:15
    ports:
      - "\${DB_PORT}:5432"
    environment:
      - POSTGRES_DB=\${DB_NAME}
      - POSTGRES_USER=\${DB_USER}
      - POSTGRES_PASSWORD=\${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  pgdata:
"""

with open("$WORKSPACE/docker-compose.yml", "w") as f:
    f.write(docker_compose)

print("Created .env and docker-compose.yml")
PYEOF
echo "Solution files created in $WORKSPACE"
