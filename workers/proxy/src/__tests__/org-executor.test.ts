/**
 * `OrgExecutor` (agent/plans/PLAN-executor-durable-object-policy.md box W1): the start, env, readiness, proxying with in-flight counting, the `sleepAfter` alarm, the image-drift restart, recovery after a restart, and the pin checks.
 *
 * Relocation (agent/plans/PLAN-org-executor-connect-timeout-relocate.md box E6): the egress-unreachable count, the threshold call to the issuer, and the retired instance's refusal, lease and drain.
 *
 * `cloudflare:workers` exists only inside workerd, so `DurableObject` is replaced by a base class that keeps `ctx` and `env` as the real one does. `ctx.container` is a fake with the surface the class uses (start, running, monitor, destroy, getTcpPort, interceptOutboundHttp, images), recording each call in one ordered log. The coordinator and the issuer are fakes whose answers each test sets.
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

import type { AcquireAnswer, RenewAnswer } from '../capacity';
import { EXECUTOR_TOKEN_PLACEHOLDER } from '../egress';
import {
  ACCOUNT_EGRESS_HOST,
  COORDINATOR_TIMEOUT_MS,
  durationMs,
  type ExecutorRecord,
  executorEnv,
  isOomExit,
  OrgExecutor,
  type OrgExecutorEnv,
  READY_TIMEOUT_MS,
  RENEW_THROTTLE_MS,
  type RelocateAnswer,
} from '../org-executor';
import { executorName, UNREACHABLE_THRESHOLD, UNREACHABLE_WINDOW_MS } from '../placement';

const T0 = Date.UTC(2026, 9, 27, 12, 0, 0);
const ORG = 'org-a';
/** The executor name of ORG at placement 0: the Durable Object name and the lease key. */
const LEASE = 'org-a:p0';
const IMAGE_V1 = 'registry.example/executor:v1';
const IMAGE_V2 = 'registry.example/executor:v2';
const IDLE_MS = 120_000;

interface Deferred {
  promise: Promise<void>;
  resolve: () => void;
  reject: (error: unknown) => void;
}

function deferred(): Deferred {
  let resolve!: () => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<void>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  // A rejection nobody awaits yet must not fail the run.
  promise.catch(() => undefined);
  return { promise, resolve, reject };
}

function fakeId(name: string) {
  return {
    name,
    equals: (other: { name?: string }) => other.name === name,
    toString: () => `id:${name}`,
  };
}

/** The fake `ctx.container`. `health` and `app` answer the readiness poll and forwarded requests. */
class FakeContainer {
  running = false;
  images: Record<string, string> = { executor: IMAGE_V1 };
  log: string[] = [];
  starts: ContainerStartupOptions[] = [];
  intercepts: { host: string; binding: unknown }[] = [];
  monitors: Deferred[] = [];
  destroys: unknown[] = [];
  /** Every URL the port was fetched with, readiness polls included. */
  portUrls: string[] = [];
  health: () => Response | Promise<Response> = () => new Response('ok');
  app: (request: Request) => Response | Promise<Response> = () => new Response('from-app');

  start(options: ContainerStartupOptions): void {
    this.log.push('start');
    this.starts.push(options);
    this.running = true;
  }

  private currentMonitor(): Deferred {
    if (this.monitors.length === 0 || this.monitorsSettled.has(this.monitors.length - 1)) {
      this.monitors.push(deferred());
    }
    return this.monitors[this.monitors.length - 1];
  }

  private readonly monitorsSettled = new Set<number>();

  monitor(): Promise<void> {
    this.log.push('monitor');
    return this.currentMonitor().promise;
  }

  /** The running container exits; `error` makes `monitor()` reject. */
  exit(error?: unknown): void {
    this.running = false;
    const index = this.monitors.length - 1;
    this.monitorsSettled.add(index);
    if (error === undefined) this.monitors[index].resolve();
    else this.monitors[index].reject(error);
  }

  destroy(reason?: unknown): Promise<void> {
    this.log.push('destroy');
    this.destroys.push(reason);
    this.exit();
    return Promise.resolve();
  }

  interceptOutboundHttp(host: string, binding: unknown): Promise<void> {
    this.log.push('intercept');
    this.intercepts.push({ host, binding });
    return Promise.resolve();
  }

  getTcpPort(port: number) {
    expect(port).toBe(8080);
    return {
      fetch: (input: Request | string): Promise<Response> => {
        const request = typeof input === 'string' ? new Request(input) : input;
        this.portUrls.push(request.url);
        // A container TCP port speaks plain HTTP, and workerd throws on an `https:` URL there.
        if (new URL(request.url).protocol !== 'http:') {
          return Promise.reject(new TypeError('container port fetch needs an http: URL'));
        }
        if (new URL(request.url).pathname === '/v1/health') return Promise.resolve(this.health());
        return Promise.resolve(this.app(request));
      },
    };
  }
}

/** The issuer's `relocate`, whose answer each test sets. */
class FakeIssuer {
  relocate = vi.fn(
    async (_orgId: string, fromPlacement: number): Promise<RelocateAnswer> => ({
      ok: true,
      placement: fromPlacement + 1,
    })
  );
}

class FakeCapacity {
  acquire = vi.fn(async (_orgId: string, _size: string): Promise<AcquireAnswer> => ({ ok: true }));
  renew = vi.fn(async (_orgId: string): Promise<RenewAnswer> => 'held');
  release = vi.fn(async (_orgId: string): Promise<void> => undefined);
}

interface Harness {
  executor: OrgExecutor;
  container: FakeContainer;
  capacity: FakeCapacity;
  issuer: FakeIssuer;
  storage: Map<string, unknown>;
  alarmAt: () => number | null;
  egress: ReturnType<typeof vi.fn>;
  ready: Promise<unknown>;
}

interface HarnessOptions {
  name?: string;
  /** The placement this instance is named for; 0 when unset. */
  placement?: number;
  container?: FakeContainer;
  capacity?: FakeCapacity;
  storage?: Map<string, unknown>;
  /** Maps every org to this instance's id, so the conflict check is reached past the id check. */
  sameIdForEveryOrg?: boolean;
  /** Storage keys whose `put` rejects. */
  failPut?: string[];
  /** Storage keys whose `delete` rejects. */
  failDelete?: string[];
}

function harness(options: HarnessOptions = {}): Harness {
  const name = options.name ?? ORG;
  const container = options.container ?? new FakeContainer();
  const capacity = options.capacity ?? new FakeCapacity();
  const issuer = new FakeIssuer();
  const id = executorName(name, options.placement ?? 0);
  const storage = options.storage ?? new Map<string, unknown>();
  let alarm: number | null = null;
  let ready: Promise<unknown> = Promise.resolve();
  const egress = vi.fn((options: { props: unknown }) => ({
    entrypoint: 'AccountEgress',
    ...options,
  }));
  const ctx = {
    id: fakeId(id),
    container,
    exports: { AccountEgress: egress },
    storage: {
      get: (key: string) => Promise.resolve(storage.get(key)),
      put: (key: string, value: unknown) => {
        if (options.failPut?.includes(key)) return Promise.reject(new Error('put failed'));
        storage.set(key, structuredClone(value));
        return Promise.resolve();
      },
      delete: (key: string) => {
        if (options.failDelete?.includes(key)) return Promise.reject(new Error('delete failed'));
        return Promise.resolve(storage.delete(key));
      },
      setAlarm: (at: number | Date) => {
        alarm = typeof at === 'number' ? at : at.getTime();
        return Promise.resolve();
      },
      getAlarm: () => Promise.resolve(alarm),
      deleteAlarm: () => {
        alarm = null;
        return Promise.resolve();
      },
    },
    blockConcurrencyWhile: (callback: () => Promise<unknown>) => {
      ready = callback();
      return ready;
    },
  } as unknown as DurableObjectState;
  const env: OrgExecutorEnv = {
    ORG_EXECUTOR: {
      idFromName: (executor: string) =>
        fakeId(options.sameIdForEveryOrg ? id : executor) as unknown as DurableObjectId,
    },
    EXECUTOR_CAPACITY: {
      idFromName: (n: string) => fakeId(n),
      get: () => capacity,
    } as unknown as OrgExecutorEnv['EXECUTOR_CAPACITY'],
    ISSUER: issuer,
    REGION: 'us',
  };
  const executor = new OrgExecutor(ctx, env);
  return { executor, container, capacity, issuer, storage, alarmAt: () => alarm, egress, ready };
}

/** A container response whose body stays open until `close` is called. */
function openStream(): { response: Response; close: () => void } {
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c;
    },
  });
  controller.enqueue(new TextEncoder().encode('{"line":1}\n'));
  return {
    response: new Response(body, { headers: { 'content-type': 'application/x-ndjson' } }),
    close: () => controller.close(),
  };
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

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
        name: 'RangeError',
        message: 'port went away',
      });
      expect(JSON.stringify(warn.mock.calls)).not.toContain('secret-body');
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
