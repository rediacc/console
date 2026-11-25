import { DatabaseSync } from 'node:sqlite';
import { describe, expect, it, vi } from 'vitest';
import { PRICE_TABLE } from '../../../../packages/shared/src/ai-credits/index.js';

vi.mock('cloudflare:workers', () => ({
  WorkerEntrypoint: class {
    constructor(
      protected ctx: unknown,
      protected env: unknown
    ) {}
  },
  DurableObject: class {
    constructor(
      protected ctx: unknown,
      protected env: unknown
    ) {}
  },
}));

const {
  CreditLedgerCore,
  DEFAULT_LIMITS,
  RESERVATION_TTL_MS,
} = await import('../credit-ledger.js');

/**
 * The ledger decisions of agent/plans/PLAN-console-ai-credits.md D4 to D6 and D9, run over a real
 * SQLite database (the Durable Object's storage is SQLite too). Every core method is synchronous,
 * which is what keeps concurrent reservations from overdrawing: each decides against the balance
 * the one before it left.
 */

const MODEL = PRICE_TABLE[0]?.model ?? '';
const NOW = Date.parse('2026-11-25T10:00:00.000Z');
const FUTURE = '2027-11-25T10:00:00.000Z';

function ledger(limits = DEFAULT_LIMITS) {
  const db = new DatabaseSync(':memory:');
  const core = new CreditLedgerCore(
    {
      // Eager, like the Durable Object's cursor: a statement runs when exec is called, not when its rows are read.
      exec: (query, ...bindings) => {
        const rows = db.prepare(query).all(...bindings);
        return { toArray: () => rows };
      },
    },
    limits
  );
  core.setEntitled(true);
  return core;
}

function request(id: string, over: Partial<{ conversationId: string; bodyBytes: number; maxTokens: number; model: string }> = {}) {
  return {
    reservationId: id,
    userId: 'u1',
    conversationId: over.conversationId ?? 'c1',
    model: over.model ?? MODEL,
    bodyBytes: over.bodyBytes ?? 3000,
    maxTokens: over.maxTokens ?? 1000,
  };
}

function funded(credits = 100_000, limits = DEFAULT_LIMITS) {
  const core = ledger(limits);
  core.grant({ id: 'lot1', credits, expiresAt: FUTURE, paymentReference: 'pay1' });
  return core;
}

describe('reserve refusals', () => {
  it('refuses an org whose plan is not entitled', () => {
    const core = funded();
    core.setEntitled(false);
    expect(core.reserve(request('r1'), NOW, false)).toEqual({ ok: false, code: 'PLAN_NOT_ENTITLED' });
  });

  it('refuses a blocked org and a globally paused tier', () => {
    const core = funded();
    core.setBlocked(true);
    expect(core.reserve(request('r1'), NOW, false)).toEqual({ ok: false, code: 'ORG_BLOCKED' });
    core.setBlocked(false);
    expect(core.reserve(request('r1'), NOW, true)).toEqual({ ok: false, code: 'GLOBAL_PAUSED' });
  });

  it('refuses a model absent from the price table', () => {
    expect(funded().reserve(request('r1', { model: 'x/unknown' }), NOW, false)).toEqual({
      ok: false,
      code: 'MODEL_NOT_ALLOWED',
    });
  });

  it('refuses when the balance is below the worst case', () => {
    const core = funded(1);
    expect(core.reserve(request('r1', { maxTokens: 8000 }), NOW, false)).toEqual({
      ok: false,
      code: 'INSUFFICIENT_CREDITS',
    });
  });

  it('refuses past the daily cap', () => {
    const core = funded(100_000, { ...DEFAULT_LIMITS, dailyCreditCap: 1 });
    expect(core.reserve(request('r1', { maxTokens: 8000 }), NOW, false)).toEqual({
      ok: false,
      code: 'DAILY_CAP',
    });
  });

  it('refuses a fourth concurrent stream', () => {
    const core = funded();
    for (const id of ['a', 'b', 'c']) expect(core.reserve(request(id), NOW, false).ok).toBe(true);
    expect(core.reserve(request('d'), NOW, false)).toEqual({ ok: false, code: 'TOO_MANY_STREAMS' });
  });

  it('refuses past the conversation token cap', () => {
    const core = funded(100_000, { ...DEFAULT_LIMITS, conversationTokenCap: 1500 });
    expect(core.reserve(request('r1', { maxTokens: 1000, bodyBytes: 300 }), NOW, false).ok).toBe(true);
    expect(core.release('r1')).toBe(true);
    expect(core.reserve(request('r2', { maxTokens: 1000, bodyBytes: 3000 }), NOW, false)).toEqual({
      ok: false,
      code: 'CONVERSATION_TOKEN_CAP',
    });
  });

  it('refuses past the loop depth of a conversation', () => {
    const core = funded(100_000, { ...DEFAULT_LIMITS, loopDepth: 2 });
    for (const id of ['a', 'b']) {
      expect(core.reserve(request(id), NOW, false).ok).toBe(true);
      core.commit(id, { promptTokens: 1, completionTokens: 1 }, NOW);
    }
    expect(core.reserve(request('c'), NOW, false)).toEqual({ ok: false, code: 'LOOP_DEPTH' });
    expect(core.reserve(request('d', { conversationId: 'other' }), NOW, false).ok).toBe(true);
  });

  it('clamps max_tokens to 8192', () => {
    const answer = funded().reserve(request('r1', { maxTokens: 50_000 }), NOW, false);
    expect(answer.ok && answer.maxTokens).toBe(8192);
  });
});

describe('commit', () => {
  it('charges the reported usage and frees the rest of the reservation', () => {
    const core = funded(10_000);
    const reserved = core.reserve(request('r1'), NOW, false);
    expect(reserved.ok).toBe(true);
    if (!reserved.ok) return;
    expect(core.balance(new Date(NOW).toISOString())).toBe(10_000 - reserved.credits);
    const done = core.commit('r1', { promptTokens: 100, completionTokens: 10 }, NOW);
    expect(done.ok && done.charged).toBeLessThan(reserved.credits);
    expect(done.ok && done.balance).toBe(10_000 - (done.ok ? done.charged : 0));
    expect(done.ok && done.history).toMatchObject({ kind: 'commit', reservationId: 'r1', inputTokens: 100 });
  });

  it('commits a reservation without usage in full, and only once', () => {
    const core = funded(10_000);
    const reserved = core.reserve(request('r1'), NOW, false);
    const done = core.commit('r1', undefined, NOW);
    expect(done.ok && done.charged).toBe(reserved.ok ? reserved.credits : -1);
    expect(core.commit('r1', undefined, NOW)).toEqual({ ok: false, code: 'RESERVATION_UNKNOWN' });
  });

  it('consumes the lot that expires first, and never drives a balance below zero', () => {
    const core = ledger();
    core.grant({ id: 'late', credits: 50, expiresAt: '2028-01-01T00:00:00.000Z', paymentReference: 'p2' });
    core.grant({ id: 'soon', credits: 50, expiresAt: '2027-01-01T00:00:00.000Z', paymentReference: 'p1' });
    expect(core.reserve(request('r1', { bodyBytes: 3, maxTokens: 1 }), NOW, false).ok).toBe(true);
    const first = core.commit('r1', { promptTokens: 1_000_000, completionTokens: 100_000 }, NOW);
    expect(first.ok && first.history.lotId).toBe('soon');
    expect(first.ok && first.charged).toBe(100);
    expect(first.ok && first.balance).toBe(0);
  });

  it('counts an expired lot as no balance', () => {
    const core = ledger();
    core.grant({ id: 'old', credits: 10_000, expiresAt: '2026-11-01T00:00:00.000Z', paymentReference: 'p' });
    expect(core.reserve(request('r1'), NOW, false)).toEqual({ ok: false, code: 'INSUFFICIENT_CREDITS' });
  });
});

describe('the 10-minute alarm', () => {
  it('commits a stale reservation in full and leaves a fresh one', () => {
    const core = funded(10_000);
    core.reserve(request('old'), NOW, false);
    core.reserve(request('fresh'), NOW + RESERVATION_TTL_MS - 1000, false);
    expect(core.nextExpiryMs()).toBe(NOW + RESERVATION_TTL_MS);
    const rows = core.expireReservations(NOW + RESERVATION_TTL_MS);
    expect(rows.map((row) => row.reservationId)).toEqual(['old']);
    expect(core.nextExpiryMs()).toBe(NOW + 2 * RESERVATION_TTL_MS - 1000);
  });
});

describe('concurrent reservations', () => {
  it('never overdraw the balance', () => {
    const core = funded(100, { ...DEFAULT_LIMITS, maxStreams: 100 });
    const one = core.reserve(request('probe'), NOW, false);
    expect(one.ok).toBe(true);
    if (!one.ok) return;
    core.release('probe');
    const attempts = Array.from({ length: 50 }, (_, i) => core.reserve(request(`r${i}`, { conversationId: `c${i}` }), NOW, false));
    const granted = attempts.filter((a) => a.ok).length;
    expect(granted).toBe(Math.floor(100 / one.credits));
    expect(granted).toBeLessThan(50);
    expect(core.balance(new Date(NOW).toISOString())).toBe(100 - granted * one.credits);
    expect(attempts.filter((a) => !a.ok).every((a) => !a.ok && a.code === 'INSUFFICIENT_CREDITS')).toBe(true);
  });
});

describe('refund', () => {
  it('returns only the unused part of an unexpired lot and refuses an expired one', () => {
    const core = funded(1_000);
    core.reserve(request('r1', { bodyBytes: 3, maxTokens: 1 }), NOW, false);
    core.commit('r1', { promptTokens: 100_000, completionTokens: 0 }, NOW);
    const used = 1_000 - core.balance(new Date(NOW).toISOString());
    expect(core.refundLot('lot1', new Date(NOW).toISOString())).toBe(1_000 - used);
    expect(core.balance(new Date(NOW).toISOString())).toBe(0);
    expect(core.refundLot('lot1', '2030-01-01T00:00:00.000Z')).toBeNull();
  });
});
