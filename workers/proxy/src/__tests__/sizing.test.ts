/**
 * Per-org instance sizing (agent/plans/PLAN-executor-durable-object-policy.md Design item 4, box W4): the rule in src/sizing.ts, and the OOM flag OrgExecutor hands the Worker to apply it.
 */

import { describe, expect, it } from 'vitest';
import { OrgExecutor, type OrgExecutorEnv } from '../org-executor';
import {
  chooseSize,
  heavyFullFallback,
  INSTANCE_BY_SIZE,
  OOM_WINDOW_MS,
  oomRecent,
  tierOf,
} from '../sizing';

const NOW = Date.UTC(2026, 9, 28, 12, 0, 0);
const DAY_MS = 24 * 60 * 60 * 1000;

describe('the instance literals', () => {
  it('HEAVY is standard-1 and LIGHT is the basic-equivalent custom size S1 chose', () => {
    expect(INSTANCE_BY_SIZE.heavy.instance).toBe('standard-1');
    expect(INSTANCE_BY_SIZE.light.instance).toEqual({ vcpu: 0.25, memoryMib: 1024, diskMb: 4000 });
  });
});

describe('tierOf', () => {
  it("only the exact string 'high' is high; a missing or unknown tier is standard", () => {
    expect(tierOf('high')).toBe('high');
    for (const value of ['standard', undefined, null, '', 'HIGH', 'enterprise', 1, {}]) {
      expect(tierOf(value)).toBe('standard');
    }
  });
});

describe('chooseSize', () => {
  it("tier 'high' gets heavy, by tier", () => {
    expect(chooseSize('high', undefined, NOW)).toEqual({ size: 'heavy', cause: 'tier' });
  });

  it('a standard tier with no OOM flag gets light', () => {
    expect(chooseSize('standard', undefined, NOW)).toEqual({ size: 'light', cause: 'none' });
  });

  it('an OOM flag within 7 days gets heavy, by OOM, and outranks the tier', () => {
    for (const age of [0, DAY_MS, 6 * DAY_MS, OOM_WINDOW_MS]) {
      expect(chooseSize('standard', NOW - age, NOW)).toEqual({ size: 'heavy', cause: 'oom' });
      expect(chooseSize('high', NOW - age, NOW)).toEqual({ size: 'heavy', cause: 'oom' });
    }
  });

  it('an 8-day-old OOM flag gets light (or heavy by tier alone)', () => {
    expect(chooseSize('standard', NOW - 8 * DAY_MS, NOW)).toEqual({ size: 'light', cause: 'none' });
    expect(chooseSize('high', NOW - 8 * DAY_MS, NOW)).toEqual({ size: 'heavy', cause: 'tier' });
  });

  it('a non-finite flag is no flag', () => {
    expect(oomRecent(Number.NaN, NOW)).toBe(false);
    expect(oomRecent(undefined, NOW)).toBe(false);
  });
});

describe('heavyFullFallback', () => {
  it('a high-tier org falls back to light; an OOM-flagged org has no fallback', () => {
    expect(heavyFullFallback({ size: 'heavy', cause: 'tier' })).toBe('light');
    expect(heavyFullFallback({ size: 'heavy', cause: 'oom' })).toBeUndefined();
    expect(heavyFullFallback({ size: 'light', cause: 'none' })).toBeUndefined();
  });
});

describe('OrgExecutor.oomAt', () => {
  function executor(stored: Map<string, unknown>): OrgExecutor {
    const ctx = {
      id: { toString: () => 'id:org-a', equals: () => true },
      container: undefined,
      storage: {
        get: (key: string) => Promise.resolve(stored.get(key)),
        put: (key: string, value: unknown) => Promise.resolve(void stored.set(key, value)),
        delete: (key: string) => Promise.resolve(stored.delete(key)),
        setAlarm: () => Promise.resolve(),
      },
      blockConcurrencyWhile: (run: () => Promise<unknown>) => run(),
    };
    return new OrgExecutor(ctx as never, {} as OrgExecutorEnv);
  }

  it('answers the stored OOM instant, or undefined when none was recorded', async () => {
    expect(await executor(new Map()).oomAt()).toBeUndefined();
    expect(await executor(new Map([['oomAt', NOW - DAY_MS]])).oomAt()).toBe(NOW - DAY_MS);
  });
});
