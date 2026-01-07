import { spawn } from 'child_process';
import { writeFileSync, unlinkSync, existsSync, mkdirSync } from 'fs';
import { tmpdir } from 'os';
import { join } from 'path';
import { getPlatform, commandExists } from '../utils/platform.js';

/**
 * Default timeout for SSH agent operations in milliseconds (10 seconds)
 * Matches Python CLI behavior
 */
const SSH_AGENT_TIMEOUT_MS = 10000;

/**
 * SSH agent result containing socket path and agent PID
 */
export interface SSHAgentResult {
  socketPath: string;
  agentPid: string;
}

/**
 * SSH agent environment variables
 */
export interface SSHAgentEnv {
  SSH_AUTH_SOCK: string;
  SSH_AGENT_PID: string;
}

/**
 * Starts an SSH agent process
 *
 * @param timeoutMs - Timeout in milliseconds (default: 10000)
 * @returns Promise resolving to agent socket path and PID
 * @throws Error if SSH agent cannot be started or times out
 */
export async function startSSHAgent(timeoutMs = SSH_AGENT_TIMEOUT_MS): Promise<SSHAgentResult> {
  const platform = getPlatform();

  if (platform === 'windows') {
    // On Windows, check if ssh-agent is available
    if (!(await commandExists('ssh-agent'))) {
      throw new Error('ssh-agent not found. Ensure OpenSSH is installed.');
    }
  }

  return new Promise((resolve, reject) => {
    let timedOut = false;

    // Set up timeout
    const timeoutId = setTimeout(() => {
      timedOut = true;
      agent.kill();
      reject(
        new Error(
          `ssh-agent startup timed out after ${timeoutMs / 1000}s. ` +
            `This may indicate system resource constraints or a hung ssh-agent process.`
        )
      );
    }, timeoutMs);

    // Start ssh-agent and capture its output
    const agent = spawn('ssh-agent', ['-s'], {
      stdio: ['ignore', 'pipe', 'pipe'],
      env: process.env,
    });

    let stdout = '';
    let stderr = '';

    agent.stdout.on('data', (data: Buffer) => {
      stdout += data.toString();
    });

    agent.stderr.on('data', (data: Buffer) => {
      stderr += data.toString();
    });

    agent.on('close', (code) => {
      clearTimeout(timeoutId);
      if (timedOut) return;

      if (code !== 0) {
        reject(new Error(`ssh-agent exited with code ${code}: ${stderr}`));
        return;
      }

      // Parse SSH_AUTH_SOCK and SSH_AGENT_PID from output
      // Output format: SSH_AUTH_SOCK=/tmp/ssh-xxx/agent.123; export SSH_AUTH_SOCK;
      const sockMatch = stdout.match(/SSH_AUTH_SOCK=([^;]+)/);
      const pidMatch = stdout.match(/SSH_AGENT_PID=(\d+)/);

      if (!sockMatch || !pidMatch) {
        reject(new Error(`Failed to parse ssh-agent output: ${stdout}`));
        return;
      }

      resolve({
        socketPath: sockMatch[1],
        agentPid: pidMatch[1],
      });
    });

    agent.on('error', (err) => {
      clearTimeout(timeoutId);
      if (timedOut) return;
      reject(new Error(`Failed to start ssh-agent: ${err.message}`));
    });
  });
}

/**
 * Adds an SSH private key to the running agent
 *
 * @param privateKey - SSH private key content
 * @param socketPath - Path to the SSH agent socket
 * @param timeoutMs - Timeout in milliseconds (default: 10000)
 * @throws Error if key cannot be added or times out
 */
export async function addKeyToAgent(
  privateKey: string,
  socketPath: string,
  timeoutMs = SSH_AGENT_TIMEOUT_MS
): Promise<void> {
  // Create a temporary file for the key
  const tempDir = join(tmpdir(), 'rediacc-ssh');
  if (!existsSync(tempDir)) {
    mkdirSync(tempDir, { recursive: true, mode: 0o700 });
  }

  const tempKeyPath = join(
    tempDir,
    `key-${Date.now()}-${Math.random().toString(36).substring(2, 8)}`
  );

  try {
    // Write the key to temp file with proper permissions
    writeFileSync(tempKeyPath, privateKey, { mode: 0o600 });

    await new Promise<void>((resolve, reject) => {
      let timedOut = false;

      // Set up timeout
      const timeoutId = setTimeout(() => {
        timedOut = true;
        sshAdd.kill();
        reject(
          new Error(
            `ssh-add timed out after ${timeoutMs / 1000}s. ` +
              `The SSH key may be invalid or require a passphrase.`
          )
        );
      }, timeoutMs);

      // Use ssh-add with the agent socket
      const sshAdd = spawn('ssh-add', [tempKeyPath], {
        stdio: ['ignore', 'pipe', 'pipe'],
        env: {
          ...process.env,
          SSH_AUTH_SOCK: socketPath,
        },
      });

      let stderr = '';
      sshAdd.stderr.on('data', (data: Buffer) => {
        stderr += data.toString();
      });

      sshAdd.on('close', (code) => {
        clearTimeout(timeoutId);
        if (timedOut) return;

        if (code !== 0) {
          reject(new Error(`ssh-add failed with code ${code}: ${stderr}`));
        } else {
          resolve();
        }
      });

      sshAdd.on('error', (err) => {
        clearTimeout(timeoutId);
        if (timedOut) return;
        reject(new Error(`Failed to run ssh-add: ${err.message}`));
      });
    });
  } finally {
    // Always clean up the temp key file
    try {
      unlinkSync(tempKeyPath);
    } catch {
      // Ignore cleanup errors
    }
  }
}

/**
 * Stops an SSH agent process by killing it
 *
 * @param agentPid - PID of the SSH agent process to kill
 * @param gracePeriodMs - Grace period in milliseconds before forceful kill (default: 1000)
 */
export async function stopSSHAgent(agentPid: string, gracePeriodMs = 1000): Promise<void> {
  const pid = parseInt(agentPid, 10);
  if (isNaN(pid)) {
    return;
  }

  try {
    // Try graceful kill first
    process.kill(pid, 'SIGTERM');

    // Wait for grace period
    await new Promise((resolve) => setTimeout(resolve, gracePeriodMs));

    // Check if still running and force kill
    try {
      process.kill(pid, 0); // Check if process exists
      process.kill(pid, 'SIGKILL'); // Force kill
    } catch {
      // Process already dead
    }
  } catch {
    // Process may already be dead
  }
}

/**
 * Gets the environment variables needed for SSH to use the agent
 *
 * @param agentResult - SSH agent result
 * @returns Environment variables object
 */
export function getSSHAgentEnv(agentResult: SSHAgentResult): SSHAgentEnv {
  return {
    SSH_AUTH_SOCK: agentResult.socketPath,
    SSH_AGENT_PID: agentResult.agentPid,
  };
}

/**
 * Checks if ssh-agent is available on the system
 *
 * @returns True if ssh-agent is available
 */
export async function isSSHAgentAvailable(): Promise<boolean> {
  return commandExists('ssh-agent');
}
