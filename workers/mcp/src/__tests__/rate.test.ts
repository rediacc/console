/**
 * Per-grant rate limits (agent/plans/PLAN-rmcp-remote-worker.md RW-T5, Design 8): 60 calls in a sliding minute and 5 calls in flight, refused with `REDIACC_RATE_LIMITED`; the same state machine behind the `RATE` Durable Object.
 */
import { describe, expect, it } from 'vitest';
import { type CallDeps, callTool, type GrantCaller } from '../call.js';
import type { McpCallAnswer } from '../executor.js';
import {
  doRateLimiter,
  GrantRateObject,
  MemoryRateLimiter,
  type RateNamespace,
  SLOT_LEASE_MS,
} from '../rate.js';
import { activeGrant } from './helpers/grant.js';

/** The budgets of Design 8, written out so a changed constant fails here. */
const RATE_CALLS_PER_MINUTE = 60;
const RATE_MAX_CONCURRENT = 5;

const OK: McpCallAnswer = {
  ok: true,
  answer: { result: { content: [{ type: 'text', text: 'ran' }], isError: false } },
};

function caller(grantId = 'eu_grant_rate'): GrantCaller {
  return { grant: activeGrant(grantId), secret: 's' };
}

describe('rate limits on tools/call', () => {
  it('refuses the 61st call in a minute with REDIACC_RATE_LIMITED and a retry hint, then serves again', async () => {
    let now = 1_000_000;
    const deps: CallDeps = {
      executor: { call: async () => OK },
      reauthUrl: () => 'https://account.test/reauth',
      rate: new MemoryRateLimiter(() => now),
    };
    const c = caller();
    for (let i = 0; i < RATE_CALLS_PER_MINUTE; i += 1) {
      now += 500;
      expect((await callTool(deps, c, 'repo_list', {})).isError).toBe(false);
    }
    const refused = await callTool(deps, c, 'repo_list', {});
    expect(refused.isError).toBe(true);
    expect(refused.structuredContent).toMatchObject({
      code: 'REDIACC_RATE_LIMITED',
      limit: 'calls',
      retryAfterSeconds: expect.any(Number),
    });
    const wait = (refused.structuredContent as { retryAfterSeconds: number }).retryAfterSeconds;
    expect(wait).toBeGreaterThan(0);
    expect(wait).toBeLessThanOrEqual(60);

    now += wait * 1000;
    expect((await callTool(deps, c, 'repo_list', {})).isError).toBe(false);
  });

  it('refuses the 6th concurrent call, and a finished call gives its slot back', async () => {
    const waiting: Array<() => void> = [];
    const deps: CallDeps = {
      executor: {
        call: () =>
          new Promise<McpCallAnswer>((resolve) => {
            waiting.push(() => resolve(OK));
          }),
      },
      reauthUrl: () => 'https://account.test/reauth',
      rate: new MemoryRateLimiter(),
    };
    const c = caller();
    const running = Array.from({ length: RATE_MAX_CONCURRENT }, () =>
      callTool(deps, c, 'repo_list', {})
    );
    await Promise.resolve();
    await new Promise((r) => setTimeout(r, 0));
    expect(waiting).toHaveLength(RATE_MAX_CONCURRENT);

    const sixth = await callTool(deps, c, 'repo_list', {});
    expect(sixth.structuredContent).toMatchObject({
      code: 'REDIACC_RATE_LIMITED',
      limit: 'concurrent',
    });
    expect(waiting).toHaveLength(RATE_MAX_CONCURRENT);

    waiting[0]();
    await running[0];
    const later = callTool(deps, c, 'repo_list', {});
    await new Promise((r) => setTimeout(r, 0));
    expect(waiting).toHaveLength(RATE_MAX_CONCURRENT + 1);
    for (const finish of waiting) finish();
    expect((await later).isError).toBe(false);
    await Promise.all(running);
  });

  it('keeps one budget per grant, and a refused call forwards nothing', async () => {
    let calls = 0;
    const deps: CallDeps = {
      executor: {
        call: () => {
          calls += 1;
          return Promise.resolve(OK);
        },
      },
      reauthUrl: () => 'https://account.test/reauth',
      rate: new MemoryRateLimiter(() => 1_000_000),
    };
    const a = caller('eu_grant_a');
    for (let i = 0; i < RATE_CALLS_PER_MINUTE; i += 1) await callTool(deps, a, 'repo_list', {});
    const before = calls;
    expect((await callTool(deps, a, 'repo_list', {})).structuredContent).toMatchObject({
      code: 'REDIACC_RATE_LIMITED',
    });
    expect(calls).toBe(before);
    expect((await callTool(deps, caller('eu_grant_b'), 'repo_list', {})).isError).toBe(false);
  });

  it('does not spend budget on a call refused by scope', async () => {
    const deps: CallDeps = {
      executor: { call: async () => OK },
      reauthUrl: () => 'https://account.test/reauth',
      rate: new MemoryRateLimiter(() => 1_000_000),
    };
    const readOnly: GrantCaller = {
      grant: activeGrant('eu_grant_ro', {
        scope: { readOnly: true, tools: null, machines: null, repos: null },
      }),
      secret: 's',
    };
    for (let i = 0; i < RATE_CALLS_PER_MINUTE + 5; i += 1) {
      await callTool(deps, readOnly, 'repo_up', {});
    }
    expect((await callTool(deps, readOnly, 'repo_list', {})).isError).toBe(false);
  });

  it('refuses a call, forwarding nothing, when the limiter cannot count it', async () => {
    let forwarded = 0;
    const deps: CallDeps = {
      executor: {
        call: () => {
          forwarded += 1;
          return Promise.resolve(OK);
        },
      },
      reauthUrl: () => 'https://account.test/reauth',
      rate: {
        acquire: () => Promise.reject(new Error('durable object unreachable')),
        burn: async () => true,
      },
    };
    const result = await callTool(deps, caller(), 'repo_list', {});
    expect(result.structuredContent).toMatchObject({ code: 'SERVER_ERROR' });
    expect(forwarded).toBe(0);
  });

  it('frees a slot whose call never reported back once the lease passes', async () => {
    let now = 5_000_000;
    const limiter = new MemoryRateLimiter(() => now);
    for (let i = 0; i < RATE_MAX_CONCURRENT; i += 1) {
      expect((await limiter.acquire('g')).ok).toBe(true);
    }
    expect(await limiter.acquire('g')).toMatchObject({ ok: false, reason: 'concurrent' });
    now += SLOT_LEASE_MS;
    expect((await limiter.acquire('g')).ok).toBe(true);
  });
});

describe('the RATE Durable Object', () => {
  /** A namespace whose objects are GrantRateObject instances over in-memory storage. */
  function namespace(): RateNamespace & { storages: Map<string, Map<string, unknown>> } {
    const objects = new Map<string, GrantRateObject>();
    const storages = new Map<string, Map<string, unknown>>();
    return {
      storages,
      idFromName: (name) => name,
      get: (id) => {
        const name = String(id);
        let object = objects.get(name);
        if (!object) {
          const store = new Map<string, unknown>();
          storages.set(name, store);
          object = new GrantRateObject({
            storage: {
              get: async <T>(key: string) => store.get(key) as T | undefined,
              put: (key: string, value: unknown) => {
                store.set(key, value);
                return Promise.resolve();
              },
            },
          });
          objects.set(name, object);
        }
        return { fetch: (request: Request) => (object as GrantRateObject).fetch(request) };
      },
    };
  }

  it('enforces the concurrency budget through the client, and a release frees a slot', async () => {
    const limiter = doRateLimiter(namespace());
    const held = [];
    for (let i = 0; i < RATE_MAX_CONCURRENT; i += 1) {
      const slot = await limiter.acquire('g1');
      expect(slot.ok).toBe(true);
      held.push(slot);
    }
    expect(await limiter.acquire('g1')).toMatchObject({ ok: false, reason: 'concurrent' });
    const first = held[0];
    if (first?.ok) await first.release();
    expect((await limiter.acquire('g1')).ok).toBe(true);
    expect((await limiter.acquire('g2')).ok).toBe(true);
  });

  it('burns a nonce once, and keeps it burned in storage', async () => {
    const ns = namespace();
    const limiter = doRateLimiter(ns);
    const expiresAt = Date.now() + 60_000;
    expect(await limiter.burn('g1', 'nonce-1', expiresAt)).toBe(true);
    expect(await limiter.burn('g1', 'nonce-1', expiresAt)).toBe(false);
    expect(await limiter.burn('g1', 'nonce-2', expiresAt)).toBe(true);
    expect(ns.storages.get('g1')?.get('nonces')).toEqual([
      ['nonce-1', expiresAt],
      ['nonce-2', expiresAt],
    ]);

    // A fresh object over the same storage (an eviction) still refuses the burned nonce.
    const revived = new GrantRateObject({
      storage: {
        get: async <T>(key: string) => ns.storages.get('g1')?.get(key) as T | undefined,
        put: async () => undefined,
      },
    });
    const answer = await revived.fetch(
      new Request('https://rate.internal/', {
        method: 'POST',
        body: JSON.stringify({ op: 'burn', nonce: 'nonce-1', expiresAt }),
      })
    );
    expect(await answer.json()).toEqual({ fresh: false });
  });
});
