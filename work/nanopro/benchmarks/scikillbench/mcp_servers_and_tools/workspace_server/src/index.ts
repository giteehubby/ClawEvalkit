#!/usr/bin/env node

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
    CallToolRequestSchema,
    ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { randomBytes } from 'crypto';
import { fileURLToPath } from 'url';
import { dirname, join, resolve, relative, isAbsolute, basename } from 'path';
import { mkdir, writeFile, appendFile, readFile, access, unlink } from 'fs/promises';
import { exec, ExecOptions } from 'child_process';
import { promisify } from 'util';
import { platform } from 'os';

// ES module compatible __filename and __dirname
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const projectRoot = resolve(__dirname, '..', '..');

function resolveStorageDir(dir: string): string {
    if (!dir) return '';
    return isAbsolute(dir) ? dir : resolve(projectRoot, dir);
}

// Define environment config interface for type safety
interface EnvironmentConfig {
    type: 'conda' | 'venv' | 'venv-uv';
    conda_name?: string;
    venv_path?: string;
    uv_venv_path?: string;
}

const CODE_STORAGE_DIR = resolveStorageDir(process.env.CODE_STORAGE_DIR || '');
const SAVED_FILES_DIR = resolveStorageDir(process.env.SAVED_FILES_DIR || '');
// Default environment settings
let ENV_CONFIG: EnvironmentConfig = {
    // Default environment (conda, venv, or venv-uv)
    type: (process.env.ENV_TYPE || 'conda') as 'conda' | 'venv' | 'venv-uv',
    // Name of the conda environment
    conda_name: process.env.CONDA_ENV_NAME,
    // Path to virtualenv
    venv_path: process.env.VENV_PATH,
    // Path to uv virtualenv
    uv_venv_path: process.env.UV_VENV_PATH
};

if (!CODE_STORAGE_DIR) {
    throw new Error('Missing required environment variable: CODE_STORAGE_DIR');
}

if (!SAVED_FILES_DIR) {
    throw new Error('Missing required environment variable: SAVED_FILES_DIR');
}

// Validate environment settings based on the selected type
if (ENV_CONFIG.type === 'conda' && !ENV_CONFIG.conda_name) {
    throw new Error('Missing required environment variable: CONDA_ENV_NAME (required for conda environment)');
} else if (ENV_CONFIG.type === 'venv' && !ENV_CONFIG.venv_path) {
    throw new Error('Missing required environment variable: VENV_PATH (required for virtualenv)');
} else if (ENV_CONFIG.type === 'venv-uv' && !ENV_CONFIG.uv_venv_path) {
    throw new Error('Missing required environment variable: UV_VENV_PATH (required for uv virtualenv)');
}

const execAsync = promisify(exec);

/**
 * Get platform-specific command for environment activation and execution
 */
function getPlatformSpecificCommand(pythonCommand: string): { command: string, options: ExecOptions } {
    const isWindows = platform() === 'win32';
    let command = '';
    let options: ExecOptions = {};
    
    switch (ENV_CONFIG.type) {
        case 'conda':
            if (!ENV_CONFIG.conda_name) {
                throw new Error("conda_name is required for conda environment");
            }
            if (isWindows) {
                command = `conda run -n ${ENV_CONFIG.conda_name} ${pythonCommand}`;
                options = { shell: 'cmd.exe' };
            } else {
                command = `source $(conda info --base)/etc/profile.d/conda.sh && conda activate ${ENV_CONFIG.conda_name} && ${pythonCommand}`;
                options = { shell: '/bin/bash' };
            }
            break;
            
        case 'venv':
            if (!ENV_CONFIG.venv_path) {
                throw new Error("venv_path is required for virtualenv");
            }
            if (isWindows) {
                command = `${join(ENV_CONFIG.venv_path, 'Scripts', 'activate')} && ${pythonCommand}`;
                options = { shell: 'cmd.exe' };
            } else {
                command = `source ${join(ENV_CONFIG.venv_path, 'bin', 'activate')} && ${pythonCommand}`;
                options = { shell: '/bin/bash' };
            }
            break;
            
        case 'venv-uv':
            if (!ENV_CONFIG.uv_venv_path) {
                throw new Error("uv_venv_path is required for uv virtualenv");
            }
            if (isWindows) {
                command = `${join(ENV_CONFIG.uv_venv_path, 'Scripts', 'activate')} && ${pythonCommand}`;
                options = { shell: 'cmd.exe' };
            } else {
                command = `source ${join(ENV_CONFIG.uv_venv_path, 'bin', 'activate')} && ${pythonCommand}`;
                options = { shell: '/bin/bash' };
            }
            break;
            
        default:
            throw new Error(`Unsupported environment type: ${ENV_CONFIG.type}`);
    }
    
    return { command, options };
}

/**
 * Execute Python code and return the result
 */
async function executeCode(code: string, filePath: string) {
    try {
        // Handle filename - resolve relative paths from CODE_STORAGE_DIR
        let absFilePath: string;
        if (isAbsolute(filePath)) {
            // For absolute paths, use as-is
            absFilePath = filePath;
        } else {
            // For relative paths, resolve from CODE_STORAGE_DIR
            absFilePath = join(CODE_STORAGE_DIR, filePath);
        }
        
        // Check if path is forbidden and provide accurate error message
        const errorReason = getPathForbiddenReason(absFilePath);
        if (errorReason) {
            return {
                type: 'text',
                text: JSON.stringify({
                    status: 'error',
                    error: errorReason,
                    file_path: absFilePath
                }),
                isError: true
            };
        }
        
        // Write code to file
        await writeFile(absFilePath, code, 'utf-8');

        // Get platform-specific command with unbuffered output
        const pythonCmd = platform() === 'win32' ? `python -u "${absFilePath}"` : `python3 -u "${absFilePath}"`;
        const { command, options } = getPlatformSpecificCommand(pythonCmd);

        // Execute code
        const { stdout, stderr } = await execAsync(command, {
            cwd: CODE_STORAGE_DIR,
            env: { ...process.env, PYTHONUNBUFFERED: '1' },
            ...options
        });

        // Return all output
        const responseOutput = [stderr, stdout].filter(Boolean).join('\n');
        
        const response = {
            status: stderr ? 'error' : 'success',
            output: responseOutput,
            file_path: absFilePath
        };

        return {
            type: 'text',
            text: JSON.stringify(response),
            isError: !!stderr
        };
    } catch (error) {
        const response = {
            status: 'error',
            error: error instanceof Error ? error.message : String(error),
            file_path: filePath
        };

        return {
            type: 'text',
            text: JSON.stringify(response),
            isError: true
        };
    }
}

/**
 * Read the content of a code file
 */
async function readCodeFile(filePath: string) {
    try {
        // Normalize the path first
        const normalizedPath = isAbsolute(filePath) ? filePath : join(PROJECT_ROOT, filePath);
        
        // Check if path is forbidden and provide accurate error message
        const errorReason = getPathForbiddenReason(normalizedPath);
        if (errorReason) {
            return {
                type: 'text',
                text: JSON.stringify({
                    status: 'error',
                    error: errorReason,
                    file_path: filePath
                }),
                isError: true
            };
        }
        // Ensure file exists
        await access(normalizedPath);
        
        // Read file content
        const content = await readFile(normalizedPath, 'utf-8');
        
        return {
            type: 'text',
            text: JSON.stringify({
                status: 'success',
                content: content,
                file_path: filePath
            }),
            isError: false
        };
    } catch (error) {
        return {
            type: 'text',
            text: JSON.stringify({
                status: 'error',
                error: error instanceof Error ? error.message : String(error),
                file_path: filePath
            }),
            isError: true
        };
    }
}

// Add package manager detection utilities at the top level
async function detectPackageManager(): Promise<'pip' | 'uv' | 'conda'> {
    try {
        // Check if uv is available
        await execAsync('uv --version', { timeout: 2000 });
        return 'uv';
    } catch {
        try {
            // Check if conda is available and we're in a conda env
            if (process.env.CONDA_DEFAULT_ENV) {
                await execAsync('conda --version', { timeout: 2000 });
                return 'conda';
            }
        } catch {
            // Fall back to pip
        }
    }
    return 'pip';
}

async function getPackageManagerCommands(packageManager: 'pip' | 'uv' | 'conda', packages?: string[]) {
    const commands = {
        pip: {
            list: [process.platform === 'win32' ? 'python' : 'python3', '-m', 'pip', 'list', '--format=freeze'],
            show: (pkg: string) => [process.platform === 'win32' ? 'python' : 'python3', '-m', 'pip', 'show', pkg],
            install: (pkgs: string[]) => [process.platform === 'win32' ? 'python' : 'python3', '-m', 'pip', 'install', ...pkgs]
        },
        uv: {
            list: ['uv', 'pip', 'list', '--format=freeze'],
            show: (pkg: string) => ['uv', 'pip', 'show', pkg],
            install: (pkgs: string[]) => ['uv', 'pip', 'install', ...pkgs]
        },
        conda: {
            list: ['conda', 'list', '--export'],
            show: (pkg: string) => ['conda', 'list', pkg],
            install: (pkgs: string[]) => ['conda', 'install', '-y', ...pkgs]
        }
    };
    
    return commands[packageManager];
}

/**
 * Install dependencies using the appropriate package manager
 */
async function installDependencies(packages: string[]) {
    try {
        if (!packages || packages.length === 0) {
            return {
                type: 'text',
                text: JSON.stringify({
                    status: 'error',
                    error: 'No packages specified'
                }),
                isError: true
            };
        }

        // Auto-detect package manager or use environment-specified one
        let packageManager: 'pip' | 'uv' | 'conda';
        
        // First, respect explicit environment configuration
        if (ENV_CONFIG.type === 'conda') {
            packageManager = 'conda';
        } else if (ENV_CONFIG.type === 'venv-uv') {
            packageManager = 'uv';
        } else if (ENV_CONFIG.type === 'venv') {
            // For venv, detect if uv is available and prefer it
            packageManager = await detectPackageManager();
        } else {
            // Auto-detect for other cases
            packageManager = await detectPackageManager();
        }

        const commands = await getPackageManagerCommands(packageManager, packages);
        
        // Create a temporary Python script to get all installed packages
        const tempId = randomBytes(4).toString('hex');
        const installScriptPath = join(CODE_STORAGE_DIR, `install_packages_${tempId}.py`);
        
                 // Build the appropriate command based on detected package manager
         let installCommand = '';
         if (packageManager === 'conda' && ENV_CONFIG.conda_name) {
             const condaInstallCmd = ['conda', 'install', '-y', '-n', ENV_CONFIG.conda_name, ...packages];
             installCommand = JSON.stringify(condaInstallCmd);
         } else {
             const installCmd = commands.install(packages);
             installCommand = JSON.stringify(installCmd);
         }
        
        const installScript = `
import subprocess
import sys
import json

def install_packages():
    """Install packages in the current environment."""
    try:
        result = subprocess.run(${installCommand}, 
                              capture_output=True, text=True, check=True)
        return {
            "status": "success",
            "output": result.stdout,
            "warnings": result.stderr
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

# Install packages
install_result = install_packages()

# Return the result
print(json.dumps(install_result))
`;

        await writeFile(installScriptPath, installScript, 'utf-8');

        // Execute the install script with unbuffered output
        const pythonCmd = platform() === 'win32' ? `python -u "${installScriptPath}"` : `python3 -u "${installScriptPath}"`;
        const { command: installCommandExec, options: installOptions } = getPlatformSpecificCommand(pythonCmd);

        const { stdout, stderr } = await execAsync(installCommandExec, {
            cwd: CODE_STORAGE_DIR,
            env: { ...process.env, PYTHONUNBUFFERED: '1' },
            ...installOptions
        });

        if (stderr) {
            return {
                type: 'text',
                text: JSON.stringify({
                    status: 'error',
                    env_type: ENV_CONFIG.type,
                    package_manager: packageManager,
                    error: stderr
                }),
                isError: true
            };
        }

        // Parse the response from the Python script
        let parsed;
        try {
            parsed = JSON.parse(stdout.trim());
        } catch (e) {
            return {
                type: 'text',
                text: JSON.stringify({
                    status: 'error',
                    env_type: ENV_CONFIG.type,
                    package_manager: packageManager,
                    error: `Failed to parse output: ${stdout}`
                }),
                isError: true
            };
        }

        // Clean up the temporary script
        try {
            await unlink(installScriptPath);
        } catch (e) {
            // Ignore cleanup errors
        }

        // Check if the installation failed
        const isError = parsed.status === 'error';

        return {
            type: 'text',
            text: JSON.stringify(parsed),
            isError: isError
        };
    } catch (error) {
        const response = {
            status: 'error',
            env_type: ENV_CONFIG.type,
            error: error instanceof Error ? error.message : String(error)
        };

        return {
            type: 'text',
            text: JSON.stringify(response),
            isError: true
        };
    }
}

/**
 * Check if packages are installed in the current environment
 */
async function checkPackageInstallation(packages: string[]) {
    try {
        // Auto-detect package manager or use environment-specified one
        let packageManager: 'pip' | 'uv' | 'conda';
        
        // First, respect explicit environment configuration
        if (ENV_CONFIG.type === 'conda') {
            packageManager = 'conda';
        } else if (ENV_CONFIG.type === 'venv-uv') {
            packageManager = 'uv';
        } else if (ENV_CONFIG.type === 'venv') {
            // For venv, detect if uv is available and prefer it
            packageManager = await detectPackageManager();
        } else {
            // Auto-detect for other cases
            packageManager = await detectPackageManager();
        }

        const commands = await getPackageManagerCommands(packageManager);
        
        // Create a temporary Python script to get all installed packages
        const tempId = randomBytes(4).toString('hex');
        const checkScriptPath = join(CODE_STORAGE_DIR, `list_packages_${tempId}.py`);
        
        // Build the appropriate command based on detected package manager
        let listCommand = '';
        if (packageManager === 'conda' && ENV_CONFIG.conda_name) {
            listCommand = `['conda', 'list', '-n', '${ENV_CONFIG.conda_name}', '--export']`;
        } else {
            listCommand = JSON.stringify(commands.list);
        }
        
        const checkScript = `
import subprocess
import sys
import json

def get_all_installed_packages():
    """Get all installed packages in the current environment."""
    try:
        result = subprocess.run(${listCommand}, 
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
                packages.append({
                    "name": name.strip(),
                    "version": version.strip()
                })
        return packages
    except Exception as e:
        return {"error": str(e)}

# Get all installed packages
all_packages = get_all_installed_packages()

# Return the result
if isinstance(all_packages, list):
    result = {
        "status": "success",
        "total_packages": len(all_packages),
        "packages": all_packages,
        "package_manager": "${packageManager}"
    }
else:
    result = {
        "status": "error",
        "error": all_packages.get("error", "Unknown error"),
        "package_manager": "${packageManager}"
    }

print(json.dumps(result))
`;

        await writeFile(checkScriptPath, checkScript, 'utf-8');

        // Execute the check script with unbuffered output
        const pythonCmd = platform() === 'win32' ? `python -u "${checkScriptPath}"` : `python3 -u "${checkScriptPath}"`;
        const { command, options } = getPlatformSpecificCommand(pythonCmd);

        const { stdout, stderr } = await execAsync(command, {
            cwd: CODE_STORAGE_DIR,
            env: { ...process.env, PYTHONUNBUFFERED: '1' },
            ...options
        });

        if (stderr) {
            return {
                type: 'text',
                text: JSON.stringify({
                    status: 'error',
                    env_type: ENV_CONFIG.type,
                    package_manager: packageManager,
                    error: stderr
                }),
                isError: true
            };
        }

        // Parse the response from the Python script
        let parsed;
        try {
            parsed = JSON.parse(stdout.trim());
        } catch (e) {
            return {
                type: 'text',
                text: JSON.stringify({
                    status: 'error',
                    env_type: ENV_CONFIG.type,
                    package_manager: packageManager,
                    error: `Failed to parse output: ${stdout}`
                }),
                isError: true
            };
        }

        // Build the final response
        const response = {
            status: parsed.status,
            env_type: ENV_CONFIG.type,
            package_manager: parsed.package_manager || packageManager,
            total_packages: parsed.total_packages || 0,
            installed_packages: parsed.packages || [],
            error: parsed.error
        };

        // Clean up the temporary script
        try {
            await unlink(checkScriptPath);
        } catch (e) {
            // Ignore cleanup errors
        }

        return {
            type: 'text',
            text: JSON.stringify(response),
            isError: false
        };
    } catch (error) {
        const response = {
            status: 'error',
            env_type: ENV_CONFIG.type,
            error: error instanceof Error ? error.message : String(error)
        };

        return {
            type: 'text',
            text: JSON.stringify(response),
            isError: true
        };
    }
}

/**
 * Save a file to the SAVED_FILES_DIR with the specified filename
 */
async function saveFile(content: string, filename: string) {
    try {
        
        
        // Handle filename - resolve relative paths from SAVED_FILES_DIR
        let actualFilePath: string;
        if (isAbsolute(filename)) {
            // For absolute paths, use as-is
            actualFilePath = filename;
        } else {
            // For relative paths, resolve from SAVED_FILES_DIR
            actualFilePath = join(SAVED_FILES_DIR, filename);
        }
        
        // Check if path is forbidden and provide accurate error message
        const errorReason = getPathForbiddenReason(actualFilePath);
        if (errorReason) {
            return {
                type: 'text',
                text: JSON.stringify({
                    status: 'error',
                    error: errorReason,
                    filename: filename
                }),
                isError: true
            };
        }
        
        // Ensure filename has .py extension if it's a relative path
        if (!isAbsolute(filename) && !actualFilePath.endsWith('.py')) {
            actualFilePath = `${actualFilePath}.py`;
        }
        
        // Write content to file
        await writeFile(actualFilePath, content, 'utf-8');
        
        return {
            type: 'text',
            text: JSON.stringify({
                status: 'success',
                message: 'File saved successfully',
                file_path: actualFilePath,
                filename: filename
            }),
            isError: false
        };
    } catch (error) {
        return {
            type: 'text',
            text: JSON.stringify({
                status: 'error',
                error: error instanceof Error ? error.message : String(error)
            }),
            isError: true
        };
    }
}

/**
 * Execute a shell command and return the result
 */
async function executeShellCommand(command: string, workingDir?: string) {
    try {
        // Security check for working directory
        let resolvedWorkingDir = workingDir;
        if (workingDir) {
            // Handle both absolute and relative paths
            const normalizedWorkingDir = isAbsolute(workingDir) ? workingDir : join(PROJECT_ROOT, workingDir);
            const errorReason = getPathForbiddenReason(normalizedWorkingDir);
            if (errorReason) {
                return {
                    type: 'text',
                    text: JSON.stringify({
                        status: 'error',
                        error: errorReason
                    }),
                    isError: true
                };
            }
            resolvedWorkingDir = normalizedWorkingDir;
        }
        
        // Enhanced security checks for shell commands using comprehensive forbidden path detection
        
        // Note: Working directory check is already done above (lines 661-676)
        
        // 1. Extract and check potential file paths from the command
        const potentialPaths = extractPathsFromCommand(command);
        for (const path of potentialPaths) {
            const errorReason = getPathForbiddenReason(path);
            if (errorReason) {
                return {
                    type: 'text',
                    text: JSON.stringify({
                        status: 'error',
                        error: errorReason
                    }),
                    isError: true
                };
            }
        }
        
        // 2. Check for dangerous commands that could access forbidden paths
        const forbiddenDirName = basename(FORBIDDEN_PATH);
        const dangerousPatterns = [
            new RegExp(`find\\s+.*${forbiddenDirName}`, 'i'),
            new RegExp(`grep\\s+.*${forbiddenDirName}`, 'i'),
            new RegExp(`cat\\s+.*${forbiddenDirName}`, 'i'),
            new RegExp(`cp\\s+.*${forbiddenDirName}`, 'i'),
            new RegExp(`mv\\s+.*${forbiddenDirName}`, 'i'),
            new RegExp(`rm\\s+.*${forbiddenDirName}`, 'i'),
            new RegExp(`ls\\s+.*${forbiddenDirName}`, 'i'),
            new RegExp(`tar\\s+.*${forbiddenDirName}`, 'i'),
            new RegExp(`zip\\s+.*${forbiddenDirName}`, 'i'),
            new RegExp(`unzip\\s+.*${forbiddenDirName}`, 'i'),
        ];
        
        for (const pattern of dangerousPatterns) {
            if (pattern.test(command)) {
                return {
                    type: 'text',
                    text: JSON.stringify({
                        status: 'error',
                        error: `Command contains explicit reference to forbidden directory: ${command}`
                    }),
                    isError: true
                };
            }
        }
        
        // 3. Check for glob patterns that could access forbidden content
        if (command.includes('*')) {
            // Check if the command uses dangerous relative paths that could access forbidden content
            // Only block "find ." or "find ./" (without specific subdirectory)
            if (command.match(/find\s+\.\s/) || command.match(/find\s+\.$/) || 
                command.match(/find\s+\.\/\s/) || command.match(/find\s+\.\/$/)) {
                // Commands like "find ." or "find ./" could search in forbidden directories
                return {
                    type: 'text',
                    text: JSON.stringify({
                        status: 'error',
                        error: `Glob pattern with relative path could access forbidden content. Please specify a specific directory: ${command}`
                    }),
                    isError: true
                };
            }
            
            // Also check for unrestricted glob patterns without any path restrictions
            // But allow commands that specify a specific directory (like "find research_agent -name '*.py'")
            if (!command.includes('/') && !command.includes('\\') && !command.match(/find\s+\w+/)) {
                return {
                    type: 'text',
                    text: JSON.stringify({
                        status: 'error',
                        error: `Unrestricted glob pattern could access forbidden content. Please specify a directory: ${command}`
                    }),
                    isError: true
                };
            }
        }
        
        // 4. Forbid dangerous commands
        const dangerousCommands = [
            'rm -rf', 'sudo', 'su', 'chmod 777', 'chown root',
            'dd if=', 'mkfs', 'fdisk', 'mount', 'umount',
            'systemctl', 'service', 'init', 'telinit',
            'curl', 'wget', 'nc', 'netcat', 'ssh', 'scp', 'rsync'
        ];
        
        for (const dangerousCmd of dangerousCommands) {
            if (command.includes(dangerousCmd)) {
                return {
                    type: 'text',
                    text: JSON.stringify({
                        status: 'error',
                        error: `Dangerous commands are forbidden: ${dangerousCmd}`
                    }),
                    isError: true
                };
            }
        }
        
        
        // Execute command with output-based security monitoring
        const { stdout, stderr } = await execAsync(command, {
            cwd: resolvedWorkingDir || PROJECT_ROOT,
            env: { ...process.env },
            timeout: 300000 // 5 minutes timeout
        });
        
        // Check if output contains forbidden directory content
        const forbiddenPath = FORBIDDEN_PATH;
        
        // More comprehensive check for forbidden directory content
        const forbiddenPatterns = [
            `"${forbiddenDirName}"`,           // "benchmark"
            `/${forbiddenDirName}/`,           // /benchmark/
            `${forbiddenDirName}/`,            // benchmark/
            forbiddenPath,                     // Full absolute path
            relative(PROJECT_ROOT, forbiddenPath), // Relative path from project root
        ];
        
        const outputToCheck = stdout + stderr;
        for (const pattern of forbiddenPatterns) {
            if (pattern && outputToCheck.includes(pattern)) {
                return {
                    type: 'text',
                    text: JSON.stringify({
                        status: 'error',
                        error: `Command output contains content from forbidden directory: ${pattern}`
                    }),
                };
            }
        }

        const response = {
            status: stderr ? 'warning' : 'success',
            stdout: stdout,
            stderr: stderr
        };

        return {
            type: 'text',
            text: JSON.stringify(response),
            isError: false
        };
    } catch (error) {
        const response = {
            status: 'error',
            error: 'Command execution failed'
        };

        return {
            type: 'text',
            text: JSON.stringify(response),
            isError: true
        };
    }
}

/**
 * Create and execute a shell script
 */
async function createAndExecuteScript(scriptContent: string, filename?: string, interpreter?: string) {
    try {
        // Generate filename if not provided
        if (!filename) {
            filename = `script_${randomBytes(4).toString('hex')}.sh`;
        }
        
        // Handle filename - resolve relative paths from CODE_STORAGE_DIR
        let filePath: string;
        if (isAbsolute(filename)) {
            // For absolute paths, use as-is
            filePath = filename;
        } else {
            // For relative paths, resolve from CODE_STORAGE_DIR
            filePath = join(CODE_STORAGE_DIR, filename);
        }
        
        // Check if path is forbidden and provide accurate error message
        const errorReason = getPathForbiddenReason(filePath);
        if (errorReason) {
            return {
                type: 'text',
                text: JSON.stringify({
                    status: 'error',
                    error: errorReason,
                    filename: filename
                }),
                isError: true
            };
        }

        // Add shebang if not present and interpreter is specified
        let finalContent = scriptContent;
        if (interpreter && !scriptContent.startsWith('#!')) {
            finalContent = `#!/usr/bin/env ${interpreter}\n\n${scriptContent}`;
        } else if (!scriptContent.startsWith('#!')) {
            // Default to bash if no shebang
            finalContent = `#!/usr/bin/env bash\n\n${scriptContent}`;
        }
        
        // Write script to file
        await writeFile(filePath, finalContent, 'utf-8');
        
        // Make script executable (Unix-like systems)
        if (platform() !== 'win32') {
            await execAsync(`chmod +x "${filePath}"`);
        }

        // Execute the script
        const { stdout, stderr } = await execAsync(`"${filePath}"`, {
            cwd: CODE_STORAGE_DIR,
            env: { ...process.env },
            timeout: 300000 // 5 minutes timeout
        });

        const response = {
            status: stderr ? 'warning' : 'success',
            stdout: stdout,
            stderr: stderr,
            script_path: filePath,
            script_content: finalContent
        };

        return {
            type: 'text',
            text: JSON.stringify(response),
            isError: false
        };
    } catch (error) {
        const response = {
            status: 'error',
            error: error instanceof Error ? error.message : String(error),
            script_path: filename ? join(CODE_STORAGE_DIR, filename) : 'unknown',
            script_content: scriptContent
        };

        return {
            type: 'text',
            text: JSON.stringify(response),
            isError: true
        };
    }
}

/**
 * Create an MCP server to handle code execution and dependency management
 */
const server = new Server(
    {
        name: "workspace-server",
        version: "0.1.0",
    },
    {
        capabilities: {
            tools: {},
        },
    }
);

/**
 * Handler for listing available tools.
 */
server.setRequestHandler(ListToolsRequestSchema, async () => {
    return {
        tools: [
            {
                name: "execute_code",
                description: `Execute Python code in the ${ENV_CONFIG.type} environment. Code is saved to ${CODE_STORAGE_DIR} and executed. Use this tool to run Python scripts and get their output.`,
                inputSchema: {
                    type: "object",
                    properties: {
                        code: {
                            type: "string",
                            description: `Python code to execute`
                        },
                        filename: {
                            type: "string",
                            description: `Optional: Name of the file to save the code (default: generated UUID)`
                        }
                    },
                    required: ["code"]
                }
            },
            {
                name: "read_file",
                description: `Read the content of any text file (Python code, log files, output files, etc.). Use this to examine local package code files, output files from external programs, log files, or any text-based files to extract specific information. PATH HANDLING: Prefer absolute paths. If using relative paths, they are resolved from ${PROJECT_ROOT}`,
                inputSchema: {
                    type: "object",
                    properties: {
                        file_path: {
                            type: "string",
                            description: `Path to the file to read (supports any text file format: .py, .log, .txt, .out, .xyz, etc.). Using absolute paths (preferred) or relative paths from ${PROJECT_ROOT}`
                        }
                    },
                    required: ["file_path"]
                }
            },
            {
                name: "install_dependencies",
                description: `Install missing Python dependencies in the ${ENV_CONFIG.type} environment. Use this tool to install packages that are required for your code to run. Example: {"packages": ["package1", "package2", "package3"]}`,
                inputSchema: {
                    type: "object",
                    properties: {
                        packages: {
                            type: "array",
                            items: {
                                type: "string"
                            },
                            description: `Array of package names to install. Each package should be a string. Example: ["package1", "package2", "package3"]`
                        }
                    },
                    required: ["packages"]
                }
            },
            {
                name: "check_installed_packages",
                description: `List all installed packages in the current Python environment. Use this tool to check what packages are already available before attempting to install new ones.`,
                inputSchema: {
                    type: "object",
                    properties: {}
                }
            },
            {
                name: "check_package_version",
                description: `Check if specific packages are installed and get their version, package path, and module location information. Use this tool to verify specific package installations. Example: {"packages": ["package1", "package2", "package3"]}`,
                inputSchema: {
                    type: "object",
                    properties: {
                        packages: {
                            type: "array",
                            items: {
                                type: "string"
                            },
                            description: `Array of package names to check. Each package should be a string. Example: ["package1", "package2", "package3"]`
                        }
                    },
                    required: ["packages"]
                }
            },
            {
                name: "save_file",
                description: `Save a file to ${SAVED_FILES_DIR} with the specified filename`,
                inputSchema: {
                    type: "object",
                    properties: {
                        content: {
                            type: "string",
                            description: `Content of the file`
                        },
                        filename: {
                            type: "string",
                            description: `Filename of the file`
                        }
                    },
                    required: ["content", "filename"]
                }
            },
            {
                name: "execute_shell_command",
                description: `Execute a shell command and return the result. Default working directory is ${PROJECT_ROOT}. PATH HANDLING: Prefer absolute paths for working_dir. If using relative paths for working_dir, they are resolved from ${PROJECT_ROOT}`,
                inputSchema: {
                    type: "object",
                    properties: {
                        command: {
                            type: "string",
                            description: `Shell command to execute`
                        },
                        working_dir: {
                            type: "string",
                            description: `Working directory for the command (absolute path or relative path from ${PROJECT_ROOT}). Default is ${PROJECT_ROOT}`
                        }
                    },
                    required: ["command"]
                }
            },
            {
                name: "create_and_execute_script",
                description: `Create and execute a shell script. Scripts are created in ${CODE_STORAGE_DIR}`,
                inputSchema: {
                    type: "object",
                    properties: {
                        script_content: {
                            type: "string",
                            description: `Content of the script`
                        },
                        filename: {
                            type: "string",
                            description: `Optional: Name of the script file`
                        },
                        interpreter: {
                            type: "string",
                            description: `Optional: Interpreter for the script`
                        }
                    },
                    required: ["script_content"]
                }
            }
        ]
    };
});

interface ExecuteCodeArgs {
    code?: string;
    filename?: string;
}

interface ReadCodeFileArgs {
    file_path?: string;
}

interface InstallDependenciesArgs {
    packages?: string[];
}

interface CheckInstalledPackagesArgs {
    // No parameters needed - returns all installed packages
}

interface SaveFileArgs {
    content?: string;
    filename?: string;
}

interface ExecuteShellCommandArgs {
    command?: string;
    working_dir?: string;
}

interface CreateAndExecuteScriptArgs {
    script_content?: string;
    filename?: string;
    interpreter?: string;
}

interface CheckPackageVersionArgs {
    packages?: string[];
}

/**
 * Handler for tool execution.
 */
server.setRequestHandler(CallToolRequestSchema, async (request) => {
    switch (request.params.name) {
        case "execute_code": {
            const args = request.params.arguments as ExecuteCodeArgs;
            if (!args?.code) {
                return {
                    content: [{
                        type: "text",
                        text: JSON.stringify({
                            "status": "error",
                            "error": "Code is required",
                            "suggestion": "Please provide Python code to execute"
                        }),
                        isError: true
                    }]
                };
            }

            try {
                
                const filename = args.filename ? `${args.filename.replace(/\.py$/, '')}_${randomBytes(4).toString('hex')}.py` : `code_${randomBytes(4).toString('hex')}.py`;
                const result = await executeCode(args.code, filename);

                return {
                    content: [{
                        type: "text",
                        text: result.text,
                        isError: result.isError
                    }]
                };
            } catch (error) {
                return {
                    content: [{
                        type: "text",
                        text: JSON.stringify({
                            "status": "error",
                            "error": error instanceof Error ? error.message : String(error),
                            "code_length": args.code.length,
                            "suggestion": "Check if the Python code is valid and try again"
                        }),
                        isError: true
                    }]
                };
            }
        }
        
        case "read_file": {
            const args = request.params.arguments as ReadCodeFileArgs;
            if (!args?.file_path) {
                return {
                    content: [{
                        type: "text",
                        text: JSON.stringify({
                            "status": "error",
                            "error": "File path is required",
                            "suggestion": "Please provide a valid file path to read"
                        }),
                        isError: true
                    }]
                };
            }

            try {
                const result = await readCodeFile(args.file_path);
                return {
                    content: [{
                        type: "text",
                        text: result.text,
                        isError: result.isError
                    }]
                };
            } catch (error) {
                return {
                    content: [{
                        type: "text",
                        text: JSON.stringify({
                            "status": "error",
                            "error": error instanceof Error ? error.message : String(error),
                            "file_path": args.file_path,
                            "suggestion": "Check if the file path is correct and accessible"
                        }),
                        isError: true
                    }]
                };
            }
        }
        
        case "install_dependencies": {
            const args = request.params.arguments as InstallDependenciesArgs;
            let packages = args?.packages;
            
            // Handle case where packages is passed as a JSON string instead of array
            if (typeof packages === 'string') {
                const packagesStr = packages; // Store the original string value
                try {
                    packages = JSON.parse(packagesStr);
                    // If JSON parse succeeds but result is still a string, wrap it in array
                    if (typeof packages === 'string') {
                        packages = [packages];
                    }
                } catch (e) {
                    // Not valid JSON, treat as a single package name
                    packages = [packagesStr];
                }
            }
            
            if (!packages || !Array.isArray(packages)) {
                return {
                    content: [{
                        type: "text",
                        text: JSON.stringify({
                            "status": "error",
                            "error": "Valid packages array is required",
                            "suggestion": "Please provide packages as an array, e.g., {\"packages\": [\"package1\", \"package2\"]}"
                        }),
                        isError: true
                    }]
                };
            }
            
            // Filter out empty strings and normalize package names
            packages = packages
                .filter(pkg => pkg && typeof pkg === 'string' && pkg.trim().length > 0)
                .map(pkg => pkg.trim());
            
            if (packages.length === 0) {
                return {
                    content: [{
                        type: "text",
                        text: JSON.stringify({
                            "status": "error",
                            "error": "No valid package names provided",
                            "suggestion": "Please provide at least one valid package name"
                        }),
                        isError: true
                    }]
                };
            }

            try {
                const result = await installDependencies(packages);
                return {
                    content: [{
                        type: "text",
                        text: result.text,
                        isError: result.isError
                    }]
                };
            } catch (error) {
                return {
                    content: [{
                        type: "text",
                        text: JSON.stringify({
                            "status": "error",
                            "error": error instanceof Error ? error.message : String(error),
                            "packages_requested": packages,
                            "suggestion": "Check if the package names are correct and try again"
                        }),
                        isError: true
                    }]
                };
            }
        }
        
        case "check_installed_packages": {
            const result = await checkPackageInstallation([]);

            return {
                content: [{
                    type: "text",
                    text: result.text,
                    isError: result.isError
                }]
            };
        }
        
        case "check_package_version": {
            const args = request.params.arguments as CheckPackageVersionArgs;
            let packages = args?.packages;
            
            // Handle case where packages is passed as a JSON string instead of array
            if (typeof packages === 'string') {
                const packagesStr = packages; // Store the original string value
                try {
                    packages = JSON.parse(packagesStr);
                    // If JSON parse succeeds but result is still a string, wrap it in array
                    if (typeof packages === 'string') {
                        packages = [packages];
                    }
                } catch (e) {
                    // Not valid JSON, treat as a single package name
                    packages = [packagesStr];
                }
            }
            
            if (!packages || !Array.isArray(packages)) {
                return {
                    content: [{
                        type: "text",
                        text: JSON.stringify({
                            "status": "error",
                            "error": "Valid packages array is required",
                            "suggestion": "Please provide packages as an array, e.g., {\"packages\": [\"package1\", \"package2\"]}"
                        }),
                        isError: true
                    }]
                };
            }
            
            // Filter out empty strings and normalize package names
            packages = packages
                .filter(pkg => pkg && typeof pkg === 'string' && pkg.trim().length > 0)
                .map(pkg => pkg.trim());
            
            if (packages.length === 0) {
                return {
                    content: [{
                        type: "text",
                        text: JSON.stringify({
                            "status": "error",
                            "error": "No valid package names provided",
                            "suggestion": "Please provide at least one valid package name"
                        }),
                        isError: true
                    }]
                };
            }

            try {
                // Auto-detect package manager or use environment-specified one
                let packageManager: 'pip' | 'uv' | 'conda';
                
                // First, respect explicit environment configuration
                if (ENV_CONFIG.type === 'conda') {
                    packageManager = 'conda';
                } else if (ENV_CONFIG.type === 'venv-uv') {
                    packageManager = 'uv';
                } else if (ENV_CONFIG.type === 'venv') {
                    // For venv, detect if uv is available and prefer it
                    packageManager = await detectPackageManager();
                } else {
                    // Auto-detect for other cases
                    packageManager = await detectPackageManager();
                }

                const commands = await getPackageManagerCommands(packageManager);
                
                const results = [];
                for (const package_name of packages) {
                    let version = "unknown";
                    let package_path = "unknown";
                    let location = "unknown";
                    let error = null;

                    // Step 1: Try to get version using appropriate package manager show command
                    try {
                        let showCommand = [];
                        if (packageManager === 'conda' && ENV_CONFIG.conda_name) {
                            showCommand = ['conda', 'list', '-n', ENV_CONFIG.conda_name, package_name];
                        } else {
                            showCommand = commands.show(package_name);
                        }
                        
                        const showCmdStr = showCommand.join(' ');
                        const { command: showCmd, options: showOptions } = getPlatformSpecificCommand(showCmdStr);
                        const { stdout: showOut, stderr: showErr } = await execAsync(showCmd, {
                            cwd: CODE_STORAGE_DIR,
                            env: { ...process.env, PYTHONUNBUFFERED: '1' },
                            ...showOptions
                        });
                        
                        const lines = showOut.split("\n");
                        for (const line of lines) {
                            if (line.startsWith("Version:")) {
                                version = line.split(":")[1].trim();
                            }
                            if (line.startsWith("Location:")) {
                                const location = line.split(":")[1].trim();
                                // Try different possible package paths
                                const possiblePaths = [
                                    `${location}/${package_name}`,
                                    `${location}/${package_name.replace(/-/g, '_')}`,
                                    `${location}/${package_name.replace(/-/g, '/')}`,
                                ];
                                
                                // For packages ending with -py, try removing the suffix
                                if (package_name.endsWith('-py')) {
                                    possiblePaths.push(`${location}/${package_name.slice(0, -3)}`);
                                }
                                
                                // For packages with multiple hyphens, try first part only
                                const hyphenCount = (package_name.match(/-/g) || []).length;
                                if (package_name.includes('-') && hyphenCount > 1) {
                                    const firstPart = package_name.split('-')[0];
                                    possiblePaths.push(`${location}/${firstPart}`);
                                }
                                
                                // Find the first existing path
                                let found_package_path = "unknown";
                                for (const path of possiblePaths) {
                                    try {
                                        const fs = require('fs');
                                        if (fs.existsSync(path)) {
                                            found_package_path = path;
                                            break;
                                        }
                                    } catch (e) {
                                        // Continue to next path
                                    }
                                }
                                
                                // Set package_path to the found path (or fallback to original logic)
                                if (found_package_path !== "unknown") {
                                    package_path = found_package_path;
                                } else {
                                    package_path = `${location}/${package_name}`;
                                }
                            }
                        }
                    } catch (e) {
                        error = `${packageManager} show failed: ${e}`;
                    }

                                        // Step 2: Try multiple import strategies to find the correct module
                    try {
                        // Generate all possible variations of the package name
                        const variations = new Set<string>();
                        
                        // Original name
                        variations.add(package_name);
                        
                        // Replace hyphens with underscores
                        if (package_name.includes('-')) {
                            variations.add(package_name.replace(/-/g, '_'));
                        }
                        
                        // Replace hyphens with dots
                        if (package_name.includes('-')) {
                            variations.add(package_name.replace(/-/g, '.'));
                        }
                        
                        // Replace underscores with hyphens
                        if (package_name.includes('_')) {
                            variations.add(package_name.replace(/_/g, '-'));
                        }
                        
                        // Replace dots with hyphens
                        if (package_name.includes('.')) {
                            variations.add(package_name.replace(/\./g, '-'));
                        }
                        
                        // Replace dots with underscores
                        if (package_name.includes('.')) {
                            variations.add(package_name.replace(/\./g, '_'));
                        }
                        
                        // Try each variation until one succeeds
                        let success = false;
                        for (const variation of variations) {
                            try {
                                const pyCmd = `python -c "import ${variation}; print(${variation}.__file__); print(getattr(${variation}, '__version__', 'no __version__'))"`;
                                const { command: pyCommand, options: pyOptions } = getPlatformSpecificCommand(pyCmd);
                                const { stdout: pyOut, stderr: pyErr } = await execAsync(pyCommand, {
                                    cwd: CODE_STORAGE_DIR,
                                    env: { ...process.env, PYTHONUNBUFFERED: '1' },
                                    ...pyOptions
                                });
                                
                                if (pyOut.trim()) {
                                    const lines = pyOut.trim().split("\n");
                                    // Check if we got a valid file path (not None)
                                    if (lines.length >= 1 && lines[0] !== 'None') {
                                        location = lines[0];
                                        if (package_path === "unknown" && location) {
                                            package_path = location.substring(0, location.lastIndexOf("/"));
                                        }
                                    } else if (lines.length >= 1 && lines[0] === 'None') {
                                        // Handle namespace packages where __file__ is None
                                        // Try to get the path from __path__
                                        try {
                                            const pathCmd = `python -c "import ${variation}; print(str(${variation}.__path__))"`;
                                            const { command: pathCommand, options: pathOptions } = getPlatformSpecificCommand(pathCmd);
                                            const { stdout: pathOut, stderr: pathErr } = await execAsync(pathCommand, {
                                                cwd: CODE_STORAGE_DIR,
                                                env: { ...process.env, PYTHONUNBUFFERED: '1' },
                                                ...pathOptions
                                            });
                                            
                                            if (pathOut.trim() && pathOut.trim() !== 'None') {
                                                // Extract path from _NamespacePath format
                                                const pathMatch = pathOut.trim().match(/_NamespacePath\(\[['"]([^'"]+)['"]\]\)/);
                                                if (pathMatch) {
                                                    location = pathMatch[1];
                                                    if (package_path === "unknown" && location) {
                                                        package_path = location.substring(0, location.lastIndexOf("/"));
                                                    }
                                                }
                                            }
                                        } catch (e) {
                                            // Ignore path extraction errors
                                        }
                                    }
                                    if (lines.length >= 2 && lines[1] !== "no __version__") {
                                        version = lines[1];
                                    }
                                    success = true;
                                    break; // Found a working variation
                                }
                            } catch (e) {
                                // Continue to next variation
                                continue;
                            }
                        }
                        
                        // Final fallback: try importlib with original name
                        if (!success) {
                            const pyCmd = `python -c "import importlib; pkg = importlib.import_module('${package_name}'); print(pkg.__file__); print(getattr(pkg, '__version__', 'no __version__'))"`;
                            const { command: pyCommand, options: pyOptions } = getPlatformSpecificCommand(pyCmd);
                            const { stdout: pyOut, stderr: pyErr } = await execAsync(pyCommand, {
                                cwd: CODE_STORAGE_DIR,
                                env: { ...process.env, PYTHONUNBUFFERED: '1' },
                                ...pyOptions
                            });
                            
                            if (pyOut.trim()) {
                                const lines = pyOut.trim().split("\n");
                                // Check if we got a valid file path (not None)
                                if (lines.length >= 1 && lines[0] !== 'None') {
                                    location = lines[0];
                                    if (package_path === "unknown" && location) {
                                        package_path = location.substring(0, location.lastIndexOf("/"));
                                    }
                                } else if (lines.length >= 1 && lines[0] === 'None') {
                                    // Handle namespace packages where __file__ is None
                                    // Try to get the path from __path__
                                    try {
                                        const pathCmd = `python -c "import importlib; pkg = importlib.import_module('${package_name}'); print(str(pkg.__path__))"`;
                                        const { command: pathCommand, options: pathOptions } = getPlatformSpecificCommand(pathCmd);
                                        const { stdout: pathOut, stderr: pathErr } = await execAsync(pathCommand, {
                                            cwd: CODE_STORAGE_DIR,
                                            env: { ...process.env, PYTHONUNBUFFERED: '1' },
                                            ...pathOptions
                                        });
                                        
                                        if (pathOut.trim() && pathOut.trim() !== 'None') {
                                            // Extract path from _NamespacePath format
                                            const pathMatch = pathOut.trim().match(/_NamespacePath\(\[['"]([^'"]+)['"]\]\)/);
                                            if (pathMatch) {
                                                location = pathMatch[1];
                                                if (package_path === "unknown" && location) {
                                                    package_path = location.substring(0, location.lastIndexOf("/"));
                                                }
                                            }
                                        }
                                    } catch (e) {
                                        // Ignore path extraction errors
                                    }
                                }
                                if (lines.length >= 2 && lines[1] !== "no __version__") {
                                    version = lines[1];
                                }
                                success = true;
                            }
                        }
                        
                    } catch (e) {
                        if (!error) error = `python import failed: ${e}`;
                    }

                    // Final fix: Use location from import if it's more accurate than package_path
                    if (location && location.endsWith('__init__.py')) {
                        const dir_from_location = location.substring(0, location.lastIndexOf('/__init__.py'));
                        if (dir_from_location) {
                            package_path = dir_from_location;
                        }
                    }
                    
                    results.push({
                        package_name,
                        version,
                        package_path,
                        location,
                        error,
                        summary: `Package ${package_name} version ${version} at ${package_path}`
                    });
                }

                return {
                    content: [{
                        type: "text",
                        text: JSON.stringify({
                            status: 'success',
                            env_type: ENV_CONFIG.type,
                            package_manager: packageManager,
                            venv_path: ENV_CONFIG.venv_path,
                            package_details: results
                        }),
                        isError: false
                    }]
                };
            } catch (error) {
                return {
                    content: [{
                        type: "text",
                        text: JSON.stringify({
                            status: 'error',
                            error: error instanceof Error ? error.message : String(error),
                            env_type: ENV_CONFIG.type,
                            venv_path: ENV_CONFIG.venv_path
                        }),
                        isError: true
                    }]
                };
            }
        }
        
        case "save_file": {
            const args = request.params.arguments as SaveFileArgs;
            if (!args?.content) {
                return {
                    content: [{
                        type: "text",
                        text: JSON.stringify({
                            "status": "error",
                            "error": "Content is required",
                            "suggestion": "Please provide file content to save"
                        }),
                        isError: true
                    }]
                };
            }
            if (!args?.filename) {
                return {
                    content: [{
                        type: "text",
                        text: JSON.stringify({
                            "status": "error",
                            "error": "Filename is required",
                            "suggestion": "Please provide a filename for the file"
                        }),
                        isError: true
                    }]
                };
            }

            try {
                const result = await saveFile(args.content, args.filename);
                return {
                    content: [result]
                };
            } catch (error) {
                return {
                    content: [{
                        type: "text",
                        text: JSON.stringify({
                            "status": "error",
                            "error": error instanceof Error ? error.message : String(error),
                            "filename": args.filename,
                            "content_length": args.content.length,
                            "suggestion": "Check if the filename is valid and the content is accessible"
                        }),
                        isError: true
                    }]
                };
            }
        }
        
        case "execute_shell_command": {
            const args = request.params.arguments as ExecuteShellCommandArgs;
            if (!args?.command) {
                return {
                    content: [{
                        type: "text",
                        text: JSON.stringify({
                            "status": "error",
                            "error": "Command is required",
                            "suggestion": "Please provide a shell command to execute"
                        }),
                        isError: true
                    }]
                };
            }

            try {
                const result = await executeShellCommand(args.command, args.working_dir);
                return {
                    content: [{
                        type: "text",
                        text: result.text,
                        isError: result.isError
                    }]
                };
            } catch (error) {
                return {
                    content: [{
                        type: "text",
                        text: JSON.stringify({
                            "status": "error",
                            "error": error instanceof Error ? error.message : String(error),
                            "command": args.command,
                            "working_dir": args.working_dir || CODE_STORAGE_DIR,
                            "suggestion": "Check if the command is valid and try again"
                        }),
                        isError: true
                    }]
                };
            }
        }
        
        case "create_and_execute_script": {
            const args = request.params.arguments as CreateAndExecuteScriptArgs;
            if (!args?.script_content) {
                return {
                    content: [{
                        type: "text",
                        text: JSON.stringify({
                            "status": "error",
                            "error": "Script content is required",
                            "suggestion": "Please provide script content to create and execute"
                        }),
                        isError: true
                    }]
                };
            }

            try {
                const result = await createAndExecuteScript(args.script_content, args.filename, args.interpreter);
                return {
                    content: [{
                        type: "text",
                        text: result.text,
                        isError: result.isError
                    }]
                };
            } catch (error) {
                return {
                    content: [{
                        type: "text",
                        text: JSON.stringify({
                            "status": "error",
                            "error": error instanceof Error ? error.message : String(error),
                            "script_length": args.script_content.length,
                            "filename": args.filename || "auto-generated",
                            "interpreter": args.interpreter || "auto-detected",
                            "suggestion": "Check if the script content is valid and try again"
                        }),
                        isError: true
                    }]
                };
            }
        }
        
        default:
            return {
                content: [{
                    type: "text",
                    text: JSON.stringify({
                        "status": "error",
                        "error": `Unknown tool: ${request.params.name}`,
                        "available_tools": [
                            "execute_code",
                            "read_file", 
                            "install_dependencies",
                            "check_installed_packages",
                            "check_package_version",
                            "save_file",
                            "execute_shell_command",
                            "create_and_execute_script"
                        ],
                        "suggestion": "Please use one of the available tools listed above"
                    }),
                    isError: true
                }]
            };
    }
});

/**
 * Start the server using stdio transport.
 */
async function main() {
    // Ensure storage directories exist
    try {
        await mkdir(CODE_STORAGE_DIR, { recursive: true });
        await mkdir(SAVED_FILES_DIR, { recursive: true });
    } catch (error) {
        console.error('Error creating directories:', error);
    }
    
    const transport = new StdioServerTransport();
    await server.connect(transport);
}

// Define the project boundaries and forbidden paths - read from environment variables only
if (!process.env.PROJECT_ROOT) {
    throw new Error('Missing required environment variable: PROJECT_ROOT');
}
if (!process.env.FORBIDDEN_PATH) {
    throw new Error('Missing required environment variable: FORBIDDEN_PATH');
}

const PROJECT_ROOT: string = resolve(process.env.PROJECT_ROOT);
const FORBIDDEN_PATH: string = resolve(process.env.FORBIDDEN_PATH);

// Utility to extract potential file paths from shell commands
function extractPathsFromCommand(command: string): string[] {
    const paths: string[] = [];
    
    // Simple regex to handle quoted strings and basic word splitting
    const tokenRegex = /"[^"]*"|'[^']*'|\S+/g;
    const words = command.match(tokenRegex) || [];
    
    for (let word of words) {
        // Remove quotes if present
        if ((word.startsWith('"') && word.endsWith('"')) || 
            (word.startsWith("'") && word.endsWith("'"))) {
            word = word.slice(1, -1);
        }
        
        // Skip command names and flags
        if (word.startsWith('-') || word.startsWith('--') || 
            ['ls', 'cat', 'find', 'grep', 'head', 'tail', 'wc', 'sort', 'uniq', 'xargs'].includes(word)) {
            continue;
        }
        
        // Check if word looks like a path (contains / or starts with . or ~ or $)
        // But skip shell redirection syntax
        if ((word.includes('/') || word.startsWith('.') || word.startsWith('~') || word.startsWith('$')) &&
            !/^(\d+>|>|>>|&>)/.test(word)) {  // Skip redirection syntax like "2>", ">", ">>", "&>"
            paths.push(word);
        }
    }
    
    // Also check for forbidden directory name specifically
    const forbiddenDirName = basename(FORBIDDEN_PATH);
    if (command.includes(forbiddenDirName)) {
        paths.push(forbiddenDirName);
    }
    
    // Note: Glob pattern checking is handled separately in the main security checks
    
    return paths;
}

// Utility to check if a path is forbidden (inside forbidden directory or outside project scope)
function isPathForbidden(targetPath: string): boolean {
    const absTarget = resolve(targetPath);
    
    // Check if path is inside the forbidden directory
    const forbiddenRel = relative(FORBIDDEN_PATH, absTarget);
    if (forbiddenRel === '' || !forbiddenRel.startsWith('..')) {
        return true; // Inside forbidden directory
    }
    
    // Check if path is outside the project scope
    const projectRel = relative(PROJECT_ROOT, absTarget);
    if (projectRel.startsWith('..')) {
        return true; // Outside project scope
    }
    
    return false; // Path is allowed
}

function getPathForbiddenReason(targetPath: string): string | null {
    // Expand environment variables and home directory before path resolution
    let expandedPath = targetPath;
    if (targetPath.startsWith('$')) {
        // Handle $VAR and ${VAR} syntax
        const envVar = targetPath.startsWith('${') ? 
            targetPath.slice(2, -1) : 
            targetPath.slice(1);
        const envValue = process.env[envVar];
        if (envValue) {
            expandedPath = envValue;
        }
    } else if (targetPath.startsWith('~')) {
        // Handle ~ and ~user syntax
        expandedPath = targetPath.replace(/^~/, process.env.HOME || '');
    }
    
    const absTarget = resolve(expandedPath);
    const absForbiddenPath = resolve(FORBIDDEN_PATH);
    
    // Check if path is inside the forbidden directory FIRST
    try {
        const forbiddenRel = relative(absForbiddenPath, absTarget);
        if (forbiddenRel === '' || !forbiddenRel.startsWith('..')) {
            return 'Cannot access forbidden directory. Please check your path.';
        }
    } catch (e) {
        // If relative() fails, the paths are on different drives (Windows) or other issues
        // Continue to other checks
    }
    
    // Check if path is outside the project scope
    try {
        const projectRel = relative(PROJECT_ROOT, absTarget);
        if (projectRel.startsWith('..')) {
            return 'Cannot access files outside project root. Please check your path.';
        }
    } catch (e) {
        // If relative() fails, the paths are on different drives (Windows) or other issues
        return 'Cannot access files outside project root. Please check your path.';
    }
    
    return null; // Path is allowed
}

main().catch((error) => {
    console.error("Server error:", error);
    process.exit(1);
});