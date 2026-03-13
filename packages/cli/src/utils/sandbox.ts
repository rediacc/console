/**
 * Sandbox utilities for wrapping remote SSH commands with renet sandbox-exec.
 * Mirrors the Go implementation in pkg/sandbox/sandbox.go.
 */

import { DEFAULTS } from '@rediacc/shared/config';
import {
  SANDBOX_READ_ONLY,
  SANDBOX_EXECUTE,
  SANDBOX_READ_WRITE_SYSTEM,
} from '@rediacc/shared-desktop/vscode';

export interface TermSandboxOptions {
  allowedReadWrite: string[];
  allowedReadOnly: string[];
  allowedExecute: string[];
  dockerSocket?: string;
}

/**
 * Build the `<renet-path> sandbox-exec` prefix for a remote command.
 * Mirrors Go's BuildSSHSandboxPrefix().
 * Returns empty string if no read-write paths are configured.
 */
export function buildSandboxPrefix(opts: TermSandboxOptions, renetBinaryPath: string): string {
  if (opts.allowedReadWrite.length === 0) return '';

  let prefix = `${shellQuote(renetBinaryPath)} sandbox-exec`;
  for (const p of opts.allowedReadWrite) {
    prefix += ` --allow-rw ${shellQuote(p)}`;
  }
  for (const p of opts.allowedReadOnly) {
    prefix += ` --allow-ro ${shellQuote(p)}`;
  }
  for (const p of opts.allowedExecute) {
    prefix += ` --allow-exec ${shellQuote(p)}`;
  }
  if (opts.dockerSocket) {
    prefix += ` --docker-socket ${shellQuote(opts.dockerSocket)}`;
  }
  prefix += ' --';
  return prefix;
}

/**
 * Derive sandbox options from SSH connection details.
 * Returns null for machine-only connections (no repo context).
 *
 * Paths mirror buildRemoteSandboxOptions() in executor_ssh.go:411.
 */
export function buildTermSandboxOptions(connectionDetails?: {
  workingDirectory?: string;
  user?: string;
  environment?: Record<string, string>;
}): TermSandboxOptions | null {
  if (!connectionDetails?.workingDirectory) return null;

  const workDir = connectionDetails.workingDirectory;
  const user = connectionDetails.user ?? DEFAULTS.REPOSITORY.UNIVERSAL_USER;
  const homeDir = `/home/${user}`;

  // Docker socket from DOCKER_SOCKET env var
  const dockerSocket = connectionDetails.environment?.DOCKER_SOCKET;

  return {
    allowedReadWrite: [workDir, ...SANDBOX_READ_WRITE_SYSTEM],
    allowedReadOnly: [homeDir, ...SANDBOX_READ_ONLY],
    allowedExecute: [...SANDBOX_EXECUTE],
    dockerSocket,
  };
}

/**
 * Escape a string for safe inclusion inside bash -c '...'.
 * Replaces single quotes with the '\'' idiom.
 */
export function shellEscapeForBashC(cmd: string): string {
  return cmd.replaceAll("'", "'\\''");
}

/**
 * Shell-quote a path for command-line safety.
 * Mirrors Go's shellQuote().
 */
function shellQuote(s: string): string {
  if (/[ '"\\$`]/.test(s)) {
    return `'${s}'`;
  }
  return s;
}
