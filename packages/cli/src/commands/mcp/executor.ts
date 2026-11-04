import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { getCommand } from '@rediacc/shared/cli-contract';
import type { JobOverlap } from '@rediacc/shared/cli-contract/wire';
import { BackgroundEnvelopeSchema } from '@rediacc/shared/cli-contract/wire';
import { JOB_CLIENT_ENV } from '../../services/jobs/attach.js';
import { hasAttachWindow } from './tool-factory.js';

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
  /** Set when the run outlasted the attach window: the job to follow with `job_status`. */
  job?: { jobId: string; machine: string; follow: string };
  /** The tool that follows the ticket (`job_status`), present with `job`. */
  next?: 'job_status';
  /** The jobs a start overlapped (a warning), or that held the scope of a refused start (a BUSY error). */
  overlaps?: JobOverlap[];
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

/** Whether the command starts a machine job the child attaches to for the window (the contract says which). */
function commandAttaches(argv: string[]): boolean {
  const firstFlag = argv.findIndex((a) => a.startsWith('-'));
  const words = firstFlag === -1 ? argv : argv.slice(0, firstFlag);
  for (let n = Math.min(words.length, 3); n > 0; n--) {
    const cmd = getCommand(words.slice(0, n).join(' '));
    if (cmd) return hasAttachWindow(cmd);
  }
  return false;
}

/** The ticket envelope a child prints when its job outlived the window, found among the lines of its stdout. */
function ticketOf(stdout: string) {
  for (const line of stdout.split('\n')) {
    if (!line.startsWith('{') || !line.includes('"jobId"')) continue;
    try {
      const parsed = BackgroundEnvelopeSchema.safeParse(JSON.parse(line));
      if (parsed.success) return parsed.data;
    } catch {
      // Not a ticket line.
    }
  }
  return undefined;
}

function ticketResult(
  argv: string[],
  ticket: NonNullable<ReturnType<typeof ticketOf>>
): ExecutionResult {
  return {
    success: true,
    command: argv.join(' '),
    data: ticket,
    errors: null,
    warnings: [],
    duration_ms: 0,
    job: { jobId: ticket.jobId, machine: ticket.machine, follow: ticket.follow },
    next: 'job_status',
    ...(ticket.overlaps.length > 0 ? { overlaps: ticket.overlaps } : {}),
  };
}

/** The structured overlaps an error entry carries (a BUSY refusal), lifted to a field of the tool result. */
function overlapsOf(errors: unknown[] | null): { overlaps?: JobOverlap[] } {
  for (const entry of errors ?? []) {
    const overlaps = (entry as { overlaps?: unknown } | null)?.overlaps;
    if (Array.isArray(overlaps) && overlaps.length > 0)
      return { overlaps: overlaps as JobOverlap[] };
  }
  return {};
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
  const windowed = commandAttaches(argv);

  try {
    const { stdout } = await execFileAsync(bin.command, [...bin.prefixArgs, ...args], {
      timeout: timeoutMs,
      maxBuffer: 10 * 1024 * 1024,
      env: {
        ...process.env,
        REDIACC_YES: '1',
        NO_COLOR: '1',
        REDIACC_AGENT: '1',
        // The child attaches to a machine job for the attach window, then hands back the ticket.
        ...(windowed ? { [JOB_CLIENT_ENV]: 'mcp' } : {}),
      },
    });

    const trimmed = stdout.trim();
    const ticket = ticketOf(trimmed);
    if (ticket) return ticketResult(argv, ticket);
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
      ...overlapsOf(envelope.errors),
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
          ...overlapsOf(envelope.errors),
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
