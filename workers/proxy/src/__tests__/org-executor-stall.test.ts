/**
 * `OrgExecutor` when a call into the container runtime stalls instead of failing: a health probe, the intercept registration, a destroy. Measured live on edge v3.0.0 on 2026-11-03: a stalled probe held one org's start for about 7 minutes, with later pins queued behind it, and the bearer of the waiting request expired before the executor read it.
 *
 * Every test here runs on fake timers, so a call that was not bounded leaves `pin` pending and fails on the settled check rather than hanging the suite.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('cloudflare:workers', () => {
  class Base {
    constructor(
      protected ctx: unknown,
      protected env: unknown
    ) {}
  }
  // WorkerEntrypoint: src/egress.ts, which org-executor.ts imports, extends it.
  return { DurableObject: Base, WorkerEntrypoint: Base };
});

import { CONTAINER_CALL_TIMEOUT_MS, type ExecutorRecord, READY_TIMEOUT_MS } from '../org-executor';
import { COORDINATOR_TIMEOUT_MS } from '../org-executor-support';
import { FakeContainer, harness, IMAGE_V1, LEASE, ORG, T0 } from './helpers/org-executor-harness';

/** EXECUTOR_LEG_TOKEN_TTL_MS in private/account/src/routes/console.ts. */
const BEARER_LIFE_MS = 60_000;

const never = <T>() => new Promise<T>(() => undefined);

/** Advance until `pending` settles or `limitMs` passes, and answer what it settled to and when. */
async function settleWithin<T>(pending: Promise<T>, limitMs: number) {
  const started = Date.now();
  let settled: { answer: T; afterMs: number } | undefined;
  void pending.then((answer) => {
    settled = { answer, afterMs: Date.now() - started };
  });
  while (settled === undefined && Date.now() - started < limitMs) {
    await vi.advanceTimersByTimeAsync(100);
  }
  if (settled === undefined) throw new Error(`still pending after ${limitMs} ms`);
  return settled;
}

let warn: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(T0);
  warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('a stalled container call', () => {
  it('a health probe that never answers fails the start at the readiness deadline and frees the lease', async () => {
    const h = harness();
    await h.ready;
    h.container.health = () => never<Response>();

    const { answer, afterMs } = await settleWithin(
      h.executor.pin(ORG, 0, 'light'),
      READY_TIMEOUT_MS * 2
    );

    expect(answer).toMatchObject({
      ok: false,
      code: 'EXECUTOR_START_FAILED',
      reason: 'not-ready',
    });
    expect(afterMs).toBeLessThanOrEqual(READY_TIMEOUT_MS + 500);
    expect(h.container.destroys).toEqual(['not-ready']);
    expect(h.capacity.release).toHaveBeenCalledWith(LEASE);
    expect(h.storage.has('executor')).toBe(false);
    expect(warn).toHaveBeenCalledWith('proxy: org executor container call stalled', {
      step: 'health',
    });
  });

  it('a stalled intercept registration fails the start before any container starts', async () => {
    const h = harness();
    await h.ready;
    h.container.interceptOutboundHttp = () => never<void>();

    const { answer, afterMs } = await settleWithin(
      h.executor.pin(ORG, 0, 'light'),
      CONTAINER_CALL_TIMEOUT_MS * 2
    );

    expect(answer).toMatchObject({
      ok: false,
      code: 'EXECUTOR_START_FAILED',
      reason: 'egress-stalled',
    });
    expect(afterMs).toBeLessThanOrEqual(CONTAINER_CALL_TIMEOUT_MS + 500);
    expect(h.container.starts).toHaveLength(0);
    expect(h.capacity.release).toHaveBeenCalledWith(LEASE);
    expect(warn).toHaveBeenCalledWith('proxy: org executor container call stalled', {
      step: 'egress',
    });
  });

  it('a stalled destroy on the failure path still answers and still frees the lease', async () => {
    const h = harness();
    await h.ready;
    h.container.health = () => never<Response>();
    h.container.destroy = () => never<void>();

    const { answer } = await settleWithin(
      h.executor.pin(ORG, 0, 'light'),
      READY_TIMEOUT_MS + CONTAINER_CALL_TIMEOUT_MS * 2
    );

    expect(answer).toMatchObject({ ok: false, code: 'EXECUTOR_START_FAILED' });
    expect(h.capacity.release).toHaveBeenCalledWith(LEASE);
    expect(warn).toHaveBeenCalledWith('proxy: org executor container call stalled', {
      step: 'destroy',
    });
  });

  it('recovery goes on past a stalled intercept registration', async () => {
    const container = new FakeContainer();
    container.running = true;
    container.interceptOutboundHttp = () => never<void>();
    const record: ExecutorRecord = {
      orgId: ORG,
      placement: 0,
      size: 'light',
      image: IMAGE_V1,
      startedAt: T0,
    };
    const h = harness({ container, storage: new Map<string, unknown>([['executor', record]]) });

    await settleWithin(h.ready, CONTAINER_CALL_TIMEOUT_MS * 2);

    expect(h.capacity.acquire).toHaveBeenCalledWith(LEASE, 'light');
  });

  it('logs the step and nothing of a request or a token', async () => {
    const h = harness();
    await h.ready;
    h.container.health = () => never<Response>();
    await settleWithin(h.executor.pin(ORG, 0, 'light'), READY_TIMEOUT_MS * 2);

    const logged = JSON.stringify(warn.mock.calls);
    expect(logged).not.toMatch(/bearer|authorization|token/i);
    expect(logged).not.toContain(ORG);
  });
});

describe('pins around a stalled start', () => {
  it('a pin arriving after the stall settled gets a fresh attempt', async () => {
    const h = harness();
    await h.ready;
    h.container.health = () => never<Response>();
    await settleWithin(h.executor.pin(ORG, 0, 'light'), READY_TIMEOUT_MS * 2);
    expect(h.container.starts).toHaveLength(1);

    h.container.health = () => new Response('ok');
    const { answer } = await settleWithin(h.executor.pin(ORG, 0, 'light'), 1_000);

    expect(answer).toEqual({ ok: true, size: 'light', egressUnreachableRecent: false });
    expect(h.container.starts).toHaveLength(2);
    expect(h.capacity.acquire).toHaveBeenCalledTimes(2);
    const response = await h.executor.fetch(new Request('https://proxy/v1/run'));
    expect(await response.text()).toBe('from-app');
  });

  it('pins queued on the stalled start share its refusal, so none waits a second start', async () => {
    const h = harness();
    await h.ready;
    h.container.health = () => never<Response>();

    const first = h.executor.pin(ORG, 0, 'light');
    await vi.advanceTimersByTimeAsync(1_000);
    const queued = [h.executor.pin(ORG, 0, 'light'), h.executor.pin(ORG, 0, 'light')];

    const { answer, afterMs } = await settleWithin(
      Promise.all([first, ...queued]),
      READY_TIMEOUT_MS * 2
    );

    for (const refused of answer) {
      expect(refused).toMatchObject({ ok: false, code: 'EXECUTOR_START_FAILED' });
    }
    expect(afterMs).toBeLessThanOrEqual(READY_TIMEOUT_MS + 500);
    expect(h.container.starts).toHaveLength(1);
  });
});

describe('a start that does not stall (the control)', () => {
  it('a healthy start answers ok at once and logs no stall', async () => {
    const h = harness();
    await h.ready;

    const { answer, afterMs } = await settleWithin(h.executor.pin(ORG, 0, 'light'), 1_000);

    expect(answer).toEqual({ ok: true, size: 'light', egressUnreachableRecent: false });
    expect(afterMs).toBeLessThan(1_000);
    expect(h.container.destroys).toHaveLength(0);
    expect(h.capacity.release).not.toHaveBeenCalled();
    expect(warn).not.toHaveBeenCalled();
  });

  it('one stalled probe costs only that probe: the next one can still finish the start', async () => {
    const h = harness();
    await h.ready;
    let probes = 0;
    h.container.health = () => {
      probes += 1;
      return probes === 1 ? never<Response>() : new Response('ok');
    };

    const { answer, afterMs } = await settleWithin(
      h.executor.pin(ORG, 0, 'light'),
      READY_TIMEOUT_MS
    );

    expect(answer).toMatchObject({ ok: true });
    expect(probes).toBe(2);
    expect(afterMs).toBeGreaterThanOrEqual(CONTAINER_CALL_TIMEOUT_MS);
    expect(afterMs).toBeLessThan(CONTAINER_CALL_TIMEOUT_MS * 2);
  });

  it('the longest start that succeeds stays inside the life of a fresh bearer', async () => {
    expect(COORDINATOR_TIMEOUT_MS + CONTAINER_CALL_TIMEOUT_MS + READY_TIMEOUT_MS).toBeLessThan(
      BEARER_LIFE_MS
    );

    const h = harness();
    await h.ready;
    // The slowest success: the intercept takes its whole allowance, and the last probe before the deadline answers.
    h.container.interceptOutboundHttp = async () => {
      await new Promise((resolve) => setTimeout(resolve, CONTAINER_CALL_TIMEOUT_MS - 100));
    };
    const readyAt = T0 + CONTAINER_CALL_TIMEOUT_MS + READY_TIMEOUT_MS - 1_000;
    h.container.health = () =>
      Date.now() >= readyAt ? new Response('ok') : new Response('booting', { status: 503 });

    const { answer, afterMs } = await settleWithin(h.executor.pin(ORG, 0, 'light'), BEARER_LIFE_MS);

    expect(answer).toMatchObject({ ok: true });
    expect(afterMs).toBeLessThan(BEARER_LIFE_MS);
  });
});
