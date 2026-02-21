/**
 * OPS Executor Service
 *
 * Spawns the local renet binary for `rdc ops` commands.
 * Handles platform detection, backend selection, and
 * streaming process output.
 */

import { spawn } from 'node:child_process';
import { execSync } from 'node:child_process';
import { DEFAULTS } from '@rediacc/shared/config';
import { contextService } from './context.js';
import { extractRenetToLocal, isSEA } from './embedded-assets.js';

/** Default timeout for ops commands (10 minutes) */
const OPS_COMMAND_TIMEOUT = 600_000;

/** Supported VM backends */
export type OpsBackend = 'kvm' | 'qemu';

/** Result from a renet ops command execution */
export interface OpsCommandResult {
  exitCode: number;
  stdout: string;
  stderr: string;
}

class OpsExecutorService {
  /**
   * Assert that the current platform supports ops commands.
   * Only Linux and macOS are supported.
   */
  assertSupportedPlatform(): void {
    if (process.platform !== 'linux' && process.platform !== 'darwin') {
      throw new Error(
        `rdc ops is not supported on ${process.platform}. Supported platforms: Linux, macOS.`
      );
    }
  }

  /**
   * Detect the appropriate VM backend for the current platform.
   * macOS uses QEMU with HVF acceleration, Linux uses KVM via libvirt.
   */
  detectBackend(): OpsBackend {
    this.assertSupportedPlatform();
    return process.platform === 'darwin' ? 'qemu' : 'kvm';
  }

  /**
   * Get the local renet binary path.
   * In SEA mode: extracts the embedded binary to a temp file.
   * In dev mode: uses the context-configured renetPath or PATH lookup.
   */
  async getRenetPath(): Promise<string> {
    if (isSEA()) {
      return extractRenetToLocal();
    }

    // Try context-configured path
    try {
      const localConfig = await contextService.getLocalConfig();
      if (localConfig.renetPath && localConfig.renetPath !== DEFAULTS.CONTEXT.RENET_BINARY) {
        return localConfig.renetPath;
      }
    } catch {
      // Context may not be set; fall through to PATH lookup
    }

    // Fall back to PATH lookup
    try {
      return execSync('which renet', { encoding: 'utf-8' }).trim();
    } catch {
      throw new Error(
        'renet binary not found. Set a renet path with "rdc context set-renet <path>" ' +
          'or ensure renet is in your PATH.'
      );
    }
  }

  /**
   * Run a renet ops subcommand locally.
   * Spawns `renet ops <subcommand> [flags]` as a child process.
   *
   * @param subcommand - The ops subcommand (e.g., 'up', 'down', 'status')
   * @param flags - Additional flags to pass
   * @param options.capture - If true, capture stdout/stderr instead of streaming
   * @param options.backend - Override auto-detected backend
   * @param options.timeout - Timeout in milliseconds (default: 10 minutes)
   */
  async runOpsCommand(
    subcommand: string,
    flags: string[] = [],
    options: {
      capture?: boolean;
      backend?: OpsBackend;
      timeout?: number;
    } = {}
  ): Promise<OpsCommandResult> {
    const renetPath = await this.getRenetPath();
    const backend = options.backend ?? this.detectBackend();
    const timeout = options.timeout ?? OPS_COMMAND_TIMEOUT;

    const args = ['ops', subcommand, ...flags];
    const env: Record<string, string> = {
      ...process.env,
      REDIACC_INFRA: backend,
    };

    return new Promise<OpsCommandResult>((resolve, reject) => {
      const child = spawn(renetPath, args, {
        env,
        stdio: options.capture ? ['ignore', 'pipe', 'pipe'] : ['inherit', 'pipe', 'pipe'],
      });

      let stdout = '';
      let stderr = '';

      child.stdout.on('data', (data: Buffer) => {
        const text = data.toString();
        stdout += text;
        if (!options.capture) {
          process.stdout.write(data);
        }
      });

      child.stderr.on('data', (data: Buffer) => {
        const text = data.toString();
        stderr += text;
        if (!options.capture) {
          process.stderr.write(data);
        }
      });

      const timer = setTimeout(() => {
        child.kill('SIGTERM');
        reject(new Error(`renet ops ${subcommand} timed out after ${timeout / 1000}s`));
      }, timeout);

      child.on('close', (code) => {
        clearTimeout(timer);
        resolve({ exitCode: code ?? 1, stdout, stderr });
      });

      child.on('error', (err) => {
        clearTimeout(timer);
        reject(new Error(`Failed to spawn renet: ${err.message}`));
      });
    });
  }

  /**
   * Run a renet ops command and capture JSON output.
   * Automatically appends --json flag.
   */
  async runOpsJSON<T>(
    subcommand: string,
    flags: string[] = [],
    options: { backend?: OpsBackend } = {}
  ): Promise<T> {
    const allFlags = [...flags, '--json'];
    const result = await this.runOpsCommand(subcommand, allFlags, {
      capture: true,
      backend: options.backend,
    });

    if (result.exitCode !== 0) {
      const errorMsg = result.stderr.trim() || result.stdout.trim() || 'Unknown error';
      throw new Error(`renet ops ${subcommand} failed (exit ${result.exitCode}): ${errorMsg}`);
    }

    try {
      return JSON.parse(result.stdout) as T;
    } catch {
      throw new Error(
        `Failed to parse JSON output from renet ops ${subcommand}: ${result.stdout.slice(0, 200)}`
      );
    }
  }

  /**
   * Run a renet ops command that streams output (non-capturing).
   * Returns the exit code.
   */
  async runOpsStreaming(
    subcommand: string,
    flags: string[] = [],
    options: { backend?: OpsBackend } = {}
  ): Promise<number> {
    const result = await this.runOpsCommand(subcommand, flags, {
      capture: false,
      backend: options.backend,
    });
    return result.exitCode;
  }
}

export const opsExecutorService = new OpsExecutorService();
