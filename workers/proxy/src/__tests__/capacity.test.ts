/**
 * `ExecutorCapacity` (agent/plans/PLAN-executor-durable-object-policy.md box W2): the cap of 25 per target, the heavy sub-cap, expiring leases and the input gate.
 *
 * `cloudflare:workers` exists only inside workerd, so `DurableObject` is replaced by a base class that keeps `ctx` and `env` as the real one does. The SQL storage is a real SQLite engine (node:sqlite) behind the `exec` cursor shape, so the coordinator's queries run as written rather than against a hand-rolled table. The fake's alarm calls yield to the event loop, the way real storage I/O does, so a coordinator that awaited between counting and admitting would let concurrent acquires interleave and the input-gate test would catch it.
 */

import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('cloudflare:workers', () => ({
  DurableObject: class {
    constructor(
      protected ctx: unknown,
      protected env: unknown
    ) {}
  },
}));

import {
  CAPACITY_NAME,
  type CapacityEnv,
  capacityStub,
  capFrom,
  ExecutorCapacity,
  HARD_CAP,
  HARD_HEAVY_CAP,
  LEASE_MS,
} from '../capacity';
import { executorName } from '../placement';

const T0 = Date.UTC(2026, 9, 26, 12, 0, 0);

interface FakeState {
  ctx: DurableObjectState;
  alarmAt: () => number | null;
}

/** The `ctx.storage.sql` cursor shape over one in-memory SQLite database. */
function fakeSql(db: DatabaseSync): SqlStorage {
  return {
    exec: (query: string, ...bindings: (string | number | null)[]) => {
      const rows = db.prepare(query).all(...bindings) as Record<string, SqlStorageValue>[];
      return {
        toArray: () => rows,
        one: () => {
          if (rows.length !== 1) throw new Error(`expected one row, got ${rows.length}`);
          return rows[0];
        },
      };
    },
  } as unknown as SqlStorage;
}

function fakeState(): FakeState {
  const db = new DatabaseSync(':memory:');
  let alarm: number | null = null;
  const yieldTurn = () => new Promise<void>((resolve) => setTimeout(resolve, 0));
  const storage = {
    sql: fakeSql(db),
    getAlarm: async () => {
      await yieldTurn();
      return alarm;
    },
    setAlarm: async (at: number | Date) => {
      await yieldTurn();
      alarm = typeof at === 'number' ? at : at.getTime();
    },
    deleteAlarm: async () => {
      await yieldTurn();
      alarm = null;
    },
  };
  return {
    ctx: { storage } as unknown as DurableObjectState,
    alarmAt: () => alarm,
  };
}

function coordinator(env: CapacityEnv = {}): { cap: ExecutorCapacity; state: FakeState } {
  const state = fakeState();
  return { cap: new ExecutorCapacity(state.ctx, env), state };
}

const orgs = (n: number, prefix = 'org') => Array.from({ length: n }, (_, i) => `${prefix}-${i}`);

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(T0);
});

afterEach(() => {
  vi.useRealTimers();
});

describe('the cap', () => {
  it('admits 25 distinct orgs and answers full to the 26th', async () => {
    const { cap } = coordinator();
    for (const org of orgs(25)) expect(await cap.acquire(org, 'light')).toEqual({ ok: true });
    expect(await cap.acquire('org-25', 'light')).toEqual({ ok: false, reason: 'full' });
    expect(cap.count()).toEqual({ total: 25, heavy: 0, cap: 25, heavyCap: 5 });
  });

  it('does not count a re-acquire by a held org twice', async () => {
    const { cap } = coordinator({ EXECUTOR_CAP: '2' });
    expect(await cap.acquire('org-a', 'light')).toEqual({ ok: true });
    expect(await cap.acquire('org-a', 'light')).toEqual({ ok: true });
    expect(await cap.acquire('org-a', 'light')).toEqual({ ok: true });
    expect(cap.count().total).toBe(1);
    expect(await cap.acquire('org-b', 'light')).toEqual({ ok: true });
    // Full now, and the held org still renews.
    expect(await cap.acquire('org-c', 'light')).toEqual({ ok: false, reason: 'full' });
    expect(await cap.acquire('org-a', 'light')).toEqual({ ok: true });
    expect(cap.count().total).toBe(2);
  });

  it('answers heavy-full to the 6th heavy acquire while a light one passes', async () => {
    const { cap } = coordinator();
    for (const org of orgs(5, 'heavy')) {
      expect(await cap.acquire(org, 'heavy')).toEqual({ ok: true });
    }
    expect(await cap.acquire('heavy-5', 'heavy')).toEqual({ ok: false, reason: 'heavy-full' });
    expect(await cap.acquire('light-0', 'light')).toEqual({ ok: true });
    // A held heavy org re-acquiring heavy is not refused by its own slot.
    expect(await cap.acquire('heavy-0', 'heavy')).toEqual({ ok: true });
    expect(cap.count()).toMatchObject({ total: 6, heavy: 5 });
  });

  it('keeps a held heavy slot when a lowered heavy cap sits below the heavy holders', async () => {
    const { cap, state } = coordinator();
    for (const org of orgs(3, 'heavy')) {
      expect(await cap.acquire(org, 'heavy')).toEqual({ ok: true });
    }
    // The same storage under a redeploy with EXECUTOR_HEAVY_CAP lowered to 1.
    const lowered = new ExecutorCapacity(state.ctx, { EXECUTOR_HEAVY_CAP: '1' });
    expect(await lowered.acquire('heavy-0', 'heavy')).toEqual({ ok: true });
    expect(await lowered.acquire('heavy-9', 'heavy')).toEqual({ ok: false, reason: 'heavy-full' });
    expect(lowered.count()).toMatchObject({ heavy: 3, heavyCap: 1 });
  });

  it('an alarm that cannot be set does not turn a written admission into a failure', async () => {
    const { cap, state } = coordinator();
    state.ctx.storage.setAlarm = () => Promise.reject(new Error('storage unavailable'));
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    expect(await cap.acquire('org-0', 'light')).toEqual({ ok: true });
    expect(cap.count()).toMatchObject({ total: 1 });
  });

  it('refuses a held light org moving to heavy when the heavy slots are taken, and keeps its light lease', async () => {
    const { cap } = coordinator({ EXECUTOR_HEAVY_CAP: '1' });
    expect(await cap.acquire('org-h', 'heavy')).toEqual({ ok: true });
    expect(await cap.acquire('org-l', 'light')).toEqual({ ok: true });
    expect(await cap.acquire('org-l', 'heavy')).toEqual({ ok: false, reason: 'heavy-full' });
    expect(cap.count()).toMatchObject({ total: 2, heavy: 1 });
    expect(await cap.renew('org-l')).toBe('held');
  });

  it('refuses an unknown size rather than counting it as light', async () => {
    const { cap } = coordinator();
    await expect(cap.acquire('org-a', 'huge' as never)).rejects.toThrow(TypeError);
    await expect(cap.acquire('', 'light')).rejects.toThrow(TypeError);
    expect(cap.count().total).toBe(0);
  });
});

describe('lease keys', () => {
  it('holds org-a:p0 and org-a:p1 as two slots', async () => {
    const { cap } = coordinator();
    expect(await cap.acquire(executorName('org-a', 0), 'light')).toEqual({ ok: true });
    expect(await cap.acquire(executorName('org-a', 1), 'light')).toEqual({ ok: true });
    expect(cap.count().total).toBe(2);
  });

  it('release of org-a:p0 leaves org-a:p1 held', async () => {
    const { cap } = coordinator();
    await cap.acquire(executorName('org-a', 0), 'light');
    await cap.acquire(executorName('org-a', 1), 'light');
    await cap.release(executorName('org-a', 0));
    expect(cap.count().total).toBe(1);
    expect(await cap.renew('org-a:p1')).toBe('held');
    expect(await cap.renew('org-a:p0')).toBe('not-held');
  });

  it('counts two placements of one org against the cap as two', async () => {
    const { cap } = coordinator({ EXECUTOR_CAP: '2' });
    await cap.acquire('org-a:p0', 'light');
    await cap.acquire('org-a:p1', 'light');
    expect(await cap.acquire('org-b:p0', 'light')).toEqual({ ok: false, reason: 'full' });
  });
});

describe('the lease', () => {
  it('frees a slot not renewed for 180 s at the next acquire', async () => {
    const { cap } = coordinator({ EXECUTOR_CAP: '1' });
    expect(await cap.acquire('org-a', 'light')).toEqual({ ok: true });
    vi.setSystemTime(T0 + LEASE_MS - 1);
    expect(await cap.acquire('org-b', 'light')).toEqual({ ok: false, reason: 'full' });
    vi.setSystemTime(T0 + LEASE_MS);
    expect(await cap.acquire('org-b', 'light')).toEqual({ ok: true });
    expect(await cap.renew('org-a')).toBe('not-held');
  });

  it('frees a slot not renewed for 180 s at the alarm, and clears the alarm once empty', async () => {
    const { cap, state } = coordinator();
    await cap.acquire('org-a', 'light');
    expect(state.alarmAt()).toBe(T0 + LEASE_MS);
    vi.setSystemTime(T0 + 60_000);
    await cap.acquire('org-b', 'heavy');
    // The alarm stays on the earliest expiry.
    expect(state.alarmAt()).toBe(T0 + LEASE_MS);

    vi.setSystemTime(T0 + LEASE_MS);
    await cap.alarm();
    expect(cap.count()).toMatchObject({ total: 1, heavy: 1 });
    expect(await cap.renew('org-a')).toBe('not-held');
    expect(state.alarmAt()).toBe(T0 + 60_000 + LEASE_MS);

    vi.setSystemTime(T0 + 60_000 + LEASE_MS);
    await cap.alarm();
    expect(cap.count().total).toBe(0);
    expect(state.alarmAt()).toBeNull();
  });

  it('renew extends a live lease, and refuses an expired one without reviving it', async () => {
    const { cap } = coordinator({ EXECUTOR_CAP: '1' });
    await cap.acquire('org-a', 'light');
    vi.setSystemTime(T0 + 120_000);
    expect(await cap.renew('org-a')).toBe('held');
    vi.setSystemTime(T0 + LEASE_MS + 10_000);
    // Past the first expiry, still inside the renewed one.
    expect(await cap.acquire('org-b', 'light')).toEqual({ ok: false, reason: 'full' });
    vi.setSystemTime(T0 + 120_000 + LEASE_MS);
    expect(await cap.renew('org-a')).toBe('not-held');
    expect(await cap.renew('org-a')).toBe('not-held');
    expect(await cap.renew('never-held')).toBe('not-held');
  });

  it('release frees the slot at once, and releasing a slot not held is a no-op', async () => {
    const { cap } = coordinator({ EXECUTOR_CAP: '1' });
    await cap.acquire('org-a', 'light');
    await cap.release('org-b');
    expect(cap.count().total).toBe(1);
    await cap.release('org-a');
    expect(await cap.acquire('org-b', 'light')).toEqual({ ok: true });
  });

  it('count is read only: it skips an expired row without deleting it', async () => {
    const { cap } = coordinator();
    await cap.acquire('org-a', 'light');
    vi.setSystemTime(T0 + LEASE_MS);
    expect(cap.count().total).toBe(0);
  });
});

describe('the configured caps', () => {
  it('EXECUTOR_CAP = "2" caps at 2', async () => {
    const { cap } = coordinator({ EXECUTOR_CAP: '2' });
    expect(await cap.acquire('org-0', 'light')).toEqual({ ok: true });
    expect(await cap.acquire('org-1', 'light')).toEqual({ ok: true });
    expect(await cap.acquire('org-2', 'light')).toEqual({ ok: false, reason: 'full' });
    expect(cap.count().cap).toBe(2);
  });

  it('EXECUTOR_CAP = "40" caps at 25', async () => {
    const { cap } = coordinator({ EXECUTOR_CAP: '40' });
    for (const org of orgs(25)) expect(await cap.acquire(org, 'light')).toEqual({ ok: true });
    expect(await cap.acquire('org-25', 'light')).toEqual({ ok: false, reason: 'full' });
    expect(cap.count().cap).toBe(HARD_CAP);
  });

  it.each([
    ['missing', undefined],
    ['empty', ''],
    ['words', 'lots'],
    ['trailing garbage', '2abc'],
    ['negative', '-1'],
    ['fractional', '2.5'],
    ['padded', ' 2'],
  ])('a %s EXECUTOR_CAP caps at 25', async (_label, value) => {
    const { cap } = coordinator({ EXECUTOR_CAP: value });
    for (const org of orgs(25)) expect(await cap.acquire(org, 'light')).toEqual({ ok: true });
    expect(await cap.acquire('org-25', 'light')).toEqual({ ok: false, reason: 'full' });
  });

  it('EXECUTOR_HEAVY_CAP is bounded by HARD_HEAVY_CAP the same way', () => {
    expect(capFrom('2', HARD_HEAVY_CAP)).toBe(2);
    expect(capFrom('9', HARD_HEAVY_CAP)).toBe(HARD_HEAVY_CAP);
    expect(capFrom(undefined, HARD_HEAVY_CAP)).toBe(HARD_HEAVY_CAP);
    expect(capFrom('x', HARD_HEAVY_CAP)).toBe(HARD_HEAVY_CAP);
  });
});

describe('the input gate', () => {
  it('50 concurrent acquires never admit more than the cap', async () => {
    const { cap } = coordinator();
    const answers = await Promise.all(orgs(50).map((org) => cap.acquire(org, 'light')));
    expect(answers.filter((a) => a.ok)).toHaveLength(HARD_CAP);
    expect(answers.filter((a) => !a.ok && a.reason === 'full')).toHaveLength(50 - HARD_CAP);
    expect(cap.count().total).toBe(HARD_CAP);
  });

  it('50 concurrent heavy acquires never admit more than the heavy sub-cap', async () => {
    const { cap } = coordinator();
    const answers = await Promise.all(orgs(50).map((org) => cap.acquire(org, 'heavy')));
    expect(answers.filter((a) => a.ok)).toHaveLength(HARD_HEAVY_CAP);
    expect(cap.count()).toMatchObject({ total: HARD_HEAVY_CAP, heavy: HARD_HEAVY_CAP });
  });
});

describe('capacityStub', () => {
  it('names the one coordinator instance, whatever the caller', () => {
    const names: string[] = [];
    const namespace = {
      idFromName: (name: string) => {
        names.push(name);
        return { name } as unknown as DurableObjectId;
      },
      get: (id: DurableObjectId) => ({ id }) as unknown as DurableObjectStub<ExecutorCapacity>,
    } as unknown as DurableObjectNamespace<ExecutorCapacity>;
    capacityStub(namespace);
    capacityStub(namespace);
    expect(names).toEqual([CAPACITY_NAME, CAPACITY_NAME]);
    expect(CAPACITY_NAME).toBe('capacity:v2');
  });
});

describe('the coordinator is reached only through capacityStub', () => {
  it('no source file but capacity.ts names the instance or the idFromName call for it', () => {
    const root = join(__dirname, '..');
    const files = (readdirSync(root, { recursive: true }) as string[]).filter(
      (f) => f.endsWith('.ts') && !f.includes('__tests__') && f !== 'capacity.ts'
    );
    expect(files.length).toBeGreaterThan(0);
    const offenders = files.filter((f) => {
      const text = readFileSync(join(root, f), 'utf8');
      return /CAPACITY_NAME|capacity:v[0-9]+|idFromName\(\s*['"`]capacity/.test(text);
    });
    expect(offenders).toEqual([]);
  });
});
