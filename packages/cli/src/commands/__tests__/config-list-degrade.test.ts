import { beforeEach, describe, expect, it, vi } from 'vitest';

// `config list` must keep listing when one config file is unparseable:
// the bad entry degrades to a status:"invalid" row instead of aborting.

const { mockList, mockLoad, mockPrint, mockError } = vi.hoisted(() => ({
  mockList: vi.fn(),
  mockLoad: vi.fn(),
  mockPrint: vi.fn(),
  mockError: vi.fn(),
}));

vi.mock('../../services/config-resources.js', () => ({
  configService: {
    list: mockList,
    getCurrentName: () => 'good',
  },
}));

vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: {
    load: mockLoad,
  },
}));

vi.mock('../../services/output.js', () => ({
  outputService: {
    print: mockPrint,
    info: vi.fn(),
    error: mockError,
    warn: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock('../../utils/errors.js', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../utils/errors.js')>();
  return {
    ...actual,
    handleError: vi.fn((e: unknown) => {
      throw e instanceof Error ? e : new Error(String(e));
    }),
    getOutputFormat: () => 'table',
  };
});

const { Command } = await import('commander');
const { registerConfigCommands } = await import('../config.js');

describe('config list — per-file degrade', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('lists valid configs and marks unparseable ones invalid instead of aborting', async () => {
    mockList.mockResolvedValue(['bad', 'good']);
    mockLoad.mockImplementation((name: string) => {
      if (name === 'bad') {
        return Promise.reject(new Error('Invalid config "bad": id: Must be a valid UUID'));
      }
      return Promise.resolve({
        resources: { machines: { srv: { ip: '1.2.3.4', user: 'root' } } },
      });
    });

    const program = new Command();
    program.option('-o, --output <format>', 'format', 'table');
    registerConfigCommands(program);

    await program.parseAsync(['config', 'list'], { from: 'user' });

    expect(mockPrint).toHaveBeenCalledTimes(1);
    const rows = mockPrint.mock.calls[0][0] as {
      name: string;
      active: string;
      machines: string;
      status: string;
    }[];
    expect(rows).toEqual([
      { name: 'bad', active: '', machines: '-', status: 'invalid' },
      { name: 'good', active: '*', machines: '1', status: 'ok' },
    ]);
  });
});
