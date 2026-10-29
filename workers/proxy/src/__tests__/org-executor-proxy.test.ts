/**
 * `OrgExecutor` (agent/plans/PLAN-executor-durable-object-policy.md box W1): the pin checks, proxying with in-flight counting, the `sleepAfter` alarm and the image-drift restart.
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

import { durationMs, type ExecutorRecord, RENEW_THROTTLE_MS } from '../org-executor';
import {
  flush,
  harness,
  IDLE_MS,
  IMAGE_V2,
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

describe('the pin', () => {
  it('refuses an org whose name does not derive this instance id', async () => {
    const h = harness();
    await h.ready;
    expect(await h.executor.pin('org-b', 0, 'light')).toEqual({
      ok: false,
      code: 'EXECUTOR_START_FAILED',
      reason: 'pin-id-mismatch',
    });
    expect(h.capacity.acquire).not.toHaveBeenCalled();
    expect(h.container.starts).toHaveLength(0);
  });

  it('refuses a second org once pinned', async () => {
    const h = harness({ sameIdForEveryOrg: true });
    await h.ready;
    expect(await h.executor.pin(ORG, 0, 'light')).toMatchObject({ ok: true });
    expect(await h.executor.pin('org-b', 0, 'light')).toEqual({
      ok: false,
      code: 'EXECUTOR_START_FAILED',
      reason: 'pin-org-conflict',
    });
    expect(h.container.starts).toHaveLength(1);
  });

  it('keeps the pinned org across a restart of the Durable Object', async () => {
    const storage = new Map<string, unknown>([['org', { orgId: ORG, placement: 0 }]]);
    const h = harness({ sameIdForEveryOrg: true, storage });
    await h.ready;
    expect(await h.executor.pin('org-b', 0, 'light')).toMatchObject({ reason: 'pin-org-conflict' });
  });

  it('refuses a placement whose name does not derive this instance id', async () => {
    const h = harness();
    await h.ready;
    expect(await h.executor.pin(ORG, 1, 'light')).toMatchObject({ reason: 'pin-id-mismatch' });
    expect(await h.executor.pin(ORG, -1, 'light')).toMatchObject({
      reason: 'pin-placement-invalid',
    });
    expect(await h.executor.pin(ORG, 1.5, 'light')).toMatchObject({
      reason: 'pin-placement-invalid',
    });
    expect(h.capacity.acquire).not.toHaveBeenCalled();
  });

  it('refuses a second placement of the same org once pinned', async () => {
    const h = harness({ sameIdForEveryOrg: true });
    await h.ready;
    expect(await h.executor.pin(ORG, 0, 'light')).toMatchObject({ ok: true });
    expect(await h.executor.pin(ORG, 1, 'light')).toMatchObject({ reason: 'pin-org-conflict' });
    expect(h.storage.get('org')).toEqual({ orgId: ORG, placement: 0 });
  });

  it('refuses an empty org and an unknown size', async () => {
    const h = harness();
    await h.ready;
    expect(await h.executor.pin('', 0, 'light')).toMatchObject({ reason: 'pin-org-invalid' });
    expect(await h.executor.pin(ORG, 0, 'huge' as never)).toMatchObject({
      reason: 'pin-size-invalid',
    });
  });
});

describe('proxying', () => {
  it('forwards to port 8080 and streams the body back untouched', async () => {
    const h = harness();
    await h.ready;
    let seen: Request | undefined;
    h.container.app = (request) => {
      seen = request;
      return new Response('{"line":1}\n{"line":2}\n', {
        status: 207,
        headers: { 'x-from': 'executor' },
      });
    };
    await h.executor.pin(ORG, 0, 'light');
    const response = await h.executor.fetch(
      new Request('https://proxy/v1/run', { method: 'POST', body: 'cmd' })
    );
    expect(seen?.method).toBe('POST');
    expect(new URL(seen?.url ?? '').pathname).toBe('/v1/run');
    expect(response.status).toBe(207);
    expect(response.headers.get('x-from')).toBe('executor');
    expect(await response.text()).toBe('{"line":1}\n{"line":2}\n');
  });

  it('re-addresses the forward to http: with the same path, query, method, headers and body', async () => {
    const h = harness();
    await h.ready;
    let seen: Request | undefined;
    let seenBody = '';
    h.container.app = async (request) => {
      seen = request;
      seenBody = await request.text();
      return new Response('done');
    };
    await h.executor.pin(ORG, 0, 'light');
    h.container.portUrls.length = 0;
    const response = await h.executor.fetch(
      new Request('https://executor.internal/v1/command?stream=1&x=a%20b', {
        method: 'POST',
        headers: { 'content-type': 'application/x-ndjson', 'x-trace': 't1' },
        body: '{"cmd":"up"}',
      })
    );
    expect(response.status).toBe(200);
    expect(await response.text()).toBe('done');
    expect(h.container.portUrls).toHaveLength(1);
    const forwarded = new URL(h.container.portUrls[0]);
    expect(forwarded.protocol).toBe('http:');
    expect(forwarded.host).toBe('executor.internal');
    expect(forwarded.pathname).toBe('/v1/command');
    expect(forwarded.search).toBe('?stream=1&x=a%20b');
    expect(seen?.method).toBe('POST');
    expect(seen?.headers.get('content-type')).toBe('application/x-ndjson');
    expect(seen?.headers.get('x-trace')).toBe('t1');
    expect(seenBody).toBe('{"cmd":"up"}');
  });

  it('logs the name and message of a failed forward and answers EXECUTOR_UNREACHABLE', async () => {
    const h = harness();
    await h.ready;
    h.container.app = () => {
      throw new RangeError('port went away');
    };
    await h.executor.pin(ORG, 0, 'light');
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    try {
      const response = await h.executor.fetch(
        new Request('https://executor.internal/v1/command', { method: 'POST', body: 'secret-body' })
      );
      expect(response.status).toBe(502);
      expect(await response.json()).toMatchObject({ code: 'EXECUTOR_UNREACHABLE' });
      expect(warn).toHaveBeenCalledWith('proxy: org executor forward failed', {
        stage: 'forward',
        name: 'RangeError',
        message: 'port went away',
      });
      expect(JSON.stringify(warn.mock.calls)).not.toContain('secret-body');
    } finally {
      warn.mockRestore();
    }
  });

  it('names the step that failed as a field: a storage error before the forward keeps the fixed alert string with stage touch', async () => {
    const h = harness();
    await h.ready;
    await h.executor.pin(ORG, 0, 'light');
    const state = (h.executor as unknown as { ctx: { storage: { setAlarm: () => Promise<void> } } })
      .ctx;
    state.storage.setAlarm = () => Promise.reject(new TypeError('alarm store down'));
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    try {
      const response = await h.executor.fetch(new Request('https://executor.internal/v1/command'));
      expect(response.status).toBe(502);
      expect(warn).toHaveBeenCalledWith('proxy: org executor forward failed', {
        stage: 'touch',
        name: 'TypeError',
        message: 'alarm store down',
      });
    } finally {
      warn.mockRestore();
    }
  });

  it('renews the lease at a request start at most once per 30 s', async () => {
    const h = harness();
    await h.ready;
    await h.executor.pin(ORG, 0, 'light');
    await (await h.executor.fetch(new Request('https://proxy/a'))).text();
    expect(h.capacity.renew).not.toHaveBeenCalled();
    vi.setSystemTime(T0 + RENEW_THROTTLE_MS);
    await (await h.executor.fetch(new Request('https://proxy/b'))).text();
    await (await h.executor.fetch(new Request('https://proxy/c'))).text();
    expect(h.capacity.renew).toHaveBeenCalledTimes(1);
  });

  it('re-acquires a lease the coordinator no longer holds', async () => {
    const h = harness();
    await h.ready;
    await h.executor.pin(ORG, 0, 'heavy');
    h.capacity.renew.mockResolvedValueOnce('not-held');
    vi.setSystemTime(T0 + RENEW_THROTTLE_MS);
    const response = await h.executor.fetch(new Request('https://proxy/a'));
    expect(response.status).toBe(200);
    expect(h.capacity.acquire).toHaveBeenLastCalledWith(LEASE, 'heavy');
  });

  it('a lost lease that cannot be re-acquired drains: in-flight requests finish, new ones get EXECUTOR_CAPACITY, then the container is destroyed', async () => {
    const h = harness();
    await h.ready;
    const stream = openStream();
    h.container.app = () => stream.response;
    await h.executor.pin(ORG, 0, 'light');
    const open = await h.executor.fetch(new Request('https://proxy/stream'));

    h.capacity.renew.mockResolvedValue('not-held');
    h.capacity.acquire.mockResolvedValue({ ok: false, reason: 'full' });
    vi.setSystemTime(T0 + RENEW_THROTTLE_MS);
    const refused = await h.executor.fetch(new Request('https://proxy/next'));
    expect(refused.status).toBe(503);
    expect(refused.headers.get('retry-after')).toBe('30');
    expect(await refused.json()).toMatchObject({ code: 'EXECUTOR_CAPACITY' });
    expect(h.container.destroys).toHaveLength(0);

    stream.close();
    expect(await open.text()).toBe('{"line":1}\n');
    await flush();
    expect(h.container.destroys).toEqual(['lease-lost']);
  });

  it('answers EXECUTOR_START_FAILED for a request with no running container', async () => {
    const h = harness();
    await h.ready;
    const response = await h.executor.fetch(new Request('https://proxy/a'));
    expect(response.status).toBe(503);
    expect(await response.json()).toMatchObject({ code: 'EXECUTOR_START_FAILED' });
  });
});

describe('sleepAfter', () => {
  it('is the literal 2m', () => {
    const h = harness();
    expect(h.executor.sleepAfter).toBe('2m');
    expect(durationMs(h.executor.sleepAfter)).toBe(IDLE_MS);
  });

  it('arms the alarm at lastActivity + sleepAfter on each request', async () => {
    const h = harness();
    await h.ready;
    await h.executor.pin(ORG, 0, 'light');
    expect(h.alarmAt()).toBe(T0 + IDLE_MS);
    vi.setSystemTime(T0 + 10_000);
    await (await h.executor.fetch(new Request('https://proxy/a'))).text();
    await flush();
    expect(h.alarmAt()).toBe(T0 + 10_000 + IDLE_MS);
  });

  it('does not destroy while a stream is open, and destroys and releases after 120 s idle', async () => {
    const h = harness();
    await h.ready;
    const stream = openStream();
    h.container.app = () => stream.response;
    await h.executor.pin(ORG, 0, 'light');
    const open = await h.executor.fetch(new Request('https://proxy/stream'));
    h.capacity.renew.mockClear();

    vi.setSystemTime(T0 + 10 * IDLE_MS);
    await h.executor.alarm();
    expect(h.container.destroys).toHaveLength(0);
    expect(h.capacity.release).not.toHaveBeenCalled();
    // With a stream open the alarm renews and re-arms, so the slot is held.
    expect(h.capacity.renew).toHaveBeenCalledWith(LEASE);
    expect(h.alarmAt()).toBe(T0 + 11 * IDLE_MS);

    stream.close();
    await open.text();
    await flush();
    const closedAt = T0 + 10 * IDLE_MS;

    vi.setSystemTime(closedAt + IDLE_MS - 1);
    await h.executor.alarm();
    expect(h.container.destroys).toHaveLength(0);
    expect(h.alarmAt()).toBe(closedAt + IDLE_MS);

    vi.setSystemTime(closedAt + IDLE_MS);
    await h.executor.alarm();
    expect(h.container.destroys).toEqual(['idle']);
    expect(h.capacity.release).toHaveBeenCalledWith(LEASE);
    expect(h.storage.has('executor')).toBe(false);

    // The next request starts a fresh container on a fresh lease.
    expect(await h.executor.pin(ORG, 0, 'light')).toMatchObject({ ok: true });
    expect(h.container.starts).toHaveLength(2);
    expect(h.capacity.acquire).toHaveBeenCalledTimes(2);
  });
});

describe('image drift', () => {
  it('restarts on the new image only at zero in flight', async () => {
    const h = harness();
    await h.ready;
    const stream = openStream();
    h.container.app = () => stream.response;
    await h.executor.pin(ORG, 0, 'heavy');
    const open = await h.executor.fetch(new Request('https://proxy/stream'));

    h.container.images = { executor: IMAGE_V2 };
    expect(await h.executor.pin(ORG, 0, 'light')).toEqual({
      ok: true,
      size: 'heavy',
      egressUnreachableRecent: false,
    });
    expect(h.container.starts).toHaveLength(1);
    expect(h.container.destroys).toHaveLength(0);

    stream.close();
    await open.text();
    await flush();
    expect(await h.executor.pin(ORG, 0, 'light')).toEqual({
      ok: true,
      size: 'heavy',
      egressUnreachableRecent: false,
    });
    expect(h.container.destroys).toEqual(['image-drift']);
    expect(h.container.starts).toHaveLength(2);
    expect(h.container.starts[1]).toMatchObject({ image: IMAGE_V2, instance: 'standard-1' });
    expect((h.storage.get('executor') as ExecutorRecord).image).toBe(IMAGE_V2);
    // The restart re-registers the intercept for the new container before it starts.
    expect(h.container.log.slice(-4)).toEqual(['destroy', 'intercept', 'start', 'monitor']);
    expect(h.capacity.release).not.toHaveBeenCalled();
  });
});
