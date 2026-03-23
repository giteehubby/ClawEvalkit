#!/usr/bin/env python3
"""
Direct Workspace Tools
Direct implementations of workspace management tools without MCP server overhead.
Provides the same functionality as workspace-server but as direct Python functions.
"""

import asyncio
import json
import os
import platform
import random
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from agents import function_tool, RunContextWrapper


# ============================================================================
# CONFIGURATION AND ENVIRONMENT SETUP
# ============================================================================

def get_project_root() -> Path:
    """Get the project root directory by looking for .git directory"""
    current_path = Path(__file__).resolve()
    # Navigate up to find project root (directory containing .git)
    while not (current_path / ".git").exists() and current_path.parent != current_path:
        current_path = current_path.parent
    if (current_path / ".git").exists():
        return current_path
    else:
        # Fallback to environment variable or current working directory
        return Path(os.getenv("PROJECT_ROOT", os.getcwd()))

def resolve_storage_dir(dir_path: str) -> str:
    """Resolve storage directory path, same logic as workspace-server"""
    if not dir_path:
        return ''
    path = Path(dir_path)
    if path.is_absolute():
        return str(path)
    return str(get_project_root() / dir_path)

# Environment configuration - independent absolute paths
PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", str(get_project_root())))
FORBIDDEN_PATH = Path(os.getenv("FORBIDDEN_PATH", str(PROJECT_ROOT / "benchmark_tasks_and_results")))  # Default fallback only

# Get configuration from environment variables with defaults
CODE_STORAGE_DIR = resolve_storage_dir(os.getenv("CODE_STORAGE_DIR", "deep_solver_benchmark/temp_code"))
SAVED_FILES_DIR = resolve_storage_dir(os.getenv("SAVED_FILES_DIR", "deep_solver_benchmark/saved_code"))

# Default environment settings
ENV_CONFIG = {
    "type": os.getenv("ENV_TYPE", "conda"),
    "conda_name": os.getenv("CONDA_ENV_NAME"),
    "venv_path": os.getenv("VENV_PATH"),
    "uv_venv_path": os.getenv("UV_VENV_PATH")
}

# Validate environment settings
if not CODE_STORAGE_DIR:
    raise ValueError("Missing required environment variable: CODE_STORAGE_DIR")
if not SAVED_FILES_DIR:
    raise ValueError("Missing required environment variable: SAVED_FILES_DIR")

# Only validate environment settings if they are explicitly set
if ENV_CONFIG["type"] == "conda" and ENV_CONFIG["conda_name"] is None:
    # Try to use default conda environment if available
    if os.getenv("CONDA_DEFAULT_ENV"):
        ENV_CONFIG["conda_name"] = os.getenv("CONDA_DEFAULT_ENV")
    else:
        # Fall back to venv if conda is not properly configured
        ENV_CONFIG["type"] = "venv"
        ENV_CONFIG["venv_path"] = os.getenv("VENV_PATH", str(PROJECT_ROOT / ".venv"))
elif ENV_CONFIG["type"] == "venv" and ENV_CONFIG["venv_path"] is None:
    # Use default venv path
    ENV_CONFIG["venv_path"] = str(PROJECT_ROOT / ".venv")
elif ENV_CONFIG["type"] == "venv-uv" and ENV_CONFIG["uv_venv_path"] is None:
    # Use default uv venv path
    ENV_CONFIG["uv_venv_path"] = str(PROJECT_ROOT / ".venv")

# Ensure storage directories exist
Path(CODE_STORAGE_DIR).mkdir(parents=True, exist_ok=True)
Path(SAVED_FILES_DIR).mkdir(parents=True, exist_ok=True)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def is_path_forbidden(target_path: str) -> bool:
    """Check if a path is forbidden (same logic as workspace-server)"""
    abs_target = Path(target_path).resolve()
    
    # Check if path is inside the forbidden directory (forbidden)
    try:
        forbidden_rel = abs_target.relative_to(FORBIDDEN_PATH)
        # If we can get a relative path, check if it's inside forbidden directory
        if str(forbidden_rel) == '.' or not str(forbidden_rel).startswith('..'):
            return True  # Inside forbidden directory
    except ValueError:
        pass  # Not inside forbidden directory
    
    # Check if path is outside the project scope (forbidden)
    try:
        project_rel = abs_target.relative_to(PROJECT_ROOT)
        # Check for parent directory traversal
        if str(project_rel).startswith('..'):
            return True
    except ValueError:
        return True  # Outside project scope
    
    return False  # Inside project scope, not in forbidden directory

def get_path_forbidden_reason(target_path: str) -> str | None:
    """Get the specific reason why a path is forbidden (same logic as workspace-server)"""
    # Expand environment variables and home directory before path resolution
    expanded_path = target_path
    if target_path.startswith('$'):
        # Handle $VAR and ${VAR} syntax
        if target_path.startswith('${'):
            env_var = target_path[2:-1]
        else:
            env_var = target_path[1:]
        env_value = os.environ.get(env_var)
        if env_value:
            expanded_path = env_value
    elif target_path.startswith('~'):
        # Handle ~ and ~user syntax
        expanded_path = os.path.expanduser(target_path)
    
    abs_target = Path(expanded_path).resolve()
    abs_forbidden_path = FORBIDDEN_PATH.resolve()
    
    # Check if path is inside the forbidden directory FIRST
    try:
        forbidden_rel = abs_target.relative_to(abs_forbidden_path)
        # If we can get a relative path, check if it's inside forbidden directory
        if str(forbidden_rel) == '.' or not str(forbidden_rel).startswith('..'):
            return 'Cannot access forbidden directory. Please check your path.'
    except ValueError:
        pass  # Not inside forbidden directory
    
    # Check if path is outside the project scope
    try:
        project_rel = abs_target.relative_to(PROJECT_ROOT)
        if str(project_rel).startswith('..'):
            return 'Cannot access files outside project root. Please check your path.'
    except ValueError:
        return 'Cannot access files outside project root. Please check your path.'
    
    return None  # Path is allowed

def extract_paths_from_command(command: str) -> List[str]:
    """Extract potential file paths from shell commands (same logic as workspace-server)"""
    import re
    paths = []
    
    # Simple regex to handle quoted strings and basic word splitting
    token_regex = r'"[^"]*"|\'[^\']*\'|\S+'
    words = re.findall(token_regex, command)
    
    for word in words:
        # Remove quotes if present
        if ((word.startswith('"') and word.endswith('"')) or 
            (word.startswith("'") and word.endswith("'"))):
            word = word[1:-1]
        
        # Skip command names and flags
        if word.startswith('-') or word.startswith('--') or \
           word in ['ls', 'cat', 'find', 'grep', 'head', 'tail', 'wc', 'sort', 'uniq', 'xargs']:
            continue
        
        # Check if word looks like a path (contains / or starts with . or ~ or $)
        # But skip shell redirection syntax
        if (('/' in word or word.startswith('.') or word.startswith('~') or word.startswith('$')) and
            not re.match(r'^(\d+>|>|>>|&>)', word)):  # Skip redirection syntax like "2>", ">", ">>", "&>"
            paths.append(word)
    
    # Also check for forbidden directory name specifically
    forbidden_dir_name = FORBIDDEN_PATH.name
    if forbidden_dir_name in command:
        paths.append(forbidden_dir_name)
    
    # Note: Glob pattern checking is handled separately in the main security checks
    
    return paths

def get_platform_specific_command(python_command: str) -> tuple[str, Dict[str, Any]]:
    """Get platform-specific command for environment activation and execution (same logic as workspace-server)"""
    is_windows = platform.system() == "Windows"
    command = ''
    options = {}
    
    if ENV_CONFIG["type"] == "conda":
        if not ENV_CONFIG["conda_name"]:
            raise ValueError("conda_name is required for conda environment")
        if is_windows:
            command = f'conda run -n {ENV_CONFIG["conda_name"]} {python_command}'
            options = {"shell": True}
        else:
            command = f'source $(conda info --base)/etc/profile.d/conda.sh && conda activate {ENV_CONFIG["conda_name"]} && {python_command}'
            options = {"shell": True, "executable": "/bin/bash"}
    
    elif ENV_CONFIG["type"] == "venv":
        if not ENV_CONFIG["venv_path"]:
            raise ValueError("venv_path is required for virtualenv")
        venv_path = Path(ENV_CONFIG["venv_path"])
        if is_windows:
            activate_script = venv_path / "Scripts" / "activate.bat"
            command = f'"{activate_script}" && {python_command}'
            options = {"shell": True}
        else:
            activate_script = venv_path / "bin" / "activate"
            command = f'source "{activate_script}" && {python_command}'
            options = {"shell": True, "executable": "/bin/bash"}
    
    elif ENV_CONFIG["type"] == "venv-uv":
        if not ENV_CONFIG["uv_venv_path"]:
            raise ValueError("uv_venv_path is required for uv virtualenv")
        uv_venv_path = Path(ENV_CONFIG["uv_venv_path"])
        if is_windows:
            activate_script = uv_venv_path / "Scripts" / "activate.bat"
            command = f'"{activate_script}" && {python_command}'
            options = {"shell": True}
        else:
            activate_script = uv_venv_path / "bin" / "activate"
            command = f'source "{activate_script}" && {python_command}'
            options = {"shell": True, "executable": "/bin/bash"}
    
    else:
        raise ValueError(f"Unsupported environment type: {ENV_CONFIG['type']}")
    
    return command, options

def detect_package_manager() -> str:
    """Detect available package manager (same logic as workspace-server)"""
    try:
        # Check if uv is available
        subprocess.run(['uv', '--version'], capture_output=True, timeout=2)
        return 'uv'
    except (subprocess.TimeoutExpired, FileNotFoundError):
        try:
            # Check if conda is available and we're in a conda env
            if os.getenv("CONDA_DEFAULT_ENV"):
                subprocess.run(['conda', '--version'], capture_output=True, timeout=2)
                return 'conda'
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
    return 'pip'

def get_package_manager_commands(package_manager: str, packages: Optional[List[str]] = None) -> Dict[str, Any]:
    """Get package manager commands (same logic as workspace-server)"""
    is_windows = platform.system() == "Windows"
    python_cmd = "python" if is_windows else "python3"
    
    commands = {
        "pip": {
            "list": [python_cmd, "-m", "pip", "list", "--format=freeze"],
            "show": lambda pkg: [python_cmd, "-m", "pip", "show", pkg],
            "install": lambda pkgs: [python_cmd, "-m", "pip", "install"] + pkgs
        },
        "uv": {
            "list": ["uv", "pip", "list", "--format=freeze"],
            "show": lambda pkg: ["uv", "pip", "show", pkg],
            "install": lambda pkgs: ["uv", "pip", "install"] + pkgs
        },
        "conda": {
            "list": ["conda", "list", "--export"],
            "show": lambda pkg: ["conda", "list", pkg],
            "install": lambda pkgs: ["conda", "install", "-y"] + pkgs
        }
    }
    
    return commands[package_manager]


# ============================================================================
# MAIN TOOL FUNCTIONS
# ============================================================================

# Internal functions without decorators for testing
async def _execute_code_internal(
    code: str,
    filename: Optional[str] = None
) -> str:
    """Internal implementation of execute_code"""
    try:
        # Handle filename - resolve relative paths from CODE_STORAGE_DIR
        if filename:
            if Path(filename).is_absolute():
                # For absolute paths, use as-is
                abs_file_path = Path(filename)
            else:
                # For relative paths, resolve from CODE_STORAGE_DIR
                abs_file_path = Path(CODE_STORAGE_DIR) / filename
            
            # Check if path is forbidden
            error_reason = get_path_forbidden_reason(str(abs_file_path))
            if error_reason:
                return json.dumps({
                    "status": "error",
                    "error": error_reason,
                    "file_path": str(abs_file_path)
                })
        else:
            # Generate random filename in CODE_STORAGE_DIR
            final_filename = f"code_{random.randint(1000, 9999)}.py"
            abs_file_path = Path(CODE_STORAGE_DIR) / final_filename
        
        # Write code to file
        abs_file_path.write_text(code, encoding='utf-8')
        
        # Get platform-specific command
        python_cmd = f'python -u "{abs_file_path}"' if platform.system() == "Windows" else f'python3 -u "{abs_file_path}"'
        command, options = get_platform_specific_command(python_cmd)
        
        # Execute code
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        
        result = subprocess.run(
            command,
            cwd=CODE_STORAGE_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes timeout
            **options
        )
        
        # Return all output
        response_output = []
        if result.stderr:
            response_output.append(result.stderr)
        if result.stdout:
            response_output.append(result.stdout)
        
        response = {
            "status": "error" if result.stderr else "success",
            "output": "\n".join(response_output),
            "file_path": str(abs_file_path)
        }
        
        return json.dumps(response)
        
    except subprocess.TimeoutExpired:
        return json.dumps({
            "status": "error",
            "error": "Code execution timed out after 5 minutes",
            "file_path": filename or "unknown"
        })
    except Exception as error:
        return json.dumps({
            "status": "error",
            "error": str(error),
            "file_path": filename or "unknown"
        })

async def _read_file_internal(
    file_path: str
) -> str:
    """Internal implementation of read_file"""
    try:
        # Handle both absolute and relative paths
        if Path(file_path).is_absolute():
            # For absolute paths, use as-is
            abs_file_path = Path(file_path)
        else:
            # For relative paths, resolve from PROJECT_ROOT
            abs_file_path = PROJECT_ROOT / file_path
        
        # Check if path is forbidden
        error_reason = get_path_forbidden_reason(str(abs_file_path))
        if error_reason:
            return json.dumps({
                "status": "error",
                "error": error_reason,
                "file_path": file_path
            })
        
        # Read file content
        content = abs_file_path.read_text(encoding='utf-8')
        
        return json.dumps({
            "status": "success",
            "content": content,
            "file_path": file_path
        })
        
    except FileNotFoundError:
        return json.dumps({
            "status": "error",
            "error": f"File not found: {file_path}",
            "file_path": file_path
        })
    except Exception as error:
        return json.dumps({
            "status": "error",
            "error": str(error),
            "file_path": file_path
        })

async def _install_dependencies_internal(
    packages: List[str]
) -> str:
    """Internal implementation of install_dependencies"""
    try:
        if not packages or len(packages) == 0:
            return json.dumps({
                "status": "error",
                "error": "No packages specified"
            })
        
        # Filter out empty strings and normalize package names
        packages = [pkg.strip() for pkg in packages if pkg and isinstance(pkg, str) and pkg.strip()]
        
        if len(packages) == 0:
            return json.dumps({
                "status": "error",
                "error": "No valid package names provided"
            })
        
        # Auto-detect package manager or use environment-specified one
        if ENV_CONFIG["type"] == "conda":
            package_manager = "conda"
        elif ENV_CONFIG["type"] == "venv-uv":
            package_manager = "uv"
        elif ENV_CONFIG["type"] == "venv":
            package_manager = detect_package_manager()
        else:
            package_manager = detect_package_manager()
        
        commands = get_package_manager_commands(package_manager, packages)
        
        # Build the appropriate command based on detected package manager
        if package_manager == "conda" and ENV_CONFIG["conda_name"]:
            install_cmd = ["conda", "install", "-y", "-n", ENV_CONFIG["conda_name"]] + packages
        else:
            install_cmd = commands["install"](packages)
        
        # Create a temporary Python script to install packages
        temp_id = random.randint(1000, 9999)
        install_script_path = Path(CODE_STORAGE_DIR) / f"install_packages_{temp_id}.py"
        
        install_script = f'''
import subprocess
import sys
import json

def install_packages():
    """Install packages in the current environment."""
    try:
        result = subprocess.run({install_cmd}, 
                              capture_output=True, text=True, check=True)
        return {{
            "status": "success",
            "output": result.stdout,
            "warnings": result.stderr
        }}
    except Exception as e:
        return {{"status": "error", "error": str(e)}}

# Install packages
install_result = install_packages()

# Return the result
print(json.dumps(install_result))
'''
        
        install_script_path.write_text(install_script, encoding='utf-8')
        
        # Execute the install script
        python_cmd = f'python -u "{install_script_path}"' if platform.system() == "Windows" else f'python3 -u "{install_script_path}"'
        command, options = get_platform_specific_command(python_cmd)
        
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        
        result = subprocess.run(
            command,
            cwd=CODE_STORAGE_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes timeout
            **options
        )
        
        # Clean up the temporary script
        try:
            install_script_path.unlink()
        except:
            pass
        
        if result.stderr:
            return json.dumps({
                "status": "error",
                "env_type": ENV_CONFIG["type"],
                "package_manager": package_manager,
                "error": result.stderr
            })
        
        # Parse the response from the Python script
        try:
            parsed = json.loads(result.stdout.strip())
            return json.dumps(parsed)
        except json.JSONDecodeError:
            return json.dumps({
                "status": "error",
                "env_type": ENV_CONFIG["type"],
                "package_manager": package_manager,
                "error": f"Failed to parse output: {result.stdout}"
            })
        
    except Exception as error:
        return json.dumps({
            "status": "error",
            "env_type": ENV_CONFIG["type"],
            "error": str(error)
        })

async def _check_installed_packages_internal() -> str:
    """Internal implementation of check_installed_packages"""
    try:
        # Auto-detect package manager or use environment-specified one
        if ENV_CONFIG["type"] == "conda":
            package_manager = "conda"
        elif ENV_CONFIG["type"] == "venv-uv":
            package_manager = "uv"
        elif ENV_CONFIG["type"] == "venv":
            package_manager = detect_package_manager()
        else:
            package_manager = detect_package_manager()
        
        commands = get_package_manager_commands(package_manager)
        
        # Create a temporary Python script to get all installed packages
        temp_id = random.randint(1000, 9999)
        check_script_path = Path(CODE_STORAGE_DIR) / f"list_packages_{temp_id}.py"
        
        # Build the appropriate command based on detected package manager
        if package_manager == "conda" and ENV_CONFIG["conda_name"]:
            list_cmd = ["conda", "list", "-n", ENV_CONFIG["conda_name"], "--export"]
        else:
            list_cmd = commands["list"]
        
        check_script = f'''
import subprocess
import sys
import json

def get_all_installed_packages():
    """Get all installed packages in the current environment."""
    try:
        result = subprocess.run({list_cmd}, 
                              capture_output=True, text=True, check=True)
        packages = []
        for line in result.stdout.strip().split('\\n'):
            if line and ('==' in line or '=' in line):
                # Handle both pip freeze format (==) and conda format (=)
                if '==' in line:
                    name, version = line.split('==', 1)
                else:
                    parts = line.split('=')
                    name, version = parts[0], parts[1] if len(parts) > 1 else 'unknown'
                packages.append({{
                    "name": name.strip(),
                    "version": version.strip()
                }})
        return packages
    except Exception as e:
        return {{"error": str(e)}}

# Get all installed packages
all_packages = get_all_installed_packages()

# Return the result
if isinstance(all_packages, list):
    result = {{
        "status": "success",
        "total_packages": len(all_packages),
        "packages": all_packages,
        "package_manager": "{package_manager}"
    }}
else:
    result = {{
        "status": "error",
        "error": all_packages.get("error", "Unknown error"),
        "package_manager": "{package_manager}"
    }}

print(json.dumps(result))
'''
        
        check_script_path.write_text(check_script, encoding='utf-8')
        
        # Execute the check script
        python_cmd = f'python -u "{check_script_path}"' if platform.system() == "Windows" else f'python3 -u "{check_script_path}"'
        command, options = get_platform_specific_command(python_cmd)
        
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        
        result = subprocess.run(
            command,
            cwd=CODE_STORAGE_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,  # 1 minute timeout
            **options
        )
        
        # Clean up the temporary script
        try:
            check_script_path.unlink()
        except:
            pass
        
        if result.stderr:
            return json.dumps({
                "status": "error",
                "env_type": ENV_CONFIG["type"],
                "package_manager": package_manager,
                "error": result.stderr
            })
        
        # Parse the response from the Python script
        try:
            parsed = json.loads(result.stdout.strip())
        except json.JSONDecodeError:
            return json.dumps({
                "status": "error",
                "env_type": ENV_CONFIG["type"],
                "package_manager": package_manager,
                "error": f"Failed to parse output: {result.stdout}"
            })
        
        # Build the final response
        response = {
            "status": parsed.get("status", "error"),
            "env_type": ENV_CONFIG["type"],
            "package_manager": parsed.get("package_manager", package_manager),
            "total_packages": parsed.get("total_packages", 0),
            "installed_packages": parsed.get("packages", []),
            "error": parsed.get("error")
        }
        
        return json.dumps(response)
        
    except Exception as error:
        return json.dumps({
            "status": "error",
            "env_type": ENV_CONFIG["type"],
            "error": str(error)
        })

async def _check_package_version_internal(
    packages: List[str]
) -> str:
    """Internal implementation of check_package_version"""
    try:
        if not packages or len(packages) == 0:
            return json.dumps({
                "status": "error",
                "error": "No packages specified"
            })
        
        # Filter out empty strings and normalize package names
        packages = [pkg.strip() for pkg in packages if pkg and isinstance(pkg, str) and pkg.strip()]
        
        if len(packages) == 0:
            return json.dumps({
                "status": "error",
                "error": "No valid package names provided"
            })
        
        # Auto-detect package manager or use environment-specified one
        if ENV_CONFIG["type"] == "conda":
            package_manager = "conda"
        elif ENV_CONFIG["type"] == "venv-uv":
            package_manager = "uv"
        elif ENV_CONFIG["type"] == "venv":
            package_manager = detect_package_manager()
        else:
            package_manager = detect_package_manager()
        
        commands = get_package_manager_commands(package_manager)
        
        results = []
        for package_name in packages:
            version = "unknown"
            package_path = "unknown"
            location = "unknown"
            error = None
            
            # Step 1: Try to get version using appropriate package manager show command
            try:
                if package_manager == "conda" and ENV_CONFIG["conda_name"]:
                    show_cmd = ["conda", "list", "-n", ENV_CONFIG["conda_name"], package_name]
                else:
                    show_cmd = commands["show"](package_name)
                
                command, options = get_platform_specific_command(" ".join(show_cmd))
                
                result = subprocess.run(
                    command,
                    cwd=CODE_STORAGE_DIR,
                    env=os.environ.copy(),
                    capture_output=True,
                    text=True,
                    timeout=30,
                    **options
                )
                
                lines = result.stdout.split("\n")
                for line in lines:
                    if line.startswith("Version:"):
                        version = line.split(":")[1].strip()
                    if line.startswith("Location:"):
                        location = line.split(":")[1].strip()
                        # Try different possible package paths
                        possible_paths = [
                            os.path.join(location, package_name),
                            os.path.join(location, package_name.replace("-", "_")),
                            os.path.join(location, package_name.replace("-", "/")),
                        ]
                        
                        # For packages ending with -py, try removing the suffix
                        if package_name.endswith("-py"):
                            possible_paths.append(os.path.join(location, package_name[:-3]))
                        
                        # For packages with multiple hyphens, try first part only
                        if "-" in package_name and package_name.count("-") > 1:
                            first_part = package_name.split("-")[0]
                            possible_paths.append(os.path.join(location, first_part))
                        
                        # Find the first existing path
                        package_path = "unknown"
                        for path in possible_paths:
                            if os.path.exists(path):
                                package_path = path
                                break
                        
                        # Fallback to original logic if none found
                        if package_path == "unknown":
                            package_path = os.path.join(location, package_name)
                        
            except Exception as e:
                error = f"{package_manager} show failed: {e}"
            
            # Step 2: Try multiple import strategies to find the correct module
            try:
                # Generate all possible variations of the package name
                variations = {package_name}
                
                # Replace hyphens with underscores
                if '-' in package_name:
                    variations.add(package_name.replace('-', '_'))
                
                # Replace hyphens with dots
                if '-' in package_name:
                    variations.add(package_name.replace('-', '.'))
                
                # Replace underscores with hyphens
                if '_' in package_name:
                    variations.add(package_name.replace('_', '-'))
                
                # Replace dots with hyphens
                if '.' in package_name:
                    variations.add(package_name.replace('.', '-'))
                
                # Replace dots with underscores
                if '.' in package_name:
                    variations.add(package_name.replace('.', '_'))
                
                # Try each variation until one succeeds
                success = False
                for variation in variations:
                    try:
                        py_cmd = f'python -c "import {variation}; print({variation}.__file__); print(getattr({variation}, \'__version__\', \'no __version__\'))"'
                        command, options = get_platform_specific_command(py_cmd)
                        
                        result = subprocess.run(
                            command,
                            cwd=CODE_STORAGE_DIR,
                            env=os.environ.copy(),
                            capture_output=True,
                            text=True,
                            timeout=30,
                            **options
                        )
                        
                        if result.stdout.strip():
                            lines = result.stdout.strip().split("\n")
                            # Check if we got a valid file path (not None)
                            if len(lines) >= 1 and lines[0] != 'None':
                                location = lines[0]
                                if package_path == "unknown" and location:
                                    package_path = str(Path(location).parent)
                            elif len(lines) >= 1 and lines[0] == 'None':
                                # Handle namespace packages where __file__ is None
                                # Try to get the path from __path__
                                try:
                                    path_cmd = f'python -c "import {variation}; print(str({variation}.__path__))"'
                                    command, options = get_platform_specific_command(path_cmd)
                                    
                                    result = subprocess.run(
                                        command,
                                        cwd=CODE_STORAGE_DIR,
                                        env=os.environ.copy(),
                                        capture_output=True,
                                        text=True,
                                        timeout=30,
                                        **options
                                    )
                                    
                                    if result.stdout.strip() and result.stdout.strip() != 'None':
                                        # Extract path from _NamespacePath format
                                        import re
                                        path_match = re.search(r"_NamespacePath\(\[['\"]([^'\"]+)['\"]\]\)", result.stdout.strip())
                                        if path_match:
                                            location = path_match.group(1)
                                            if package_path == "unknown" and location:
                                                package_path = str(Path(location).parent)
                                except:
                                    pass
                            
                            if len(lines) >= 2 and lines[1] != "no __version__":
                                version = lines[1]
                            success = True
                            break  # Found a working variation
                            
                    except:
                        continue
                
                # Final fallback: try importlib with original name
                if not success:
                    py_cmd = f'python -c "import importlib; pkg = importlib.import_module(\'{package_name}\'); print(pkg.__file__); print(getattr(pkg, \'__version__\', \'no __version__\'))"'
                    command, options = get_platform_specific_command(py_cmd)
                    
                    result = subprocess.run(
                        command,
                        cwd=CODE_STORAGE_DIR,
                        env=os.environ.copy(),
                        capture_output=True,
                        text=True,
                        timeout=30,
                        **options
                    )
                    
                    if result.stdout.strip():
                        lines = result.stdout.strip().split("\n")
                        # Check if we got a valid file path (not None)
                        if len(lines) >= 1 and lines[0] != 'None':
                            location = lines[0]
                            if package_path == "unknown" and location:
                                package_path = str(Path(location).parent)
                        elif len(lines) >= 1 and lines[0] == 'None':
                            # Handle namespace packages where __file__ is None
                            try:
                                path_cmd = f'python -c "import importlib; pkg = importlib.import_module(\'{package_name}\'); print(str(pkg.__path__))"'
                                command, options = get_platform_specific_command(path_cmd)
                                
                                result = subprocess.run(
                                    command,
                                    cwd=CODE_STORAGE_DIR,
                                    env=os.environ.copy(),
                                    capture_output=True,
                                    text=True,
                                    timeout=30,
                                    **options
                                )
                                
                                if result.stdout.strip() and result.stdout.strip() != 'None':
                                    # Extract path from _NamespacePath format
                                    import re
                                    path_match = re.search(r"_NamespacePath\(\[['\"]([^'\"]+)['\"]\]\)", result.stdout.strip())
                                    if path_match:
                                        location = path_match.group(1)
                                        if package_path == "unknown" and location:
                                            package_path = str(Path(location).parent)
                            except:
                                pass
                        
                        if len(lines) >= 2 and lines[1] != "no __version__":
                            version = lines[1]
                        success = True
                        
            except Exception as e:
                if not error:
                    error = f"python import failed: {e}"
            
            # Final fix: Use location from import
            if location and location.endswith('__init__.py'):
                dir_from_location = location[:location.rfind('/__init__.py')]
                if dir_from_location:
                    package_path = dir_from_location
            
            results.append({
                "package_name": package_name,
                "version": version,
                "package_path": package_path,
                "location": location,
                "error": error,
                "summary": f"Package {package_name} version {version} at {package_path}"
            })
        
        return json.dumps({
            "status": "success",
            "env_type": ENV_CONFIG["type"],
            "package_manager": package_manager,
            "venv_path": ENV_CONFIG.get("venv_path"),
            "package_details": results
        })
        
    except Exception as error:
        return json.dumps({
            "status": "error",
            "error": str(error),
            "env_type": ENV_CONFIG["type"],
            "venv_path": ENV_CONFIG.get("venv_path")
        })

async def _save_file_internal(
    content: str,
    filename: str
) -> str:
    """Internal implementation of save_file"""
    try:
        # Handle filename - resolve relative paths from SAVED_FILES_DIR
        if Path(filename).is_absolute():
            # For absolute paths, use as-is
            file_path = Path(filename)
        else:
            # For relative paths, resolve from SAVED_FILES_DIR
            file_path = Path(SAVED_FILES_DIR) / filename
        
        # Check if path is forbidden
        error_reason = get_path_forbidden_reason(str(file_path))
        if error_reason:
            return json.dumps({
                "status": "error",
                "error": error_reason,
                "filename": filename
            })
        
        # Ensure filename has .py extension if it's a relative path
        if not Path(filename).is_absolute() and not file_path.name.endswith('.py'):
            file_path = file_path.with_suffix('.py')
        
        # Write content to file
        file_path.write_text(content, encoding='utf-8')
        
        return json.dumps({
            "status": "success",
            "message": "File saved successfully",
            "file_path": str(file_path),
            "filename": filename
        })
        
    except Exception as error:
        return json.dumps({
            "status": "error",
            "error": str(error)
        })

async def _execute_shell_command_internal(
    command: str,
    working_dir: Optional[str] = None
) -> str:
    """Internal implementation of execute_shell_command with 6-layer security architecture"""
    try:
        # Security check for working directory (Layer 1)
        resolved_working_dir = working_dir
        if working_dir:
            # Handle both absolute and relative paths
            if Path(working_dir).is_absolute():
                abs_working_dir = Path(working_dir)
            else:
                abs_working_dir = PROJECT_ROOT / working_dir
            
            error_reason = get_path_forbidden_reason(str(abs_working_dir))
            if error_reason:
                return json.dumps({
                    "status": "error",
                    "error": error_reason
                })
            resolved_working_dir = str(abs_working_dir)
        
        # Enhanced security checks for shell commands using comprehensive forbidden path detection
        
        # 1. Extract and check potential file paths from the command (Layer 2)
        potential_paths = extract_paths_from_command(command)
        for path in potential_paths:
            error_reason = get_path_forbidden_reason(path)
            if error_reason:
                return json.dumps({
                    "status": "error",
                    "error": error_reason
                })
        
        # 2. Check for dangerous commands that could access forbidden paths (Layer 3)
        forbidden_dir_name = FORBIDDEN_PATH.name
        dangerous_patterns = [
            rf'find\s+.*{forbidden_dir_name}',
            rf'grep\s+.*{forbidden_dir_name}',
            rf'cat\s+.*{forbidden_dir_name}',
            rf'cp\s+.*{forbidden_dir_name}',
            rf'mv\s+.*{forbidden_dir_name}',
            rf'rm\s+.*{forbidden_dir_name}',
            rf'ls\s+.*{forbidden_dir_name}',
            rf'tar\s+.*{forbidden_dir_name}',
            rf'zip\s+.*{forbidden_dir_name}',
            rf'unzip\s+.*{forbidden_dir_name}',
        ]
        
        import re
        for pattern in dangerous_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return json.dumps({
                    "status": "error",
                    "error": f"Command contains explicit reference to forbidden directory: {command}"
                })
        
        # 3. Check for glob patterns that could access forbidden content (Layer 4)
        if '*' in command:
            # Check if the command uses dangerous relative paths that could access forbidden content
            # Only block "find ." or "find ./" (without specific subdirectory)
            if (re.search(r'find\s+\.\s', command) or re.search(r'find\s+\.$', command) or
                re.search(r'find\s+\.\/\s', command) or re.search(r'find\s+\.\/$', command)):
                # Commands like "find ." or "find ./" could search in forbidden directories
                return json.dumps({
                    "status": "error",
                    "error": f"Glob pattern with relative path could access forbidden content. Please specify a specific directory: {command}"
                })
            
            # Also check for unrestricted glob patterns without any path restrictions
            # But allow commands that specify a specific directory (like "find deep_solver_benchmark -name '*.py'")
            if '/' not in command and '\\' not in command and not re.search(r'find\s+\w+', command):
                return json.dumps({
                    "status": "error",
                    "error": f"Unrestricted glob pattern could access forbidden content. Please specify a directory: {command}"
                })
        
        # 4. Forbid dangerous commands (Layer 5)
        dangerous_commands = [
            'rm -rf', 'sudo', 'su', 'chmod 777', 'chown root',
            'dd if=', 'mkfs', 'fdisk', 'mount', 'umount',
            'systemctl', 'service', 'init', 'telinit',
            'curl', 'wget', 'nc', 'netcat', 'ssh', 'scp', 'rsync'
        ]
        
        for dangerous_cmd in dangerous_commands:
            if dangerous_cmd in command:
                return json.dumps({
                    "status": "error",
                    "error": f"Dangerous commands are forbidden: {dangerous_cmd}"
                })
        
        # Execute command with output-based security monitoring
        actual_working_dir = resolved_working_dir if working_dir else str(PROJECT_ROOT)
        
        result = subprocess.run(
            command,
            cwd=actual_working_dir,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes timeout
            shell=True
        )
        
        # Check if output contains forbidden directory content (Layer 6)
        forbidden_path = str(FORBIDDEN_PATH)
        
        # More comprehensive check for forbidden directory content
        forbidden_patterns = [
            f'"{forbidden_dir_name}"',           # "benchmark"
            f'/{forbidden_dir_name}/',           # /benchmark/
            f'{forbidden_dir_name}/',            # benchmark/
            forbidden_path,                     # Full absolute path
            str(Path(forbidden_path).relative_to(PROJECT_ROOT)), # Relative path from project root
        ]
        
        output_to_check = result.stdout + result.stderr
        for pattern in forbidden_patterns:
            if pattern and pattern in output_to_check:
                return json.dumps({
                    "status": "error",
                    "error": f"Command output contains content from forbidden directory: {pattern}"
                })
        
        response = {
            "status": "warning" if result.stderr else "success",
            "stdout": result.stdout,
            "stderr": result.stderr
        }
        
        return json.dumps(response)
        
    except subprocess.TimeoutExpired:
        return json.dumps({
            "status": "error",
            "error": "Command execution timed out after 5 minutes"
        })
    except Exception as error:
        return json.dumps({
            "status": "error",
            "error": "Command execution failed"
        })

async def _create_and_execute_script_internal(
    script_content: str,
    filename: Optional[str] = None,
    interpreter: Optional[str] = None
) -> str:
    """Internal implementation of create_and_execute_script"""
    try:
        # Generate filename if not provided
        if not filename:
            filename = f"script_{random.randint(1000, 9999)}.sh"
        
        # Handle filename - resolve relative paths from CODE_STORAGE_DIR
        if Path(filename).is_absolute():
            # For absolute paths, use as-is
            file_path = Path(filename)
        else:
            # For relative paths, resolve from CODE_STORAGE_DIR
            file_path = Path(CODE_STORAGE_DIR) / filename
        
        # Check if path is forbidden
        error_reason = get_path_forbidden_reason(str(file_path))
        if error_reason:
            return json.dumps({
                "status": "error",
                "error": error_reason,
                "filename": filename
            })
        
        # Add shebang if not present and interpreter is specified
        final_content = script_content
        if interpreter and not script_content.startswith('#!'):
            final_content = f"#!/usr/bin/env {interpreter}\n\n{script_content}"
        elif not script_content.startswith('#!'):
            # Default to bash if no shebang
            final_content = f"#!/usr/bin/env bash\n\n{script_content}"
        
        # Write script to file
        file_path.write_text(final_content, encoding='utf-8')
        
        # Make script executable (Unix-like systems)
        if platform.system() != "Windows":
            os.chmod(file_path, 0o755)
        
        # Execute the script
        result = subprocess.run(
            str(file_path),
            cwd=CODE_STORAGE_DIR,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes timeout
            shell=True
        )
        
        response = {
            "status": "warning" if result.stderr else "success",
            "stdout": result.stdout,
            "stderr": result.stderr,
            "script_path": str(file_path),
            "script_content": final_content
        }
        
        return json.dumps(response)
        
    except subprocess.TimeoutExpired:
        return json.dumps({
            "status": "error",
            "error": "Script execution timed out after 5 minutes",
            "script_path": filename or "unknown",
            "script_content": script_content
        })
    except Exception as error:
        return json.dumps({
            "status": "error",
            "error": str(error),
            "script_path": filename or "unknown",
            "script_content": script_content
        })

@function_tool
async def read_file(
    file_path: str
) -> str:
    f"""
    Read the content of any text file (Python code, log files, output files, etc.). Use this to examine local package code files, output files from external programs, log files, or any text-based files to extract specific information
    
    PATH HANDLING: Prefer absolute paths. If using relative paths, they are resolved from {PROJECT_ROOT}
    
    Args:
        file_path: Path to the file to read (supports any text file format: .py, .log, .txt, .out, .xyz, etc.). Using absolute paths (preferred) or relative paths from {PROJECT_ROOT}
    
    Returns:
        JSON string with file content and status
    """
    return await _read_file_internal(file_path)

@function_tool
async def install_dependencies(
    packages: List[str]
) -> str:
    """
    Install missing Python dependencies in the configured environment. Use this tool to install packages that are required for your code to run. Example: {"packages": ["package1", "package2", "package3"]}
    
    Args:
        packages: Array of package names to install. Each package should be a string. Example: ["package1", "package2", "package3"]
    
    Returns:
        JSON string with installation results
    """
    return await _install_dependencies_internal(packages)

@function_tool
async def check_installed_packages() -> str:
    """
    List all installed packages in the current Python environment. Use this tool to check what packages are already available before attempting to install new ones
    
    Returns:
        JSON string with all installed packages information
    """
    return await _check_installed_packages_internal()

@function_tool
async def check_package_version(
    packages: List[str]
) -> str:
    """
    Check if specific packages are installed and get their version, package path, and module location information. Use this tool to verify specific package installations. Example: {"packages": ["package1", "package2", "package3"]}
    
    Args:
        packages: Array of package names to check. Each package should be a string. Example: ["package1", "package2", "package3"]
    
    Returns:
        JSON string with package version and location information
    """
    return await _check_package_version_internal(packages)

@function_tool
async def save_file(
    content: str,
    filename: str
) -> str:
    f"""
    Save a file to {SAVED_FILES_DIR} with the specified filename
    
    Args:
        content: Content of the file
        filename: Filename of the file
    
    Returns:
        JSON string with save results
    """
    return await _save_file_internal(content, filename)

@function_tool
async def execute_shell_command(
    command: str,
    working_dir: Optional[str] = None
) -> str:
    f"""
    Execute a shell command and return the result. Default working directory is {PROJECT_ROOT}
    
    PATH HANDLING: Prefer absolute paths for working_dir. If using relative paths for working_dir, they are resolved from {PROJECT_ROOT}
    
    Args:
        command: Shell command to execute
        working_dir: Working directory for the command (absolute path or relative path from {PROJECT_ROOT}). Default is {PROJECT_ROOT}
    
    Returns:
        JSON string with command execution results
    """
    return await _execute_shell_command_internal(command, working_dir)

@function_tool
async def create_and_execute_script(
    script_content: str,
    filename: Optional[str] = None,
    interpreter: Optional[str] = None
) -> str:
    f"""
    Create and execute a shell script. Scripts are created in {CODE_STORAGE_DIR}
    
    Args:
        script_content: Content of the script
        filename: Optional name of the script file
        interpreter: Optional interpreter for the script
    
    Returns:
        JSON string with script execution results
    """
    return await _create_and_execute_script_internal(script_content, filename, interpreter)


# Create decorated versions for agents framework
@function_tool
async def execute_code(
    code: str,
    filename: Optional[str] = None
) -> str:
    f"""
    Execute Python code in the configured environment. Code is saved to {CODE_STORAGE_DIR} and executed. Use this tool to run Python scripts and get their output.
    
    Args:
        code: Python code to execute
        filename: Optional name of the file to save the code (default: generated UUID)
    
    Returns:
        JSON string with execution results including status, output, and file path
    """
    return await _execute_code_internal(code, filename)

# Export all tools
__all__ = [
    "execute_code",
    "read_file", 
    "install_dependencies",
    "check_installed_packages",
    "check_package_version",
    "save_file",
    "execute_shell_command",
    "create_and_execute_script"
]
