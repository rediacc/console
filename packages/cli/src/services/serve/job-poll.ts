/**
 * The serve-side half of the detached-job poll (PLAN-detached-jobs Design 4).
 *
 * `GET /v1/jobs/:id/poll` runs `renet job logs --id <id> --since-line N
 * --max-lines K --with-status` through an SSH exec and answers one JSON body:
 * the new event lines and the job's status together. This module is the pure
 * part: the argv, the parser, and the once-per-job terminal ledger. The route,
 * authorization and audit wiring stay in server.ts and command-dispatch.ts.
 *
 * renet's output (pkg/jobs/logs.go): the job's NDJSON events verbatim, one per
 * line, then one `{"type":"job_status", ...Status}` trailer line.
 */

import { assertJobId } from '../executor/job-client.js';

/** Lines per poll when the client names none. */
export const DEFAULT_MAX_LINES = 500;
/** The serialized body never exceeds this. */
export const MAX_BODY_BYTES = 256 * 1024;

// Local until the J2 contract types land; the shape is Design 4's body.
export type JobPollState = 'running' | 'succeeded' | 'failed' | 'cancelled' | (string & {});

export interface JobPollStatus {
  state: JobPollState;
  exitCode?: number;
  finishedAt?: string;
  function: string;
}

export interface JobPollEvent {
  /** Zero-based index of this line in the job's stream. */
  line: number;
  event: unknown;
}

export interface JobPollBody {
  events: JobPollEvent[];
  /** The `sinceLine` for the next poll: the count of lines received so far. */
  nextLine: number;
  /** True when more output is already available, so the client polls again at once. */
  more: boolean;
  status: JobPollStatus;
}

export class JobPollParseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'JobPollParseError';
  }
}

function clampLines(maxLines: number | undefined): number {
  if (maxLines === undefined || !Number.isFinite(maxLines) || maxLines < 1) {
    return DEFAULT_MAX_LINES;
  }
  return Math.min(Math.floor(maxLines), DEFAULT_MAX_LINES);
}

/** The renet argv (after the binary) for one poll. Throws on an id renet could not have minted. */
export function buildJobPollArgv(jobId: string, sinceLine: number, maxLines?: number): string[] {
  const since = Number.isFinite(sinceLine) && sinceLine > 0 ? Math.floor(sinceLine) : 0;
  return [
    'job',
    'logs',
    '--id',
    assertJobId(jobId),
    '--since-line',
    String(since),
    '--max-lines',
    String(clampLines(maxLines)),
    '--with-status',
  ];
}

function parseEvent(text: string): unknown {
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return { type: 'raw', text };
  }
}

function parseStatus(trailer: string): JobPollStatus {
  let raw: Record<string, unknown>;
  try {
    raw = JSON.parse(trailer) as Record<string, unknown>;
  } catch {
    throw new JobPollParseError('job logs: the status trailer is not JSON');
  }
  if (raw.type !== 'job_status' || typeof raw.state !== 'string') {
    throw new JobPollParseError('job logs: the output has no job_status trailer');
  }
  const status: JobPollStatus = {
    state: raw.state,
    function: typeof raw.function === 'string' ? raw.function : '',
  };
  if (typeof raw.exit_code === 'number') status.exitCode = raw.exit_code;
  if (typeof raw.finished_at === 'string' && raw.finished_at !== '') {
    status.finishedAt = raw.finished_at;
  }
  return status;
}

function bodySize(body: JobPollBody): number {
  return Buffer.byteLength(JSON.stringify(body));
}

/**
 * Turns `renet job logs --with-status` stdout into the poll body. `more` is set
 * when the page is full or the byte cap cut it short; a cut resumes at the first
 * unsent line, and a single event too large for any body is replaced by a
 * `truncated` marker so the cursor still advances.
 */
export function parseJobPollOutput(
  stdout: string,
  opts: { sinceLine: number; maxLines?: number }
): JobPollBody {
  const lines = stdout.split('\n').filter((l) => l.trim() !== '');
  const trailer = lines.pop();
  if (trailer === undefined) throw new JobPollParseError('job logs: empty output');
  const status = parseStatus(trailer);
  const limit = clampLines(opts.maxLines);

  const body: JobPollBody = { events: [], nextLine: opts.sinceLine, more: false, status };
  for (const [i, text] of lines.entries()) {
    const line = opts.sinceLine + i;
    body.events.push({ line, event: parseEvent(text) });
    body.nextLine = line + 1;
    if (bodySize(body) <= MAX_BODY_BYTES) continue;

    body.events.pop();
    body.nextLine = line;
    if (body.events.length > 0) {
      body.more = true;
      return body;
    }
    body.events.push({ line, event: { type: 'truncated', bytes: Buffer.byteLength(text) } });
    body.nextLine = line + 1;
    body.more = i + 1 < lines.length;
    return body;
  }
  body.more = lines.length >= limit;
  return body;
}

const TERMINAL_STATES = new Set<string>(['succeeded', 'failed', 'cancelled']);

export function isTerminalState(state: string): boolean {
  return TERMINAL_STATES.has(state);
}

export interface TerminalLedger {
  /** True exactly once per job id: the first time a terminal state is seen for it. */
  firstTerminal(jobId: string, state: string): boolean;
}

/** In-memory, bounded; the oldest ids are forgotten past `capacity`. */
export function createTerminalLedger(capacity = 10_000): TerminalLedger {
  const seen = new Set<string>();
  return {
    firstTerminal(jobId, state) {
      if (!isTerminalState(state) || seen.has(jobId)) return false;
      seen.add(jobId);
      if (seen.size > capacity) {
        const oldest = seen.values().next().value;
        if (oldest !== undefined) seen.delete(oldest);
      }
      return true;
    },
  };
}
