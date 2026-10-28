/**
 * Per-org routing and pinning (agent/plans/PLAN-console-executor-multi-org.md box W1).
 *
 * `ExecutorIssuer.route` is the account Worker's RPC (box A2); here it is a fake that counts calls. The Container base class is a stub that records what `pin` asks of it, so the tests prove what the Durable Object code requests, not what the library does with it (MU1 and MU3 were read in the library source, see the box notes).
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const lib = vi.hoisted(() => ({
  names: [] as string[],
  pins: [] as string[],
  pinError: undefined as Error | undefined,
  calls: [] as unknown[][],
}));

vi.mock('@cloudflare/containers', () => ({
  ContainerProxy: class {},
  Container: class {
    static outboundHandlers: unknown;
    envVars: Record<string, string> | undefined;
    constructor(
      readonly ctx: unknown,
      readonly env: unknown
    ) {}
    setOutboundByHost(...args: unknown[]): Promise<void> {
      lib.calls.push(['setOutboundByHost', ...args]);
      return Promise.resolve();
    }
    startAndWaitForPorts(...args: unknown[]): Promise<void> {
      lib.calls.push(['startAndWaitForPorts', ...args]);
      return Promise.resolve();
    }
  },
  getContainer: (_binding: unknown, name: string) => {
    lib.names.push(name);
    return {
      pin: (org: string) => {
        lib.pins.push(org);
        return lib.pinError ? Promise.reject(lib.pinError) : Promise.resolve();
      },
      fetch: () => Promise.resolve(Response.json({ from: 'container', name })),
    };
  },
}));

import worker, { type Env, ExecutorContainer } from '../index';
import type { ExecutorIssuerRpc } from '../issued-token';
import { executorEnv as executorEnvVars, type PinAnswer } from '../org-executor';

/** Which org a caller token belongs to; anything else is refused. */
const ORG_OF: Record<string, string> = { rdt_a: 'org-a', rdt_b: 'org-b' };

interface Issuer {
  binding: Service<ExecutorIssuerRpc>;
  routes: string[];
  issues: number;
}

function issuer(mode: 'ok' | 'throws' = 'ok'): Issuer {
  const counts: Issuer = { binding: null as never, routes: [], issues: 0 };
  counts.binding = {
    route: (bearer: string) => {
      counts.routes.push(bearer);
      if (mode === 'throws') return Promise.reject(new Error('issuer down'));
      const orgId = ORG_OF[bearer];
      return Promise.resolve(orgId ? { orgId } : { refused: 'route-refused' });
    },
    issue: () => {
      counts.issues += 1;
      return Promise.reject(new Error('the front door never mints'));
    },
  } as unknown as Service<ExecutorIssuerRpc>;
  return counts;
}

function env(i: Issuer | undefined, extra: Partial<Env> = {}): Env {
  return {
    EXECUTOR: null as never,
    ACCOUNT_URL: 'https://account.test',
    ISSUER: i?.binding,
    ...extra,
  };
}

function call(token?: string): Request {
  return new Request('https://proxy.test/v1/command', {
    headers: token ? { authorization: `Bearer ${token}` } : {},
  });
}

beforeEach(() => {
  lib.names = [];
  lib.pins = [];
  lib.pinError = undefined;
  lib.calls = [];
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
});

describe('front door', () => {
  it('two callers of two orgs reach two Durable Object names, each named by the org alone', async () => {
    const i = issuer();
    const a = await worker.fetch(call('rdt_a'), env(i));
    const b = await worker.fetch(call('rdt_b'), env(i));

    expect(await a.json()).toEqual({ from: 'container', name: 'org-a' });
    expect(await b.json()).toEqual({ from: 'container', name: 'org-b' });
    expect(lib.names).toEqual(['org-a', 'org-b']);
    expect(lib.pins).toEqual(['org-a', 'org-b']);
    expect(i.routes).toEqual(['rdt_a', 'rdt_b']);
  });

  it('answers 401 for a route refusal, without starting a container', async () => {
    const response = await worker.fetch(call('rdt_stranger'), env(issuer()));

    expect(response.status).toBe(401);
    expect(lib.names).toEqual([]);
    expect(lib.pins).toEqual([]);
  });

  it('answers 401 for no bearer and never asks the issuer', async () => {
    const i = issuer();
    const response = await worker.fetch(call(), env(i));

    expect(response.status).toBe(401);
    expect(i.routes).toEqual([]);
  });

  for (const [name, i] of [
    ['the issuer route call throws', issuer('throws')],
    ['there is no ISSUER binding', undefined],
  ] as const) {
    it(`answers 503, not 401, when ${name}`, async () => {
      const response = await worker.fetch(call('rdt_a'), env(i));

      expect(response.status).toBe(503);
      expect(lib.names).toEqual([]);
    });
  }

  it('never mints at the front door, and a malformed route answer is refused', async () => {
    const i = issuer();
    for (const answer of [{}, { orgId: '' }, { orgId: 7 }, undefined]) {
      (i.binding as unknown as { route: unknown }).route = () => Promise.resolve(answer);
      const response = await worker.fetch(call('rdt_a'), env(i));
      expect(response.status).toBe(401);
    }
    expect(i.issues).toBe(0);
    expect(lib.names).toEqual([]);
  });
});

function traced(): { ctx: ExecutionContext; attrs: Record<string, unknown> } {
  const attrs: Record<string, unknown> = {};
  const ctx = {
    tracing: {
      getActiveSpan: () => ({
        setAttribute: (k: string, v: unknown) => (attrs[k] = v),
      }),
    },
  } as unknown as ExecutionContext;
  return { ctx, attrs };
}

describe('legacy start failures', () => {
  it('a start error is a 503 EXECUTOR_START_FAILED whatever its text: capacity is never guessed from error text', async () => {
    for (const text of [
      'Maximum instances reached for this container application',
      'container capacity exceeded',
      'image pull failed',
    ]) {
      lib.pinError = new Error(text);
      const { ctx, attrs } = traced();
      const response = await worker.fetch(call('rdt_a'), env(issuer()), ctx);

      expect(response.status).toBe(503);
      expect(response.headers.get('retry-after')).toBeNull();
      expect(await response.json()).toMatchObject({ code: 'EXECUTOR_START_FAILED' });
      expect(attrs['rediacc.proxy.outcome']).toBe('start-failed');
    }
  });

  it('never falls back to another org instance on a failed start', async () => {
    lib.pinError = new Error('container capacity exceeded');
    await worker.fetch(call('rdt_a'), env(issuer()));

    expect(lib.names).toEqual(['org-a']);
  });
});

const DAY_MS = 24 * 60 * 60 * 1000;

/** The `durable` backend's ORG_EXECUTOR namespace: records every stub it hands out and every pin, answering from `answers` in order (an empty queue answers ok on the asked size). */
const durable = {
  gets: [] as string[],
  oomAt: undefined as number | undefined,
  pins: [] as [string, string][],
  answers: [] as PinAnswer[],
  pinThrows: false as boolean,
  fetches: [] as string[],
};

function orgExecutors(): Env['ORG_EXECUTOR'] {
  return {
    idFromName: (name: string) => ({ name }),
    get: (doId: { name: string }) => {
      durable.gets.push(doId.name);
      return {
        oomAt: () => Promise.resolve(durable.oomAt),
        pin: (orgId: string, size: string) => {
          durable.pins.push([orgId, size]);
          if (durable.pinThrows) return Promise.reject(new Error('do unreachable'));
          return Promise.resolve(durable.answers.shift() ?? { ok: true, size });
        },
        fetch: () => {
          durable.fetches.push(doId.name);
          return Promise.resolve(Response.json({ from: 'org-executor', name: doId.name }));
        },
      };
    },
  } as unknown as Env['ORG_EXECUTOR'];
}

/** An issuer whose route also answers a tier: `rdt_high` is a BUSINESS org, `rdt_std` a PROFESSIONAL one, and `rdt_a` comes from an older account Worker with no tier. */
function tieredIssuer(): Issuer {
  const counts = issuer();
  const tiers: Record<string, { orgId: string; tier?: string }> = {
    rdt_high: { orgId: 'org-high', tier: 'high' },
    rdt_std: { orgId: 'org-std', tier: 'standard' },
    rdt_a: { orgId: 'org-a' },
  };
  (counts.binding as unknown as { route: unknown }).route = (bearer: string) => {
    counts.routes.push(bearer);
    return Promise.resolve(tiers[bearer] ?? { refused: 'route-refused' });
  };
  return counts;
}

function durableEnv(extra: Partial<Env> = {}): Env {
  return env(tieredIssuer(), {
    EXECUTOR_BACKEND: 'durable',
    ORG_EXECUTOR: orgExecutors(),
    ...extra,
  });
}

describe('backend routing by EXECUTOR_BACKEND', () => {
  beforeEach(() => {
    durable.gets = [];
    durable.oomAt = undefined;
    durable.pins = [];
    durable.answers = [];
    durable.pinThrows = false;
    durable.fetches = [];
  });

  for (const backend of ['container', undefined, '', 'Durable', 'org-executor']) {
    it(`EXECUTOR_BACKEND=${JSON.stringify(backend)} routes every request to EXECUTOR and never to ORG_EXECUTOR`, async () => {
      const e = durableEnv({ EXECUTOR_BACKEND: backend });
      for (const token of ['rdt_a', 'rdt_high', 'rdt_a']) {
        const response = await worker.fetch(call(token), e);
        expect(await response.json()).toMatchObject({ from: 'container' });
      }

      expect(lib.names).toEqual(['org-a', 'org-high', 'org-a']);
      expect(durable.gets).toEqual([]);
    });
  }

  it('durable routes every request to ORG_EXECUTOR and never to EXECUTOR', async () => {
    const e = durableEnv();
    for (const token of ['rdt_a', 'rdt_high', 'rdt_a']) {
      const response = await worker.fetch(call(token), e);
      expect(response.status).toBe(200);
      expect(await response.json()).toMatchObject({ from: 'org-executor' });
    }

    expect(durable.gets).toEqual(['org-a', 'org-high', 'org-a']);
    expect(durable.fetches).toEqual(['org-a', 'org-high', 'org-a']);
    expect(lib.names).toEqual([]);
    expect(lib.pins).toEqual([]);
  });

  it('durable without an ORG_EXECUTOR binding is a 503 EXECUTOR_START_FAILED, never a fall back to EXECUTOR', async () => {
    const response = await worker.fetch(call('rdt_a'), durableEnv({ ORG_EXECUTOR: undefined }));

    expect(response.status).toBe(503);
    expect(await response.json()).toMatchObject({ code: 'EXECUTOR_START_FAILED' });
    expect(lib.names).toEqual([]);
  });

  it('a route refusal starts nothing on the durable backend', async () => {
    const response = await worker.fetch(call('rdt_stranger'), durableEnv());

    expect(response.status).toBe(401);
    expect(durable.gets).toEqual([]);
  });
});

describe('sizing on the durable backend', () => {
  beforeEach(() => {
    durable.gets = [];
    durable.oomAt = undefined;
    durable.pins = [];
    durable.answers = [];
    durable.pinThrows = false;
    durable.fetches = [];
  });

  it("tier 'high' starts heavy (standard-1)", async () => {
    await worker.fetch(call('rdt_high'), durableEnv());
    expect(durable.pins).toEqual([['org-high', 'heavy']]);
  });

  it("tier 'standard' and a missing tier start light", async () => {
    await worker.fetch(call('rdt_std'), durableEnv());
    await worker.fetch(call('rdt_a'), durableEnv());
    expect(durable.pins).toEqual([
      ['org-std', 'light'],
      ['org-a', 'light'],
    ]);
  });

  it('an OOM flag within 7 days starts heavy, and an 8-day-old flag starts light', async () => {
    durable.oomAt = Date.now() - 6 * DAY_MS;
    await worker.fetch(call('rdt_a'), durableEnv());
    durable.oomAt = Date.now() - 8 * DAY_MS;
    await worker.fetch(call('rdt_a'), durableEnv());

    expect(durable.pins).toEqual([
      ['org-a', 'heavy'],
      ['org-a', 'light'],
    ]);
  });

  it('with the heavy slots full, a high-tier org retries and runs light', async () => {
    durable.answers = [{ ok: false, code: 'EXECUTOR_CAPACITY', reason: 'heavy-full' }];
    const { ctx, attrs } = traced();
    const response = await worker.fetch(call('rdt_high'), durableEnv(), ctx);

    expect(response.status).toBe(200);
    expect(durable.pins).toEqual([
      ['org-high', 'heavy'],
      ['org-high', 'light'],
    ]);
    expect(attrs['rediacc.proxy.size']).toBe('light');
    expect(attrs['rediacc.proxy.outcome']).toBe('forwarded');
  });

  it('with the heavy slots full, an OOM-flagged org gets 503 EXECUTOR_CAPACITY with Retry-After 30 and no light retry', async () => {
    durable.oomAt = Date.now() - DAY_MS;
    durable.answers = [{ ok: false, code: 'EXECUTOR_CAPACITY', reason: 'heavy-full' }];
    const { ctx, attrs } = traced();
    const response = await worker.fetch(call('rdt_high'), durableEnv(), ctx);

    expect(response.status).toBe(503);
    expect(response.headers.get('retry-after')).toBe('30');
    expect(await response.json()).toMatchObject({ code: 'EXECUTOR_CAPACITY' });
    expect(durable.pins).toEqual([['org-high', 'heavy']]);
    expect(durable.fetches).toEqual([]);
    expect(attrs['rediacc.proxy.outcome']).toBe('capacity');
  });

  it('a full target is a 503 EXECUTOR_CAPACITY with Retry-After 30, from the coordinator answer alone', async () => {
    durable.answers = [{ ok: false, code: 'EXECUTOR_CAPACITY', reason: 'full' }];
    const response = await worker.fetch(call('rdt_a'), durableEnv());

    expect(response.status).toBe(503);
    expect(response.headers.get('retry-after')).toBe('30');
    expect(await response.json()).toMatchObject({ code: 'EXECUTOR_CAPACITY' });
    expect(durable.pins).toEqual([['org-a', 'light']]);
  });

  it('a start failure answer, or a Durable Object that cannot be reached, is a 503 EXECUTOR_START_FAILED without Retry-After', async () => {
    durable.answers = [{ ok: false, code: 'EXECUTOR_START_FAILED', reason: 'not-ready' }];
    const answered = await worker.fetch(call('rdt_a'), durableEnv());
    durable.pinThrows = true;
    const { ctx, attrs } = traced();
    const thrown = await worker.fetch(call('rdt_a'), durableEnv(), ctx);

    for (const response of [answered, thrown]) {
      expect(response.status).toBe(503);
      expect(response.headers.get('retry-after')).toBeNull();
      expect(await response.json()).toMatchObject({ code: 'EXECUTOR_START_FAILED' });
    }
    expect(attrs['rediacc.proxy.outcome']).toBe('start-failed');
    expect(durable.fetches).toEqual([]);
  });

  it('a running container keeps its started size: the span names the size pin answers', async () => {
    durable.answers = [{ ok: true, size: 'heavy' }];
    const { ctx, attrs } = traced();
    await worker.fetch(call('rdt_a'), durableEnv(), ctx);

    expect(durable.pins).toEqual([['org-a', 'light']]);
    expect(attrs['rediacc.proxy.size']).toBe('heavy');
  });

  it('the span carries rediacc.proxy.size and no org id, on every outcome', async () => {
    const answers: PinAnswer[][] = [
      [],
      [{ ok: false, code: 'EXECUTOR_CAPACITY', reason: 'heavy-full' }],
      [{ ok: false, code: 'EXECUTOR_CAPACITY', reason: 'full' }],
      [{ ok: false, code: 'EXECUTOR_START_FAILED', reason: 'not-ready' }],
    ];
    for (const queue of answers) {
      durable.answers = [...queue];
      const { ctx, attrs } = traced();
      await worker.fetch(call('rdt_high'), durableEnv(), ctx);

      expect(['light', 'heavy']).toContain(attrs['rediacc.proxy.size']);
      for (const value of Object.values(attrs)) {
        expect(String(value)).not.toContain('org-');
        expect(String(value)).not.toContain('rdt_');
      }
    }
  });
});

/** A Durable Object id as the runtime makes it: `idFromName` is stable per name and `equals` compares them. */
function id(name: string): {
  toString(): string;
  equals(other: { toString(): string }): boolean;
} {
  return {
    toString: () => `id:${name}`,
    equals: (other) => other.toString() === `id:${name}`,
  };
}

function instance(name: string): ExecutorContainer {
  const e = env(undefined, {
    EXECUTOR: {
      idFromName: (n: string) => id(n),
    } as unknown as Env['EXECUTOR'],
  });
  return new ExecutorContainer({ id: id(name) } as never, e);
}

describe('ExecutorContainer.pin', () => {
  it('refuses an org whose idFromName differs from the instance id, and starts nothing', async () => {
    const container = instance('org-a');

    await expect(container.pin('org-b')).rejects.toThrow('pin-id-mismatch');
    expect(lib.calls).toEqual([]);
  });

  it('refuses an empty or non-string org', async () => {
    const container = instance('org-a');

    await expect(container.pin('')).rejects.toThrow('pin-org-invalid');
    await expect(container.pin(undefined as never)).rejects.toThrow('pin-org-invalid');
    expect(lib.calls).toEqual([]);
  });

  it('a second pin with another org is refused, even when the id check alone would have passed', async () => {
    const container = instance('org-a');
    await container.pin('org-a');
    // Forge the id match for org-b to reach the conflict rule on its own.
    (container as unknown as { ctx: { id: unknown } }).ctx.id = {
      toString: () => 'id:org-b',
      equals: () => true,
    };

    await expect(container.pin('org-b')).rejects.toThrow('pin-org-conflict');
    expect(lib.calls.filter((c) => c[0] === 'startAndWaitForPorts')).toHaveLength(1);
  });

  it('pins the same org again without a conflict', async () => {
    const container = instance('org-a');
    await container.pin('org-a');
    await expect(container.pin('org-a')).resolves.toBeUndefined();
  });

  it('routes account.internal to accountEgress with the org, then starts with exactly the four env names', async () => {
    const container = instance('org-a');
    await container.pin('org-a');

    expect(lib.calls[0]).toEqual([
      'setOutboundByHost',
      'account.internal',
      'accountEgress',
      { orgId: 'org-a' },
    ]);
    const start = lib.calls[1] as [string, { startOptions: { envVars: Record<string, string> } }];
    expect(start[0]).toBe('startAndWaitForPorts');
    const envVars = start[1].startOptions.envVars;
    expect(Object.keys(envVars).sort((a, b) => a.localeCompare(b))).toEqual([
      'REDIACC_ACCOUNT_SERVER',
      'REDIACC_EXECUTOR_ORG_ID',
      'REDIACC_REGION',
      'REDIACC_TOKEN',
    ]);
    expect(envVars.REDIACC_EXECUTOR_ORG_ID).toBe('org-a');
    expect(envVars.REDIACC_TOKEN).toBe('rediacc-executor-placeholder');
    // A later restart that skips `pin` still carries the org.
    expect(container.envVars).toEqual(envVars);
    expect(envVars).toEqual(executorEnvVars((container as unknown as { env: Env }).env, 'org-a'));
  });

  it('installs the egress routing before the start, so no start happens with account.internal unrouted', async () => {
    await instance('org-a').pin('org-a');
    expect(lib.calls.map((c) => c[0])).toEqual(['setOutboundByHost', 'startAndWaitForPorts']);
  });
});
