/**
 * OPS Executor Service
 *
 * Spawns the local renet binary for `rdc ops` commands.
 * Handles platform detection, backend selection, and
 * streaming process output.
 */

import { execSync, spawn } from 'node:child_process';
import { DEFAULTS } from '@rediacc/shared/config';
import { configService } from '../config/config-resources.js';
import { extractRenetToLocal, isSEA } from '../core/embedded-assets.js';

/** Default timeout for ops commands (15 minutes — Ceph provisioning needs ~10 min) */
const OPS_COMMAND_TIMEOUT = 900_000;
// Grace between SIGTERM and SIGKILL when an ops command overruns its timeout.
const OPS_SIGKILL_GRACE = 10_000;

/** Supported VM backends */
export type OpsBackend = 'kvm' | 'qemu' | 'hyperv';

/** Result from a renet ops command execution */
interface OpsCommandResult {
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
    if (
      process.platform !== 'linux' &&
      process.platform !== 'darwin' &&
      process.platform !== 'win32'
    ) {
      throw new Error(
        `rdc ops is not supported on ${process.platform}. Supported platforms: Linux, macOS, Windows.`
      );
    }
  }

  /**
   * Detect the appropriate VM backend for the current platform.
   * macOS uses QEMU with HVF, Windows uses Hyper-V, Linux uses KVM via libvirt.
   */
  detectBackend(): OpsBackend {
    this.assertSupportedPlatform();
    if (process.platform === 'darwin') return 'qemu';
    if (process.platform === 'win32') return 'hyperv';
    return 'kvm';
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

    // Try context-configured renetPath directly (avoids requiring machines/SSH)
    try {
      const context = await configService.getCurrent();
      if (context?.renetPath && context.renetPath !== DEFAULTS.CONTEXT.RENET_BINARY) {
        return context.renetPath;
      }
    } catch {
      // Context may not be set; fall through to PATH lookup
    }

    // Fall back to PATH lookup
    try {
      const whichCmd = process.platform === 'win32' ? 'where.exe renet' : 'which renet';
      return execSync(whichCmd, { encoding: 'utf-8' }).trim().split('\n')[0];
    } catch {
      throw new Error(
        'renet binary not found. Ensure renet is in your PATH or set renetPath in the config file.'
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
      // Grace between SIGTERM and SIGKILL on timeout. Exposed only so the
      // regression test can drive the real kill path in ~1s instead of 10s.
      sigkillGraceMs?: number;
    } = {}
  ): Promise<OpsCommandResult> {
    const renetPath = await this.getRenetPath();
    const backend = options.backend ?? this.detectBackend();
    const timeout = options.timeout ?? OPS_COMMAND_TIMEOUT;
    const sigkillGrace = options.sigkillGraceMs ?? OPS_SIGKILL_GRACE;

    const args = ['ops', subcommand, ...flags];
    const env: Record<string, string> = {
      ...process.env,
      REDIACC_INFRA: backend,
    };

    return new Promise<OpsCommandResult>((resolve, reject) => {
      const child = spawn(renetPath, args, {
        env,
        stdio: options.capture ? ['ignore', 'pipe', 'pipe'] : ['inherit', 'pipe', 'pipe'],
        // detached: renet spawns the VM process (QEMU/KVM) as its own child.
        // A new process group makes `child.pid` the group leader, so a timeout
        // can signal the WHOLE tree (renet + the VM grandchild) via a negative
        // pid — killing renet alone would orphan the grandchild. renet ops runs
        // non-interactively (-o json), so it never needs the controlling TTY
        // this detaches from.
        detached: true,
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

      // Signal the whole process group (renet + its VM grandchild). detached
      // made child.pid the group leader, so a negative pid reaches the tree;
      // fall back to the child alone if the group is already gone or the
      // platform has no process groups (Windows).
      const killGroup = (signal: NodeJS.Signals): void => {
        try {
          if (child.pid) process.kill(-child.pid, signal);
        } catch {
          try {
            child.kill(signal);
          } catch {
            /* already dead */
          }
        }
      };

      let settled = false;
      let timedOut = false;
      let escalateTimer: ReturnType<typeof setTimeout> | undefined;
      let hardCapTimer: ReturnType<typeof setTimeout> | undefined;
      const clearTimers = (): void => {
        clearTimeout(timer);
        if (escalateTimer) clearTimeout(escalateTimer);
        if (hardCapTimer) clearTimeout(hardCapTimer);
      };

      const timer = setTimeout(() => {
        timedOut = true;
        // Round-31's fix rejected here immediately and unref'd the SIGKILL
        // timer, so process.exit() (reached via handleError) fired before the
        // 10s escalation, leaving renet AND the QEMU grandchild alive. Instead:
        // SIGTERM the group now, escalate to SIGKILL after the grace window,
        // and settle only when the child actually `close`s -- so the kill
        // completes BEFORE the CLI exits. A hard cap still guarantees we never
        // hang forever if `close` never arrives (uninterruptible sleep).
        killGroup('SIGTERM');
        escalateTimer = setTimeout(() => killGroup('SIGKILL'), sigkillGrace);
        hardCapTimer = setTimeout(() => {
          if (settled) return;
          settled = true;
          clearTimers();
          child.stdout.destroy();
          child.stderr.destroy();
          child.unref();
          reject(new Error(`renet ops ${subcommand} timed out after ${timeout / 1000}s (forced)`));
        }, sigkillGrace + 5_000);
      }, timeout);

      child.on('close', (code) => {
        if (settled) return;
        settled = true;
        clearTimers();
        if (timedOut) {
          reject(new Error(`renet ops ${subcommand} timed out after ${timeout / 1000}s`));
        } else {
          resolve({ exitCode: code ?? 1, stdout, stderr });
        }
      });

      child.on('error', (err) => {
        if (settled) return;
        settled = true;
        clearTimers();
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
