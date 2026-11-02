import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  format: 'table' as 'json' | 'table',
  execute: vi.fn(),
  print: vi.fn(),
  info: vi.fn(),
  warn: vi.fn(),
  fail: vi.fn(),
}));

vi.mock('../../i18n/index.js', () => ({ t: (key: string) => key }));
vi.mock('../../utils/errors.js', () => ({
  getOutputFormat: () => mocks.format,
  handleError: (error: unknown) => {
    throw error;
  },
}));
vi.mock('../_validate.js', () => ({ assertMachineExists: async () => undefined }));
vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: mocks.execute }),
}));
vi.mock('../../utils/local-execution-failures.js', () => ({
  renderLocalExecutionFailure: mocks.fail,
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { print: mocks.print, info: mocks.info, warn: mocks.warn },
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    listRepositories: async () => [{ name: 'gpu-a', config: { networkId: 2816 } }],
  },
}));

const { registerGpuCommands } = await import('../machine/gpu.js');

const REPORT = {
  inventory: {
    platform: 'wsl',
    gpus: [
      {
        vendor: 'nvidia',
        index: 0,
        uuid: 'GPU-1',
        name: 'NVIDIA GeForce RTX 3060',
        driver_version: '616.56',
        memory_total: '12288 MiB',
      },
    ],
    specs: [
      { path: '/etc/cdi/nvidia.yaml', kind: 'nvidia.com/gpu', devices: ['nvidia.com/gpu=all'] },
    ],
  },
  recorded: true,
  grants: [
    {
      network_id: 2816,
      devices: [
        { name: 'nvidia.com/gpu=all', exclusive: true, granted_at: '2026-10-25T00:00:00Z' },
      ],
    },
  ],
};

async function run(): Promise<void> {
  const program = new Command();
  program.exitOverride();
  registerGpuCommands(program.command('machine'));
  await program.parseAsync(['machine', 'gpu', 'list', 'm1'], { from: 'user' });
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.format = 'table';
  mocks.execute.mockResolvedValue({ success: true, stdout: JSON.stringify(REPORT) });
});

describe('rdc machine gpu list', () => {
  it('dispatches machine_gpu_list at the machine', async () => {
    await run();
    expect(mocks.execute.mock.calls[0][0]).toMatchObject({
      functionName: 'machine_gpu_list',
      machineName: 'm1',
    });
  });

  it('renders the GPUs and the devices with the repository that holds each', async () => {
    await run();
    const tables = mocks.print.mock.calls.map((c) => c[0]);
    expect(tables[0]).toEqual([
      {
        index: 0,
        vendor: 'nvidia',
        name: 'NVIDIA GeForce RTX 3060',
        driver: '616.56',
        memory: '12288 MiB',
      },
    ]);
    expect(tables[1]).toEqual([
      {
        device: 'nvidia.com/gpu=all',
        spec: '/etc/cdi/nvidia.yaml',
        grantedTo: 'gpu-a (exclusive)',
      },
    ]);
  });

  it('prints the report itself for --json output', async () => {
    mocks.format = 'json';
    await run();
    expect(mocks.print).toHaveBeenCalledWith(REPORT, 'json');
  });

  it('says so when the machine has no GPUs and no recorded inventory', async () => {
    mocks.execute.mockResolvedValue({
      success: true,
      stdout: JSON.stringify({ inventory: { gpus: [], specs: [] }, recorded: false, grants: [] }),
    });
    await run();
    expect(mocks.warn).toHaveBeenCalledWith('commands.machine.gpu.list.notRecorded');
    expect(mocks.info).toHaveBeenCalledWith('commands.machine.gpu.list.noGpus');
    expect(mocks.info).toHaveBeenCalledWith('commands.machine.gpu.list.noDevices');
    expect(mocks.print).not.toHaveBeenCalled();
  });

  it('reports a failed dispatch without rendering', async () => {
    mocks.execute.mockResolvedValue({ success: false, error: 'boom' });
    await run();
    expect(mocks.fail).toHaveBeenCalled();
    expect(mocks.print).not.toHaveBeenCalled();
  });
});
