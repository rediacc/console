import { beforeEach, describe, expect, it, vi } from 'vitest';

const known = new Set(['mail', 'gitlab']);
let strategies: Record<string, unknown> = {};
const setBackupStrategy = vi.fn(() => Promise.resolve());

vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getRepository: vi.fn((ref: string) =>
      Promise.resolve(known.has(ref) ? { guid: ref } : undefined)
    ),
    getBackupStrategy: vi.fn((name: string) => Promise.resolve(strategies[name])),
    setBackupStrategy: (...args: unknown[]) =>
      (setBackupStrategy as (...a: unknown[]) => unknown)(...args),
  },
}));

const { applyBackupStrategyOptions, assertStrategyBindable } = await import(
  '../backup-strategy.js'
);

describe('backup strategy set validates include/exclude names (G2)', () => {
  beforeEach(() => setBackupStrategy.mockClear());

  it('refuses an unknown include name, naming it, and writes nothing', async () => {
    await expect(applyBackupStrategyOptions('s', { include: 'mail,ghost' })).rejects.toThrow(
      /ghost/
    );
    expect(setBackupStrategy).not.toHaveBeenCalled();
  });

  it('refuses an unknown exclude name and names every unknown one', async () => {
    const err = await applyBackupStrategyOptions('s', { exclude: 'phantom,gitlab,spectre' }).catch(
      (e: Error) => e
    );
    expect((err as Error).message).toMatch(/phantom/);
    expect((err as Error).message).toMatch(/spectre/);
    expect((err as Error).message).not.toMatch(/gitlab/);
    expect(setBackupStrategy).not.toHaveBeenCalled();
  });

  it('admits known names (control)', async () => {
    await applyBackupStrategyOptions('s', { include: 'mail,gitlab' });
    expect(setBackupStrategy).toHaveBeenCalledTimes(1);
  });

  it('lets a clearing value through without lookups', async () => {
    await applyBackupStrategyOptions('s', { include: 'none' });
    expect(setBackupStrategy).toHaveBeenCalledTimes(1);
  });
});

describe('backup strategy bind refuses what schedule would refuse (G8)', () => {
  const hosted = { kind: 'hosted-service', name: 'd' };

  it('refuses a strategy with a retired storage destination', async () => {
    strategies = {
      s: { schedule: '0 3 * * *', destinations: [{ kind: 'storage', name: 'old', storage: 'x' }] },
    };
    await expect(assertStrategyBindable('s')).rejects.toThrow(/old/);
  });

  it('refuses a bad cron or an unparseable bwlimit', async () => {
    strategies = { s: { schedule: 'daily', destinations: [hosted] } };
    await expect(assertStrategyBindable('s')).rejects.toThrow(/cron/);
    strategies = { s: { schedule: '0 3 * * *', bandwidthLimit: 'fast', destinations: [hosted] } };
    await expect(assertStrategyBindable('s')).rejects.toThrow(/bandwidthLimit/);
  });

  it('ignores a disabled unschedulable destination, as the scheduler does', async () => {
    strategies = {
      s: {
        schedule: '0 3 * * *',
        destinations: [hosted, { kind: 'storage', name: 'old', enabled: false }],
      },
    };
    await expect(assertStrategyBindable('s')).resolves.toBeUndefined();
  });

  it('admits an exclude list, which the schedule renders as --exclude-repo <guid> (G1)', async () => {
    strategies = { s: { schedule: '0 3 * * *', exclude: ['mail'], destinations: [hosted] } };
    await expect(assertStrategyBindable('s')).resolves.toBeUndefined();
  });

  it('admits a schedulable strategy (control)', async () => {
    strategies = { s: { schedule: '0 3 * * *', bandwidthLimit: '6M', destinations: [hosted] } };
    await expect(assertStrategyBindable('s')).resolves.toBeUndefined();
  });
});
