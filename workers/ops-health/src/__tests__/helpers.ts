import type { Env } from '../env';
import type { Runtime } from '../index';
import { OpsStateCore, type StorageLike } from '../state';

/** A storage that yields to the event loop on every get and put, so two unserialized read-modify-writes would interleave and one would be lost. */
export class YieldingStorage implements StorageLike {
  readonly data = new Map<string, unknown>();
  puts = 0;

  async get<T>(key: string): Promise<T | undefined> {
    await new Promise((resolve) => setTimeout(resolve, 1));
    const value = this.data.get(key);
    return value === undefined ? undefined : (structuredClone(value) as T);
  }

  async put<T>(key: string, value: T): Promise<void> {
    await new Promise((resolve) => setTimeout(resolve, 1));
    this.puts += 1;
    this.data.set(key, structuredClone(value));
  }
}

/** A Durable Object namespace whose single stub is an OpsStateCore over `storage`. */
export function fakeNamespace(core: OpsStateCore): Env['OPS_STATE'] {
  const stub = core as unknown;
  return {
    idFromName: (name: string) => ({ name }),
    get: () => stub,
  } as unknown as Env['OPS_STATE'];
}

export interface Harness {
  env: Env;
  storage: YieldingStorage;
  core: OpsStateCore;
}

export const SES_ENV = {
  OPS_ALERT_EMAILS: 'ops@example.test, second@example.test',
  AWS_SES_ACCESS_KEY_ID_EU: 'AKIDEXAMPLE',
  AWS_SES_SECRET_ACCESS_KEY_EU: 'secret-example',
  AWS_SES_REGION_EU: 'eu-central-1',
  AWS_SES_FROM: 'alerts@example.test',
};

export function harness(overrides: Partial<Env> = {}): Harness {
  const storage = new YieldingStorage();
  const core = new OpsStateCore(storage);
  const env: Env = {
    OPS_STATE: fakeNamespace(core),
    OPS_HEALTH_READ_TOKEN: 'read-token',
    OPS_HEALTH_INGEST_TOKEN: 'ingest-token',
    ...SES_ENV,
    ...overrides,
  };
  return { env, storage, core };
}

export type Route = (url: URL, init?: RequestInit) => Response | Promise<Response>;

/** A fetch that answers from `route` and records every call; an unrouted URL throws, so no test reaches the network. */
export function fakeFetch(route: Route) {
  const calls: { url: string; init?: RequestInit }[] = [];
  const href = (input: RequestInfo | URL): string => {
    if (typeof input === 'string') return input;
    return input instanceof URL ? input.href : input.url;
  };
  const fn = ((input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(href(input));
    calls.push({ url: url.href, init });
    try {
      return Promise.resolve(route(url, init));
    } catch (error) {
      return Promise.reject(error);
    }
  }) as typeof fetch;
  return { fn, calls };
}

/** A socket whose handshake resolves or rejects, and whose reads follow `reads`. */
export function fakeSocket(options: { handshake: 'ok' | Error; reads?: string[] }): Socket {
  const queue = [...(options.reads ?? [])];
  const opened =
    options.handshake === 'ok'
      ? Promise.resolve({ remoteAddress: '', localAddress: '' } as SocketInfo)
      : Promise.reject(options.handshake);
  opened.catch(() => undefined);
  const reader = {
    read: () => {
      const next = queue.shift();
      if (next === undefined) return Promise.resolve({ done: true, value: undefined });
      return Promise.resolve({ done: false, value: new TextEncoder().encode(next) });
    },
    releaseLock: () => undefined,
  };
  return {
    opened,
    readable: { getReader: () => reader },
    writable: {
      getWriter: () => {
        throw new Error('a probe must never write to a socket');
      },
    },
    close: async () => undefined,
    closed: Promise.resolve(),
  } as unknown as Socket;
}

export function runtime(fetchFn: typeof fetch, connect: Runtime['connect'], now: number): Runtime {
  return { fetch: fetchFn, connect, now: () => now };
}

export const T0 = Date.parse('2026-11-04T12:00:00.000Z');
export const MIN = 60_000;
export const HOUR = 3_600_000;
