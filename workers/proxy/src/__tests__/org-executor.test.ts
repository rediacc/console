/**
 * `OrgExecutor` (agent/plans/PLAN-executor-durable-object-policy.md box W1): the start, env, readiness, proxying with in-flight counting, the `sleepAfter` alarm, the image-drift restart, recovery after a restart, and the pin checks.
 *
 * `cloudflare:workers` exists only inside workerd, so `DurableObject` is replaced by a base class that keeps `ctx` and `env` as the real one does. `ctx.container` is a fake with the surface the class uses (start, running, monitor, destroy, getTcpPort, interceptOutboundHttp, images), recording each call in one ordered log. The coordinator is a fake stub whose answers each test sets.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('cloudflare:workers', () => ({
  DurableObject: class {
    constructor(
      protected ctx: unknown,
      protected env: unknown
    ) {}
  },
}));

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
} from '../org-executor';

const T0 = Date.UTC(2026, 9, 27, 12, 0, 0);
const ORG = 'org-a';
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
        if (new URL(request.url).pathname === '/v1/health') return Promise.resolve(this.health());
        return Promise.resolve(this.app(request));
      },
    };
  }
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
  storage: Map<string, unknown>;
  alarmAt: () => number | null;
  egress: ReturnType<typeof vi.fn>;
  ready: Promise<unknown>;
}

interface HarnessOptions {
  name?: string;
  container?: FakeContainer;
  capacity?: FakeCapacity;
  storage?: Map<string, unknown>;
  /** Maps every org to this instance's id, so the conflict check is reached past the id check. */
  sameIdForEveryOrg?: boolean;
}

function harness(options: HarnessOptions = {}): Harness {
  const name = options.name ?? ORG;
  const container = options.container ?? new FakeContainer();
  const capacity = options.capacity ?? new FakeCapacity();
  const storage = options.storage ?? new Map<string, unknown>();
  let alarm: number | null = null;
  let ready: Promise<unknown> = Promise.resolve();
  const egress = vi.fn((options: { props: unknown }) => ({
    entrypoint: 'AccountEgress',
    ...options,
  }));
  const ctx = {
    id: fakeId(name),
    container,
    exports: { AccountEgress: egress },
    storage: {
      get: (key: string) => Promise.resolve(storage.get(key)),
      put: (key: string, value: unknown) => {
        storage.set(key, structuredClone(value));
        return Promise.resolve();
      },
      delete: (key: string) => Promise.resolve(storage.delete(key)),
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
      idFromName: (org: string) =>
        fakeId(options.sameIdForEveryOrg ? name : org) as unknown as DurableObjectId,
    },
    EXECUTOR_CAPACITY: {
      idFromName: (n: string) => fakeId(n),
      get: () => capacity,
    } as unknown as OrgExecutorEnv['EXECUTOR_CAPACITY'],
    REGION: 'us',
  };
  const executor = new OrgExecutor(ctx, env);
  return { executor, container, capacity, storage, alarmAt: () => alarm, egress, ready };
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
    expect(await h.executor.pin(ORG, 'light')).toEqual({ ok: true, size: 'light' });
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
    await h.executor.pin(ORG, 'light');
    expect(h.container.starts[0]).toMatchObject({
      image: IMAGE_V1,
      enableInternet: true,
      instance: { vcpu: 0.25, memoryMib: 1024, diskMb: 4000 },
    });
    expect(h.capacity.acquire).toHaveBeenCalledWith(ORG, 'light');
    expect(h.storage.get('executor')).toEqual({
      orgId: ORG,
      size: 'light',
      image: IMAGE_V1,
      startedAt: T0,
    });

    const heavy = harness({ name: 'org-h' });
    await heavy.ready;
    expect(await heavy.executor.pin('org-h', 'heavy')).toEqual({ ok: true, size: 'heavy' });
    expect(heavy.container.starts[0]).toMatchObject({ image: IMAGE_V1, instance: 'standard-1' });
  });

  it('registers the intercept before start, with props naming this org and this instance', async () => {
    const h = harness();
    await h.ready;
    await h.executor.pin(ORG, 'light');
    expect(h.container.log.slice(0, 3)).toEqual(['intercept', 'start', 'monitor']);
    expect(h.container.intercepts[0].host).toBe('account.internal');
    expect(h.egress).toHaveBeenCalledWith({ props: { orgId: ORG, containerId: `id:${ORG}` } });
  });

  it('a running container is not started again, and keeps its size', async () => {
    const h = harness();
    await h.ready;
    await h.executor.pin(ORG, 'light');
    expect(await h.executor.pin(ORG, 'heavy')).toEqual({ ok: true, size: 'light' });
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
    const answer = await h.executor.pin(ORG, 'light');
    expect(answer).toMatchObject({ ok: false, code: 'EXECUTOR_START_FAILED' });
    expect(h.capacity.release).toHaveBeenCalledWith(ORG);
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
    const pending = h.executor.pin(ORG, 'light');
    await vi.advanceTimersByTimeAsync(READY_TIMEOUT_MS + 500);
    expect(await pending).toMatchObject({
      ok: false,
      code: 'EXECUTOR_START_FAILED',
      reason: 'not-ready',
    });
    expect(h.container.destroys).toHaveLength(1);
    expect(h.capacity.release).toHaveBeenCalledWith(ORG);
  });

  it('a full or heavy-full coordinator answers EXECUTOR_CAPACITY and starts nothing', async () => {
    const h = harness();
    await h.ready;
    h.capacity.acquire.mockResolvedValueOnce({ ok: false, reason: 'full' });
    expect(await h.executor.pin(ORG, 'light')).toEqual({
      ok: false,
      code: 'EXECUTOR_CAPACITY',
      reason: 'full',
    });
    h.capacity.acquire.mockResolvedValueOnce({ ok: false, reason: 'heavy-full' });
    expect(await h.executor.pin(ORG, 'heavy')).toMatchObject({
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
    expect(await h.executor.pin(ORG, 'light')).toMatchObject({
      ok: false,
      code: 'EXECUTOR_START_FAILED',
      reason: 'coordinator-failed',
    });

    vi.useRealTimers();
    vi.useFakeTimers();
    h.capacity.acquire.mockImplementationOnce(() => new Promise<AcquireAnswer>(() => undefined));
    const pending = h.executor.pin(ORG, 'light');
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
    expect(await h.executor.pin(ORG, 'light')).toMatchObject({ code: 'EXECUTOR_START_FAILED' });
    expect(h.container.starts).toHaveLength(0);
    expect(h.capacity.release).toHaveBeenCalledWith(ORG);
  });
});

describe('the pin', () => {
  it('refuses an org whose name does not derive this instance id', async () => {
    const h = harness();
    await h.ready;
    expect(await h.executor.pin('org-b', 'light')).toEqual({
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
    expect(await h.executor.pin(ORG, 'light')).toMatchObject({ ok: true });
    expect(await h.executor.pin('org-b', 'light')).toEqual({
      ok: false,
      code: 'EXECUTOR_START_FAILED',
      reason: 'pin-org-conflict',
    });
    expect(h.container.starts).toHaveLength(1);
  });

  it('keeps the pinned org across a restart of the Durable Object', async () => {
    const storage = new Map<string, unknown>([['org', ORG]]);
    const h = harness({ sameIdForEveryOrg: true, storage });
    await h.ready;
    expect(await h.executor.pin('org-b', 'light')).toMatchObject({ reason: 'pin-org-conflict' });
  });

  it('refuses an empty org and an unknown size', async () => {
    const h = harness();
    await h.ready;
    expect(await h.executor.pin('', 'light')).toMatchObject({ reason: 'pin-org-invalid' });
    expect(await h.executor.pin(ORG, 'huge' as never)).toMatchObject({
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
    await h.executor.pin(ORG, 'light');
    const response = await h.executor.fetch(
      new Request('https://proxy/v1/run', { method: 'POST', body: 'cmd' })
    );
    expect(seen?.method).toBe('POST');
    expect(new URL(seen?.url ?? '').pathname).toBe('/v1/run');
    expect(response.status).toBe(207);
    expect(response.headers.get('x-from')).toBe('executor');
    expect(await response.text()).toBe('{"line":1}\n{"line":2}\n');
  });

  it('renews the lease at a request start at most once per 30 s', async () => {
    const h = harness();
    await h.ready;
    await h.executor.pin(ORG, 'light');
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
    await h.executor.pin(ORG, 'heavy');
    h.capacity.renew.mockResolvedValueOnce('not-held');
    vi.setSystemTime(T0 + RENEW_THROTTLE_MS);
    const response = await h.executor.fetch(new Request('https://proxy/a'));
    expect(response.status).toBe(200);
    expect(h.capacity.acquire).toHaveBeenLastCalledWith(ORG, 'heavy');
  });

  it('a lost lease that cannot be re-acquired drains: in-flight requests finish, new ones get EXECUTOR_CAPACITY, then the container is destroyed', async () => {
    const h = harness();
    await h.ready;
    const stream = openStream();
    h.container.app = () => stream.response;
    await h.executor.pin(ORG, 'light');
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
    await h.executor.pin(ORG, 'light');
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
    await h.executor.pin(ORG, 'light');
    const open = await h.executor.fetch(new Request('https://proxy/stream'));
    h.capacity.renew.mockClear();

    vi.setSystemTime(T0 + 10 * IDLE_MS);
    await h.executor.alarm();
    expect(h.container.destroys).toHaveLength(0);
    expect(h.capacity.release).not.toHaveBeenCalled();
    // With a stream open the alarm renews and re-arms, so the slot is held.
    expect(h.capacity.renew).toHaveBeenCalledWith(ORG);
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
    expect(h.capacity.release).toHaveBeenCalledWith(ORG);
    expect(h.storage.has('executor')).toBe(false);

    // The next request starts a fresh container on a fresh lease.
    expect(await h.executor.pin(ORG, 'light')).toMatchObject({ ok: true });
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
    await h.executor.pin(ORG, 'heavy');
    const open = await h.executor.fetch(new Request('https://proxy/stream'));

    h.container.images = { executor: IMAGE_V2 };
    expect(await h.executor.pin(ORG, 'light')).toEqual({ ok: true, size: 'heavy' });
    expect(h.container.starts).toHaveLength(1);
    expect(h.container.destroys).toHaveLength(0);

    stream.close();
    await open.text();
    await flush();
    expect(await h.executor.pin(ORG, 'light')).toEqual({ ok: true, size: 'heavy' });
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
      ['org', ORG],
      ['executor', record],
    ]);
    const h = harness({ container, storage });
    await h.ready;
    expect(h.capacity.acquire).toHaveBeenCalledWith(ORG, 'heavy');
    expect(container.log).toContain('monitor');
    expect(container.log).toContain('intercept');
    expect(h.egress).toHaveBeenCalledWith({ props: { orgId: ORG, containerId: `id:${ORG}` } });
    expect(container.destroys).toHaveLength(0);
    expect(h.alarmAt()).toBe(T0 + IDLE_MS);

    // It serves without a new start, and an exit seen by the re-attached monitor releases the slot.
    expect(await h.executor.pin(ORG, 'light')).toEqual({ ok: true, size: 'heavy' });
    expect(container.starts).toHaveLength(0);
    container.exit(Object.assign(new Error('killed'), { exitCode: 137 }));
    await flush();
    expect(h.capacity.release).toHaveBeenCalledWith(ORG);
    expect(h.storage.get('oomAt')).toBe(T0);
  });

  it('destroys a running container whose lease is refused after the restart', async () => {
    const container = running();
    const capacity = new FakeCapacity();
    capacity.acquire.mockResolvedValue({ ok: false, reason: 'full' });
    const storage = new Map<string, unknown>([
      ['org', ORG],
      ['executor', record],
    ]);
    const h = harness({ container, capacity, storage });
    await h.ready;
    expect(container.destroys).toEqual(['lease-refused']);
    expect(h.storage.has('executor')).toBe(false);
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
    expect(h.capacity.release).toHaveBeenCalledWith(ORG);
  });
});

describe('exits', () => {
  it('a clean exit releases the slot, and the next pin starts again', async () => {
    const h = harness();
    await h.ready;
    await h.executor.pin(ORG, 'light');
    h.container.exit();
    await flush();
    expect(h.capacity.release).toHaveBeenCalledWith(ORG);
    expect(h.storage.has('oomAt')).toBe(false);
    expect(await h.executor.pin(ORG, 'light')).toMatchObject({ ok: true });
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
