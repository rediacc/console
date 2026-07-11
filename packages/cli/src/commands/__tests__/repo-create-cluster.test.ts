import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// i18n stub
vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

// configService — capture the addRepository payload to assert registration (#12).
const mockGetRepository = vi.hoisted(() => vi.fn());
const mockAddRepository = vi.hoisted(() => vi.fn());
const mockRemoveRepository = vi.hoisted(() => vi.fn());
const mockAllocateNetworkId = vi.hoisted(() => vi.fn().mockResolvedValue(4160));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getRepository: mockGetRepository,
    addRepository: mockAddRepository,
    removeRepository: mockRemoveRepository,
    allocateNetworkId: mockAllocateNetworkId,
  },
}));

const mockExecute = vi.hoisted(() => vi.fn().mockResolvedValue({ success: true, allSteps: [] }));
vi.mock('../../services/executor/local-executor.js', () => ({
  localExecutorService: { execute: mockExecute },
}));

const mockResolveRepoTarget = vi.hoisted(() =>
  vi.fn().mockResolvedValue({ machineName: 'prod-cp-1', kubeCluster: 'prod' })
);
vi.mock('../../utils/repo-target.js', () => ({ resolveRepoTarget: mockResolveRepoTarget }));

vi.mock('../../utils/agent-guard.js', () => ({ assertAgentRepoCreate: vi.fn() }));
vi.mock('../../services/cluster/cluster-target.js', () => ({
  clusterMountRemotePath: (c: string) => `/mnt/rediacc/mounts/${c}`,
}));
vi.mock('../../utils/config-schema.js', () => ({
  compositeKey: (name: string, tag: string) => `${name}:${tag}`,
}));

vi.mock('../../services/core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), warn: vi.fn() },
}));
vi.mock('../../utils/local-execution-failures.js', () => ({
  renderLocalExecutionFailure: vi.fn(),
}));
vi.mock('../../utils/errors.js', async () => {
  const actual =
    await vi.importActual<typeof import('../../utils/errors.js')>('../../utils/errors.js');
  return {
    ...actual,
    handleError: (e: unknown) => {
      throw e;
    },
  };
});
// remote/vscode is imported at module top for the delete cleanup path.
vi.mock('../../remote/vscode/index.js', () => ({
  generateConnectionName: vi.fn(),
  removePersistedKeys: vi.fn(),
  removeSSHConfigEntry: vi.fn(),
}));

const { handleRepoCreate } = await import('../repo-create-delete.js');

beforeEach(() => {
  vi.clearAllMocks();
  mockGetRepository.mockResolvedValue(undefined); // not yet registered
  mockExecute.mockResolvedValue({ success: true, allSteps: [] });
});
afterEach(() => vi.clearAllMocks());

describe('repo create --cluster registers the repo (#12)', () => {
  it('calls addRepository so repo up/down/list --cluster can resolve it', async () => {
    await handleRepoCreate('shop', { cluster: 'prod', size: '5G' });

    // The repo is registered under <name>:latest with an identity + credential.
    expect(mockAddRepository).toHaveBeenCalledTimes(1);
    const [key, config] = mockAddRepository.mock.calls[0];
    expect(key).toBe('shop:latest');
    expect(config).toMatchObject({ tag: 'latest', networkId: 4160 });
    expect(config.repositoryGuid).toBeTruthy();
    expect(config.credential).toBeTruthy();

    // The dispatched repository_create carries the SAME guid + networkId.
    const dispatch = mockExecute.mock.calls[0][0];
    expect(dispatch.functionName).toBe('repository_create');
    expect(dispatch.params).toMatchObject({
      repository: 'shop',
      cluster: 'prod',
      guid: config.repositoryGuid,
      network_id: 4160,
      start_docker: false,
    });
  });

  it('rolls back the registration when the dispatch fails', async () => {
    mockExecute.mockResolvedValue({ success: false, error: 'boom' });
    // rollbackCreateRepo re-reads getRepository to decide whether to remove.
    mockGetRepository.mockResolvedValueOnce(undefined); // pre-check: not registered
    mockGetRepository.mockResolvedValue({ repositoryGuid: 'x' }); // rollback: now present

    await handleRepoCreate('shop', { cluster: 'prod', size: '5G' });

    expect(mockAddRepository).toHaveBeenCalledTimes(1);
    expect(mockRemoveRepository).toHaveBeenCalledWith('shop');
  });
});
