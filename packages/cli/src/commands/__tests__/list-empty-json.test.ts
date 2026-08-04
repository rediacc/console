/**
 * Regression test for the empty-collection JSON contract.
 *
 * `rdc machine list -o json` with zero machines printed NOTHING to stdout: the
 * empty guard fired an `outputService.info` hint (which goes to stderr) and
 * returned before `outputService.print` ever ran, so a JSON consumer got an
 * empty string to parse instead of {"success":true,"data":[]}. Several sibling
 * list commands shared the shape.
 *
 * The contract these pin: the hint is a TABLE-mode courtesy, and every
 * machine-readable format falls through to print().
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockPrint, mockInfo, mockListMachines, mockListConfigs, mockLoadConfig, mockListArchived } =
  vi.hoisted(() => ({
    mockPrint: vi.fn(),
    mockInfo: vi.fn(),
    mockListMachines: vi.fn(),
    mockListConfigs: vi.fn(),
    mockLoadConfig: vi.fn(),
    mockListArchived: vi.fn(),
  }));

vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    listMachines: mockListMachines,
    list: mockListConfigs,
    listArchivedRepositories: mockListArchived,
    getCurrentName: () => 'default',
  },
}));

vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: { load: mockLoadConfig },
}));

vi.mock('../../services/core/output.js', () => ({
  outputService: {
    print: mockPrint,
    info: mockInfo,
    warn: vi.fn(),
    error: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock('../../i18n/index.js', () => ({ t: (key: string) => key }));

const { Command } = await import('commander');
const { registerMachineRegistrationCommands } = await import('../machine/register.js');
const { registerConfigCommands } = await import('../config.js');
const { createRepoAdminCommand } = await import('../repo-admin.js');

function programWith(output: string): InstanceType<typeof Command> {
  const program = new Command();
  program.option('-o, --output <format>', 'format', 'table');
  program.setOptionValue('output', output);
  return program;
}

/** Every list command reachable from this file, keyed by its argv. */
const cases: {
  name: string;
  argv: string[];
  register: (p: InstanceType<typeof Command>) => void;
}[] = [
  {
    name: 'machine list',
    argv: ['machine', 'list'],
    register: (p) => {
      const machine = p.command('machine');
      registerMachineRegistrationCommands(machine, p);
    },
  },
  {
    name: 'config list',
    argv: ['config', 'list'],
    register: (p) => registerConfigCommands(p),
  },
  {
    name: 'repo admin archive list',
    argv: ['repo', 'admin', 'archive', 'list'],
    register: (p) => {
      createRepoAdminCommand(p.command('repo'), p);
    },
  },
];

describe('list commands with zero items', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListMachines.mockResolvedValue([]);
    mockListConfigs.mockResolvedValue([]);
    mockListArchived.mockResolvedValue([]);
  });

  for (const { name, argv, register } of cases) {
    it(`${name} -o json prints an empty data array instead of nothing`, async () => {
      const program = programWith('json');
      register(program);

      await program.parseAsync(argv, { from: 'user' });

      expect(mockPrint).toHaveBeenCalledTimes(1);
      expect(mockPrint.mock.calls[0][0]).toEqual([]);
      expect(mockPrint.mock.calls[0][1]).toBe('json');
    });

    it(`${name} in table mode still prints the human hint and no table`, async () => {
      const program = programWith('table');
      register(program);

      await program.parseAsync(argv, { from: 'user' });

      expect(mockPrint).not.toHaveBeenCalled();
      expect(mockInfo).toHaveBeenCalled();
    });
  }
});

describe('the envelope an empty list actually produces', () => {
  it('is {"success":true,...,"data":[]} on stdout', async () => {
    vi.resetModules();
    vi.doUnmock('../../services/core/output.js');
    const { outputService } = await vi.importActual<typeof import('../../services/core/output.js')>(
      '../../services/core/output.js'
    );

    const log = vi.spyOn(console, 'log').mockImplementation(() => {});
    try {
      outputService.print([], 'json');
      expect(log).toHaveBeenCalledTimes(1);
      const envelope = JSON.parse(String(log.mock.calls[0][0])) as {
        success: boolean;
        data: unknown[];
      };
      expect(envelope.success).toBe(true);
      expect(envelope.data).toEqual([]);
    } finally {
      log.mockRestore();
    }
  });
});
