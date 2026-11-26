import { execFile, spawn } from 'node:child_process';
import { existsSync, mkdirSync, unlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { debugLog } from '../../utils/debug.js';
import { commandExists, getPlatform } from '../utils/platform.js';
import { decodeSSHKey } from '../utils/sshKeyText.js';

/**
 * Default timeout for SSH agent operations in milliseconds (10 seconds)
 * Matches Python CLI behavior
 */
const SSH_AGENT_TIMEOUT_MS = 10000;

/** Named pipe of the Win32-OpenSSH agent service. */
export const WINDOWS_SSH_AGENT_PIPE = '\\\\.\\pipe\\openssh-ssh-agent';

/** Upper bound for the Windows service probe; `sc.exe query` answers in milliseconds. */
const WINDOWS_AGENT_PROBE_TIMEOUT_MS = 3000;

/**
 * SSH agent result containing socket path and agent PID.
 * agentPid is empty when the agent is not ours to stop (the Windows service).
 */
export interface SSHAgentResult {
  socketPath: string;
  agentPid: string;
}

/**
 * Whether the Win32-OpenSSH agent service is RUNNING.
 * The service is Disabled by default, so a stopped or missing service is the normal answer, not an error.
 */
export function isWindowsSSHAgentServiceRunning(
  timeoutMs = WINDOWS_AGENT_PROBE_TIMEOUT_MS
): Promise<boolean> {
  return new Promise((resolve) => {
    execFile(
      'sc.exe',
      ['query', 'ssh-agent'],
      { timeout: timeoutMs, windowsHide: true },
      (err, stdout) => {
        if (err) {
          debugLog(`ssh-agent service probe failed: ${err.message}`);
          resolve(false);
          return;
        }
        resolve(/STATE\s*:\s*\d+\s+RUNNING/i.test(String(stdout)));
      }
    );
  });
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
    // Win32-OpenSSH's agent is a service on a named pipe: `ssh-agent -s` never works there
    // (error 1058 when the service is disabled, a hang otherwise). Use the service or nothing.
    if (!(await isWindowsSSHAgentServiceRunning())) {
      throw new Error('ssh-agent service is not running');
    }
    return { socketPath: WINDOWS_SSH_AGENT_PIPE, agentPid: '' };
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
      const sockMatch = /SSH_AUTH_SOCK=([^;]+)/.exec(stdout);
      const pidMatch = /SSH_AGENT_PID=(\d+)/.exec(stdout);

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

  // ssh-add uses libcrypto's stricter PEM parser, CRLF line endings or a missing trailing newline cause "error in libcrypto" even on keys that `ssh -i` accepts. Normalize before writing.
  const normalizedKey = decodeSSHKey(privateKey);

  try {
    // Write the key to temp file with proper permissions
    writeFileSync(tempKeyPath, normalizedKey, { mode: 0o600 });

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

        if (code === 0) {
          resolve();
        } else {
          reject(new Error(`ssh-add failed with code ${code}: ${stderr}`));
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
  const pid = Number.parseInt(agentPid, 10);
  if (Number.isNaN(pid)) {
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
 * Checks if ssh-agent is available on the system
 *
 * @returns True if ssh-agent is available
 */
export async function isSSHAgentAvailable(): Promise<boolean> {
  if (!(await commandExists('ssh-agent'))) return false;
  if (getPlatform() === 'windows' && !(await isWindowsSSHAgentServiceRunning())) {
    debugLog('ssh-agent service is not running, using file-based keys');
    return false;
  }
  return true;
}
