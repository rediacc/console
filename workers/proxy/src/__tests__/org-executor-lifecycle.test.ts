/**
 * `OrgExecutor` (agent/plans/PLAN-executor-durable-object-policy.md box W1): recovery after a restart and container exits.
 *
 * Relocation (agent/plans/PLAN-org-executor-connect-timeout-relocate.md box E6): the egress-unreachable count, the threshold call to the issuer, and the retired instance's refusal, lease and drain.
 *
 * `cloudflare:workers` exists only inside workerd, so `DurableObject` is replaced by a base class that keeps `ctx` and `env` as the real one does. The fakes are in src/__tests__/helpers/org-executor-harness.ts.
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

import {
  COORDINATOR_TIMEOUT_MS,
  durationMs,
  type ExecutorRecord,
  isOomExit,
  type RelocateAnswer,
} from '../org-executor';
import { UNREACHABLE_THRESHOLD, UNREACHABLE_WINDOW_MS } from '../placement';
import {
  FakeCapacity,
  FakeContainer,
  flush,
  type Harness,
  harness,
  IDLE_MS,
  IMAGE_V1,
  LEASE,
  ORG,
  openStream,
  T0,
} from './helpers/org-executor-harness';

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(T0);
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('recovery after a restart', () => {
  const record: ExecutorRecord = {
    orgId: ORG,
    placement: 0,
    size: 'heavy',
    image: IMAGE_V1,
    startedAt: T0 - 60_000,
  };

  function running(): FakeContainer {
    const container = new FakeContainer();
    container.running = true;
    return container;
  }

  it('a constructor finding a running container re-acquires, re-attaches monitor() and re-registers the intercept', async () => {
    const container = running();
    const storage = new Map<string, unknown>([
      ['org', { orgId: ORG, placement: 0 }],
      ['executor', record],
    ]);
    const h = harness({ container, storage });
    await h.ready;
    expect(h.capacity.acquire).toHaveBeenCalledWith(LEASE, 'heavy');
    expect(container.log).toContain('monitor');
    expect(container.log).toContain('intercept');
    expect(h.egress).toHaveBeenCalledWith({
      props: { orgId: ORG, placement: 0, containerId: `id:${LEASE}` },
    });
    expect(container.destroys).toHaveLength(0);
    expect(h.alarmAt()).toBe(T0 + IDLE_MS);

    // It serves without a new start, and an exit seen by the re-attached monitor releases the slot.
    expect(await h.executor.pin(ORG, 0, 'light')).toEqual({
      ok: true,
      size: 'heavy',
      egressUnreachableRecent: false,
    });
    expect(container.starts).toHaveLength(0);
    container.exit(Object.assign(new Error('killed'), { exitCode: 137 }));
    await flush();
    expect(h.capacity.release).toHaveBeenCalledWith(LEASE);
    expect(h.storage.get('oomAt')).toBe(T0);
    // The recovered record is heavy, so this OOM is also the heavy one.
    expect(h.storage.get('oomHeavyAt')).toBe(T0);
    expect(await h.executor.oomHeavyAt()).toBe(T0);
  });

  it('destroys a running container whose lease is refused after the restart', async () => {
    const container = running();
    const capacity = new FakeCapacity();
    capacity.acquire.mockResolvedValue({ ok: false, reason: 'full' });
    const storage = new Map<string, unknown>([
      ['org', { orgId: ORG, placement: 0 }],
      ['executor', record],
    ]);
    const h = harness({ container, capacity, storage });
    await h.ready;
    expect(container.destroys).toEqual(['lease-refused']);
    expect(h.storage.has('executor')).toBe(false);
  });

  it('destroys a running container whose record names no placement, as unrecorded', async () => {
    const container = running();
    const { placement: _dropped, ...legacy } = record;
    const storage = new Map<string, unknown>([
      ['org', { orgId: ORG, placement: 0 }],
      ['executor', legacy],
    ]);
    const h = harness({ container, storage });
    await h.ready;
    expect(container.destroys).toEqual(['unrecorded']);
    expect(h.capacity.acquire).not.toHaveBeenCalled();
    expect(h.storage.has('executor')).toBe(false);
  });

  it('a retired instance restarting under a running container destroys it and releases its slot', async () => {
    const container = running();
    const storage = new Map<string, unknown>([
      ['org', { orgId: ORG, placement: 0 }],
      ['executor', record],
      ['retired', { to: 1 }],
    ]);
    const h = harness({ container, storage });
    await h.ready;
    expect(container.destroys).toEqual(['relocated']);
    expect(h.capacity.acquire).not.toHaveBeenCalled();
    expect(h.capacity.release).toHaveBeenCalledWith(LEASE);
    expect(await h.executor.pin(ORG, 0, 'light')).toMatchObject({ code: 'EXECUTOR_RELOCATED' });
  });

  it('destroys a running container with no record, since it would run uncounted', async () => {
    const container = running();
    const h = harness({ container });
    await h.ready;
    expect(container.destroys).toEqual(['unrecorded']);
    expect(h.capacity.acquire).not.toHaveBeenCalled();
  });

  it('a record with no running container is cleared and its slot released', async () => {
    const storage = new Map<string, unknown>([['executor', record]]);
    const h = harness({ storage });
    await h.ready;
    expect(h.storage.has('executor')).toBe(false);
    expect(h.capacity.release).toHaveBeenCalledWith(LEASE);
  });
});

describe('exits', () => {
  it('an OOM exit on a light container flags oomAt but not oomHeavyAt', async () => {
    const h = harness();
    await h.ready;
    await h.executor.pin(ORG, 0, 'light');
    h.container.exit(Object.assign(new Error('killed'), { exitCode: 137 }));
    await flush();
    expect(h.storage.has('oomAt')).toBe(true);
    expect(h.storage.has('oomHeavyAt')).toBe(false);
  });

  it('an OOM exit on a heavy container also sets oomHeavyAt', async () => {
    const h = harness();
    await h.ready;
    await h.executor.pin(ORG, 0, 'heavy');
    h.container.exit(Object.assign(new Error('killed'), { exitCode: 137 }));
    await flush();
    expect(h.storage.has('oomHeavyAt')).toBe(true);
  });

  it('4ab1a051.4: a failed oomHeavyAt put still deletes the executor record', async () => {
    const h = harness({ failPut: ['oomHeavyAt'] });
    await h.ready;
    await h.executor.pin(ORG, 0, 'heavy');
    expect(h.storage.has('executor')).toBe(true);
    h.container.exit(Object.assign(new Error('killed'), { exitCode: 137 }));
    await flush();
    expect(h.storage.has('oomAt')).toBe(true);
    expect(h.storage.has('executor')).toBe(false);
    expect(h.capacity.release).toHaveBeenCalledWith(LEASE);
  });

  it('2ec734de.2: a failed record delete on exit still releases the slot, and a restart clears the stale record', async () => {
    const h = harness({ failDelete: ['executor'] });
    await h.ready;
    await h.executor.pin(ORG, 0, 'light');
    h.container.exit();
    await flush();
    expect(h.capacity.release).toHaveBeenCalledWith(LEASE);
    expect(h.storage.has('executor')).toBe(true);
    // The Durable Object restarts over the same storage; the container is dead, so the record is not recovered as running.
    const restarted = harness({ storage: h.storage, container: h.container });
    await restarted.ready;
    expect(h.storage.has('executor')).toBe(false);
    expect(h.container.destroys).toHaveLength(0);
    expect(await restarted.executor.pin(ORG, 0, 'light')).toMatchObject({ ok: true });
    expect(h.container.starts).toHaveLength(2);
  });

  it('4ab1a051.5: a clean exit after a heavy OOM keeps oomHeavyAt for its window', async () => {
    const h = harness();
    await h.ready;
    await h.executor.pin(ORG, 0, 'heavy');
    h.container.exit(Object.assign(new Error('killed'), { exitCode: 137 }));
    await flush();
    const flagged = h.storage.get('oomHeavyAt');
    expect(flagged).toBeDefined();
    await h.executor.pin(ORG, 0, 'heavy');
    h.container.exit();
    await flush();
    expect(h.storage.get('oomHeavyAt')).toBe(flagged);
  });

  it('a clean exit releases the slot, and the next pin starts again', async () => {
    const h = harness();
    await h.ready;
    await h.executor.pin(ORG, 0, 'light');
    h.container.exit();
    await flush();
    expect(h.capacity.release).toHaveBeenCalledWith(LEASE);
    expect(h.storage.has('oomAt')).toBe(false);
    expect(h.storage.has('oomHeavyAt')).toBe(false);
    expect(await h.executor.pin(ORG, 0, 'light')).toMatchObject({ ok: true });
    expect(h.container.starts).toHaveLength(2);
  });

  it('isOomExit reads exit code 137 or an error naming OOM', () => {
    expect(isOomExit({ exitCode: 137 })).toBe(true);
    expect(isOomExit(new Error('container OOM killed'))).toBe(true);
    expect(isOomExit(new Error('Container exited with code 137'))).toBe(true);
    expect(isOomExit(new Error('out of memory'))).toBe(true);
    expect(isOomExit({ exitCode: 1 })).toBe(false);
    expect(isOomExit(new Error('exited with code 1370'))).toBe(false);
    expect(isOomExit(undefined)).toBe(false);
  });

  it('durationMs reads s, m, h and plain seconds, and refuses anything else', () => {
    expect(durationMs('90s')).toBe(90_000);
    expect(durationMs('2m')).toBe(120_000);
    expect(durationMs('1h')).toBe(3_600_000);
    expect(durationMs('45')).toBe(45_000);
    expect(() => durationMs('2 minutes')).toThrow();
  });
});

describe('relocation', () => {
  const MINUTE = 60_000;

  function report(h: Harness, at: number) {
    vi.setSystemTime(at);
    return h.executor.recordEgressUnreachable(ORG, 0);
  }

  it('three reports within 10 minutes relocate once; the instance retires and drains after the open stream', async () => {
    const h = harness();
    await h.ready;
    const stream = openStream();
    h.container.app = () => stream.response;
    await h.executor.pin(ORG, 0, 'light');
    const open = await h.executor.fetch(new Request('https://proxy/v1/command'));

    expect(await report(h, T0 + MINUTE)).toEqual({
      ok: true,
      count: 1,
      threshold: 3,
      relocated: false,
    });
    expect(await report(h, T0 + 2 * MINUTE)).toMatchObject({ count: 2, relocated: false });
    expect(h.issuer.relocate).not.toHaveBeenCalled();
    expect(await report(h, T0 + 9 * MINUTE)).toEqual({
      ok: true,
      count: 3,
      threshold: 3,
      relocated: true,
    });
    expect(h.issuer.relocate).toHaveBeenCalledTimes(1);
    expect(h.issuer.relocate).toHaveBeenCalledWith(ORG, 0);
    expect(h.storage.get('retired')).toEqual({ to: 1 });

    expect(await h.executor.pin(ORG, 0, 'light')).toEqual({
      ok: false,
      code: 'EXECUTOR_RELOCATED',
      reason: 'retired',
    });
    const next = await h.executor.fetch(new Request('https://proxy/v1/command'));
    expect(next.status).toBe(503);
    expect(await next.json()).toMatchObject({ code: 'EXECUTOR_RELOCATED' });

    // The request whose report caused the move ends with its own result line first.
    expect(h.container.destroys).toHaveLength(0);
    expect(h.capacity.release).not.toHaveBeenCalled();
    stream.close();
    expect(await open.text()).toBe('{"line":1}\n');
    await flush();
    expect(h.container.destroys).toEqual(['relocated']);
    expect(h.capacity.release).toHaveBeenCalledWith(LEASE);
    expect(h.capacity.release).toHaveBeenCalledTimes(1);

    // A later report on the retired instance asks the issuer nothing more.
    expect(await report(h, T0 + 10 * MINUTE)).toMatchObject({ relocated: true });
    expect(h.issuer.relocate).toHaveBeenCalledTimes(1);
  });

  it('two reports, then a third 11 minutes after the first, never relocate', async () => {
    const h = harness();
    await h.ready;
    await h.executor.pin(ORG, 0, 'light');
    await report(h, T0);
    await report(h, T0 + 2 * MINUTE);
    expect(await report(h, T0 + 11 * MINUTE)).toMatchObject({ count: 2, relocated: false });
    expect(h.storage.get('egressUnreachable')).toEqual([T0 + 2 * MINUTE, T0 + 11 * MINUTE]);
    expect(h.storage.get('egressUnreachableAt')).toBe(T0 + 11 * MINUTE);
    expect(h.issuer.relocate).not.toHaveBeenCalled();
    expect(UNREACHABLE_WINDOW_MS).toBe(10 * MINUTE);
  });

  it('a budget answer leaves the instance serving, and the pin flags the recent report', async () => {
    const h = harness();
    await h.ready;
    await h.executor.pin(ORG, 0, 'light');
    h.issuer.relocate.mockResolvedValue({ ok: false, reason: 'budget', placement: 0 });
    for (const minute of [1, 2, 3]) await report(h, T0 + minute * MINUTE);
    expect(h.issuer.relocate).toHaveBeenCalledTimes(1);
    expect(h.storage.has('retired')).toBe(false);
    expect(await h.executor.pin(ORG, 0, 'light')).toEqual({
      ok: true,
      size: 'light',
      egressUnreachableRecent: true,
    });
    const response = await h.executor.fetch(new Request('https://proxy/a'));
    expect(response.status).toBe(200);
    expect(h.container.destroys).toHaveLength(0);

    // Past the window the flag clears.
    vi.setSystemTime(T0 + 3 * MINUTE + UNREACHABLE_WINDOW_MS);
    expect(await h.executor.pin(ORG, 0, 'light')).toMatchObject({ egressUnreachableRecent: false });
  });

  it('a stale answer retires too, since another caller already moved the org', async () => {
    const h = harness();
    await h.ready;
    await h.executor.pin(ORG, 0, 'light');
    h.issuer.relocate.mockResolvedValue({ ok: false, reason: 'stale', placement: 1 });
    for (const minute of [1, 2]) await report(h, T0 + minute * MINUTE);
    expect(await report(h, T0 + 3 * MINUTE)).toMatchObject({ relocated: true });
    // Nothing was in flight, so the container stops and its slot goes at once.
    expect(h.container.destroys).toEqual(['relocated']);
    expect(h.capacity.release).toHaveBeenCalledWith(LEASE);
  });

  it('an issuer that throws or hangs leaves the org where it is', async () => {
    const h = harness();
    await h.ready;
    await h.executor.pin(ORG, 0, 'light');
    h.issuer.relocate.mockRejectedValueOnce(new Error('issuer down'));
    for (const minute of [1, 2]) await report(h, T0 + minute * MINUTE);
    expect(await report(h, T0 + 3 * MINUTE)).toMatchObject({ relocated: false });

    vi.useRealTimers();
    vi.useFakeTimers();
    vi.setSystemTime(T0 + 4 * MINUTE);
    h.issuer.relocate.mockImplementationOnce(() => new Promise<RelocateAnswer>(() => undefined));
    const pending = h.executor.recordEgressUnreachable(ORG, 0);
    await vi.advanceTimersByTimeAsync(COORDINATOR_TIMEOUT_MS + 1);
    expect(await pending).toMatchObject({ relocated: false });
    expect(h.storage.has('retired')).toBe(false);
    expect(await h.executor.pin(ORG, 0, 'light')).toMatchObject({ ok: true });
  });

  it('a report naming another placement or org is refused and counts nothing', async () => {
    const h = harness();
    await h.ready;
    await h.executor.pin(ORG, 0, 'light');
    expect(await h.executor.recordEgressUnreachable(ORG, 1)).toEqual({
      ok: false,
      reason: 'report-id-mismatch',
    });
    expect(await h.executor.recordEgressUnreachable('org-b', 0)).toMatchObject({ ok: false });
    expect(h.storage.has('egressUnreachable')).toBe(false);

    const shared = harness({ sameIdForEveryOrg: true });
    await shared.ready;
    await shared.executor.pin(ORG, 0, 'light');
    expect(await shared.executor.recordEgressUnreachable(ORG, 1)).toEqual({
      ok: false,
      reason: 'report-org-conflict',
    });
  });

  it('a retired instance whose renew answers not-held does not acquire again', async () => {
    const h = harness();
    await h.ready;
    const stream = openStream();
    h.container.app = () => stream.response;
    await h.executor.pin(ORG, 0, 'light');
    const open = await h.executor.fetch(new Request('https://proxy/v1/command'));
    for (const minute of [1, 2, 3]) await report(h, T0 + minute * MINUTE);
    h.capacity.acquire.mockClear();
    h.capacity.renew.mockResolvedValue('not-held');

    vi.setSystemTime(T0 + 4 * MINUTE);
    await h.executor.alarm();
    expect(h.capacity.renew).toHaveBeenCalledWith(LEASE);
    expect(h.capacity.acquire).not.toHaveBeenCalled();
    stream.close();
    await open.text();
    await flush();
    expect(h.container.destroys).toEqual(['relocated']);
    expect(h.capacity.acquire).not.toHaveBeenCalled();
  });

  it('the threshold is 3', () => {
    expect(UNREACHABLE_THRESHOLD).toBe(3);
  });
});
