import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);

export interface ExecutorOptions {
  configName?: string;
  defaultTimeoutMs: number;
}

export interface ExecutionResult {
  success: boolean;
  command: string;
  data: unknown;
  errors: unknown[] | null;
  warnings: string[];
  duration_ms: number;
}

interface RdcEnvelope {
  success: boolean;
  command: string;
  data: unknown;
  errors: unknown[] | null;
  warnings: string[];
  metrics: { duration_ms: number };
}

interface ExecError extends Error {
  stdout?: string;
  stderr?: string;
  killed?: boolean;
  code?: string | number;
}

/**
 * Resolve the rdc binary for child process execution.
 * Handles both SEA binary and development (tsx/node) modes.
 */
export function resolveRdcBinary(): { command: string; prefixArgs: string[] } {
  // SEA binary: process.execPath IS the rdc binary
  if (!process.argv[1] || process.execPath === process.argv[1]) {
    return { command: process.execPath, prefixArgs: [] };
  }
  // Development: node/tsx + script path
  return { command: process.execPath, prefixArgs: [process.argv[1]] };
}

/**
 * Execute an rdc command as a child process and parse the JSON envelope response.
 */
export async function executeRdcCommand(
  argv: string[],
  options: ExecutorOptions & { timeoutMs?: number }
): Promise<ExecutionResult> {
  const args: string[] = [];
  if (options.configName) {
    args.push('--config', options.configName);
  }
  args.push(...argv, '--output', 'json', '--yes', '--quiet');

  const timeoutMs = options.timeoutMs ?? options.defaultTimeoutMs;
  const bin = resolveRdcBinary();

  try {
    const { stdout } = await execFileAsync(bin.command, [...bin.prefixArgs, ...args], {
      timeout: timeoutMs,
      maxBuffer: 10 * 1024 * 1024,
      env: {
        ...process.env,
        REDIACC_YES: '1',
        NO_COLOR: '1',
        REDIACC_NO_COLOR: '1',
        REDIACC_AGENT: '1',
      },
    });

    const trimmed = stdout.trim();
    if (!trimmed) {
      return {
        success: true,
        command: argv.join(' '),
        data: null,
        errors: null,
        warnings: [],
        duration_ms: 0,
      };
    }

    const envelope: RdcEnvelope = JSON.parse(trimmed);
    return {
      success: envelope.success,
      command: envelope.command,
      data: envelope.data,
      errors: envelope.errors,
      warnings: envelope.warnings,
      duration_ms: envelope.metrics.duration_ms,
    };
  } catch (error: unknown) {
    const err = error as ExecError;

    // If the command produced JSON on stdout before failing, parse it
    if (err.stdout?.trim()) {
      try {
        const envelope: RdcEnvelope = JSON.parse(err.stdout.trim());
        return {
          success: false,
          command: envelope.command,
          data: envelope.data,
          errors: envelope.errors,
          warnings: envelope.warnings,
          duration_ms: envelope.metrics.duration_ms,
        };
      } catch {
        // JSON parse failed, fall through
      }
    }

    // Timeout
    if (err.killed) {
      return {
        success: false,
        command: argv.join(' '),
        data: null,
        errors: [{ code: 'TIMEOUT', message: `Command timed out after ${timeoutMs}ms` }],
        warnings: [],
        duration_ms: timeoutMs,
      };
    }

    // Generic error
    return {
      success: false,
      command: argv.join(' '),
      data: null,
      errors: [{ code: 'EXECUTION_ERROR', message: err.message }],
      warnings: [],
      duration_ms: 0,
    };
  }
}
