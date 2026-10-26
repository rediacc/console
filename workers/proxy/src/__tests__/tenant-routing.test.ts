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

import worker, { type Env, ExecutorContainer, executorEnvVars } from '../index';
import type { ExecutorIssuerRpc } from '../issued-token';

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

describe('capacity', () => {
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

  it('a capacity error on start is a 503 EXECUTOR_CAPACITY with Retry-After 30 and the capacity outcome', async () => {
    lib.pinError = new Error('Maximum instances reached for this container application');
    const { ctx, attrs } = traced();
    const response = await worker.fetch(call('rdt_a'), env(issuer()), ctx);

    expect(response.status).toBe(503);
    expect(response.headers.get('retry-after')).toBe('30');
    expect(await response.json()).toMatchObject({ code: 'EXECUTOR_CAPACITY' });
    expect(attrs['rediacc.proxy.outcome']).toBe('capacity');
  });

  it('never falls back to another org instance on a capacity error', async () => {
    lib.pinError = new Error('container capacity exceeded');
    await worker.fetch(call('rdt_a'), env(issuer()));

    expect(lib.names).toEqual(['org-a']);
  });

  it('another start failure is a 503 that is not labelled capacity', async () => {
    lib.pinError = new Error('image pull failed');
    const { ctx, attrs } = traced();
    const response = await worker.fetch(call('rdt_a'), env(issuer()), ctx);

    expect(response.status).toBe(503);
    expect(response.headers.get('retry-after')).toBeNull();
    expect(await response.json()).toMatchObject({
      code: 'EXECUTOR_START_FAILED',
    });
    expect(attrs['rediacc.proxy.outcome']).toBe('start-failed');
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
