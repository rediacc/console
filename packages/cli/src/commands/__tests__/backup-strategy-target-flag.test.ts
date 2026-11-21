import { Command } from 'commander';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string) => key,
}));
vi.mock('../../services/backup/backup-retention.js', async (orig) => ({
  ...(await orig<object>()),
  hasAccountToken: () => true,
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getBackupStrategy: () => Promise.resolve({ schedule: '0 3 * * *' }),
    getBackupStrategies: () => Promise.resolve({}),
    setBackupStrategy: () => Promise.resolve(),
    listBackupStrategies: () => Promise.resolve({}),
    listMachines: () => Promise.resolve([]),
    getLocalConfig: () => Promise.resolve({ repositories: {}, machines: {} }),
  },
}));
const out = vi.hoisted(() => ({ info: vi.fn(), success: vi.fn(), warn: vi.fn() }));
vi.mock('../../services/core/output.js', () => ({ outputService: out }));
vi.mock('../../utils/errors.js', async (orig) => ({
  ...(await orig<object>()),
  handleError: (error: unknown) => {
    throw error;
  },
}));

const { registerBackupStrategyCommands } = await import('../backup-strategy.js');

describe('strategy set --target', () => {
  it('refuses --target without --destination instead of writing nothing and reporting success', async () => {
    const backup = new Command('backup').exitOverride();
    registerBackupStrategyCommands(backup);
    await expect(
      backup.parseAsync(['strategy', 'set', 's', '--target', 'offsite'], { from: 'user' })
    ).rejects.toThrow('commands.backup.strategy.set.targetNeedsDestination');
    expect(out.success).not.toHaveBeenCalled();
  });
});
