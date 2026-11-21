/**
 * `backup strategy bind|unbind` and `remove --destination` keep the server's replication rules in step with the
 * strategy's replicate destinations; every failure is a warning because the config change is already written.
 */
import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../i18n/index.js', () => ({ t: (key: string) => key }));
const rules = vi.hoisted(() => ({ register: vi.fn(), remove: vi.fn(), token: vi.fn() }));
vi.mock('../backup-retention.js', async (orig) => ({
  ...(await orig<object>()),
  hasAccountToken: rules.token,
}));
vi.mock('../backup-replication.js', async (orig) => ({
  ...(await orig<object>()),
  registerStrategyReplication: rules.register,
  removeReplicationRulesFor: rules.remove,
}));
const strategy = vi.hoisted(() => ({
  schedule: '0 3 * * *',
  destinations: [
    { name: 'primary', kind: 'hosted-service' },
    { name: 'copy', kind: 'hosted-service', mode: 'replicate', target: 'eu-west', from: 'home' },
  ],
}));
vi.mock('../../config/config-resources.js', () => ({
  configService: {
    getBackupStrategy: () => Promise.resolve(strategy),
    removeBackupDestination: () => Promise.resolve(),
    listBackupStrategies: () => Promise.resolve({}),
  },
}));
vi.mock('../../config/config-strategy-binding.js', () => ({
  bindBackupStrategy: () => Promise.resolve(true),
  unbindBackupStrategy: () => Promise.resolve(true),
  removeStrategyChecked: () => Promise.resolve([]),
  machinesBoundToStrategy: () => Promise.resolve(['m1']),
}));
const out = vi.hoisted(() => ({ info: vi.fn(), success: vi.fn(), warn: vi.fn() }));
vi.mock('../../core/output.js', () => ({ outputService: out }));
vi.mock('../../../utils/errors.js', async (orig) => ({
  ...(await orig<object>()),
  handleError: (error: unknown) => {
    throw error;
  },
}));

const { registerBackupStrategyCommands } = await import('../../../commands/backup-strategy.js');

async function run(...args: string[]): Promise<void> {
  const backup = new Command('backup').exitOverride();
  registerBackupStrategyCommands(backup);
  await backup.parseAsync(['strategy', ...args], { from: 'user' });
}

const synced = { done: 2, unsupported: false, failures: [] };

beforeEach(() => {
  for (const fn of Object.values(rules)) fn.mockReset();
  for (const fn of Object.values(out)) fn.mockReset();
  rules.token.mockReturnValue(true);
  rules.register.mockResolvedValue(synced);
  rules.remove.mockResolvedValue(synced);
});

describe('bind', () => {
  it('registers the rules for the bound machine', async () => {
    await run('bind', 's', '--machine', 'm1');
    expect(rules.register).toHaveBeenCalledWith(strategy, 'm1');
    expect(out.info).toHaveBeenCalledWith('commands.backup.strategy.replication.registered');
  });

  it('warns clearly on an older account server and still binds', async () => {
    rules.register.mockResolvedValue({ done: 0, unsupported: true, failures: [] });
    await run('bind', 's', '--machine', 'm1');
    expect(out.warn).toHaveBeenCalledWith('commands.backup.strategy.replication.unsupported');
    expect(out.success).toHaveBeenCalledWith('commands.backup.strategy.bind.bound');
  });

  it('warns, not crashes, when the sync throws', async () => {
    rules.register.mockRejectedValue(new Error('offline'));
    await run('bind', 's', '--machine', 'm1');
    expect(out.warn).toHaveBeenCalledWith('commands.backup.strategy.replication.syncFailed');
    expect(out.success).toHaveBeenCalledWith('commands.backup.strategy.bind.bound');
  });

  it('says rules were not sent when there is no account token', async () => {
    rules.token.mockReturnValue(false);
    await run('bind', 's', '--machine', 'm1');
    expect(rules.register).not.toHaveBeenCalled();
    expect(out.warn).toHaveBeenCalledWith('commands.backup.strategy.replication.notPushed');
  });
});

describe('unbind and destination removal', () => {
  it('drops every replicate destination rule for the machine on unbind', async () => {
    await run('unbind', 's', '--machine', 'm1');
    expect(rules.remove).toHaveBeenCalledWith(strategy, [strategy.destinations[1]], 'm1');
  });

  it('drops the rules of a removed replicate destination, and none for an upload one', async () => {
    await run('remove', 's', '--destination', 'copy');
    expect(rules.remove).toHaveBeenCalledTimes(1);
    rules.remove.mockClear();
    await run('remove', 's', '--destination', 'primary');
    expect(rules.remove).not.toHaveBeenCalled();
  });
});
