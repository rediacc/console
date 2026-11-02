/**
 * Per-org routing and pinning (agent/plans/PLAN-console-executor-multi-org.md box W1), and routing by placement (agent/plans/PLAN-org-executor-connect-timeout-relocate.md box E7).
 *
 * `ExecutorIssuer.route` is the account Worker's RPC (box A2); here it is a fake that counts calls. ORG_EXECUTOR is a fake namespace that records every stub it hands out and every pin.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import worker, { type Env } from '../index';
import type { ExecutorIssuerRpc } from '../issued-token';
import type { PinAnswer } from '../org-executor';

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
      return Promise.resolve(orgId ? { orgId, placement: 0 } : { refused: 'route-refused' });
    },
    issue: () => {
      counts.issues += 1;
      return Promise.reject(new Error('the front door never mints'));
    },
  } as unknown as Service<ExecutorIssuerRpc>;
  return counts;
}

const DAY_MS = 24 * 60 * 60 * 1000;

/** The ORG_EXECUTOR namespace: records every stub it hands out and every pin, answering from `answers` in order (an empty queue answers ok on the asked size). */
const durable = {
  gets: [] as string[],
  oomAt: undefined as number | undefined,
  oomHeavyAt: undefined as number | undefined,
  pins: [] as [string, string][],
  /** The placement every pin was asked for, in order. */
  placements: [] as number[],
  answers: [] as PinAnswer[],
  pinThrows: false as boolean,
  oomHeavyThrows: false as boolean,
  fetches: [] as string[],
};

function orgExecutors(): Env['ORG_EXECUTOR'] {
  return {
    idFromName: (name: string) => ({ name }),
    get: (doId: { name: string }) => {
      durable.gets.push(doId.name);
      return {
        oomAt: () => Promise.resolve(durable.oomAt),
        oomHeavyAt: () =>
          durable.oomHeavyThrows
            ? Promise.reject(new Error('do unreachable'))
            : Promise.resolve(durable.oomHeavyAt),
        pin: (orgId: string, placement: number, size: string) => {
          durable.pins.push([orgId, size]);
          durable.placements.push(placement);
          if (durable.pinThrows) return Promise.reject(new Error('do unreachable'));
          return Promise.resolve(
            durable.answers.shift() ?? { ok: true, size, egressUnreachableRecent: false }
          );
        },
        fetch: () => {
          durable.fetches.push(doId.name);
          return Promise.resolve(Response.json({ from: 'org-executor', name: doId.name }));
        },
      };
    },
  } as unknown as Env['ORG_EXECUTOR'];
}

function env(i: Issuer | undefined, extra: Partial<Env> = {}): Env {
  return {
    ORG_EXECUTOR: orgExecutors(),
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
  durable.gets = [];
  durable.oomAt = undefined;
  durable.oomHeavyAt = undefined;
  durable.pins = [];
  durable.placements = [];
  durable.answers = [];
  durable.pinThrows = false;
  durable.oomHeavyThrows = false;
  durable.fetches = [];
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
});

describe('front door', () => {
  it('two callers of two orgs reach two Durable Object names, each named by the org and its placement', async () => {
    const i = issuer();
    const a = await worker.fetch(call('rdt_a'), env(i));
    const b = await worker.fetch(call('rdt_b'), env(i));

    expect(await a.json()).toEqual({ from: 'org-executor', name: 'org-a:p0' });
    expect(await b.json()).toEqual({ from: 'org-executor', name: 'org-b:p0' });
    expect(durable.gets).toEqual(['org-a:p0', 'org-b:p0']);
    expect(durable.pins.map(([org]) => org)).toEqual(['org-a', 'org-b']);
    expect(i.routes).toEqual(['rdt_a', 'rdt_b']);
  });

  it('answers 401 for a route refusal, without starting an executor', async () => {
    const response = await worker.fetch(call('rdt_stranger'), env(issuer()));

    expect(response.status).toBe(401);
    expect(durable.gets).toEqual([]);
    expect(durable.pins).toEqual([]);
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
      expect(durable.gets).toEqual([]);
    });
  }

  it('never mints at the front door, and a malformed route answer is refused', async () => {
    const i = issuer();
    for (const answer of [{}, { orgId: '' }, { orgId: 7, placement: 0 }, undefined]) {
      (i.binding as unknown as { route: unknown }).route = () => Promise.resolve(answer);
      const response = await worker.fetch(call('rdt_a'), env(i));
      expect(response.status).toBe(401);
    }
    expect(i.issues).toBe(0);
    expect(durable.gets).toEqual([]);
  });

  it('a route answer without a valid placement is a 503 refused:route-placement-missing that starts nothing', async () => {
    for (const placement of [undefined, -1, 1.5, '1', null]) {
      const i = issuer();
      (i.binding as unknown as { route: unknown }).route = () =>
        Promise.resolve({ orgId: 'org-a', placement });
      const { ctx, attrs } = traced();
      const response = await worker.fetch(call('rdt_a'), env(i), ctx);

      expect(response.status).toBe(503);
      expect(attrs['rediacc.proxy.outcome']).toBe('refused:route-placement-missing');
    }
    expect(durable.gets).toEqual([]);
    expect(durable.gets).toEqual([]);
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

/** An issuer whose route also answers a tier and a placement: `rdt_high` is a BUSINESS org, `rdt_std` a PROFESSIONAL one, `rdt_a` answers no tier, and `rdt_moved` is an org at placement 1. */
function tieredIssuer(): Issuer {
  const counts = issuer();
  const tiers: Record<string, { orgId: string; tier?: string; placement: number }> = {
    rdt_high: { orgId: 'org-high', tier: 'high', placement: 0 },
    rdt_std: { orgId: 'org-std', tier: 'standard', placement: 0 },
    rdt_a: { orgId: 'org-a', placement: 0 },
    rdt_moved: { orgId: 'org-a', placement: 1 },
  };
  (counts.binding as unknown as { route: unknown }).route = (bearer: string) => {
    counts.routes.push(bearer);
    return Promise.resolve(tiers[bearer] ?? { refused: 'route-refused' });
  };
  return counts;
}

function durableEnv(extra: Partial<Env> = {}): Env {
  return env(tieredIssuer(), { ORG_EXECUTOR: orgExecutors(), ...extra });
}

describe('routing', () => {
  it('routes every request to ORG_EXECUTOR', async () => {
    const e = durableEnv();
    for (const token of ['rdt_a', 'rdt_high', 'rdt_a']) {
      const response = await worker.fetch(call(token), e);
      expect(response.status).toBe(200);
      expect(await response.json()).toMatchObject({ from: 'org-executor' });
    }

    expect(durable.gets).toEqual(['org-a:p0', 'org-high:p0', 'org-a:p0']);
    expect(durable.fetches).toEqual(['org-a:p0', 'org-high:p0', 'org-a:p0']);
    expect(durable.placements).toEqual([0, 0, 0]);
  });

  it('without an ORG_EXECUTOR binding is a 503 EXECUTOR_START_FAILED', async () => {
    const response = await worker.fetch(call('rdt_a'), durableEnv({ ORG_EXECUTOR: undefined }));

    expect(response.status).toBe(503);
    expect(await response.json()).toMatchObject({ code: 'EXECUTOR_START_FAILED' });
    expect(durable.gets).toEqual([]);
  });

  it('a route answering placement 1 reaches the stub named org-a:p1 and pins with that placement', async () => {
    const response = await worker.fetch(call('rdt_moved'), durableEnv());

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ from: 'org-executor', name: 'org-a:p1' });
    expect(durable.gets).toEqual(['org-a:p1']);
    expect(durable.placements).toEqual([1]);
  });

  it('a route refusal starts nothing ', async () => {
    const response = await worker.fetch(call('rdt_stranger'), durableEnv());

    expect(response.status).toBe(401);
    expect(durable.gets).toEqual([]);
  });
});

describe('sizing', () => {
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

  it('a heavy container that ran out of memory within 7 days is served with outcome oom-heavy', async () => {
    durable.oomAt = Date.now() - DAY_MS;
    durable.oomHeavyAt = Date.now() - DAY_MS;
    const { ctx, attrs } = traced();
    const response = await worker.fetch(call('rdt_a'), durableEnv(), ctx);
    expect(response.status).toBe(200);
    expect(attrs['rediacc.proxy.size']).toBe('heavy');
    expect(attrs['rediacc.proxy.outcome']).toBe('oom-heavy');
  });

  it('4ab1a051.1: a Durable Object that cannot answer oomHeavyAt is served as forwarded', async () => {
    durable.oomHeavyThrows = true;
    const { ctx, attrs } = traced();
    const response = await worker.fetch(call('rdt_high'), durableEnv(), ctx);
    expect(response.status).toBe(200);
    expect(attrs['rediacc.proxy.outcome']).toBe('forwarded');
  });

  it('a pin answer with egressUnreachableRecent is served with outcome egress-unreachable, ahead of oom-heavy', async () => {
    durable.oomAt = Date.now() - DAY_MS;
    durable.oomHeavyAt = Date.now() - DAY_MS;
    durable.answers = [{ ok: true, size: 'heavy', egressUnreachableRecent: true }];
    const { ctx, attrs } = traced();
    const response = await worker.fetch(call('rdt_a'), durableEnv(), ctx);

    expect(response.status).toBe(200);
    expect(durable.fetches).toEqual(['org-a:p0']);
    expect(attrs['rediacc.proxy.outcome']).toBe('egress-unreachable');
  });

  it('a heavy OOM flag older than 7 days leaves the outcome forwarded', async () => {
    durable.oomHeavyAt = Date.now() - 8 * DAY_MS;
    const { ctx, attrs } = traced();
    await worker.fetch(call('rdt_high'), durableEnv(), ctx);
    expect(attrs['rediacc.proxy.outcome']).toBe('forwarded');
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
    durable.answers = [{ ok: true, size: 'heavy', egressUnreachableRecent: false }];
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
