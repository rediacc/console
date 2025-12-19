import { describe, it, expect, vi, beforeEach } from 'vitest';
import { handleForkFunction } from '../handleForkFunction';
import type { FunctionExecutionContext, FunctionData } from '../../hooks/useFunctionExecution';

describe('handleForkFunction', () => {
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
      teamStorages: [],
      executeAction: vi.fn().mockResolvedValue({ success: true, taskId: 'task-123' }),
      createRepositoryCredential: vi.fn().mockResolvedValue({
        repositoryGuid: 'new-repo-123',
        repositoryName: 'test-repo',
        repositoryTag: 'fork-tag',
      }),
      onQueueItemCreated: vi.fn(),
      closeModal: vi.fn(),
      t: vi.fn((key) => key),
    } as unknown as FunctionExecutionContext;

    mockFunctionData = {
      function: { name: 'fork' } as any,
      params: { tag: 'fork-tag' },
      priority: 4,
      description: 'Fork repository',
    };
  });

  it('should successfully fork a repository', async () => {
    await handleForkFunction(mockFunctionData, mockContext);

    expect(mockContext.createRepositoryCredential).toHaveBeenCalledWith('test-repo', 'fork-tag');
    expect(mockContext.executeAction).toHaveBeenCalled();
    expect(mockContext.closeModal).toHaveBeenCalled();
    expect(mockContext.onQueueItemCreated).toHaveBeenCalledWith('task-123', 'test-machine');
  });

  it('should return early if no repository is selected', async () => {
    mockContext.selectedRepository = null;

    await handleForkFunction(mockFunctionData, mockContext);

    expect(mockContext.createRepositoryCredential).not.toHaveBeenCalled();
  });

  it('should return early if tag is missing', async () => {
    mockFunctionData.params.tag = '';

    await handleForkFunction(mockFunctionData, mockContext);

    expect(mockContext.closeModal).toHaveBeenCalled();
    expect(mockContext.createRepositoryCredential).not.toHaveBeenCalled();
  });

  it('should handle repository creation failure', async () => {
    mockContext.createRepositoryCredential = vi.fn().mockRejectedValue(new Error('Creation failed'));

    await handleForkFunction(mockFunctionData, mockContext);

    expect(mockContext.closeModal).toHaveBeenCalled();
    expect(mockContext.executeAction).not.toHaveBeenCalled();
  });

  it('should handle repository not found', async () => {
    mockContext.teamRepositories = [];

    await handleForkFunction(mockFunctionData, mockContext);

    expect(mockContext.closeModal).toHaveBeenCalled();
    expect(mockContext.createRepositoryCredential).not.toHaveBeenCalled();
  });
});
