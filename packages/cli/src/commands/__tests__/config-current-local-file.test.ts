/**
 * `rdc config current` reads the active config's LOCAL file, never a pull: the remote pointer and
 * the encryption mode it reports are this device's own sections, so a remote config whose token
 * cannot be renewed (a login tied to another network address, vm:check A2.3 on 2026-11-27) still
 * reports instead of dying with the renewal refusal.
 */

import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { exists, load, getCurrent, print } = vi.hoisted(() => ({
  exists: vi.fn(),
  load: vi.fn(),
  getCurrent: vi.fn(),
  print: vi.fn(),
}));

vi.mock('../../i18n/index.js', () => ({ t: (key: string) => key }));
vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: { exists, load },
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: { getCurrentName: () => 'work', getCurrent },
}));
vi.mock('../../services/account/account-pointer.js', () => ({
  readAccountPointer: () => ({ accountServer: 'https://acct.example' }),
}));
vi.mock('../../services/account/subscription-auth.js', () => ({
  getSubscriptionTokenFile: (name: string) => `/tmp/api-token-${name}.json`,
  getSubscriptionTokenState: () => ({ kind: 'none' }),
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { print },
}));
vi.mock('../../utils/errors.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../utils/errors.js')>()),
  handleError: (error: unknown) => {
    throw error;
  },
}));

const { registerCurrentCommand } = await import('../config/current.js');

async function run(): Promise<void> {
  const program = new Command();
  program.exitOverride();
  program.option('-o, --output <format>', 'output', 'json');
  registerCurrentCommand(program.command('config'), program);
  await program.parseAsync(['node', 'rdc', 'config', 'current']);
}

describe('config current on a remote config', () => {
  beforeEach(() => {
    exists.mockReset().mockResolvedValue(true);
    load.mockReset().mockResolvedValue({
      schemaVersion: 3,
      id: 'i',
      version: 1,
      remote: { storeId: 'store-9', configId: 'c', apiUrl: 'https://acct.example' },
    });
    // A pull of this config would renew its token, and that renewal is refused.
    getCurrent
      .mockReset()
      .mockRejectedValue(new Error('the login is tied to another network address'));
    print.mockReset();
  });

  it('reports the remote store from the local file without pulling', async () => {
    await run();
    expect(getCurrent).not.toHaveBeenCalled();
    expect(load).toHaveBeenCalledWith('work');
    expect(print.mock.calls[0][0]).toMatchObject({ name: 'work', remoteStore: 'store-9' });
  });
});
