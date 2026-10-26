import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  print: vi.fn(),
  execute: vi.fn(),
  listRepositories: vi.fn(),
}));

vi.mock('../../i18n/index.js', () => ({ t: (key: string) => key }));
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    success: vi.fn(),
    print: mocks.print,
  },
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: { listRepositories: mocks.listRepositories },
}));
vi.mock('../../services/config/config-datastores.js', () => ({
  getDatastore: vi.fn(),
  requireDatastoreHost: vi.fn(),
}));
vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: mocks.execute }),
}));
vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoTarget: async () => ({ machineName: 'm1', kubeCluster: undefined }),
}));
vi.mock('../../utils/guid-resolver.js', () => ({
  loadGuidMap: async () => ({}),
  createRepoNameResolver: () => (guid: string) => ({ name: guid, source: 'config' }),
}));
vi.mock('../../utils/errors.js', async () => {
  const actual =
    await vi.importActual<typeof import('../../utils/errors.js')>('../../utils/errors.js');
  return {
    ...actual,
    getOutputFormat: () => 'table',
    handleError: (error: unknown) => {
      throw error;
    },
  };
});

const { handleRepoList } = await import('../repo-batch-utils.js');

beforeEach(() => {
  vi.clearAllMocks();
  mocks.execute.mockResolvedValue({
    success: true,
    stdout: JSON.stringify([{ name: 'g-gpu' }, { name: 'g-plain' }]),
  });
  mocks.listRepositories.mockResolvedValue([
    {
      name: 'a',
      config: { repositoryGuid: 'g-gpu', gpuDevices: ['nvidia.com/gpu=all', 'x/dri=1'] },
    },
    { name: 'b', config: { repositoryGuid: 'g-plain' } },
  ]);
});

describe('repo list GPU column', () => {
  it('shows the granted devices, and "-" for a repo with none', async () => {
    await handleRepoList({});
    const rows = mocks.print.mock.calls[0][0] as { name: string; gpu: string }[];
    expect(rows.find((r) => r.name === 'g-gpu')?.gpu).toBe('nvidia.com/gpu=all, x/dri=1');
    expect(rows.find((r) => r.name === 'g-plain')?.gpu).toBe('-');
  });
});
