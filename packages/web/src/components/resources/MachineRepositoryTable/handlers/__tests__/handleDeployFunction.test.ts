import { describe, it, expect, vi, beforeEach } from 'vitest';
import { handleDeployFunction } from '../handleDeployFunction';
import type { FunctionExecutionContext, FunctionData } from '../../hooks/useFunctionExecution';

describe('handleDeployFunction', () => {
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
      teamMachines: [
        {
          machineName: 'target-machine-1',
          vaultContent: '{}',
        },
        {
          machineName: 'target-machine-2',
          vaultContent: '{}',
        },
      ],
      teamStorages: [],
      executeAction: vi.fn().mockResolvedValue({ success: true, taskId: 'task-123' }),
      createRepositoryCredential: vi.fn().mockResolvedValue({
        repositoryGuid: 'new-repo-123',
        repositoryName: 'test-repo',
        repositoryTag: 'deploy-tag',
      }),
      onQueueItemCreated: vi.fn(),
      closeModal: vi.fn(),
      t: vi.fn((key, params) => `${key}${params ? JSON.stringify(params) : ''}`),
    } as unknown as FunctionExecutionContext;

    mockFunctionData = {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      function: { name: 'deploy' } as any,
      params: { tag: 'deploy-tag', machines: ['target-machine-1', 'target-machine-2'] },
      priority: 4,
      description: 'Deploy repository',
    };
  });

  it('should successfully deploy to multiple machines', async () => {
    await handleDeployFunction(mockFunctionData, mockContext);

    expect(mockContext.createRepositoryCredential).toHaveBeenCalledWith('test-repo', 'deploy-tag');
    expect(mockContext.executeAction).toHaveBeenCalledTimes(2);
    expect(mockContext.closeModal).toHaveBeenCalled();
  });

  it('should handle single machine as string', async () => {
    mockFunctionData.params.machines = 'target-machine-1';

    await handleDeployFunction(mockFunctionData, mockContext);

    expect(mockContext.executeAction).toHaveBeenCalledTimes(1);
  });

  it('should skip non-existent machines', async () => {
    mockFunctionData.params.machines = ['target-machine-1', 'non-existent'];

    await handleDeployFunction(mockFunctionData, mockContext);

    expect(mockContext.executeAction).toHaveBeenCalledTimes(1);
  });

  it('should return early if tag is missing', async () => {
    mockFunctionData.params.tag = '';

    await handleDeployFunction(mockFunctionData, mockContext);

    expect(mockContext.closeModal).toHaveBeenCalled();
    expect(mockContext.createRepositoryCredential).not.toHaveBeenCalled();
  });

  it('should handle repository creation failure', async () => {
    mockContext.createRepositoryCredential = vi
      .fn()
      .mockRejectedValue(new Error('Creation failed'));

    await handleDeployFunction(mockFunctionData, mockContext);

    expect(mockContext.closeModal).toHaveBeenCalled();
    expect(mockContext.executeAction).not.toHaveBeenCalled();
  });
});
