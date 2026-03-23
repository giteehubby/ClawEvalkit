# Workspace Server

A specialized MCP server designed for comprehensive workspace management and code execution workflows. Provides powerful tools for executing code, managing files, and handling dependencies in various Python environments.

## Features

- Execute Python code from LLM prompts with automatic file management
- Read and save files with flexible path handling and security restrictions
- Install and manage Python dependencies using multiple package managers
- Check package installations and versions with intelligent name variation handling
- Execute shell commands and scripts with automatic shebang insertion
- Support for multiple Python environments (Conda, virtualenv, UV virtualenv)
- Configurable code storage and file directories
- Built-in security features to protect sensitive directories

## Prerequisites

- Node.js installed
- One of the following:
  - Conda installed with desired Conda environment created
  - Python virtualenv
  - UV virtualenv

## Setup

1. Navigate to the workspace_server directory:

```bash
cd mcp_servers_and_tools/workspace_server
```

2. Install the Node.js dependencies:

```bash
npm install
```

3. Build the project:

```bash
npm run build
```

## Configuration

To configure the Workspace Server, add the following to your MCP servers configuration file:

### Using Node.js

```json
{
  "mcpServers": {
    "workspace-server": {
      "command": "node",
      "args": [
        "/path/to/mcp_servers_and_tools/workspace_server/build/index.js" 
      ],
      "env": {
        "CODE_STORAGE_DIR": "/path/to/code/storage",
        "SAVED_FILES_DIR": "/path/to/saved/files",
        "PROJECT_ROOT": "/path/to/your/project/root",
        "FORBIDDEN_PATH": "/path/to/forbidden/directory",
        "ENV_TYPE": "conda",
        "CONDA_ENV_NAME": "your-conda-env"
      }
    }
  }
}
```

### Using Docker

Build the Docker image:
```bash
docker build -t workspace-server .
```

Run with default settings:
```json
{
  "mcpServers": {
    "workspace-server": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "workspace-server"]
    }
  }
}
```

Or override environment variables:
```bash
docker run -i --rm \
  -e PROJECT_ROOT=/app \
  -e FORBIDDEN_PATH=/app/forbidden \
  -e CODE_STORAGE_DIR=/app/generated_code \
  workspace-server
```

### Environment Variables

#### Required Variables
- `CODE_STORAGE_DIR`: Directory where the generated code will be stored
- `SAVED_FILES_DIR`: Directory where saved files will be stored
- `PROJECT_ROOT`: Absolute path to the project root directory (used for security boundaries)
- `FORBIDDEN_PATH`: Absolute path to a directory that agents are forbidden from accessing (e.g., benchmark directory)

#### Optional Variables
- `ENV_TYPE`: Type of Python environment (`conda`, `venv`, or `venv-uv`)
- `CONDA_ENV_NAME`: Name of the Conda environment (required if `ENV_TYPE=conda`)
- `VENV_PATH`: Path to the virtualenv (required if `ENV_TYPE=venv`)
- `UV_VENV_PATH`: Path to the UV virtualenv (required if `ENV_TYPE=venv-uv`)

## Available Tools

1. **`execute_code`**: Execute Python code in the configured environment. Code is saved to a temporary file and executed.
2. **`read_file`**: Read the content of any text file (Python code, log files, output files, etc.). Use absolute paths for best results.
3. **`install_dependencies`**: Install Python dependencies using the appropriate package manager (pip, uv, or conda).
4. **`check_installed_packages`**: List all installed packages in the current Python environment.
5. **`check_package_version`**: Check specific package versions, installation paths, and module locations. Automatically handles package name variations (hyphens, underscores, dots).
6. **`save_file`**: Save a file to the SAVED_FILES_DIR with the specified filename.
7. **`execute_shell_command`**: Execute a shell command with configurable working directory.
8. **`create_and_execute_script`**: Create and execute a shell script. Automatically adds shebang if not present.

## Security Features

- **Project Root Restriction**: All file operations are restricted to the `PROJECT_ROOT` directory to prevent access to files outside the project scope.
- **Forbidden Path Protection**: Agents are explicitly forbidden from accessing the `FORBIDDEN_PATH` directory (e.g., benchmark directory) to prevent accidental modifications to sensitive data.
- **Path Validation**: Comprehensive path checking to ensure operations are performed in safe locations.
- **Command Security**: Dangerous shell commands (like `rm -rf`, `sudo`, etc.) are blocked for security.
