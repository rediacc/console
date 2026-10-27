/** `backup strategy remove`: refused while bound, --unbind cascades in one edit, clean case removes. */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CliExitError } from '../../utils/cli-exit-error.js';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const m = vi.hoisted(() => ({
  getMachines: vi.fn(),
  removeBackupStrategy: vi.fn(),
  update: vi.fn(),
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getResourceState: async () => ({ getMachines: m.getMachines }),
    removeBackupStrategy: m.removeBackupStrategy,
    getEffectiveConfigName: () => 'cfg',
  },
}));
vi.mock('../../services/config/synced-write.js', () => ({ updateSyncedConfig: m.update }));

import { removeStrategyChecked } from '../../services/config/config-strategy-binding.js';

beforeEach(() => {
  vi.clearAllMocks();
  m.getMachines.mockReturnValue({
    a: { ip: '1', user: 'u', backupStrategies: ['nightly', 'weekly'] },
    b: { ip: '2', user: 'u', backupStrategies: ['nightly'] },
    c: { ip: '3', user: 'u' },
  });
});

describe('backup strategy remove references', () => {
  it('refuses with exit 12 naming the bound machines', async () => {
    const err = (await removeStrategyChecked('nightly', false).catch(
      (e: unknown) => e
    )) as CliExitError;
    expect(err).toBeInstanceOf(CliExitError);
    expect(err.exitCode).toBe(12);
    expect(err.details).toEqual(['a', 'b']);
    expect(m.removeBackupStrategy).not.toHaveBeenCalled();
    expect(m.update).not.toHaveBeenCalled();
  });

  it('--unbind drops the strategy and every binding in one edit', async () => {
    expect(await removeStrategyChecked('nightly', true)).toEqual(['a', 'b']);
    expect(m.update).toHaveBeenCalledOnce();
    const edit = m.update.mock.calls[0][1] as (cfg: unknown) => {
      resources: {
        backupStrategies: Record<string, unknown>;
        machines: Record<string, { backupStrategies?: string[] }>;
      };
    };
    const out = edit({
      resources: {
        backupStrategies: { nightly: {}, weekly: {} },
        machines: m.getMachines(),
      },
    });
    expect(Object.keys(out.resources.backupStrategies)).toEqual(['weekly']);
    expect(out.resources.machines.a.backupStrategies).toEqual(['weekly']);
    expect(out.resources.machines.b.backupStrategies).toBeUndefined();
  });

  it('removes an unbound strategy plainly', async () => {
    expect(await removeStrategyChecked('orphan', false)).toEqual([]);
    expect(m.removeBackupStrategy).toHaveBeenCalledWith('orphan');
    expect(m.update).not.toHaveBeenCalled();
  });
});

describe('strategy remove option conflicts', () => {
  it('refuses --unbind together with --destination instead of ignoring --unbind', async () => {
    const { Command } = await import('commander');
    const { registerBackupStrategyCommands } = await import('../backup-strategy.js');
    const backup = new Command('backup').exitOverride();
    registerBackupStrategyCommands(backup);
    for (const sub of backup.commands) sub.exitOverride();
    const remove = backup.commands
      .find((c) => c.name() === 'strategy')
      ?.commands.find((c) => c.name() === 'remove');
    remove?.exitOverride().configureOutput({ writeErr: () => {} });
    await expect(
      backup.parseAsync(['strategy', 'remove', 's1', '--destination', 'd1', '--unbind'], {
        from: 'user',
      })
    ).rejects.toThrow(/cannot be used with/);
  });
});
