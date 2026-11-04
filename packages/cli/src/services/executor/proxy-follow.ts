/**
 * The pure half of the proxy client: what a command stream folds into, the poll pacing of a followed job
 * (PLAN-detached-jobs Design 5) and the outcomes a followed job ends in. No network, no ticket.
 */

import { type StreamLine } from '@rediacc/shared/cli-contract/wire';
import { EXIT_CODES } from '../../types/index.js';

/** What the executor reported: how it ended, and what the command printed. */
export interface ProxyCommandOutcome {
  success: boolean;
  exitCode: number;
  error?: string;
  /** What the command rendered: its envelope, its table. Printed verbatim. */
  stdout: string;
  /** The job the command ran as, when it ran as one (a ticket may still be open). */
  jobId?: string;
  /** Raw bytes the command wrote instead (`repo cat` of a binary file). Written verbatim. */
  stdoutBytes?: Uint8Array;
  stderr: string;
}

/** The poll pacing (Design 5): 2 s, growing by half each empty poll, capped at 30 s, with +-10 % jitter. */
export const POLL_FIRST_DELAY_MS = 2_000;
const POLL_MAX_DELAY_MS = 30_000;
const POLL_GROWTH = 1.5;
const POLL_JITTER = 0.1;
/** Lines asked of one poll. */
export const POLL_MAX_LINES = 500;
/** How many times a POST dropped before the job line is retried with the same request id. */
export const MAX_START_RETRIES = 3;

export function isTerminalState(state: string): boolean {
  return state === 'succeeded' || state === 'failed' || state === 'cancelled';
}

/** The next empty-poll delay: the current one grown, never past the cap. */
export function nextPollDelayMs(current: number): number {
  return Math.min(Math.round(current * POLL_GROWTH), POLL_MAX_DELAY_MS);
}

/** A delay with symmetric jitter, so many clients do not poll in step. */
export function jittered(ms: number, random: () => number): number {
  return Math.round(ms * (1 + (random() * 2 - 1) * POLL_JITTER));
}

/** Build the outcome from a result line. */
function toOutcome(line: Extract<StreamLine, { kind: 'result' }>): ProxyCommandOutcome {
  return {
    success: line.result.success,
    exitCode: line.result.exitCode,
    error: line.result.error,
    stdout: line.stdout ?? '',
    ...(line.result.jobId ? { jobId: line.result.jobId } : {}),
    ...(line.stdoutBase64 === undefined
      ? {}
      : { stdoutBytes: new Uint8Array(Buffer.from(line.stdoutBase64, 'base64')) }),
    stderr: line.stderr ?? '',
  };
}

/** What a stream read so far, carried across a re-attach so a resume dedupes correctly. */
export interface StreamState {
  eventsSeen: number;
  /** The detached job the executor handed the work to, once it announced one. */
  jobId?: string;
  /** The machine the job runs on, from the job line. */
  machine?: string;
  /** The highest spool-line ordinal delivered, so a resume skips what it already has. */
  highestLine: number;
  /** The result line said `running`: the request ended with the ticket and polls finish it. */
  running?: boolean;
  /** The terminal result, once it lands. */
  outcome?: ProxyCommandOutcome;
}

/** A job line records where to poll and the offset to resume from. */
export function foldJobLine(line: Extract<StreamLine, { kind: 'job' }>, state: StreamState): void {
  state.jobId = line.jobId;
  state.machine = line.machine;
  state.highestLine = Math.max(state.highestLine, line.sinceLine);
}

/** A result line ends the stream; `running` says the job outlived the attach window. */
export function foldResultLine(
  line: Extract<StreamLine, { kind: 'result' }>,
  state: StreamState
): void {
  state.outcome = toOutcome(line);
  if (line.result.state === 'running') state.running = true;
  state.jobId ??= line.result.jobId;
}

/** A stream that broke: retried before any job or result, followed by polls once a job is known, otherwise the failure is real. */
export function recoverBrokenStream(
  error: unknown,
  state: StreamState,
  fallbackMachine: string | undefined,
  retriable: boolean
): 'done' | 'retry' {
  if (!state.jobId && !state.outcome && retriable) return 'retry';
  if (state.jobId && (state.machine ?? fallbackMachine)) return 'done';
  throw error;
}

/** The command's own printed output rides along from the result line that handed the job back. */
export function terminalOutcome(
  status: { state: string; exitCode?: number },
  jobId: string,
  first: ProxyCommandOutcome | undefined
): ProxyCommandOutcome {
  const success = status.state === 'succeeded';
  return {
    success,
    exitCode: status.exitCode ?? (success ? 0 : 1),
    ...(success ? {} : { error: `job ${jobId} ${status.state}` }),
    stdout: first?.stdout ?? '',
    stderr: first?.stderr ?? '',
    jobId,
  };
}

export function lostOutcome(
  jobId: string,
  machine: string,
  first: ProxyCommandOutcome | undefined
): ProxyCommandOutcome {
  return {
    success: false,
    exitCode: EXIT_CODES.FOLLOW_LOST,
    error: `Lost sight of job ${jobId}. It keeps running on '${machine}'. Wait for it with: rdc job wait ${jobId} -m ${machine}`,
    stdout: first?.stdout ?? '',
    stderr: first?.stderr ?? '',
    jobId,
  };
}
