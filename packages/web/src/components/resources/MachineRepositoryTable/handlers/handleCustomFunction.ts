import { showMessage } from '@/utils/messages';
import type { BridgeFunctionName } from '@rediacc/shared/queue-vault';
import { getGrandRepoVault } from '../hooks/useFunctionExecution';
import type { CustomFunctionData } from './types';
import type { FunctionExecutionContext } from '../hooks/useFunctionExecution';

export const handleCustomFunction = async (
  functionData: CustomFunctionData,
  context: FunctionExecutionContext
): Promise<void> => {
  const {
    selectedRepository,
    teamRepositories,
    machine,
    executeDynamic,
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

  if (!RepoData?.vaultContent) {
    showMessage(
      'error',
      t('resources:repositories.noCredentialsFound', { name: selectedRepository.name })
    );
    closeModal();
    return;
  }

  const grandRepoVault = getGrandRepoVault(RepoData, teamRepositories);

  const result = await executeDynamic(functionData.function.name as BridgeFunctionName, {
    params: functionData.params,
    teamName: machine.teamName,
    machineName: machine.machineName,
    bridgeName: machine.bridgeName,
    priority: functionData.priority,
    addedVia: 'machine-Repository-list',
    machineVault: machine.vaultContent ?? '{}',
    repositoryGuid: RepoData.repositoryGuid,
    vaultContent: grandRepoVault,
    repositoryNetworkId: RepoData.repositoryNetworkId,
    repositoryNetworkMode: RepoData.repositoryNetworkMode,
    repositoryTag: RepoData.repositoryTag,
  });

  closeModal();

  if (result.success) {
    if (result.taskId) {
      showMessage('success', t('resources:repositories.queueItemCreated'));
      if (onQueueItemCreated) {
        onQueueItemCreated(result.taskId, machine.machineName);
      }
    } else if (result.isQueued) {
      showMessage('info', t('resources:repositories.highestPriorityQueued'));
    }
  } else {
    throw new Error(result.error ?? t('resources:repositories.failedToCreateQueueItem'));
  }
};
