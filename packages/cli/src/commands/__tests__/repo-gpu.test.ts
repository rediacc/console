import { WK_INFRA_DOMAIN } from '@rediacc/shared/config/well-known.generated';
import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  executeRepoFunction: vi.fn(),
  setRepositoryGpuDevices: vi.fn(),
  getRepository: vi.fn(),
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));
vi.mock('../../utils/errors.js', async () => {
  const actual =
    await vi.importActual<typeof import('../../utils/errors.js')>('../../utils/errors.js');
  return {
    ...actual,
    handleError: (error: unknown) => {
      throw error;
    },
  };
});
vi.mock('../_validate.js', () => ({ assertMachineExists: async () => undefined }));
vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoRef: async () => ({ name: 'app', repoKey: 'app:latest', machineName: 'm1' }),
}));
vi.mock('../../utils/repo-executor.js', () => ({
  executeRepoFunction: mocks.executeRepoFunction,
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getRepository: mocks.getRepository,
    setRepositoryGpuDevices: mocks.setRepositoryGpuDevices,
  },
}));

const { registerRepoGpuCommands } = await import('../repo-gpu.js');

async function run(argv: string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  registerRepoGpuCommands(program.command('repo'));
  await program.parseAsync(['repo', 'gpu', ...argv], { from: 'user' });
}

const GRANT_STDOUT = JSON.stringify({
  devices: [
    { name: 'nvidia.com/gpu=all', exclusive: true },
    { name: `${WK_INFRA_DOMAIN}/dri=renderD128` },
  ],
});

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getRepository.mockResolvedValue({ gpuDevices: ['nvidia.com/gpu=all'] });
  mocks.executeRepoFunction.mockResolvedValue({ success: true, stdout: GRANT_STDOUT });
});

describe('rdc repo gpu grant|revoke', () => {
  it('grant dispatches repository_gpu_grant with the device and exclusivity', async () => {
    await run(['grant', 'app', '--device', 'nvidia.com/gpu=all', '--exclusive']);
    const [fn, repoKey, machine, params] = mocks.executeRepoFunction.mock.calls[0];
    expect([fn, repoKey, machine]).toEqual(['repository_gpu_grant', 'app:latest', 'm1']);
    expect(params).toEqual({ device: 'nvidia.com/gpu=all', exclusive: true });
  });

  it('grant mirrors the device names renet reports into state.repos', async () => {
    await run(['grant', 'app', '--device', `${WK_INFRA_DOMAIN}/dri=renderD128`]);
    expect(mocks.setRepositoryGpuDevices).toHaveBeenCalledWith('app:latest', [
      'nvidia.com/gpu=all',
      `${WK_INFRA_DOMAIN}/dri=renderD128`,
    ]);
  });

  it('revoke dispatches repository_gpu_revoke without exclusivity and updates the mirror', async () => {
    mocks.executeRepoFunction.mockResolvedValue({
      success: true,
      stdout: JSON.stringify({ devices: [] }),
    });
    await run(['revoke', 'app', '--device', 'nvidia.com/gpu=all']);
    const [fn, , , params] = mocks.executeRepoFunction.mock.calls[0];
    expect(fn).toBe('repository_gpu_revoke');
    expect(params).toEqual({ device: 'nvidia.com/gpu=all' });
    expect(mocks.setRepositoryGpuDevices).toHaveBeenCalledWith('app:latest', []);
  });

  it('falls back to editing the mirror when the output carries no grant', async () => {
    mocks.executeRepoFunction.mockResolvedValue({ success: true, stdout: 'ok' });
    await run(['revoke', 'app', '--device', 'nvidia.com/gpu=all']);
    expect(mocks.setRepositoryGpuDevices).toHaveBeenCalledWith('app:latest', []);
  });

  it('falls back to editing the mirror when the output is JSON without a devices list', async () => {
    mocks.executeRepoFunction.mockResolvedValue({ success: true, stdout: '{}' });
    await run(['revoke', 'app', '--device', 'nvidia.com/gpu=all']);
    expect(mocks.setRepositoryGpuDevices).toHaveBeenCalledWith('app:latest', []);
    mocks.setRepositoryGpuDevices.mockClear();
    await run(['grant', 'app', '--device', 'x/dri=2']);
    expect(mocks.setRepositoryGpuDevices).toHaveBeenCalledWith('app:latest', [
      'nvidia.com/gpu=all',
      'x/dri=2',
    ]);
  });

  it("reads `devices: null` as renet's empty grant, not as a missing listing", async () => {
    mocks.executeRepoFunction.mockResolvedValue({
      success: true,
      stdout: JSON.stringify({ devices: null }),
    });
    await run(['revoke', 'app', '--device', 'x/dri=2']);
    expect(mocks.setRepositoryGpuDevices).toHaveBeenCalledWith('app:latest', []);
  });

  it('leaves the mirror alone when the dispatch fails', async () => {
    mocks.executeRepoFunction.mockResolvedValue({ success: false });
    await run(['grant', 'app', '--device', 'nvidia.com/gpu=all']);
    expect(mocks.setRepositoryGpuDevices).not.toHaveBeenCalled();
  });

  it('requires --device', async () => {
    await expect(run(['grant', 'app'])).rejects.toThrow(/device/);
    expect(mocks.executeRepoFunction).not.toHaveBeenCalled();
  });
});
