/**
 * The executor's run recorder (agent/plans/PLAN-console-run-index.md D3, D4).
 *
 * Every command the executor dispatches posts its life to the account server's run index:
 * `start` after authorize, `progress` at most every 15 s (the last step), `job` when the dispatch
 * hands off to a detached job, and `end` with the exit and error code and the output tail sealed
 * under the session CEK (the account server never reads command output). Events of one run are
 * delivered in order and carry a rising `seq`; the route keeps the highest. Delivery retries twice
 * and never fails or delays the command: every failure is reported to `onFailure` and dropped.
 *
 * A detached run's row stays `detached` until a terminal poll observes the job: `endJob` posts
 * the end for a run this process still remembers. A run of a previous process (the container
 * slept) is not remembered, and its row stays `detached` until the panel re-attaches it.
 */

import { randomUUID } from 'node:crypto';
import { sealRunTail } from '@rediacc/shared/config-crypto/run-tail';
import { deadlineFetch } from './account-fetch.js';
import type { SessionPrincipal } from './sessions.js';

/** Where the executor posts run events, relative to the account server. */
const RUN_EVENTS_PATH = '/account/api/v1/console/runs/events';

/** The least time between two progress events of one run. */
export const PROGRESS_INTERVAL_MS = 15_000;

/** Deliveries per event: the first attempt and two retries. */
export const RUN_EVENT_ATTEMPTS = 3;

/** Detached runs remembered for a terminal poll. */
const MAX_DETACHED = 1000;

type RunState = 'running' | 'detached' | 'succeeded' | 'failed' | 'cancelled';

interface RunBegin {
  principal: SessionPrincipal;
  /** The command request's id; one is minted when the request carried none. */
  runId?: string;
  pathKey: string;
  machine?: string;
  repo?: string;
  /** The session CEK, read when the tail is sealed (never held by the recorder). */
  cek?: () => Promise<Uint8Array | undefined>;
}

interface RunOutcome {
  state: Exclude<RunState, 'running'>;
  exitCode?: number;
  errorCode?: string;
  /** What the command printed; the last 8 KiB of both are sealed into the tail. */
  stdout?: string;
  stderr?: string;
}

interface RunHandle {
  readonly runId: string;
  /** A step began; reported by the next progress event. */
  step(name: string): void;
  /** The dispatch became a detached job. */
  job(jobId: string, machine?: string): void;
  /** The dispatch finished. Resolves once the event was delivered or given up on; never rejects. */
  end(outcome: RunOutcome): Promise<void>;
}

export interface RunIndex {
  begin(run: RunBegin): RunHandle;
  /** A terminal poll observed `jobId`: post the end of the detached run it belongs to, once. */
  endJob(
    jobId: string,
    outcome: Pick<RunOutcome, 'state' | 'exitCode' | 'errorCode'>
  ): Promise<void>;
}

export interface RunIndexOptions {
  accountUrl: string;
  executorToken: string;
  fetchImpl?: typeof globalThis.fetch;
  now?: () => number;
  progressIntervalMs?: number;
  /** Called for an event that was not delivered. */
  onFailure?: (reason: string, event: { runId: string; state: RunState; seq: number }) => void;
}

interface RunEvent {
  runId: string;
  seq: number;
  state: RunState;
  pathKey: string;
  startedAt: string;
  machine?: string;
  repo?: string;
  jobId?: string;
  exitCode?: number;
  errorCode?: string;
  lastStep?: string;
  endedAt?: string;
  tail?: string;
  onBehalfOfTokenId?: string;
}

type EventBase = Omit<RunEvent, 'seq' | 'state'>;

/** The shipping side shared by every run: one delivery with retries, never throwing. */
class Shipper {
  private readonly fetchImpl: typeof globalThis.fetch;
  private readonly url: string;

  constructor(private readonly options: RunIndexOptions) {
    this.fetchImpl = deadlineFetch(options.fetchImpl ?? globalThis.fetch);
    this.url = `${options.accountUrl.replace(/\/+$/, '')}${RUN_EVENTS_PATH}`;
  }

  /** One attempt: undefined when accepted, else why not and whether a retry could help. */
  private async attempt(body: string): Promise<{ reason: string; retry: boolean } | undefined> {
    try {
      const response = await this.fetchImpl(this.url, {
        method: 'POST',
        headers: {
          authorization: `Bearer ${this.options.executorToken}`,
          'content-type': 'application/json',
        },
        body,
      });
      if (response.ok) return undefined;
      return {
        reason: `the account server answered ${response.status}`,
        retry: response.status >= 500 || response.status === 429,
      };
    } catch (error) {
      return { reason: error instanceof Error ? error.message : String(error), retry: true };
    }
  }

  async deliver(event: RunEvent): Promise<void> {
    const body = JSON.stringify(event);
    let failed: { reason: string; retry: boolean } | undefined;
    for (let attempt = 1; attempt <= RUN_EVENT_ATTEMPTS; attempt++) {
      failed = await this.attempt(body);
      if (!failed?.retry) break;
    }
    if (failed) this.report(failed.reason, event);
  }

  private report(reason: string, event: RunEvent): void {
    try {
      this.options.onFailure?.(reason, { runId: event.runId, state: event.state, seq: event.seq });
    } catch {
      // A reporter that throws must not reach the command.
    }
  }
}

/** One run's event stream: in-order delivery, rising seq, throttled progress. */
class Run implements RunHandle {
  readonly runId: string;
  private seq = 0;
  private chain: Promise<void> = Promise.resolve();
  private lastProgressAt: number;
  private lastStepSent: string | undefined;
  private pendingStep: string | undefined;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private phase: 'live' | 'ended' = 'live';
  private jobId: string | undefined;

  constructor(
    private readonly shipper: Shipper,
    private readonly base: EventBase,
    private readonly begun: RunBegin,
    private readonly clock: { now: () => number; interval: number },
    private readonly onDetached: (jobId: string, run: Run) => void
  ) {
    this.runId = base.runId;
    this.lastProgressAt = clock.now();
    void this.post('running');
  }

  /** Queue one event behind the run's earlier ones; the sequence number is taken here, in order. */
  post(state: RunState, extra: Partial<RunEvent> = {}): Promise<void> {
    const event: RunEvent = { ...this.base, seq: this.seq++, state, ...extra };
    this.chain = this.chain.then(() => this.shipper.deliver(event));
    return this.chain;
  }

  step(name: string): void {
    if (this.phase === 'ended' || name === this.lastStepSent) return;
    this.pendingStep = name;
    const wait = this.lastProgressAt + this.clock.interval - this.clock.now();
    if (wait <= 0) {
      this.flushProgress();
    } else if (!this.timer) {
      this.timer = setTimeout(() => this.flushProgress(), wait);
      this.timer.unref?.();
    }
  }

  private flushProgress(): void {
    // A step that flushes overdue progress while its timer is still pending must cancel that timer, or it later posts a second progress event inside the interval.
    if (this.timer) clearTimeout(this.timer);
    this.timer = undefined;
    if (this.phase === 'ended' || this.pendingStep === undefined) return;
    this.lastStepSent = this.pendingStep;
    this.pendingStep = undefined;
    this.lastProgressAt = this.clock.now();
    void this.post('running', { lastStep: this.lastStepSent });
  }

  job(id: string, machine?: string): void {
    if (this.phase === 'ended') return;
    this.jobId = id;
    this.base.jobId = id;
    if (machine) this.base.machine = machine;
    void this.post('running');
  }

  private async sealedTail(outcome: RunOutcome): Promise<string | undefined> {
    const text = [outcome.stdout, outcome.stderr].filter(Boolean).join('\n');
    if (!this.begun.cek || text === '') return undefined;
    try {
      const key = await this.begun.cek();
      return key ? await sealRunTail(key, this.begun.principal.orgId, this.runId, text) : undefined;
    } catch {
      return undefined;
    }
  }

  async end(outcome: RunOutcome): Promise<void> {
    if (this.phase === 'ended') return;
    const terminal = outcome.state !== 'detached';
    if (terminal) this.phase = 'ended';
    this.stopProgress();
    const tail = await this.sealedTail(outcome);
    const sent = this.post(outcome.state, {
      ...closing(outcome),
      ...(terminal ? { endedAt: new Date(this.clock.now()).toISOString() } : {}),
      ...(tail ? { tail } : {}),
    });
    if (!terminal && this.jobId) this.onDetached(this.jobId, this);
    await sent;
  }

  /** The terminal poll's end for a detached run. */
  endFromPoll(outcome: Pick<RunOutcome, 'state' | 'exitCode' | 'errorCode'>): Promise<void> {
    this.phase = 'ended';
    return this.post(outcome.state, {
      ...closing(outcome),
      endedAt: new Date(this.clock.now()).toISOString(),
    });
  }

  private stopProgress(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = undefined;
    this.pendingStep = undefined;
  }
}

/** The exit and error code an event carries, when known. */
function closing(outcome: Pick<RunOutcome, 'exitCode' | 'errorCode'>): Partial<RunEvent> {
  return {
    ...(outcome.exitCode === undefined ? {} : { exitCode: outcome.exitCode }),
    ...(outcome.errorCode ? { errorCode: outcome.errorCode } : {}),
  };
}

export function createRunIndex(options: RunIndexOptions): RunIndex {
  const shipper = new Shipper(options);
  const now = options.now ?? Date.now;
  const clock = { now, interval: options.progressIntervalMs ?? PROGRESS_INTERVAL_MS };
  const detached = new Map<string, Run>();

  const remember = (jobId: string, run: Run): void => {
    if (detached.size >= MAX_DETACHED) {
      const oldest = detached.keys().next().value;
      if (oldest !== undefined) detached.delete(oldest);
    }
    detached.set(jobId, run);
  };

  return {
    begin(run) {
      const base: EventBase = {
        runId: run.runId ?? randomUUID(),
        pathKey: run.pathKey,
        startedAt: new Date(now()).toISOString(),
        ...(run.machine ? { machine: run.machine } : {}),
        ...(run.repo ? { repo: run.repo } : {}),
        ...(run.principal.tokenId ? { onBehalfOfTokenId: run.principal.tokenId } : {}),
      };
      return new Run(shipper, base, run, clock, remember);
    },
    async endJob(jobId, outcome) {
      const run = detached.get(jobId);
      if (!run) return;
      detached.delete(jobId);
      await run.endFromPoll(outcome);
    },
  };
}
