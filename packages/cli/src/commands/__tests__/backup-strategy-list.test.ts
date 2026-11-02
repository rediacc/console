import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({ t: (key: string) => key }));

const mocks = vi.hoisted(() => ({
  print: vi.fn(),
  info: vi.fn(),
  warn: vi.fn(),
  strategies: {} as Record<string, unknown>,
  machines: [] as { name: string; config: { backupStrategies?: string[] } }[],
  format: { value: 'json' },
}));

vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: mocks.info,
    success: vi.fn(),
    warn: mocks.warn,
    error: vi.fn(),
    print: mocks.print,
  },
}));
vi.mock('../../utils/errors.js', async () => ({
  ...(await vi.importActual<typeof import('../../utils/errors.js')>('../../utils/errors.js')),
  getOutputFormat: () => mocks.format.value,
  handleError: (e: unknown) => {
    throw e;
  },
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    listBackupStrategies: () => Promise.resolve(mocks.strategies),
    getBackupStrategy: (name: string) => Promise.resolve(mocks.strategies[name]),
    listMachines: () => Promise.resolve(mocks.machines),
  },
}));

import { registerBackupStrategyCommands } from '../backup-strategy.js';

async function run(args: string[]): Promise<void> {
  const program = new Command().exitOverride();
  registerBackupStrategyCommands(program.command('backup'));
  await program.parseAsync(['node', 'rdc', 'backup', 'strategy', ...args]);
}

const nightly = {
  schedule: '0 2 * * *',
  mode: 'full',
  destinations: [{ name: 'chunks', kind: 'hosted-service' }],
  retention: { keepLast: 3 },
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.format.value = 'json';
  mocks.strategies = { nightly };
  mocks.machines = [{ name: 'm1', config: { backupStrategies: ['nightly'] } }];
});

const printedRows = (): Record<string, unknown>[] => mocks.print.mock.calls.at(-1)?.[0];

describe('backup strategy list', () => {
  it.each(['json', 'yaml', 'table'])('prints rows on stdout through print in %s', async (format) => {
    mocks.format.value = format;
    await run(['list']);
    expect(mocks.print).toHaveBeenCalledTimes(1);
    expect(mocks.print.mock.calls[0][1]).toBe(format);
    expect(printedRows()).toEqual([
      {
        name: 'nightly',
        schedule: '0 2 * * *',
        mode: 'full',
        destinations: 1,
        enabled: true,
        machines: 'm1',
      },
    ]);
  });

  it('an empty list is [] under json, not prose on stderr alone', async () => {
    mocks.strategies = {};
    await run(['list']);
    expect(mocks.print).toHaveBeenCalledWith([], 'json');
  });
});

describe('backup strategy show', () => {
  it('prints one row per strategy through print, carrying the retention and destinations', async () => {
    await run(['show', 'nightly']);
    expect(mocks.print).toHaveBeenCalledTimes(1);
    const [row] = printedRows();
    expect(row).toMatchObject({
      name: 'nightly',
      schedule: '0 2 * * *',
      mode: 'full',
      enabled: true,
      retention: 'last=3',
    });
    expect(String(row.destinations)).toContain('chunks');
  });

  it('with no name prints every strategy; an empty config prints []', async () => {
    mocks.strategies = { nightly, hourly: { ...nightly, schedule: '0 * * * *' } };
    await run(['show']);
    expect(printedRows().map((r) => r.name)).toEqual(['nightly', 'hourly']);
    mocks.strategies = {};
    await run(['show']);
    expect(mocks.print).toHaveBeenLastCalledWith([], 'json');
  });

  it('an unknown strategy is an error naming it, not an empty success', async () => {
    await expect(run(['show', 'ghost'])).rejects.toThrow('commands.backup.strategy.show.notFound');
  });
});
