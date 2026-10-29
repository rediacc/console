/**
 * The local ticket store: one JSONL file per config at
 * `<config dir>/jobs/<config>.jsonl` (directory 0700, file 0600).
 *
 * Every state change is one appended line under O_APPEND, so concurrent `rdc`
 * processes (an MCP server running tools in parallel) never lose a ticket. A
 * ticket is the fold of its lines by `requestId`. Compaction drops the lines of
 * acknowledged tickets under a lock file once more than COMPACT_THRESHOLD of
 * them pile up.
 *
 * No secret ever enters the file: `sanitizeEvent` copies an allow-list of
 * fields, so a vault, env or payload passed by mistake is dropped, not stored.
 */

import {
  chmodSync,
  closeSync,
  constants,
  existsSync,
  fstatSync,
  mkdirSync,
  openSync,
  readFileSync,
  renameSync,
  statSync,
  unlinkSync,
  writeFileSync,
  writeSync,
} from 'node:fs';
import { join } from 'node:path';
import { getConfigDir } from '@rediacc/shared/paths';

/** Schema version written on every line. */
export const TICKET_SCHEMA_VERSION = 1;

/** Acknowledged tickets beyond this many trigger compaction. */
export const COMPACT_THRESHOLD = 200;

const LOCK_STALE_MS = 30_000;
const LOCK_WAIT_MS = 2_000;
const APPEND_RETRIES = 5;
const SECRET_KEY = /secret|vault|password|passwd|token|credential|env|private|key/i;

export type TicketKind =
  | 'starting'
  | 'started'
  | 'seen'
  | 'finished'
  | 'acknowledged'
  | 'then-started'
  | 'step-done';

export type TicketState = 'starting' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'unknown';

export interface TicketVia {
  kind: 'ssh' | 'proxy';
  url?: string;
}

type Scalar = string | number | boolean;

/** A client-side step mirrored from the spool's `steps.json` (J15 fills these). */
export interface TicketStep {
  name: string;
  on: 'success' | 'failure';
  params?: Record<string, Scalar>;
}

/** A successor machine call recorded on the ticket. */
export interface TicketThen {
  function: string;
  params?: Record<string, Scalar>;
}

/** One line of the store. */
export interface TicketEvent {
  v: number;
  ts: string;
  kind: TicketKind;
  requestId: string;
  jobId?: string;
  config?: string;
  machine?: string;
  via?: TicketVia;
  verb?: string;
  function?: string;
  repo?: string;
  startedAt?: string;
  lastSeenLine?: number;
  state?: TicketState;
  exitCode?: number;
  finishedAt?: string;
  then?: TicketThen;
  /** The step plan mirror (`starting`/`started` events). */
  steps?: TicketStep[];
  /** The step a `step-done` event reports. */
  step?: string;
}

/** The folded view of one request id. */
export interface Ticket {
  requestId: string;
  jobId?: string;
  config?: string;
  machine?: string;
  via?: TicketVia;
  verb?: string;
  function?: string;
  repo?: string;
  startedAt?: string;
  lastSeenLine: number;
  state: TicketState;
  exitCode?: number;
  finishedAt?: string;
  then?: TicketThen;
  thenStarted: boolean;
  steps: TicketStep[];
  stepsDone: string[];
  acknowledged: boolean;
  /** Timestamp of the last event that observed the job (seen or finished). */
  lastCheckedAt?: string;
}

export interface TicketInput extends Partial<Omit<TicketEvent, 'v' | 'ts' | 'kind' | 'requestId'>> {
  [extra: string]: unknown;
}

export function isTerminalTicketState(state: TicketState): boolean {
  return state === 'succeeded' || state === 'failed' || state === 'cancelled';
}

function cleanParams(params: unknown): Record<string, Scalar> | undefined {
  if (!params || typeof params !== 'object') return undefined;
  const out: Record<string, Scalar> = {};
  for (const [key, value] of Object.entries(params)) {
    if (SECRET_KEY.test(key)) continue;
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
      out[key] = value;
    }
  }
  return out;
}

const STRING_FIELDS = [
  'jobId',
  'config',
  'machine',
  'verb',
  'function',
  'repo',
  'startedAt',
  'finishedAt',
  'step',
] as const;

function cleanVia(raw: unknown): TicketVia | undefined {
  if (!raw || typeof raw !== 'object') return undefined;
  const via = raw as TicketVia;
  const clean: TicketVia = { kind: via.kind === 'proxy' ? 'proxy' : 'ssh' };
  if (typeof via.url === 'string') clean.url = stripUrlSecrets(via.url);
  return clean;
}

function cleanThen(raw: unknown): TicketThen | undefined {
  const then = raw as TicketThen | undefined;
  if (!then || typeof then.function !== 'string') return undefined;
  return { function: then.function, params: cleanParams(then.params) };
}

function cleanSteps(raw: unknown): TicketStep[] | undefined {
  if (!Array.isArray(raw)) return undefined;
  return (raw as TicketStep[])
    .filter((s) => s && typeof s.name === 'string')
    .map((s) => ({
      name: s.name,
      on: s.on === 'failure' ? 'failure' : 'success',
      params: cleanParams(s.params),
    }));
}

/** Copy only the schema's fields. Anything else (a vault, env, payload) is dropped. */
export function sanitizeEvent(
  kind: TicketKind,
  requestId: string,
  input: TicketInput,
  now: Date = new Date()
): TicketEvent {
  const event: TicketEvent = { v: TICKET_SCHEMA_VERSION, ts: now.toISOString(), kind, requestId };
  for (const key of STRING_FIELDS) {
    const value = input[key];
    if (typeof value === 'string') event[key] = value;
  }
  if (typeof input.lastSeenLine === 'number') event.lastSeenLine = input.lastSeenLine;
  if (typeof input.exitCode === 'number') event.exitCode = input.exitCode;
  if (typeof input.state === 'string') event.state = input.state as TicketState;
  event.via = cleanVia(input.via);
  event.then = cleanThen(input.then);
  event.steps = cleanSteps(input.steps);
  // Drop the undefined keys so a line never carries a null placeholder.
  return JSON.parse(JSON.stringify(event)) as TicketEvent;
}

/** A proxy URL may carry userinfo or a query token; keep origin and path only. */
function stripUrlSecrets(raw: string): string {
  try {
    const url = new URL(raw);
    return `${url.origin}${url.pathname}`;
  } catch {
    return '';
  }
}

/** Fold event lines into tickets keyed by requestId, in first-seen order. */
export function foldEvents(events: TicketEvent[]): Ticket[] {
  const tickets = new Map<string, Ticket>();
  for (const e of events) {
    let t = tickets.get(e.requestId);
    if (!t) {
      t = {
        requestId: e.requestId,
        lastSeenLine: 0,
        state: 'starting',
        thenStarted: false,
        steps: [],
        stepsDone: [],
        acknowledged: false,
      };
      tickets.set(e.requestId, t);
    }
    applyEvent(t, e);
  }
  return [...tickets.values()];
}

const COPIED_FIELDS = [
  'jobId',
  'config',
  'machine',
  'via',
  'verb',
  'function',
  'repo',
  'startedAt',
] as const;

/** Per-kind effect on the folded ticket. Kinds with no entry only copy fields. */
const KIND_EFFECTS: Partial<Record<TicketKind, (t: Ticket, e: TicketEvent) => void>> = {
  started: (t, e) => {
    if (!isTerminalTicketState(t.state)) t.state = e.state ?? 'running';
  },
  seen: (t, e) => {
    t.lastCheckedAt = e.ts;
    if (e.state && !isTerminalTicketState(t.state)) t.state = e.state;
  },
  finished: (t, e) => {
    t.state = e.state ?? 'unknown';
    t.exitCode = e.exitCode ?? t.exitCode;
    t.finishedAt = e.finishedAt ?? t.finishedAt;
    t.lastCheckedAt = e.ts;
  },
  acknowledged: (t) => {
    t.acknowledged = true;
  },
  'then-started': (t) => {
    t.thenStarted = true;
  },
  'step-done': (t, e) => {
    if (e.step && !t.stepsDone.includes(e.step)) t.stepsDone.push(e.step);
  },
};

function applyEvent(t: Ticket, e: TicketEvent): void {
  for (const key of COPIED_FIELDS) {
    if (e[key] !== undefined) Object.assign(t, { [key]: e[key] });
  }
  t.then = e.then ?? t.then;
  t.steps = e.steps ?? t.steps;
  t.lastSeenLine = Math.max(t.lastSeenLine, e.lastSeenLine ?? 0);
  KIND_EFFECTS[e.kind]?.(t, e);
}

function sleepSync(ms: number): void {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

export class TicketStore {
  readonly dir: string;
  readonly path: string;
  private readonly lockPath: string;

  constructor(
    readonly config: string,
    baseDir: string = getConfigDir()
  ) {
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(config)) {
      throw new Error(`Invalid config name for the ticket store: ${JSON.stringify(config)}`);
    }
    this.dir = join(baseDir, 'jobs');
    this.path = join(this.dir, `${config}.jsonl`);
    this.lockPath = `${this.path}.lock`;
  }

  private ensureDir(): void {
    mkdirSync(this.dir, { recursive: true, mode: 0o700 });
    chmodSync(this.dir, 0o700);
  }

  /** Append one event. Safe against concurrent appenders and a concurrent compaction. */
  append(kind: TicketKind, requestId: string, input: TicketInput = {}): TicketEvent {
    const event = sanitizeEvent(kind, requestId, { config: this.config, ...input });
    const line = Buffer.from(`${JSON.stringify(event)}\n`, 'utf8');
    this.ensureDir();

    for (let attempt = 0; attempt < APPEND_RETRIES; attempt++) {
      this.waitForLock();
      const fd = openSync(
        this.path,
        constants.O_WRONLY | constants.O_APPEND | constants.O_CREAT,
        0o600
      );
      let replaced = false;
      try {
        writeSync(fd, line);
        // A compaction that renamed a new file in after we opened ours took our line to the unlinked inode. Detect it and write again.
        replaced = !sameInode(fd, this.path);
      } finally {
        closeSync(fd);
      }
      if (!replaced) {
        chmodSync(this.path, 0o600);
        return event;
      }
    }
    throw new Error('Could not append to the job ticket store: it kept being replaced.');
  }

  private waitForLock(): void {
    const deadline = Date.now() + LOCK_WAIT_MS;
    while (existsSync(this.lockPath) && Date.now() < deadline) {
      if (this.lockIsStale()) return;
      sleepSync(10);
    }
  }

  private lockIsStale(): boolean {
    try {
      return Date.now() - statSync(this.lockPath).mtimeMs > LOCK_STALE_MS;
    } catch {
      return true;
    }
  }

  readEvents(): TicketEvent[] {
    let raw: string;
    try {
      raw = readFileSync(this.path, 'utf8');
    } catch {
      return [];
    }
    return parseLines(raw);
  }

  tickets(): Ticket[] {
    return foldEvents(this.readEvents());
  }

  /** Tickets that are pending or finished and not yet acknowledged, newest first. */
  pending(): Ticket[] {
    return this.tickets()
      .filter((t) => !t.acknowledged)
      .sort((a, b) => (b.startedAt ?? '').localeCompare(a.startedAt ?? ''));
  }

  /** Find a ticket by job id or request id. */
  find(id: string): Ticket | undefined {
    const all = this.tickets();
    return all.find((t) => t.jobId === id) ?? all.find((t) => t.requestId === id);
  }

  /**
   * Drop the lines of acknowledged tickets when more than COMPACT_THRESHOLD of
   * them exist. Returns true when it rewrote the file.
   */
  compactIfNeeded(): boolean {
    const acked = this.tickets().filter((t) => t.acknowledged).length;
    if (acked <= COMPACT_THRESHOLD) return false;
    return this.compact();
  }

  compact(): boolean {
    this.ensureDir();
    let lockFd: number;
    try {
      lockFd = openSync(
        this.lockPath,
        constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL,
        0o600
      );
    } catch {
      if (!this.lockIsStale()) return false;
      try {
        unlinkSync(this.lockPath);
      } catch {
        // someone else cleaned it
      }
      return false;
    }
    try {
      const raw = readFileSync(this.path, 'utf8');
      const readBytes = Buffer.byteLength(raw, 'utf8');
      const events = parseLines(raw);
      const live = new Set(
        foldEvents(events)
          .filter((t) => !t.acknowledged)
          .map((t) => t.requestId)
      );
      const kept = events.filter((e) => live.has(e.requestId));
      const tmp = `${this.path}.${process.pid}.tmp`;
      writeFileSync(tmp, kept.map((e) => `${JSON.stringify(e)}\n`).join(''), { mode: 0o600 });
      // Lines appended while we worked (past the bytes we read) are carried over.
      const tail = readFileSync(this.path).subarray(readBytes);
      if (tail.length > 0) writeFileSync(tmp, tail, { flag: 'a' });
      renameSync(tmp, this.path);
      chmodSync(this.path, 0o600);
      return true;
    } finally {
      closeSync(lockFd);
      try {
        unlinkSync(this.lockPath);
      } catch {
        // already gone
      }
    }
  }
}

function sameInode(fd: number, path: string): boolean {
  try {
    return fstatSync(fd).ino === statSync(path).ino;
  } catch {
    return false;
  }
}

function parseLines(raw: string): TicketEvent[] {
  const events: TicketEvent[] = [];
  for (const line of raw.split('\n')) {
    if (!line.trim()) continue;
    try {
      const parsed = JSON.parse(line) as TicketEvent;
      if (parsed && typeof parsed.requestId === 'string' && typeof parsed.kind === 'string') {
        events.push(parsed);
      }
    } catch {
      // a torn or foreign line never takes the store down
    }
  }
  return events;
}
