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
type JobPollState = 'running' | 'succeeded' | 'failed' | 'cancelled' | (string & {});

interface JobPollStatus {
  state: JobPollState;
  exitCode?: number;
  finishedAt?: string;
  function: string;
}

interface JobPollEvent {
  /** Zero-based index of this line in the job's stream. */
  line: number;
  event: unknown;
}

export interface JobPollBody {
  events: JobPollEvent[];
  /** The `sinceLine` for the next poll: an absolute line index (`sinceLine` plus the lines this page covered). */
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

function clampSince(sinceLine: number): number {
  return Number.isFinite(sinceLine) && sinceLine > 0 ? Math.floor(sinceLine) : 0;
}

/** The renet argv (after the binary) for one poll. Throws on an id renet could not have minted. */
export function buildJobPollArgv(jobId: string, sinceLine: number, maxLines?: number): string[] {
  const since = clampSince(sinceLine);
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
  let parsed: unknown;
  try {
    parsed = JSON.parse(trailer);
  } catch {
    throw new JobPollParseError('job logs: the status trailer is not JSON');
  }
  if (typeof parsed !== 'object' || parsed === null) {
    throw new JobPollParseError('job logs: the output has no job_status trailer');
  }
  const raw = parsed as Record<string, unknown>;
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
  // A blank line is a line like any other: it keeps its place in the numbering, it just carries no event.
  const lines = stdout.split('\n');
  while (lines.length > 0 && lines[lines.length - 1].trim() === '') lines.pop();
  const trailer = lines.pop();
  if (trailer === undefined) throw new JobPollParseError('job logs: empty output');
  const status = parseStatus(trailer);
  const limit = clampLines(opts.maxLines);
  const sinceLine = clampSince(opts.sinceLine);
  const page = new PollPage(sinceLine, status);
  for (const [i, text] of lines.entries()) {
    const line = sinceLine + i;
    if (text.trim() === '') {
      page.skip(line);
    } else if (!page.add(line, text)) {
      return page.cut(line, text, i + 1 < lines.length);
    }
  }
  page.body.more = lines.length >= limit;
  return page.body;
}

/**
 * The page under construction. The serialized size is a running count: the envelope with an empty
 * page, plus each event and the commas between them, so a line costs its own bytes only.
 */
class PollPage {
  readonly body: JobPollBody;
  private readonly envelope: number;
  private readonly sinceDigits: number;
  private eventBytes = 0;

  constructor(
    private readonly sinceLine: number,
    status: JobPollStatus
  ) {
    this.body = { events: [], nextLine: sinceLine, more: false, status };
    this.envelope = Buffer.byteLength(JSON.stringify(this.body));
    this.sinceDigits = String(sinceLine).length;
  }

  /** A blank line keeps its place in the numbering and carries no event. */
  skip(line: number): void {
    this.body.nextLine = line + 1;
  }

  /** Adds the line's event unless it would push the body past the cap. */
  add(line: number, text: string): boolean {
    const event: JobPollEvent = { line, event: parseEvent(text) };
    const bytes = Buffer.byteLength(JSON.stringify(event)) + (this.body.events.length > 0 ? 1 : 0);
    const total =
      this.envelope + String(line + 1).length - this.sinceDigits + this.eventBytes + bytes;
    if (total > MAX_BODY_BYTES) return false;
    this.body.events.push(event);
    this.eventBytes += bytes;
    this.body.nextLine = line + 1;
    return true;
  }

  /** The byte cap hit at `line`: resume there, or replace an event too large for any body. */
  cut(line: number, text: string, moreAfter: boolean): JobPollBody {
    if (this.body.events.length > 0) {
      this.body.nextLine = line;
      this.body.more = true;
      return this.body;
    }
    this.body.events.push({ line, event: { type: 'truncated', bytes: Buffer.byteLength(text) } });
    this.body.nextLine = line + 1;
    this.body.more = moreAfter;
    return this.body;
  }
}

const TERMINAL_STATES = new Set<string>(['succeeded', 'failed', 'cancelled']);

function isTerminalState(state: string): boolean {
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
