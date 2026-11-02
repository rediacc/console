/**
 * `backup strategy set --rpo / --repo-rpo / --repo-cell-size / --no-estimate / --dry-run` (D-rpo):
 * the estimate gate, what a dry run writes, the re-seed warning, and the default keep-within window
 * that must never replace a retention the operator declared.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key} ${JSON.stringify(params)}` : key,
}));
const store = vi.hoisted(() => ({
  strategy: undefined as Record<string, unknown> | undefined,
  set: vi.fn(),
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getBackupStrategy: () => Promise.resolve(store.strategy),
    setBackupStrategy: (name: string, update: Record<string, unknown>) => {
      store.set(name, update);
      store.strategy = { ...store.strategy, ...update };
      return Promise.resolve();
    },
    getRepository: () => Promise.resolve({}),
  },
}));
const out = vi.hoisted(() => ({ info: vi.fn(), success: vi.fn(), warn: vi.fn() }));
vi.mock('../../services/core/output.js', () => ({ outputService: out }));

const { applyBackupStrategyOptions } = await import('../backup-strategy.js');

const measured = { lines: ['monthly cost $1.87', 'waiting 78 GiB of 20 GiB cap'] };
function deps(over: { estimate?: unknown; plan?: string | undefined } = {}) {
  return {
    estimate: vi.fn().mockResolvedValue('estimate' in over ? over.estimate : measured),
    planCode: vi.fn().mockResolvedValue('plan' in over ? over.plan : 'PROFESSIONAL'),
  };
}

beforeEach(() => {
  store.strategy = { schedule: '0 3 * * *', destinations: [] };
  store.set.mockReset();
  for (const fn of Object.values(out)) fn.mockReset();
});

const lastUpdate = (): Record<string, unknown> => store.set.mock.calls.at(-1)?.[1] ?? {};

describe('the estimate gate', () => {
  it('refuses a target with no churn measurement and writes nothing', async () => {
    await expect(
      applyBackupStrategyOptions('s', { rpo: '15m' }, deps({ estimate: undefined }))
    ).rejects.toThrow(/noMeasurement/);
    expect(store.set).not.toHaveBeenCalled();
  });

  it('--no-estimate skips the estimate and saves the target', async () => {
    const d = deps({ estimate: undefined });
    await applyBackupStrategyOptions('s', { rpo: '15m', estimate: false }, d);
    expect(d.estimate).not.toHaveBeenCalled();
    expect(lastUpdate()).toMatchObject({ rpo: '15m' });
  });

  it('prints the cost and cap lines before it saves', async () => {
    await applyBackupStrategyOptions('s', { rpo: '15m' }, deps());
    const printed = out.info.mock.calls.map((c) => c[0]);
    expect(printed).toEqual(expect.arrayContaining(measured.lines));
    expect(lastUpdate()).toMatchObject({ rpo: '15m' });
  });

  it('asks the estimate for the strategy target and for each per-repo target', async () => {
    const d = deps();
    await applyBackupStrategyOptions('s', { rpo: '30m', repoRpo: ['mail=5m'] }, d);
    expect(d.estimate).toHaveBeenCalledWith([
      { ref: undefined, rpoSeconds: 1800 },
      { ref: 'mail', rpoSeconds: 300 },
    ]);
  });

  it('a change with no target needs no estimate (control)', async () => {
    const d = deps({ estimate: undefined });
    await applyBackupStrategyOptions('s', { mode: 'cold' }, d);
    expect(d.estimate).not.toHaveBeenCalled();
    expect(store.set).toHaveBeenCalled();
  });
});

describe('--dry-run', () => {
  it('estimates and reports, and writes nothing', async () => {
    const d = deps();
    await applyBackupStrategyOptions('s', { rpo: '15m', repoRpo: ['mail=1h'], dryRun: true }, d);
    expect(d.estimate).toHaveBeenCalled();
    expect(store.set).not.toHaveBeenCalled();
    expect(out.info.mock.calls.map((c) => String(c[0])).join('\n')).toMatch(/dryRun/);
  });

  it('still refuses a target it could not estimate', async () => {
    await expect(
      applyBackupStrategyOptions('s', { rpo: '15m', dryRun: true }, deps({ estimate: undefined }))
    ).rejects.toThrow(/noMeasurement/);
  });
});

describe('a cell size change', () => {
  it('warns that it re-seeds and names the repo and size', async () => {
    await applyBackupStrategyOptions(
      's',
      { repoRpo: ['mail=15m'], repoCellSize: ['mail=1M'], estimate: false },
      deps()
    );
    const warned = out.warn.mock.calls.map((c) => String(c[0])).join('\n');
    expect(warned).toMatch(/reseedWarning.*"ref":"mail".*"size":"1M"/);
    expect(lastUpdate().repoTargets).toEqual({ mail: { rpo: '15m', cellSize: '1M' } });
  });

  it('is refused for a repo with no target, which has no unit to carry it', async () => {
    await expect(
      applyBackupStrategyOptions('s', { repoCellSize: ['mail=1M'], estimate: false }, deps())
    ).rejects.toThrow(/repoCellSizeNeedsTarget/);
  });

  it('does not warn when the size is unchanged (control)', async () => {
    store.strategy = {
      schedule: '0 3 * * *',
      destinations: [],
      repoTargets: { mail: { rpo: '15m', cellSize: '1M' } },
    };
    await applyBackupStrategyOptions('s', { repoCellSize: ['mail=1M'], estimate: false }, deps());
    expect(out.warn).not.toHaveBeenCalled();
  });
});

describe('the default keep-within window', () => {
  it('fills the plan default when no retention is declared, and says so', async () => {
    await applyBackupStrategyOptions(
      's',
      { rpo: '15m', estimate: false },
      deps({ plan: 'BUSINESS' })
    );
    expect(lastUpdate().retention).toEqual({ keepWithinSeconds: 172_800 });
    expect(out.info.mock.calls.map((c) => String(c[0])).join('\n')).toMatch(
      /retentionDefaulted.*"plan":"BUSINESS"/
    );
  });

  it('leaves a declared retention alone', async () => {
    store.strategy = { schedule: '0 3 * * *', destinations: [], retention: { keepLast: 3 } };
    await applyBackupStrategyOptions('s', { rpo: '15m', estimate: false }, deps());
    expect('retention' in lastUpdate()).toBe(false);
    expect(store.strategy.retention).toEqual({ keepLast: 3 });
  });

  it('leaves a retention given in the same call alone', async () => {
    await applyBackupStrategyOptions(
      's',
      { rpo: '15m', retention: 'last=5', estimate: false },
      deps()
    );
    expect(lastUpdate().retention).toEqual({ keepLast: 5 });
  });

  it('fills nothing on a plan with no storage, or when the plan is unknown, and warns', async () => {
    await applyBackupStrategyOptions('s', { rpo: '15m', estimate: false }, deps({ plan: 'FREE' }));
    expect('retention' in lastUpdate()).toBe(false);
    expect(out.warn).toHaveBeenCalled();
    out.warn.mockReset();
    await applyBackupStrategyOptions(
      's',
      { rpo: '30m', estimate: false },
      deps({ plan: undefined })
    );
    expect('retention' in lastUpdate()).toBe(false);
    expect(out.warn.mock.calls.map((c) => String(c[0])).join('\n')).toMatch(
      /retentionDefaultNoPlan/
    );
  });
});

describe('option validation', () => {
  it.each([
    [{ rpo: '3m' }, /rpoInvalid.*below 5 minutes/],
    [{ rpo: '7m' }, /rpoInvalid/],
    [{ rpo: '15' }, /rpoInvalid/],
    [{ repoRpo: ['mail'] }, /repoOptionInvalid/],
    [{ repoRpo: ['=15m'] }, /repoOptionInvalid/],
    [{ repoRpo: ['mail=2m'] }, /rpoInvalid/],
    [{ repoRpo: ['mail=15m'], repoCellSize: ['mail=big'] }, /cellSizeInvalid/],
    [{ cron: '*/2 * * * *' }, /at least 5 minutes/],
  ])('refuses %j before writing anything', async (options, message) => {
    await expect(
      applyBackupStrategyOptions('s', { ...options, estimate: false }, deps())
    ).rejects.toThrow(message);
    expect(store.set).not.toHaveBeenCalled();
  });

  it('none clears the strategy target and removes a per-repo one', async () => {
    store.strategy = {
      schedule: '0 3 * * *',
      destinations: [],
      rpo: '15m',
      repoTargets: { mail: { rpo: '5m' }, gitlab: { rpo: '1h' } },
    };
    await applyBackupStrategyOptions('s', { rpo: 'none', repoRpo: ['mail=none'] }, deps());
    const update = lastUpdate();
    expect('rpo' in update && update.rpo === undefined).toBe(true);
    expect(update.repoTargets).toEqual({ gitlab: { rpo: '1h' } });
  });

  it('removing the last per-repo target drops the map', async () => {
    store.strategy = {
      schedule: '0 3 * * *',
      destinations: [],
      repoTargets: { mail: { rpo: '5m' } },
    };
    await applyBackupStrategyOptions('s', { repoRpo: ['mail=none'] }, deps());
    expect(lastUpdate().repoTargets).toBeUndefined();
  });

  it('a per-repo target keeps its other fields when only its rpo changes', async () => {
    store.strategy = {
      schedule: '0 3 * * *',
      destinations: [],
      repoTargets: { mail: { rpo: '5m', hookFailure: 'abort' } },
    };
    await applyBackupStrategyOptions('s', { repoRpo: ['mail=30m'], estimate: false }, deps());
    expect(lastUpdate().repoTargets).toEqual({ mail: { rpo: '30m', hookFailure: 'abort' } });
  });
});
