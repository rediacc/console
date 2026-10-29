/**
 * `rdc job wait`: resume following a ticketed job, then acknowledge it.
 *
 * Over SSH it resumes from the ticket's `lastSeenLine` through the same tail
 * `rdc job logs --follow` uses. The proxy path is J6's: `deps.followProxy` is
 * the seam, and until J6 supplies it a proxy ticket is refused with a message.
 */

import { isTerminalState, JobLogCursor, type JobStatus } from '../executor/job-client.js';
import type { RenetEvent } from '../executor/types.js';
import { isTerminalTicketState, type Ticket, type TicketStore } from './ticket-store.js';

/** Opaque to this module: whatever `withConnection` hands to follow and readStatus. */
export type WaitConnection = unknown;

export interface JobWaitDeps {
  /** Open a read-only connection, run `fn`, release. */
  withConnection<T>(machine: string, fn: (conn: WaitConnection) => Promise<T>): Promise<T>;
  /** Tail a job from the cursor. Resolves true when interrupted (abort), false at the end of the job. */
  follow(
    conn: WaitConnection,
    jobId: string,
    cursor: JobLogCursor,
    onEvent: (event: RenetEvent, line?: number) => void,
    signal: AbortSignal
  ): Promise<boolean>;
  readStatus(conn: WaitConnection, jobId: string, machine: string): Promise<JobStatus>;
  /** J6 seam: follow a proxy ticket with short polls. Absent until the proxy client lands. */
  followProxy?: (ticket: Ticket, signal: AbortSignal) => Promise<JobStatus | undefined>;
  /** Resolve a ticket stuck at `starting` through `job list --request-id`. Absent until renet supports it (J1b). */
  resolveStarting?: (ticket: Ticket) => Promise<string | undefined>;
}

export type WaitOutcome =
  | { kind: 'finished'; status: Pick<JobStatus, 'state' | 'exit_code' | 'error'>; exitCode: number }
  | { kind: 'timeout' }
  | { kind: 'interrupted' }
  | { kind: 'unresolved' }
  | { kind: 'proxy-unsupported' };

export interface WaitOptions {
  timeoutMs?: number;
  onEvent: (event: RenetEvent, line?: number) => void;
  /** Aborts the wait without touching the job (Ctrl-C). */
  signal?: AbortSignal;
}

/** The job's exit code: renet's own, else mirrored from the terminal state. */
export function exitCodeFor(status: Pick<JobStatus, 'state' | 'exit_code'>): number {
  if (status.exit_code !== undefined && status.exit_code !== null) return status.exit_code;
  return status.state === 'succeeded' ? 0 : 1;
}

/** A ticket that never got its job id: resolve it through the request index, when renet has one. */
async function ensureJobId(
  store: TicketStore,
  ticket: Ticket,
  deps: JobWaitDeps
): Promise<Ticket | undefined> {
  if (ticket.jobId) return ticket;
  const resolved = await deps.resolveStarting?.(ticket);
  if (!resolved) return undefined;
  store.append('started', ticket.requestId, { jobId: resolved });
  return { ...ticket, jobId: resolved };
}

/** Run the follow under a signal that fires on timeout or on the caller's abort. */
async function withWaitSignal<T>(
  options: WaitOptions,
  run: (signal: AbortSignal) => Promise<T>
): Promise<{ result: T; timedOut: boolean }> {
  const controller = new AbortController();
  let timedOut = false;
  const timer =
    options.timeoutMs === undefined
      ? undefined
      : setTimeout(() => {
          timedOut = true;
          controller.abort();
        }, options.timeoutMs);
  const onOuterAbort = () => controller.abort();
  options.signal?.addEventListener('abort', onOuterAbort, { once: true });
  try {
    return { result: await run(controller.signal), timedOut };
  } finally {
    if (timer) clearTimeout(timer);
    options.signal?.removeEventListener('abort', onOuterAbort);
  }
}

export async function waitForJob(
  store: TicketStore,
  ticket: Ticket,
  deps: JobWaitDeps,
  options: WaitOptions
): Promise<WaitOutcome> {
  const current = await ensureJobId(store, ticket, deps);
  if (!current?.jobId) return { kind: 'unresolved' };
  const jobId = current.jobId;

  // Already known finished: nothing to follow, only acknowledge.
  if (isTerminalTicketState(current.state)) {
    const status = { state: current.state as JobStatus['state'], exit_code: current.exitCode };
    store.append('acknowledged', current.requestId);
    return { kind: 'finished', status, exitCode: exitCodeFor(status) };
  }
  if (current.via?.kind === 'proxy' && !deps.followProxy) return { kind: 'proxy-unsupported' };

  const { result: status, timedOut } = await withWaitSignal(options, (signal) =>
    current.via?.kind === 'proxy'
      ? (deps.followProxy as NonNullable<JobWaitDeps['followProxy']>)(current, signal)
      : followOverSsh(store, current, jobId, deps, options.onEvent, signal)
  );

  if (!status || !isTerminalState(status.state)) {
    return timedOut ? { kind: 'timeout' } : { kind: 'interrupted' };
  }

  const exitCode = exitCodeFor(status);
  store.append('finished', current.requestId, {
    state: status.state,
    exitCode,
    finishedAt: status.finished_at,
  });
  store.append('acknowledged', current.requestId);
  return { kind: 'finished', status, exitCode };
}

function followOverSsh(
  store: TicketStore,
  ticket: Ticket,
  jobId: string,
  deps: JobWaitDeps,
  onEvent: WaitOptions['onEvent'],
  signal: AbortSignal
): Promise<JobStatus | undefined> {
  const machine = ticket.machine as string;
  const cursor = new JobLogCursor(ticket.lastSeenLine);
  return deps.withConnection(machine, async (conn) => {
    let interrupted: boolean;
    try {
      interrupted = await deps.follow(conn, jobId, cursor, onEvent, signal);
    } finally {
      // The cursor counts complete lines only, so resuming from it never skips or repeats one.
      store.append('seen', ticket.requestId, { lastSeenLine: cursor.sinceLine });
    }
    if (interrupted) return undefined;
    return deps.readStatus(conn, jobId, machine);
  });
}
