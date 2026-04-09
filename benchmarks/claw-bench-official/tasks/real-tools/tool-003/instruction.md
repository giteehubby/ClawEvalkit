# Task: Environment Configuration

You are given a `.env.example` template and a configuration specification. Generate a proper `.env` file and a `docker-compose.yml`.

## Input Files

- `workspace/.env.example` — Template with 10 environment variable placeholders
- `workspace/config_spec.json` — JSON describing variable types, defaults, and descriptions

## Goal

Create a working `.env` file and a `docker-compose.yml` that references these environment variables.

## Requirements

### .env File (`workspace/.env`)

1. Must contain all 10 variables from `.env.example`
2. Replace all placeholder values (like `<your_value_here>`, `changeme`, `placeholder`) with proper values from `config_spec.json` defaults
3. No placeholder values should remain
4. Format: `KEY=value` (one per line)
5. May include comments (lines starting with `#`)

### docker-compose.yml (`workspace/docker-compose.yml`)

1. Must be valid YAML
2. Must define at least one service (e.g., `app` or `web`)
3. The service must have an `environment` section that references the env vars
4. Should use `${VARIABLE_NAME}` syntax for variable references or `env_file` directive
5. Should include realistic service configuration (image, ports, etc.)

## Notes

- Use the `default` values from `config_spec.json` for each variable
- For sensitive values (passwords, keys), generate reasonable non-placeholder values
- The docker-compose.yml should be version "3.8" or later format
