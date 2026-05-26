import { beforeEach, describe, expect, it, vi } from 'vitest';

// configService mock — all methods are hoisted so the module factory can use them.
const mockGetLocalMachine = vi.hoisted(() => vi.fn());
const mockGetStorage = vi.hoisted(() => vi.fn());
const mockListRepositories = vi.hoisted(() => vi.fn());
const mockGetRepository = vi.hoisted(() => vi.fn());
const mockGetRepositoryGuidMap = vi.hoisted(() => vi.fn());

vi.mock('../../services/config-resources.js', () => ({
  configService: {
    getLocalMachine: mockGetLocalMachine,
    getStorage: mockGetStorage,
    listRepositories: mockListRepositories,
    getRepository: mockGetRepository,
    getRepositoryGuidMap: mockGetRepositoryGuidMap,
  },
}));

const { assertMachineExists, assertStorageExists, assertRepositoryExists } = await import(
  '../_validate.js'
);

describe('assertMachineExists', () => {
  beforeEach(() => vi.clearAllMocks());

  it('resolves when the machine exists', async () => {
    mockGetLocalMachine.mockResolvedValue({ ip: '127.0.0.1', user: 'root' });
    await expect(assertMachineExists('hostinger')).resolves.toBeUndefined();
    expect(mockGetLocalMachine).toHaveBeenCalledWith('hostinger');
  });

  it('rejects with the not-found error from getLocalMachine', async () => {
    mockGetLocalMachine.mockRejectedValue(
      new Error('Machine "unknown" not found. Available: hostinger')
    );
    await expect(assertMachineExists('unknown')).rejects.toThrow(
      'Machine "unknown" not found. Available: hostinger'
    );
  });
});

describe('assertStorageExists', () => {
  beforeEach(() => vi.clearAllMocks());

  it('resolves when the storage exists', async () => {
    mockGetStorage.mockResolvedValue({ vaultContent: {} });
    await expect(assertStorageExists('my-s3')).resolves.toBeUndefined();
  });

  it('rethrows the original error when the name is not a repo either', async () => {
    mockGetStorage.mockRejectedValue(new Error('Storage "ghost" not found. Available: none'));
    mockListRepositories.mockResolvedValue([]);
    await expect(assertStorageExists('ghost')).rejects.toThrow(
      'Storage "ghost" not found. Available: none'
    );
  });

  it('throws a repository hint when the name matches a known repository', async () => {
    mockGetStorage.mockRejectedValue(new Error('Storage "myapp" not found. Available: none'));
    mockListRepositories.mockResolvedValue([
      { name: 'myapp:latest', config: { repositoryGuid: 'guid-1', tag: 'latest' } },
    ]);
    await expect(assertStorageExists('myapp')).rejects.toThrow(
      '"myapp" is a repository, not a storage. To delete a repository image use: rdc repository delete --name myapp'
    );
  });

  it('throws a repository hint when the full composite key matches', async () => {
    mockGetStorage.mockRejectedValue(
      new Error('Storage "myapp:latest" not found. Available: none')
    );
    mockListRepositories.mockResolvedValue([
      { name: 'myapp:latest', config: { repositoryGuid: 'guid-1', tag: 'latest' } },
    ]);
    await expect(assertStorageExists('myapp:latest')).rejects.toThrow(
      '"myapp:latest" is a repository, not a storage. To delete a repository image use: rdc repository delete --name myapp'
    );
  });
});

describe('assertRepositoryExists', () => {
  beforeEach(() => vi.clearAllMocks());

  it('resolves when the repository exists', async () => {
    mockGetRepository.mockResolvedValue({ repositoryGuid: 'guid-1', tag: 'latest' });
    await expect(assertRepositoryExists('myapp')).resolves.toBeUndefined();
  });

  it('rejects with available list when repository is not found', async () => {
    mockGetRepository.mockResolvedValue(undefined);
    mockListRepositories.mockResolvedValue([
      { name: 'other:latest', config: {} },
      { name: 'demo:staging', config: {} },
    ]);
    await expect(assertRepositoryExists('missing')).rejects.toThrow(
      'Repository "missing" not found. Available: other:latest, demo:staging'
    );
  });

  it('rejects with "none" when no repositories are configured', async () => {
    mockGetRepository.mockResolvedValue(undefined);
    mockListRepositories.mockResolvedValue([]);
    await expect(assertRepositoryExists('missing')).rejects.toThrow(
      'Repository "missing" not found. Available: none'
    );
  });
});
