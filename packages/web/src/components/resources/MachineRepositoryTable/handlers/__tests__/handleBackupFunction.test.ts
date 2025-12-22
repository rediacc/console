import { describe, it, expect, vi, beforeEach } from 'vitest';
import { handleBackupFunction } from '../handleBackupFunction';
import type { FunctionExecutionContext, FunctionData } from '../../hooks/useFunctionExecution';

vi.mock('@/platform', () => ({
  canBackupToStorage: vi.fn(() => ({ canBackup: true })),
}));

describe('handleBackupFunction', () => {
  let mockContext: FunctionExecutionContext;
  let mockFunctionData: FunctionData;

  beforeEach(() => {
    mockContext = {
      selectedRepository: {
        name: 'test-repo',
        repositoryTag: 'latest',
        mounted: true,
      },
      teamRepositories: [
        {
          repositoryName: 'test-repo',
          repositoryTag: 'latest',
          repositoryGuid: 'repo-123',
          vaultContent: '{"key":"value"}',
          grandGuid: 'grand-123',
        },
      ],
      machine: {
        teamName: 'test-team',
        machineName: 'test-machine',
        bridgeName: 'test-bridge',
        vaultContent: '{}',
      },
      teamMachines: [],
      teamStorages: [
        {
          storageName: 'storage-1',
          vaultContent: '{}',
        },
        {
          storageName: 'storage-2',
          vaultContent: '{}',
        },
      ],
      executeAction: vi.fn().mockResolvedValue({ success: true, taskId: 'task-123' }),
      createRepositoryCredential: vi.fn(),
      onQueueItemCreated: vi.fn(),
      closeModal: vi.fn(),
      t: vi.fn((key) => key),
    } as unknown as FunctionExecutionContext;

    mockFunctionData = {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      function: { name: 'backup' } as any,
      params: { storages: ['storage-1', 'storage-2'] },
      priority: 4,
      description: 'Backup repository',
    };
  });

  it('should successfully backup to multiple storages', async () => {
    await handleBackupFunction(mockFunctionData, mockContext);

    expect(mockContext.executeAction).toHaveBeenCalledTimes(2);
    expect(mockContext.closeModal).toHaveBeenCalled();
  });

  it('should handle single storage as string', async () => {
    mockFunctionData.params.storages = 'storage-1';

    await handleBackupFunction(mockFunctionData, mockContext);

    expect(mockContext.executeAction).toHaveBeenCalledTimes(1);
  });

  it('should skip non-existent storages', async () => {
    mockFunctionData.params.storages = ['storage-1', 'non-existent'];

    await handleBackupFunction(mockFunctionData, mockContext);

    expect(mockContext.executeAction).toHaveBeenCalledTimes(1);
  });

  it('should return early if repository is not found', async () => {
    mockContext.teamRepositories = [];

    await handleBackupFunction(mockFunctionData, mockContext);

    expect(mockContext.closeModal).toHaveBeenCalled();
    expect(mockContext.executeAction).not.toHaveBeenCalled();
  });
});
