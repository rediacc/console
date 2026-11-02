/**
 * The scheduling rules the declared target adds (D-rpo, decision O6): a 5-minute floor on a target AND
 * on a cron schedule, a target length a timer can repeat, and per-repo targets that are validated where
 * the strategy is bound, not at 03:00.
 */

import { describe, expect, it } from 'vitest';
import { cronMinGapSeconds } from '../backup/backup-schedule-interval.js';
import type { ScheduledStrategy } from '../backup/backup-schedule-targets.js';
import { strategyUnschedulableReason } from '../backup/backup-strategy-validate.js';

const hosted = { kind: 'hosted-service' as const, name: 'chunks' };
const strategy = (extra: Partial<ScheduledStrategy> = {}): ScheduledStrategy => ({
  schedule: '0 3 * * *',
  destinations: [hosted],
  ...extra,
});

describe('cronMinGapSeconds', () => {
  it.each([
    ['* * * * *', 60],
    ['*/2 * * * *', 120],
    ['0,3 * * * *', 180],
    ['*/5 * * * *', 300],
    ['0 * * * *', 3600],
    ['0 3 * * *', 86_400],
  ])('%s is %d seconds', (cron, seconds) => {
    expect(cronMinGapSeconds(cron)).toBe(seconds);
  });
});

describe('cron schedules below the floor are refused (O6)', () => {
  it.each(['* * * * *', '*/4 * * * *', '0,3 * * * *'])('refuses %s', (schedule) => {
    expect(strategyUnschedulableReason(strategy({ schedule }))).toMatch(/at least 5 minutes/);
  });

  it('accepts exactly 5 minutes (control)', () => {
    expect(strategyUnschedulableReason(strategy({ schedule: '*/5 * * * *' }))).toBeUndefined();
  });

  it('refuses a too-frequent deep-verify cron the same way', () => {
    expect(
      strategyUnschedulableReason(strategy({ verify: { deepSchedule: '*/2 * * * *' } }))
    ).toMatch(/at least 5 minutes/);
  });
});

describe('declared targets', () => {
  it('accepts a strategy rpo and a per-repo target (control)', () => {
    expect(
      strategyUnschedulableReason(strategy({ rpo: '15m', repoTargets: { mail: { rpo: '30m' } } }))
    ).toBeUndefined();
  });

  it('refuses a strategy rpo under 5 minutes or one the timer cannot repeat', () => {
    expect(strategyUnschedulableReason(strategy({ rpo: '2m' }))).toMatch(/Invalid rpo "2m"/);
    expect(strategyUnschedulableReason(strategy({ rpo: '7m' }))).toMatch(/divide 60/);
  });

  it('names the repo whose target is refused', () => {
    expect(
      strategyUnschedulableReason(strategy({ repoTargets: { 'mail:trial': { rpo: '1m' } } }))
    ).toMatch(/Per-repo target for "mail:trial".*below 5 minutes/);
  });

  it('refuses an unreadable cell size or duration that bypassed the schema (hand-edited config)', () => {
    const bad = (target: Record<string, string>) =>
      strategyUnschedulableReason(
        strategy({ repoTargets: { mail: { rpo: '15m', ...target } as never } })
      );
    expect(bad({ cellSize: 'big' })).toMatch(/cellSize/);
    expect(bad({ indexEvery: 'often' })).toMatch(/indexEvery/);
    expect(bad({ hookTimeout: '10 minutes' })).toMatch(/hookTimeout/);
    expect(bad({ hookFailure: 'ignore' })).toMatch(/hookFailure/);
  });

  it('a strategy with an rpo is not held to the floor on its unused cron', () => {
    expect(
      strategyUnschedulableReason(strategy({ schedule: '* * * * *', rpo: '15m' }))
    ).toBeUndefined();
  });
});
