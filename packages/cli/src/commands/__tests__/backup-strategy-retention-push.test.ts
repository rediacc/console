import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string) => key,
}));
const retention = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('../../services/backup/backup-retention.js', async (orig) => ({
  ...(await orig<object>()),
  hasAccountToken: () => true,
  pushStrategyRetention: retention.push,
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getBackupStrategy: () => Promise.resolve({ schedule: '0 3 * * *', retention: { keepLast: 7 } }),
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

async function setRetention(): Promise<void> {
  const backup = new Command('backup').exitOverride();
  registerBackupStrategyCommands(backup);
  await backup.parseAsync(['strategy', 'set', 's', '--retention', 'last=7'], { from: 'user' });
}

beforeEach(() => {
  retention.push.mockReset();
  out.warn.mockReset();
});

describe('strategy set --retention push failures', () => {
  it('fails the command on a 4xx with the server message', async () => {
    retention.push.mockRejectedValue(
      Object.assign(new Error('The COMMUNITY plan allows at most keepLast 3'), { status: 400 })
    );
    await expect(setRetention()).rejects.toThrow(/COMMUNITY plan/);
    expect(out.warn).not.toHaveBeenCalled();
  });

  it('only warns when the server is unreachable or answers 5xx', async () => {
    retention.push.mockRejectedValue(Object.assign(new Error('boom'), { status: 503 }));
    await setRetention();
    expect(out.warn).toHaveBeenCalledTimes(1);
    retention.push.mockRejectedValue(new Error('fetch failed'));
    await setRetention();
    expect(out.warn).toHaveBeenCalledTimes(2);
  });
});
