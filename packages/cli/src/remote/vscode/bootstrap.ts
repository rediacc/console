/**
 * Remote Environment Bootstrap for VS Code Server
 * Ported from desktop/src/cli/commands/vscode_main.py ensure_vscode_env_setup()
 *
 * This module creates the necessary environment files on the remote machine
 * to ensure VS Code terminals have access to repository environment variables.
 */

import { spawn } from 'node:child_process';
import { DEFAULTS } from '@rediacc/shared/config';
import { BASHRC_REDIACC_CONTENT } from '../repository/bashFunctions.js';
import { formatBashExports, needsUserSwitch } from './envCompose.js';

/**
 * Marker comment for identifying managed content
 */
const REDIACC_MARKER_START = '# --- REDIACC MANAGED START ---';
const REDIACC_MARKER_END = '# --- REDIACC MANAGED END ---';

/**
 * Options for remote environment setup
 */
interface RemoteEnvSetupOptions {
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
interface RemoteEnvSetupResult {
  success: boolean;
  error?: string;
  envFilePath?: string;
}

/**
 * Builds the JSON configuration handed to setup-script.py as a single argv
 * element.
 *
 * NOT interpolated into the script. The Python used to live in a template
 * literal here, with values pasted into its source; four of six went in
 * unescaped, so a universalUser of `'; import os; os.system('id'); x='` parsed
 * as code and ran on the remote host under `sudo -u`. Passing an opaque JSON
 * argument means a value can no longer become a statement -- the only quoting
 * left is shell-quoting one argument.
 */
function buildSetupConfig(
  envBlock: string,
  universalUser: string,
  serverInstallPath: string
): string {
  return JSON.stringify({
    envBlock,
    bashFunctions: BASHRC_REDIACC_CONTENT,
    universalUser,
    serverInstallPath,
    markerStart: REDIACC_MARKER_START,
    markerEnd: REDIACC_MARKER_END,
  });
}

/**
 * The remote setup program, embedded as text at bundle time (esbuild's `.py`
 * text loader; see packages/cli/bundle.mjs).
 *
 * DYNAMIC, and inside the function that needs it, for a reason that cost a
 * regression to learn: a STATIC `import ... from './setup-script.py'` is
 * resolved by every runtime that loads this module's graph, not just by the
 * bundler. packages/cli/scripts/check-command-planes.ts walks the whole command
 * tree under tsx, which has no .py loader, and died with
 * ERR_UNKNOWN_FILE_EXTENSION -- transitively, so grepping for direct importers
 * of this file found nothing and said it was safe. Deferring the import means
 * only code that actually runs the bootstrap ever asks for it, and esbuild
 * still inlines it into the bundle.
 */
async function loadSetupScript(): Promise<string> {
  const mod = await import('./setup-script.py');
  return mod.default;
}

/** Single-quotes a value for POSIX sh. Applies to VALUES only, never to code. */
function shellSingleQuote(s: string): string {
  return `'${s.replaceAll("'", "'\\''")}'`;
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
    const timeout = options?.timeout ?? DEFAULTS.TIMEOUT.VSCODE_BOOTSTRAP;
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

    // The script is a fixed program; only the config varies.
    const script = shellSingleQuote(await loadSetupScript());
    const config = shellSingleQuote(buildSetupConfig(envBlock, universalUser, serverInstallPath));

    // Build command to execute
    // If we need user switching, wrap in sudo
    const command = needsUserSwitch(sshUser, universalUser)
      ? `sudo -u ${shellSingleQuote(universalUser)} python3 -c ${script} ${config}`
      : `python3 -c ${script} ${config}`;

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
