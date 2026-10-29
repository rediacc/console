/**
 * `rdc config init` without a name updates the EFFECTIVE config (REDIACC_CONFIG / --config), not the
 * default one: a flag-only init under REDIACC_CONFIG=work writes `renetPath` into work, never into
 * rediacc.json.
 */

import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { update, exists, getEffectiveConfigName } = vi.hoisted(() => ({
  update: vi.fn(),
  exists: vi.fn(),
  getEffectiveConfigName: vi.fn(),
}));

vi.mock('../../i18n/index.js', () => ({ t: (key: string) => key }));
vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: { exists, update },
}));
vi.mock('../../services/config/synced-write.js', () => ({
  isRemoteConfigFile: () => Promise.resolve(false),
  updateSyncedConfig: vi.fn(),
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: { getEffectiveConfigName, init: vi.fn() },
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { success: vi.fn(), info: vi.fn(), warn: vi.fn(), print: vi.fn() },
}));
vi.mock('../../utils/errors.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../utils/errors.js')>()),
  handleError: (error: unknown) => {
    throw error;
  },
}));

const { registerConfigCommands } = await import('../config.js');

async function run(argv: string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  registerConfigCommands(program);
  await program.parseAsync(['node', 'rdc', 'config', ...argv]);
}

describe('config init without a name', () => {
  beforeEach(() => {
    update.mockReset().mockResolvedValue(undefined);
    exists.mockReset().mockResolvedValue(true);
    getEffectiveConfigName.mockReset().mockReturnValue('work');
  });

  it('writes --renet-path into the effective config', async () => {
    await run(['init', '--renet-path', '/opt/renet']);

    expect(exists).toHaveBeenCalledWith('work');
    expect(update).toHaveBeenCalledTimes(1);
    expect(update.mock.calls[0][0]).toBe('work');
    const edit = update.mock.calls[0][1] as (
      cfg: Record<string, unknown>
    ) => Record<string, unknown>;
    expect(edit({ schemaVersion: 3, id: 'x', version: 1 })).toMatchObject({
      renetPath: '/opt/renet',
    });
  });
});
