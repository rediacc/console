/**
 * `backup.strategies[].retention` stops being write-only.
 *
 * Until the account server grew retentionPolicySweep, `RetentionPolicySchema`
 * had no writer, no reader and no consumer anywhere in the repo — a declared
 * shape whose own doc comment described enforcement that did not exist. Now
 * the CLI pushes it and the server enforces it, so the two distinctions the
 * push path depends on need pinning:
 *
 * - an ABSENT `retention` (no policy pushed at all) must stay distinguishable
 *   from `retention: {}` (a policy that is present and declares no bound). If
 *   the schema collapsed them, the push path could not tell "leave this
 *   lineage alone" from "policy present, unbounded", and would either delete
 *   nothing forever or clear a policy it should have left in place.
 * - a knob must be a non-negative integer. A float or a negative silently
 *   becomes a nonsense keep-set on the server, which deletes snapshots.
 */

import { describe, expect, it } from 'vitest';
import { RdcConfigSchema } from '../schemas.js';

function configWith(retention?: unknown) {
  const strategy: Record<string, unknown> = {
    destinations: [{ kind: 'hosted-service', name: 'offsite' }],
    schedule: '0 3 * * *',
  };
  if (retention !== undefined) strategy.retention = retention;
  return {
    schemaVersion: 3 as const,
    id: '11111111-2222-4333-8444-555555555555',
    version: 1,
    resources: { backupStrategies: { nightly: strategy } },
  };
}

const retentionOf = (parsed: ReturnType<typeof RdcConfigSchema.parse>) =>
  (
    parsed.resources?.backupStrategies as
      | Record<string, { retention?: Record<string, number> }>
      | undefined
  )?.nightly.retention;

describe('RetentionPolicySchema', () => {
  it('round-trips a fully specified policy', () => {
    const policy = {
      keepLast: 5,
      keepHourly: 24,
      keepDaily: 7,
      keepWeekly: 4,
      keepMonthly: 12,
      keepYearly: 3,
    };
    const parsed = RdcConfigSchema.parse(configWith(policy));
    expect(retentionOf(parsed)).toEqual(policy);
  });

  it('distinguishes an ABSENT policy from one with every knob unset', () => {
    expect(retentionOf(RdcConfigSchema.parse(configWith()))).toBeUndefined();
    // Present, empty: "policy declared, no bound" — NOT the same as absent.
    expect(retentionOf(RdcConfigSchema.parse(configWith({})))).toEqual({});
  });

  it('accepts 0 as a knob (an explicit "keep none from this bucket")', () => {
    expect(retentionOf(RdcConfigSchema.parse(configWith({ keepLast: 0 })))).toEqual({
      keepLast: 0,
    });
  });

  // EVERY knob, not just one: they are declared independently, so a single knob losing its `.int()` would otherwise slip through. Mutating exactly that on `keepLast` is what proved a one-knob version of this test blind.
  const KNOBS = [
    'keepLast',
    'keepHourly',
    'keepDaily',
    'keepWeekly',
    'keepMonthly',
    'keepYearly',
  ] as const;

  it.each(KNOBS)('rejects a negative %s', (knob) => {
    expect(() => RdcConfigSchema.parse(configWith({ [knob]: -1 }))).toThrow();
  });

  it.each(KNOBS)('rejects a non-integer %s', (knob) => {
    expect(() => RdcConfigSchema.parse(configWith({ [knob]: 1.5 }))).toThrow();
  });

  it.each(KNOBS)('rejects a string %s', (knob) => {
    expect(() => RdcConfigSchema.parse(configWith({ [knob]: '7' }))).toThrow();
  });
});

describe('retention keepWithinSeconds (D-retention)', () => {
  it('round-trips and counts as a declared knob', () => {
    expect(retentionOf(RdcConfigSchema.parse(configWith({ keepWithinSeconds: 86_400 })))).toEqual({
      keepWithinSeconds: 86_400,
    });
  });

  it.each([0, -5, 1.5, '24h'])('rejects keepWithinSeconds %s', (value) => {
    expect(() => RdcConfigSchema.parse(configWith({ keepWithinSeconds: value }))).toThrow();
  });
});

describe('declared protection targets (D-rpo)', () => {
  function withStrategy(extra: Record<string, unknown>) {
    const base = configWith();
    const strategy = {
      destinations: [{ kind: 'hosted-service', name: 'offsite' }],
      schedule: '0 3 * * *',
      ...extra,
    };
    return { ...base, resources: { backupStrategies: { nightly: strategy } } };
  }
  const targetsOf = (parsed: ReturnType<typeof RdcConfigSchema.parse>) =>
    (
      parsed.resources?.backupStrategies as
        | Record<string, { repoTargets?: unknown; rpo?: unknown }>
        | undefined
    )?.nightly;

  it('round-trips a strategy rpo and a per-repo target with every field', () => {
    const repoTargets = {
      mail: {
        rpo: '15m',
        cellSize: '1M',
        indexEvery: '1h',
        hookTimeout: '45s',
        hookFailure: 'abort',
      },
    };
    const parsed = RdcConfigSchema.parse(withStrategy({ rpo: '30m', repoTargets }));
    expect(targetsOf(parsed)).toMatchObject({ rpo: '30m', repoTargets });
  });

  it.each(['4m', '299s', '7m', '90m', 'soon', '15', '0m'])('rejects rpo %s', (rpo) => {
    expect(() => RdcConfigSchema.parse(withStrategy({ rpo }))).toThrow();
    expect(() => RdcConfigSchema.parse(withStrategy({ repoTargets: { mail: { rpo } } }))).toThrow();
  });

  it.each(['5m', '10m', '15m', '30m', '1h', '2h', '24h'])('accepts rpo %s', (rpo) => {
    expect(() => RdcConfigSchema.parse(withStrategy({ rpo }))).not.toThrow();
  });

  it('refuses the removed repoSchedules key by name instead of stripping it', () => {
    expect(() =>
      RdcConfigSchema.parse(withStrategy({ repoSchedules: { mail: '*/30 * * * *' } }))
    ).toThrow(/repoTargets/);
  });

  it('refuses a misspelt target field and an unknown hookFailure', () => {
    expect(() =>
      RdcConfigSchema.parse(withStrategy({ repoTargets: { mail: { rpo: '15m', rop: '5m' } } }))
    ).toThrow();
    expect(() =>
      RdcConfigSchema.parse(
        withStrategy({ repoTargets: { mail: { rpo: '15m', hookFailure: 'ignore' } } })
      )
    ).toThrow();
  });
});
