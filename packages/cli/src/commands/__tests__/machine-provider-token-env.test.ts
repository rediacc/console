import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({ t: (key: string) => key }));
const addCloudProvider = vi.hoisted(() => vi.fn());
vi.mock('../../services/config/config-resources.js', () => ({
  configService: { addCloudProvider, removeCloudProvider: vi.fn(), listCloudProviders: vi.fn() },
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { success: vi.fn(), info: vi.fn(), print: vi.fn(), format: vi.fn() },
}));
vi.mock('../../utils/errors.js', () => ({
  handleError: (error: unknown) => {
    throw error;
  },
}));

import { registerProviderCommands } from '../machine/provider.js';

async function add(args: string[]) {
  const program = new Command();
  program.exitOverride();
  const machine = program.command('machine');
  registerProviderCommands(machine, program);
  machine.commands.forEach((c) => {
    c.exitOverride();
    c.commands.forEach((cc) => cc.exitOverride());
  });
  await program.parseAsync(['machine', 'provider', 'add', ...args], { from: 'user' });
}

describe('machine provider add --token-env', () => {
  beforeEach(() => addCloudProvider.mockReset());
  afterEach(() => {
    delete process.env.TEST_PROVIDER_TOKEN;
  });

  it('stores the token read from the named environment variable', async () => {
    process.env.TEST_PROVIDER_TOKEN = 'tok-123';
    await add(['p1', '--provider', 'linode/linode', '--token-env', 'TEST_PROVIDER_TOKEN']);
    expect(addCloudProvider).toHaveBeenCalledWith(
      'p1',
      expect.objectContaining({ apiToken: 'tok-123', provider: 'linode/linode' })
    );
  });

  it('refuses an unset or empty variable and stores nothing', async () => {
    await expect(
      add(['p1', '--provider', 'linode/linode', '--token-env', 'TEST_PROVIDER_TOKEN'])
    ).rejects.toThrow('commands.machine.provider.add.tokenEnvEmpty');
    process.env.TEST_PROVIDER_TOKEN = '   ';
    await expect(
      add(['p1', '--provider', 'linode/linode', '--token-env', 'TEST_PROVIDER_TOKEN'])
    ).rejects.toThrow('commands.machine.provider.add.tokenEnvEmpty');
    expect(addCloudProvider).not.toHaveBeenCalled();
  });

  it('no longer accepts the token itself on argv', async () => {
    await expect(
      add(['p1', '--provider', 'linode/linode', '--token', 'tok-123'])
    ).rejects.toThrow();
    expect(addCloudProvider).not.toHaveBeenCalled();
  });
});
