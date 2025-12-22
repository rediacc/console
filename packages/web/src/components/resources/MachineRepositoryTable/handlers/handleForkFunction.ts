import { showMessage } from '@/utils/messages';
import { getGrandRepoVault, getRequiredTag } from '../hooks/useFunctionExecution';
import type { FunctionExecutionContext, FunctionData } from '../hooks/useFunctionExecution';

export const handleForkFunction = async (
  functionData: FunctionData,
  context: FunctionExecutionContext
): Promise<void> => {
  const {
    selectedRepository,
    teamRepositories,
    machine,
    executeAction,
    createRepositoryCredential,
    onQueueItemCreated,
    closeModal,
    t,
  } = context;

  if (!selectedRepository) return;

  const RepoData = teamRepositories.find(
    (r) =>
      r.repositoryName === selectedRepository.name &&
      r.repositoryTag === selectedRepository.repositoryTag
  );

  if (!RepoData || !RepoData.vaultContent) {
    showMessage(
      'error',
      t('resources:repositories.noCredentialsFound', { name: selectedRepository.name })
    );
    closeModal();
    return;
  }

  const forkTag = getRequiredTag(functionData.params, 'Tag is required for fork', t, closeModal);
  if (!forkTag) return;

  let newRepo;
  try {
    newRepo = await createRepositoryCredential(selectedRepository.name, forkTag);
  } catch {
    showMessage('error', t('resources:repositories.failedToCreateRepository'));
    closeModal();
    return;
  }

  const grandRepoVault = getGrandRepoVault(RepoData, teamRepositories);

  try {
    const result = await executeAction({
      teamName: machine.teamName,
      machineName: machine.machineName,
      bridgeName: machine.bridgeName,
      functionName: 'push',
      params: {
        repository: RepoData.repositoryGuid,
        repositoryName: RepoData.repositoryName,
        dest: newRepo.repositoryGuid,
        destName: newRepo.repositoryName,
        destinationType: 'machine',
        to: machine.machineName,
        state: selectedRepository.mounted ? 'online' : 'offline',
        grand: RepoData.grandGuid || RepoData.repositoryGuid || '',
      },
      priority: functionData.priority,
      addedVia: 'machine-Repository-list-fork',
      machineVault: machine.vaultContent || '{}',
      repositoryGuid: RepoData.repositoryGuid,
      vaultContent: grandRepoVault,
      repositoryNetworkId: newRepo.repositoryNetworkId,
      repositoryNetworkMode: newRepo.repositoryNetworkMode,
      repositoryTag: newRepo.repositoryTag,
    });

    closeModal();

    if (result.success) {
      if (result.taskId) {
        showMessage(
          'success',
          t('resources:repositories.forkStarted', {
            dest: `${selectedRepository.name}:${forkTag}`,
          })
        );
        if (onQueueItemCreated) onQueueItemCreated(result.taskId, machine.machineName);
      } else if (result.isQueued) {
        showMessage('info', t('resources:repositories.highestPriorityQueued'));
      }
    } else {
      throw new Error(result.error || 'Failed to fork Repository');
    }
  } catch {
    showMessage('error', t('resources:repositories.failedToForkRepository'));
  }
};
