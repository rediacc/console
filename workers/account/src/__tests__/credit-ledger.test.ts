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

const { CreditLedger, CreditLedgerCore, DEFAULT_LIMITS, HISTORY_RETRY_MS, RESERVATION_TTL_MS } =
  await import('../credit-ledger.js');

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

function request(
  id: string,
  over: Partial<{
    conversationId: string;
    bodyBytes: number;
    maxTokens: number;
    model: string;
  }> = {}
) {
  return {
    reservationId: id,
    userId: 'u1',
    conversationId: 'c1',
    model: MODEL,
    bodyBytes: 3000,
    maxTokens: 1000,
    ...over,
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
    expect(core.reserve(request('r1'), NOW, false)).toEqual({
      ok: false,
      code: 'PLAN_NOT_ENTITLED',
    });
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
    expect(core.reserve(request('r1', { maxTokens: 1000, bodyBytes: 300 }), NOW, false).ok).toBe(
      true
    );
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
    expect(done.ok && done.history).toMatchObject({
      kind: 'commit',
      reservationId: 'r1',
      inputTokens: 100,
    });
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
    core.grant({
      id: 'late',
      credits: 50,
      expiresAt: '2028-01-01T00:00:00.000Z',
      paymentReference: 'p2',
    });
    core.grant({
      id: 'soon',
      credits: 50,
      expiresAt: '2027-01-01T00:00:00.000Z',
      paymentReference: 'p1',
    });
    expect(core.reserve(request('r1', { bodyBytes: 3, maxTokens: 1 }), NOW, false).ok).toBe(true);
    const first = core.commit('r1', { promptTokens: 1_000_000, completionTokens: 100_000 }, NOW);
    expect(first.ok && first.history.lotId).toBe('soon');
    expect(first.ok && first.charged).toBe(100);
    expect(first.ok && first.balance).toBe(0);
  });

  it('counts an expired lot as no balance', () => {
    const core = ledger();
    core.grant({
      id: 'old',
      credits: 10_000,
      expiresAt: '2026-11-01T00:00:00.000Z',
      paymentReference: 'p',
    });
    expect(core.reserve(request('r1'), NOW, false)).toEqual({
      ok: false,
      code: 'INSUFFICIENT_CREDITS',
    });
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

describe('reservations decided one after another', () => {
  it('never overdraw the balance when many are asked for in a row', () => {
    const core = funded(100, { ...DEFAULT_LIMITS, maxStreams: 100 });
    const one = core.reserve(request('probe'), NOW, false);
    expect(one.ok).toBe(true);
    if (!one.ok) return;
    core.release('probe');
    const attempts = Array.from({ length: 50 }, (_, i) =>
      core.reserve(request(`r${i}`, { conversationId: `c${i}` }), NOW, false)
    );
    const granted = attempts.filter((a) => a.ok).length;
    expect(granted).toBe(Math.floor(100 / one.credits));
    expect(granted).toBeLessThan(50);
    expect(core.balance(new Date(NOW).toISOString())).toBe(100 - granted * one.credits);
    expect(
      attempts.filter((a) => !a.ok).every((a) => !a.ok && a.code === 'INSUFFICIENT_CREDITS')
    ).toBe(true);
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

describe('reconcile adjustments', () => {
  const nowIso = new Date(NOW).toISOString();
  const AFTER_EXPIRY = '2028-01-01T00:00:00.000Z';

  it('adjustLot adds credit back to an unexpired lot and reports the amount applied', () => {
    const core = funded(1_000);
    expect(core.adjustLot('lot1', 250, nowIso)).toBe(250);
    expect(core.balance(nowIso)).toBe(1_250);
  });

  it('adjustLot applies nothing to an unknown or expired lot or to a bad amount', () => {
    const core = funded(1_000);
    expect(core.adjustLot('nope', 5, nowIso)).toBe(0);
    expect(core.adjustLot('lot1', 5, AFTER_EXPIRY)).toBe(0);
    expect(core.adjustLot('lot1', 0, nowIso)).toBe(0);
    expect(core.adjustLot('lot1', -3, nowIso)).toBe(0);
    expect(core.adjustLot('lot1', 1.5, nowIso)).toBe(0);
    expect(core.balance(nowIso)).toBe(1_000);
  });

  it('lapseLot zeroes an expired lot, returns what it held, and finds nothing the second time', () => {
    const core = funded(1_000);
    expect(core.lapseLot('lot1', AFTER_EXPIRY)).toBe(1_000);
    expect(core.lapseLot('lot1', AFTER_EXPIRY)).toBe(0);
    expect(core.balance(nowIso)).toBe(0);
  });

  it('lapseLot leaves an unexpired or unknown lot alone', () => {
    const core = funded(1_000);
    expect(core.lapseLot('lot1', nowIso)).toBe(0);
    expect(core.lapseLot('nope', AFTER_EXPIRY)).toBe(0);
    expect(core.balance(nowIso)).toBe(1_000);
  });
});

describe('grant', () => {
  it('a repeated id changes nothing, so a retried grant never doubles', () => {
    const core = funded(1_000);
    core.grant({ id: 'lot1', credits: 1_000, expiresAt: FUTURE, paymentReference: 'pay1' });
    expect(core.balance(new Date(NOW).toISOString())).toBe(1_000);
  });

  it('refuses a credit count that is not a whole number of at least 1', () => {
    const core = ledger();
    for (const credits of [0, -5, 1.5, Number.NaN]) {
      expect(() =>
        core.grant({ id: 'bad', credits, expiresAt: FUTURE, paymentReference: 'p' })
      ).toThrow(RangeError);
    }
    expect(core.balance(new Date(NOW).toISOString())).toBe(0);
  });

  it('stores the expiry in toISOString form, so a value without milliseconds is not read as unexpired', () => {
    const core = ledger();
    // 09:59:59.500 + a same-second expiry '10:00:00Z' sorts AFTER now (10:00:00.000Z) as a raw string, though it is not later.
    core.grant({
      id: 'edge',
      credits: 500,
      expiresAt: '2026-11-25T10:00:00Z',
      paymentReference: 'p',
    });
    expect(core.balance(new Date(NOW).toISOString())).toBe(0);
    expect(core.balance(new Date(NOW - 1000).toISOString())).toBe(500);
  });

  it('rewrites a lot stored with a raw expiry when the ledger opens', () => {
    const sqlite = new DatabaseSync(':memory:');
    const sql = {
      exec: (query: string, ...bindings: unknown[]) => {
        const rows = sqlite.prepare(query).all(...bindings);
        return { toArray: () => rows };
      },
    };
    const first = new CreditLedgerCore(sql);
    sql.exec(
      "INSERT INTO lots (id, credits_granted, credits_remaining, expires_at, payment_reference) VALUES ('old', 500, 500, '2026-11-25T10:00:00Z', 'p')"
    );
    expect(first.balance(new Date(NOW).toISOString())).toBe(500);
    const reopened = new CreditLedgerCore(sql);
    expect(reopened.balance(new Date(NOW).toISOString())).toBe(0);
    // Control: a lot already in the milliseconds form is left as it was.
    sql.exec(
      "INSERT INTO lots (id, credits_granted, credits_remaining, expires_at, payment_reference) VALUES ('ok', 7, 7, '2099-01-01T00:00:00.000Z', 'p')"
    );
    new CreditLedgerCore(sql);
    expect(sql.exec("SELECT expires_at e FROM lots WHERE id='ok'").toArray()).toEqual([
      { e: '2099-01-01T00:00:00.000Z' },
    ]);
  });

  it('refuses an expiry that is not a timestamp', () => {
    expect(() =>
      ledger().grant({ id: 'x', credits: 5, expiresAt: 'soon', paymentReference: 'p' })
    ).toThrow(RangeError);
  });
});

describe('commit with reported usage that is not whole and non-negative', () => {
  it('charges the whole reservation instead of a negative amount', () => {
    const core = funded(10_000);
    const reserved = core.reserve(request('r1'), NOW, false);
    const done = core.commit('r1', { promptTokens: -1_000_000, completionTokens: 5 }, NOW);
    expect(reserved.ok && done.ok && done.charged).toBe(reserved.ok ? reserved.credits : -1);
    expect(done.ok && done.history.credits).toBeLessThan(0);
    expect(core.balance(new Date(NOW).toISOString())).toBe(
      10_000 - (reserved.ok ? reserved.credits : 0)
    );
  });

  it('control: honest usage is still charged by what was used', () => {
    const core = funded(10_000);
    core.reserve(request('r1'), NOW, false);
    const done = core.commit('r1', { promptTokens: 10, completionTokens: 10 }, NOW);
    expect(done.ok && done.history.inputTokens).toBe(10);
  });
});

/** The Durable Object class over real SQLite storage and a scripted D1, as the Worker runs it. */
function durableObject(db: { first: () => unknown; run: (args: unknown[]) => unknown }) {
  const sqlite = new DatabaseSync(':memory:');
  let alarm: number | null = null;
  const ctx = {
    id: { name: 'org1' },
    storage: {
      sql: {
        exec: (query: string, ...bindings: unknown[]) => {
          const rows = sqlite.prepare(query).all(...bindings);
          return { toArray: () => rows };
        },
      },
      getAlarm: () => Promise.resolve(alarm),
      setAlarm: (at: number) => {
        alarm = at;
        return Promise.resolve();
      },
    },
  };
  const inserted: unknown[][] = [];
  const env = {
    DB: {
      prepare: () => ({
        first: () => Promise.resolve(db.first()),
        bind: (...args: unknown[]) => ({
          run: () => {
            inserted.push(args);
            db.run(args);
            return Promise.resolve();
          },
        }),
      }),
    },
  };
  const object = new CreditLedger(ctx as never, env as never);
  object.setEntitled(true);
  object.grant({ id: 'lot1', credits: 100_000, expiresAt: FUTURE, paymentReference: 'pay1' });
  return { object, inserted, alarm: () => alarm };
}

describe('the pause read fails closed', () => {
  it('refuses every reserve with GLOBAL_PAUSED when the D1 read fails', async () => {
    const { object } = durableObject({
      first: () => {
        throw new Error('D1 is down');
      },
      run: () => undefined,
    });
    expect(await object.reserve(request('r1'))).toEqual({ ok: false, code: 'GLOBAL_PAUSED' });
  });

  it('control: an unpaused control row lets the reserve through', async () => {
    const { object } = durableObject({ first: () => ({ p: null }), run: () => undefined });
    expect((await object.reserve(request('r1'))).ok).toBe(true);
  });
});

describe('reservations that interleave at the Durable Object boundary', () => {
  it('never overdraw when many reserve calls are in flight at once', async () => {
    const { object } = durableObject({ first: () => ({ p: null }), run: () => undefined });
    const one = await object.reserve(request('probe'));
    if (!one.ok) throw new Error('probe refused');
    object.release('probe');
    // Fund for exactly two reservations, then ask for ten at once (stream limit 3 is above two).
    const fresh = durableObject({ first: () => ({ p: null }), run: () => undefined });
    const small = fresh.object;
    small.refundLot('lot1');
    small.grant({
      id: 'lot2',
      credits: one.credits * 2 + 1,
      expiresAt: FUTURE,
      paymentReference: 'p2',
    });
    const answers = await Promise.all(
      Array.from({ length: 10 }, (_, i) =>
        small.reserve(request(`r${i}`, { conversationId: `c${i}` }))
      )
    );
    expect(answers.filter((a) => a.ok)).toHaveLength(2);
    expect(small.balance()).toBe(1);
  });
});

describe('the history row of a charge', () => {
  it('survives a failed D1 write and is written once by the retry', async () => {
    const d1 = { failing: true as boolean };
    const { object, inserted, alarm } = durableObject({
      first: () => ({ p: null }),
      run: () => {
        if (d1.failing) throw new Error('D1 write failed');
      },
    });
    const first = await object.reserve(request('r1'));
    expect(first.ok).toBe(true);
    const done = await object.commit('org1', 'r1');
    // The charge stands and the answer is ok; the failed row is kept and a retry is armed.
    expect(done.ok).toBe(true);
    expect(inserted).toHaveLength(1);
    expect(alarm()).not.toBeNull();
    expect((alarm() ?? 0) - Date.now()).toBeLessThanOrEqual(HISTORY_RETRY_MS);

    d1.failing = false;
    await object.alarm();
    expect(inserted).toHaveLength(2);
    // The retry carries the id of the first attempt, so a write that had landed unseen is not doubled.
    expect(inserted[1]?.[0]).toBe(inserted[0]?.[0]);
    // Nothing is left to retry.
    await object.alarm();
    expect(inserted).toHaveLength(2);
  });

  it('a row D1 rejects for good does not hold the rows behind it', async () => {
    const d1 = { failing: true as boolean, poison: 'r1' };
    const { object, inserted } = durableObject({
      first: () => ({ p: null }),
      run: (args) => {
        if (d1.failing || args[5] === d1.poison) throw new Error('D1 write failed');
      },
    });
    for (const id of ['r1', 'r2']) {
      expect((await object.reserve(request(id))).ok).toBe(true);
      await object.commit('org1', id);
    }
    d1.failing = false;
    inserted.length = 0;
    await object.alarm();
    // r1 fails again, r2 behind it still lands.
    expect(inserted.map((a) => a[5])).toEqual(['r1', 'r2']);
    // The poisoned row is retried, behind the rest, and nothing else is left.
    inserted.length = 0;
    await object.alarm();
    expect(inserted.map((a) => a[5])).toEqual(['r1']);
  });

  it('control: a write that succeeds leaves nothing queued and no retry armed', async () => {
    const { object, inserted, alarm } = durableObject({
      first: () => ({ p: null }),
      run: () => undefined,
    });
    await object.reserve(request('r1'));
    await object.commit('org1', 'r1');
    expect(inserted).toHaveLength(1);
    await object.alarm();
    expect(inserted).toHaveLength(1);
    // Only the reservation's own 10-minute alarm stands, not a retry.
    expect((alarm() ?? 0) - Date.now()).toBeGreaterThan(HISTORY_RETRY_MS);
  });
});
