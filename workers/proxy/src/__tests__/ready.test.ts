/**
 * `/v1/ready` (agent/plans/PLAN-console-executor-multi-org.md box W2): the issuer's `probe()` plus `GET server-info` over ACCOUNT, cached for 30 s, never minting.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@cloudflare/containers', () => ({
  ContainerProxy: class {},
  Container: class {
    static outboundByHost: unknown;
    constructor(
      readonly ctx: unknown,
      readonly env: unknown
    ) {}
  },
  getContainer: () => ({ fetch: () => Promise.resolve(new Response('container')) }),
}));

import worker, { type Env } from '../index';
import { type ExecutorIssuerRpc, resetIssuedTokenCache } from '../issued-token';
import { READY_CACHE_MS, readiness, resetReadyCache } from '../ready';

const ACCOUNT_URL = 'https://account.test';
const VERSION_ID = '5b0e7d5c-0000-4000-8000-000000000001';
const metadata = { CF_VERSION_METADATA: { id: VERSION_ID, tag: '', timestamp: '' } };

interface Counting {
  binding: Service<ExecutorIssuerRpc>;
  probes: number;
  issues: number;
}

function issuer(probe: () => Promise<unknown>): Counting {
  const counts = { probes: 0, issues: 0 } as Counting;
  counts.binding = {
    probe: () => {
      counts.probes += 1;
      return probe();
    },
    issue: () => {
      counts.issues += 1;
      return Promise.reject(new Error('ready must never mint'));
    },
  } as unknown as Service<ExecutorIssuerRpc>;
  return counts;
}

const probeOk = () =>
  Promise.resolve({ ok: true, scopes: ['proxy:exec', 'audit:write'], ttlMs: 2_700_000 });

function account(status = 200): { binding: Fetcher; seen: Request[] } {
  const seen: Request[] = [];
  const binding = {
    fetch: (input: Request | string, init?: RequestInit) => {
      seen.push(input instanceof Request ? input : new Request(input, init));
      return Promise.resolve(Response.json({}, { status }));
    },
  } as unknown as Fetcher;
  return { binding, seen };
}

function env(i: Counting, a: { binding: Fetcher }, extra: Partial<Env> = {}): Env {
  return {
    EXECUTOR: null as never,
    ACCOUNT_URL,
    ACCOUNT: a.binding,
    ISSUER: i.binding,
    ...extra,
  };
}

async function ready(e: Env): Promise<{ status: number; body: unknown }> {
  const response = await worker.fetch(new Request('https://proxy.test/v1/ready'), e);
  return { status: response.status, body: await response.json() };
}

beforeEach(() => {
  resetIssuedTokenCache();
  resetReadyCache();
  vi.restoreAllMocks();
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
});

describe('/v1/ready', () => {
  it('answers 200 with the worker version after probe() and server-info, with no mint', async () => {
    const i = issuer(probeOk);
    const a = account();
    expect(await ready(env(i, a, metadata))).toEqual({
      status: 200,
      body: { ready: true, workerVersion: VERSION_ID },
    });
    expect(i.probes).toBe(1);
    expect(i.issues).toBe(0);
    expect(a.seen).toHaveLength(1);
    const sent = a.seen[0] as Request;
    expect(sent.method).toBe('GET');
    expect(sent.url).toBe(`${ACCOUNT_URL}/account/api/v1/.well-known/server-info`);
    expect(sent.headers.get('authorization')).toBeNull();
  });

  it('answers 503 issuer-probe-failed when probe throws, writes no mint and does not ask ACCOUNT', async () => {
    const i = issuer(() => Promise.reject(new Error('ISSUER_D1_DOWN for org acme')));
    const a = account();
    expect(await ready(env(i, a, metadata))).toEqual({
      status: 503,
      body: { ready: false, reason: 'issuer-probe-failed' },
    });
    expect(i.issues).toBe(0);
    expect(a.seen).toEqual([]);
  });

  it('answers 503 issuer-probe-failed for a probe that does not say ok', async () => {
    const i = issuer(() => Promise.resolve({ ok: false, scopes: [] }));
    expect((await ready(env(i, account(), metadata))).body).toEqual({
      ready: false,
      reason: 'issuer-probe-failed',
    });
  });

  const SCOPES: [string, string[], string][] = [
    ['proxy:exec', ['audit:write'], 'no-proxy-exec-scope'],
    ['audit:write', ['proxy:exec'], 'no-audit-write-scope'],
  ];
  for (const [name, scopes, reason] of SCOPES) {
    it(`answers 503 ${reason} when probe lists no ${name}`, async () => {
      const i = issuer(() => Promise.resolve({ ok: true, scopes, ttlMs: 1 }));
      expect((await ready(env(i, account(), metadata))).body).toEqual({ ready: false, reason });
    });
  }

  it('answers 503 no-issuer without the binding', async () => {
    const e = env(issuer(probeOk), account(), metadata);
    delete e.ISSUER;
    expect((await ready(e)).body).toEqual({ ready: false, reason: 'no-issuer' });
  });

  it('answers 503 server-info-http-<status> and server-info-unreachable for a bad ACCOUNT', async () => {
    expect((await ready(env(issuer(probeOk), account(503), metadata))).body).toEqual({
      ready: false,
      reason: 'server-info-http-503',
    });
    resetReadyCache();
    const down = {
      binding: { fetch: () => Promise.reject(new Error('boom')) } as unknown as Fetcher,
    };
    expect((await ready(env(issuer(probeOk), down, metadata))).body).toEqual({
      ready: false,
      reason: 'server-info-unreachable',
    });
  });

  it('answers 503 no-version-metadata without the [version_metadata] binding, and probes nothing', async () => {
    const i = issuer(probeOk);
    expect((await ready(env(i, account()))).body).toEqual({
      ready: false,
      reason: 'no-version-metadata',
    });
    expect(i.probes).toBe(0);
  });

  it('caches the answer for 30 s, ready or not, so polling cannot drive the issuer', async () => {
    let clock = 1_000;
    const now = () => clock;
    const i = issuer(() => Promise.reject(new Error('down')));
    const e = env(i, account(), metadata);

    await Promise.all(Array.from({ length: 10 }, () => readiness(e, now)));
    clock += READY_CACHE_MS - 1;
    expect((await readiness(e, now)).status).toBe(503);
    expect(i.probes).toBe(1);

    clock += 1;
    await readiness(e, now);
    expect(i.probes).toBe(2);
    expect(i.issues).toBe(0);
  });

  it('needs no caller token: an unauthenticated poll is answered', async () => {
    expect((await ready(env(issuer(probeOk), account(), metadata))).status).toBe(200);
  });
});

/** A coordinator namespace whose one stub answers `count()` from `count`, recording every name it is asked for. */
function coordinator(
  count: () => unknown,
  names: string[] = []
): NonNullable<Env['EXECUTOR_CAPACITY']> {
  const stub = { count: async () => count() };
  const idFromName = (name: string) => {
    names.push(name);
    return { toString: () => name };
  };
  return { idFromName, get: () => stub } as unknown as NonNullable<Env['EXECUTOR_CAPACITY']>;
}

const liveCount = () => ({ total: 3, heavy: 1, cap: 25, heavyCap: 5, extra: 'org-a' });
const coordinatorDown = () => {
  throw new Error('coordinator down');
};

describe('/v1/ready executors (box L0 drills)', () => {
  it('adds the coordinator count, only its four integers, from the one capacity:v2 instance', async () => {
    const names: string[] = [];
    const capacity = coordinator(liveCount, names);
    const e = env(issuer(probeOk), account(), { ...metadata, EXECUTOR_CAPACITY: capacity });
    expect(await ready(e)).toEqual({
      status: 200,
      body: {
        ready: true,
        workerVersion: VERSION_ID,
        executors: { total: 3, heavy: 1, cap: 25, heavyCap: 5 },
      },
    });
    expect(names).toEqual(['capacity:v2']);
  });

  it('leaves executors out, and stays ready, when the coordinator cannot answer', async () => {
    const capacity = coordinator(coordinatorDown);
    const e = env(issuer(probeOk), account(), { ...metadata, EXECUTOR_CAPACITY: capacity });
    expect(await ready(e)).toEqual({
      status: 200,
      body: { ready: true, workerVersion: VERSION_ID },
    });
  });

  it('asks the coordinator nothing on a not-ready answer, and at most once per cache window', async () => {
    let counts = 0;
    const counting = () => {
      counts += 1;
      return liveCount();
    };
    const capacity = coordinator(counting);
    const failing = issuer(() => Promise.reject(new Error('down')));
    const down = env(failing, account(), { ...metadata, EXECUTOR_CAPACITY: capacity });
    expect((await ready(down)).status).toBe(503);
    expect(counts).toBe(0);

    resetReadyCache();
    let clock = 1_000;
    const now = () => clock;
    const e = env(issuer(probeOk), account(), { ...metadata, EXECUTOR_CAPACITY: capacity });
    const polls = Array.from({ length: 10 }, () => e);
    await Promise.all(polls.map((poll) => readiness(poll, now)));
    clock += READY_CACHE_MS - 1;
    await readiness(e, now);
    expect(counts).toBe(1);
  });
});
