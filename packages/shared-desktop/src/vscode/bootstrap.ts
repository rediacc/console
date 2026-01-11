/**
 * Remote Environment Bootstrap for VS Code Server
 * Ported from desktop/src/cli/commands/vscode_main.py ensure_vscode_env_setup()
 *
 * This module creates the necessary environment files on the remote machine
 * to ensure VS Code terminals have access to repository environment variables.
 */

import { spawn } from 'node:child_process';
import { formatBashExports, needsUserSwitch } from './envCompose.js';

/**
 * Marker comment for identifying managed content
 */
const REDIACC_MARKER_START = '# --- REDIACC MANAGED START ---';
const REDIACC_MARKER_END = '# --- REDIACC MANAGED END ---';

/**
 * Options for remote environment setup
 */
export interface RemoteEnvSetupOptions {
  /** SSH destination (user@host) */
  sshDestination: string;
  /** SSH options array */
  sshOptions: string[];
  /** Environment variables to set up */
  envVars: Record<string, string>;
  /** Universal user for ownership */
  universalUser: string;
  /** SSH user (current connection user) */
  sshUser: string;
  /** Server install path (e.g., /mnt/rediacc) */
  serverInstallPath: string;
  /** Optional SSH agent socket path */
  agentSocketPath?: string;
  /** Optional callback for logging */
  onLog?: (message: string) => void;
}

/**
 * Result of remote environment setup
 */
export interface RemoteEnvSetupResult {
  success: boolean;
  error?: string;
  envFilePath?: string;
}

/**
 * Generates the Python script for remote environment setup
 * This script is executed on the remote machine via SSH
 *
 * @param envBlock - Environment export statements
 * @param universalUser - User for file ownership
 * @param serverInstallPath - Base path for VS Code server
 * @returns Python script content
 */
function generateSetupScript(
  envBlock: string,
  universalUser: string,
  serverInstallPath: string
): string {
  // Escape the env block for embedding in Python string
  const escapedEnvBlock = envBlock
    .replaceAll('\\', '\\\\')
    .replaceAll("'", "\\'")
    .replaceAll('\n', '\\n');

  return `
import os
import pathlib
import pwd
import grp

# Configuration
ENV_BLOCK = '''${escapedEnvBlock}'''
UNIVERSAL_USER = '${universalUser}'
SERVER_INSTALL_PATH = '${serverInstallPath}'
MARKER_START = '${REDIACC_MARKER_START}'
MARKER_END = '${REDIACC_MARKER_END}'

def get_uid_gid(username):
    """Get UID and GID for a username"""
    try:
        pw = pwd.getpwnam(username)
        return pw.pw_uid, pw.pw_gid
    except KeyError:
        return None, None

def ensure_dir(path, mode=0o755, uid=None, gid=None):
    """Create directory with proper permissions and ownership"""
    path = pathlib.Path(path)
    if not path.exists():
        path.mkdir(parents=True, mode=mode)
    if uid is not None and gid is not None:
        os.chown(path, uid, gid)

def write_file_atomic(path, content, mode=0o644, uid=None, gid=None):
    """Write file atomically with proper permissions"""
    path = pathlib.Path(path)
    temp_path = path.with_suffix('.tmp')
    temp_path.write_text(content)
    os.chmod(temp_path, mode)
    if uid is not None and gid is not None:
        os.chown(temp_path, uid, gid)
    temp_path.rename(path)

def update_managed_content(path, new_content, mode=0o644, uid=None, gid=None):
    """Update managed section in a file, preserving other content"""
    path = pathlib.Path(path)

    existing = ''
    if path.exists():
        existing = path.read_text()

    # Check for existing managed section
    start_idx = existing.find(MARKER_START)
    end_idx = existing.find(MARKER_END)

    managed_block = f"{MARKER_START}\\n{new_content}\\n{MARKER_END}"

    if start_idx != -1 and end_idx != -1:
        # Replace existing managed section
        new_content_full = existing[:start_idx] + managed_block + existing[end_idx + len(MARKER_END):]
    else:
        # Append managed section
        new_content_full = existing.rstrip() + '\\n\\n' + managed_block + '\\n' if existing else managed_block + '\\n'

    write_file_atomic(path, new_content_full, mode, uid, gid)

def main():
    uid, gid = get_uid_gid(UNIVERSAL_USER)

    # Setup directory: ~/.vscode-server or {server_install_path}/.vscode-server
    if SERVER_INSTALL_PATH:
        setup_dir = pathlib.Path(SERVER_INSTALL_PATH) / '.vscode-server'
    else:
        setup_dir = pathlib.Path.home() / '.vscode-server'

    # Create directory structure
    ensure_dir(setup_dir, 0o775, uid, gid)

    # Write environment file
    env_file = setup_dir / 'rediacc-env.sh'
    write_file_atomic(env_file, ENV_BLOCK + '\\n', 0o644, uid, gid)

    # Write server-env-setup file (sourced by VS Code)
    setup_file = setup_dir / 'server-env-setup'
    setup_content = f'source "{env_file}"'
    update_managed_content(setup_file, setup_content, 0o644, uid, gid)

    print(f"Environment setup complete: {env_file}")

if __name__ == '__main__':
    main()
`;
}

/**
 * Executes a command on the remote machine via SSH
 *
 * @param destination - SSH destination
 * @param sshOptions - SSH options array
 * @param command - Command to execute
 * @param options - Additional options
 * @returns Promise resolving to success status and output
 */
async function executeRemoteCommand(
  destination: string,
  sshOptions: string[],
  command: string,
  options?: {
    agentSocketPath?: string;
    timeout?: number;
  }
): Promise<{ success: boolean; stdout: string; stderr: string }> {
  return new Promise((resolve) => {
    const args = [...sshOptions, destination, command];

    // Build environment
    let env = { ...process.env };
    if (options?.agentSocketPath) {
      env = { ...env, SSH_AUTH_SOCK: options.agentSocketPath };
    }

    const ssh = spawn('ssh', args, {
      stdio: 'pipe',
      env,
    });

    let stdout = '';
    let stderr = '';

    ssh.stdout.on('data', (data: Buffer) => {
      stdout += data.toString();
    });

    ssh.stderr.on('data', (data: Buffer) => {
      stderr += data.toString();
    });

    // Set timeout
    const timeout = options?.timeout ?? 30000;
    const timer = setTimeout(() => {
      ssh.kill();
      resolve({
        success: false,
        stdout,
        stderr: `${stderr}\nCommand timed out`,
      });
    }, timeout);

    ssh.on('close', (code) => {
      clearTimeout(timer);
      resolve({
        success: code === 0,
        stdout,
        stderr,
      });
    });

    ssh.on('error', (err) => {
      clearTimeout(timer);
      resolve({
        success: false,
        stdout,
        stderr: err.message,
      });
    });
  });
}

/**
 * Ensures VS Code environment is set up on the remote machine
 * Creates necessary files for environment variable propagation
 *
 * @param options - Setup options
 * @returns Promise resolving to setup result
 */
export async function ensureVSCodeEnvSetup(
  options: RemoteEnvSetupOptions
): Promise<RemoteEnvSetupResult> {
  const {
    sshDestination,
    sshOptions,
    envVars,
    universalUser,
    sshUser,
    serverInstallPath,
    agentSocketPath,
    onLog,
  } = options;

  const log = onLog ?? (() => {});

  try {
    log('Preparing VS Code environment setup...');

    // Generate environment block
    const envBlock = formatBashExports(envVars);

    // Generate the setup script
    const script = generateSetupScript(envBlock, universalUser, serverInstallPath);

    // Build command to execute
    // If we need user switching, wrap in sudo
    let command: string;
    if (needsUserSwitch(sshUser, universalUser)) {
      // Execute as universal user
      const escapedScript = script.replaceAll("'", "'\\''");
      command = `sudo -u ${universalUser} python3 -c '${escapedScript}'`;
    } else {
      // Execute directly
      const escapedScript = script.replaceAll("'", "'\\''");
      command = `python3 -c '${escapedScript}'`;
    }

    log('Executing remote setup script...');

    // Execute the setup command
    const result = await executeRemoteCommand(sshDestination, sshOptions, command, {
      agentSocketPath,
      timeout: 60000, // 1 minute timeout for setup
    });

    if (!result.success) {
      log(`Setup failed: ${result.stderr}`);
      return {
        success: false,
        error: result.stderr || 'Unknown error during setup',
      };
    }

    log('VS Code environment setup complete');

    // Extract env file path from output if available
    const pathMatch = /Environment setup complete: (.+)/.exec(result.stdout);
    const envFilePath = pathMatch ? pathMatch[1].trim() : undefined;

    return {
      success: true,
      envFilePath,
    };
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    log(`Setup error: ${errorMessage}`);
    return {
      success: false,
      error: errorMessage,
    };
  }
}

/**
 * Generates a shell command to verify environment setup
 * Can be used to check if setup was successful
 *
 * @param serverInstallPath - Server install path
 * @returns Shell command string
 */
export function generateVerifyCommand(serverInstallPath: string): string {
  const envFile = serverInstallPath
    ? `${serverInstallPath}/.vscode-server/rediacc-env.sh`
    : '~/.vscode-server/rediacc-env.sh';

  return `test -f "${envFile}" && echo "OK" || echo "MISSING"`;
}
