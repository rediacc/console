/**
 * The shared fakes of the `OrgExecutor` suites (src/__tests__/org-executor*.test.ts): the fake container, coordinator and issuer, and the harness that builds an instance on them.
 *
 * `ctx.container` is a fake with the surface the class uses (start, running, monitor, destroy, getTcpPort, interceptOutboundHttp, images), recording each call in one ordered log. The coordinator and the issuer are fakes whose answers each test sets. Each suite mocks `cloudflare:workers` itself, before it imports this module.
 *
 * The reachability probe (src/reachability.ts) connects through `cloudflare:sockets`, which vitest aliases to src/__tests__/cloudflare-sockets-stub.ts. Each harness installs a `connect` whose sockets greet with an SSH banner unless `banner` says otherwise, and counts the connects in `probes`.
 */

import { expect, vi } from 'vitest';
import type { AcquireAnswer, RenewAnswer } from '../../capacity';
import { OrgExecutor, type OrgExecutorEnv, type RelocateAnswer } from '../../org-executor';
import { executorName } from '../../placement';
import { fakeSocket, type ScriptedRead, setConnect } from '../cloudflare-sockets-stub';

export const T0 = Date.UTC(2026, 9, 27, 12, 0, 0);
export const ORG = 'org-a';
/** The executor name of ORG at placement 0: the Durable Object name and the lease key. */
export const LEASE = 'org-a:p0';
export const IMAGE_V1 = 'registry.example/executor:v1';
export const IMAGE_V2 = 'registry.example/executor:v2';
export const IDLE_MS = 120_000;

export interface Deferred {
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
export class FakeContainer {
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

export class FakeCapacity {
  acquire = vi.fn(async (_orgId: string, _size: string): Promise<AcquireAnswer> => ({ ok: true }));
  renew = vi.fn(async (_orgId: string): Promise<RenewAnswer> => 'held');
  release = vi.fn(async (_orgId: string): Promise<void> => undefined);
}

export interface Harness {
  executor: OrgExecutor;
  container: FakeContainer;
  capacity: FakeCapacity;
  issuer: FakeIssuer;
  storage: Map<string, unknown>;
  alarmAt: () => number | null;
  egress: ReturnType<typeof vi.fn>;
  ready: Promise<unknown>;
  /** Every address the reachability probe connected to. */
  probes: SocketAddress[];
  /** Change what the next probe sockets answer. */
  setBanner: (script: ScriptedRead[]) => void;
}

export interface HarnessOptions {
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
  /** What each probe socket reads; an SSH banner when unset. */
  banner?: ScriptedRead[];
}

export function harness(options: HarnessOptions = {}): Harness {
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
  const probes: SocketAddress[] = [];
  let banner: ScriptedRead[] = options.banner ?? ['SSH-2.0-harness\r\n'];
  setConnect((address) => {
    probes.push(address as SocketAddress);
    return fakeSocket(banner).socket;
  });
  const executor = new OrgExecutor(ctx, env);
  return {
    executor,
    container,
    capacity,
    issuer,
    storage,
    alarmAt: () => alarm,
    egress,
    ready,
    probes,
    setBanner: (script) => {
      banner = script;
    },
  };
}

/** A container response whose body stays open until `close` is called. */
export function openStream(): { response: Response; close: () => void } {
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

export const flush = () => new Promise((resolve) => setTimeout(resolve, 0));
