/**
 * `OrgExecutor` (agent/plans/PLAN-executor-durable-object-policy.md box W1): the start, env and readiness. The pin, proxying, `sleepAfter` and image drift are in org-executor-proxy.test.ts; recovery, exits and relocation in org-executor-lifecycle.test.ts.
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

import type { AcquireAnswer } from '../capacity';
import { EXECUTOR_TOKEN_PLACEHOLDER } from '../egress';
import {
  ACCOUNT_EGRESS_HOST,
  COORDINATOR_TIMEOUT_MS,
  type ExecutorRecord,
  executorEnv,
  READY_TIMEOUT_MS,
} from '../org-executor';
import { flush, harness, IMAGE_V1, IMAGE_V2, LEASE, ORG, T0 } from './helpers/org-executor-harness';

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(T0);
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('start', () => {
  it('boots the container with exactly the four env names and no issued token', async () => {
    const h = harness();
    await h.ready;
    expect(await h.executor.pin(ORG, 0, 'light')).toEqual({
      ok: true,
      size: 'light',
      egressUnreachableRecent: false,
    });
    const env = h.container.starts[0].env ?? {};
    expect(Object.keys(env).sort((a, b) => a.localeCompare(b))).toEqual([
      'REDIACC_ACCOUNT_SERVER',
      'REDIACC_EXECUTOR_ORG_ID',
      'REDIACC_REGION',
      'REDIACC_TOKEN',
    ]);
    expect(env).toEqual({
      REDIACC_TOKEN: EXECUTOR_TOKEN_PLACEHOLDER,
      REDIACC_ACCOUNT_SERVER: `http://${ACCOUNT_EGRESS_HOST}`,
      REDIACC_REGION: 'us',
      REDIACC_EXECUTOR_ORG_ID: ORG,
    });
    expect(JSON.stringify(env)).not.toMatch(/rdt_/);
    expect(executorEnv({}, ORG).REDIACC_REGION).toBe('eu');
    expect(executorEnv({ REGION: '' }, ORG).REDIACC_REGION).toBe('eu');
  });

  it('starts with the image from images.executor, enableInternet true, and the size class instance', async () => {
    const h = harness();
    await h.ready;
    await h.executor.pin(ORG, 0, 'light');
    expect(h.container.starts[0]).toMatchObject({
      image: IMAGE_V1,
      enableInternet: true,
      instance: { vcpu: 0.25, memoryMib: 1024, diskMb: 4000 },
    });
    expect(h.capacity.acquire).toHaveBeenCalledWith(LEASE, 'light');
    expect(h.storage.get('executor')).toEqual({
      orgId: ORG,
      placement: 0,
      size: 'light',
      image: IMAGE_V1,
      startedAt: T0,
    });

    const heavy = harness({ name: 'org-h' });
    await heavy.ready;
    expect(await heavy.executor.pin('org-h', 0, 'heavy')).toEqual({
      ok: true,
      size: 'heavy',
      egressUnreachableRecent: false,
    });
    expect(heavy.container.starts[0]).toMatchObject({ image: IMAGE_V1, instance: 'standard-1' });
  });

  it('registers the intercept before start, with props naming this org and this instance', async () => {
    const h = harness();
    await h.ready;
    await h.executor.pin(ORG, 0, 'light');
    expect(h.container.log.slice(0, 3)).toEqual(['intercept', 'start', 'monitor']);
    expect(h.container.intercepts[0].host).toBe('account.internal');
    expect(h.egress).toHaveBeenCalledWith({
      props: { orgId: ORG, placement: 0, containerId: `id:${LEASE}` },
    });
  });

  it('a running container is not started again, and keeps its size', async () => {
    const h = harness();
    await h.ready;
    await h.executor.pin(ORG, 0, 'light');
    expect(await h.executor.pin(ORG, 0, 'heavy')).toEqual({
      ok: true,
      size: 'light',
      egressUnreachableRecent: false,
    });
    expect(h.container.starts).toHaveLength(1);
    expect(h.capacity.acquire).toHaveBeenCalledTimes(1);
  });

  it('a monitor() rejection during readiness is EXECUTOR_START_FAILED and releases the lease', async () => {
    const h = harness();
    await h.ready;
    h.container.health = () => {
      h.container.exit(Object.assign(new Error('exited'), { exitCode: 1 }));
      return new Response('booting', { status: 503 });
    };
    const answer = await h.executor.pin(ORG, 0, 'light');
    expect(answer).toMatchObject({ ok: false, code: 'EXECUTOR_START_FAILED' });
    expect(h.capacity.release).toHaveBeenCalledWith(LEASE);
    expect(h.storage.has('executor')).toBe(false);
    // Nothing is served from a container that never became ready.
    const response = await h.executor.fetch(new Request('https://proxy/v1/run'));
    expect(response.status).toBe(503);
    expect(await response.json()).toMatchObject({ code: 'EXECUTOR_START_FAILED' });
  });

  it('a container that never answers its health route fails the start after the readiness window', async () => {
    vi.useRealTimers();
    vi.useFakeTimers();
    vi.setSystemTime(T0);
    const h = harness();
    await h.ready;
    h.container.health = () => new Response('booting', { status: 503 });
    const pending = h.executor.pin(ORG, 0, 'light');
    await vi.advanceTimersByTimeAsync(READY_TIMEOUT_MS + 500);
    expect(await pending).toMatchObject({
      ok: false,
      code: 'EXECUTOR_START_FAILED',
      reason: 'not-ready',
    });
    expect(h.container.destroys).toHaveLength(1);
    expect(h.capacity.release).toHaveBeenCalledWith(LEASE);
  });

  it('a full or heavy-full coordinator answers EXECUTOR_CAPACITY and starts nothing', async () => {
    const h = harness();
    await h.ready;
    h.capacity.acquire.mockResolvedValueOnce({ ok: false, reason: 'full' });
    expect(await h.executor.pin(ORG, 0, 'light')).toEqual({
      ok: false,
      code: 'EXECUTOR_CAPACITY',
      reason: 'full',
    });
    h.capacity.acquire.mockResolvedValueOnce({ ok: false, reason: 'heavy-full' });
    expect(await h.executor.pin(ORG, 0, 'heavy')).toMatchObject({
      code: 'EXECUTOR_CAPACITY',
      reason: 'heavy-full',
    });
    expect(h.container.starts).toHaveLength(0);
    expect(h.container.intercepts).toHaveLength(0);
  });

  it('a coordinator that throws or times out fails closed: EXECUTOR_START_FAILED and no start', async () => {
    const h = harness();
    await h.ready;
    h.capacity.acquire.mockRejectedValueOnce(new Error('coordinator down'));
    expect(await h.executor.pin(ORG, 0, 'light')).toMatchObject({
      ok: false,
      code: 'EXECUTOR_START_FAILED',
      reason: 'coordinator-failed',
    });

    vi.useRealTimers();
    vi.useFakeTimers();
    h.capacity.acquire.mockImplementationOnce(() => new Promise<AcquireAnswer>(() => undefined));
    const pending = h.executor.pin(ORG, 0, 'light');
    await vi.advanceTimersByTimeAsync(COORDINATOR_TIMEOUT_MS + 1);
    expect(await pending).toMatchObject({
      code: 'EXECUTOR_START_FAILED',
      reason: 'coordinator-failed',
    });
    expect(h.container.starts).toHaveLength(0);
  });

  it('a missing egress entrypoint fails the start rather than running the container without its intercept', async () => {
    const h = harness();
    await h.ready;
    h.egress.mockImplementation(() => {
      throw new Error('ctx.exports.AccountEgress is undefined');
    });
    expect(await h.executor.pin(ORG, 0, 'light')).toMatchObject({ code: 'EXECUTOR_START_FAILED' });
    expect(h.container.starts).toHaveLength(0);
    expect(h.capacity.release).toHaveBeenCalledWith(LEASE);
  });
});

describe('review 5acbb97d', () => {
  it('5acbb97d.1: two concurrent pins with no container start exactly one container on one lease', async () => {
    const h = harness();
    await h.ready;
    const answers = await Promise.all([
      h.executor.pin(ORG, 0, 'light'),
      h.executor.pin(ORG, 0, 'light'),
    ]);
    expect(answers).toEqual([
      { ok: true, size: 'light', egressUnreachableRecent: false },
      { ok: true, size: 'light', egressUnreachableRecent: false },
    ]);
    expect(h.container.starts).toHaveLength(1);
    expect(h.capacity.acquire).toHaveBeenCalledTimes(1);
    expect(h.container.destroys).toHaveLength(0);
  });

  it('5acbb97d.1: three concurrent pins still start exactly one container', async () => {
    const h = harness();
    await h.ready;
    await Promise.all([1, 2, 3].map(() => h.executor.pin(ORG, 0, 'light')));
    expect(h.container.starts).toHaveLength(1);
    expect(h.container.destroys).toHaveLength(0);
  });

  it('5acbb97d.2: an image-drift restart the coordinator refuses keeps the old container serving', async () => {
    const h = harness();
    await h.ready;
    await h.executor.pin(ORG, 0, 'light');
    h.container.images = { executor: IMAGE_V2 };
    h.capacity.acquire.mockResolvedValue({ ok: false, reason: 'full' });
    expect(await h.executor.pin(ORG, 0, 'light')).toEqual({
      ok: true,
      size: 'light',
      egressUnreachableRecent: false,
    });
    expect(h.container.destroys).toHaveLength(0);
    expect(h.container.running).toBe(true);
    const response = await h.executor.fetch(new Request('https://proxy/a'));
    expect(response.status).toBe(200);
    expect(await response.text()).toBe('from-app');
  });

  it('ccd9a210.1: an image-drift restart takes one lease, so a refusal after the stop cannot leave no container', async () => {
    const h = harness();
    await h.ready;
    await h.executor.pin(ORG, 0, 'light');
    h.container.images = { executor: IMAGE_V2 };
    h.capacity.acquire.mockClear();
    h.capacity.acquire
      .mockResolvedValueOnce({ ok: true })
      .mockResolvedValue({ ok: false, reason: 'full' });
    expect(await h.executor.pin(ORG, 0, 'light')).toEqual({
      ok: true,
      size: 'light',
      egressUnreachableRecent: false,
    });
    expect(h.capacity.acquire).toHaveBeenCalledTimes(1);
    expect(h.container.destroys).toEqual(['image-drift']);
    expect(h.container.running).toBe(true);
    expect((h.storage.get('executor') as ExecutorRecord).image).toBe(IMAGE_V2);
  });

  it('2ec734de.1: a restart whose image vanishes after the lease releases that lease', async () => {
    const h = harness();
    await h.ready;
    await h.executor.pin(ORG, 0, 'light');
    h.container.images = { executor: IMAGE_V2 };
    h.capacity.release.mockClear();
    h.capacity.acquire.mockImplementationOnce(() => {
      h.container.images = {};
      return Promise.resolve({ ok: true });
    });
    expect(await h.executor.pin(ORG, 0, 'light')).toMatchObject({
      code: 'EXECUTOR_START_FAILED',
    });
    expect(h.capacity.release).toHaveBeenCalledTimes(1);
    expect(h.capacity.release).toHaveBeenCalledWith(LEASE);
  });

  it('5acbb97d.3: a monitor() rejection during readiness releases the lease exactly once', async () => {
    const h = harness();
    await h.ready;
    h.container.health = () => {
      h.container.exit(Object.assign(new Error('exited'), { exitCode: 1 }));
      return new Response('booting', { status: 503 });
    };
    expect(await h.executor.pin(ORG, 0, 'light')).toMatchObject({ code: 'EXECUTOR_START_FAILED' });
    await flush();
    expect(h.capacity.release).toHaveBeenCalledTimes(1);
  });

  it('5acbb97d.4: a version with no images.executor does not destroy a running container', async () => {
    const h = harness();
    await h.ready;
    await h.executor.pin(ORG, 0, 'light');
    h.container.images = {};
    expect(await h.executor.pin(ORG, 0, 'light')).toEqual({
      ok: true,
      size: 'light',
      egressUnreachableRecent: false,
    });
    expect(h.container.destroys).toHaveLength(0);
    expect(h.container.starts).toHaveLength(1);
  });
});
