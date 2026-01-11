import { showMessage } from '@/utils/messages';
import type { BridgeFunctionName } from '@rediacc/shared/queue-vault';
import { getGrandRepoVault, getRequiredTag } from '../hooks/useFunctionExecution';
import type { ForkFunctionData } from './types';
import type { FunctionExecutionContext } from '../hooks/useFunctionExecution';

// Helper to find repository data
const findRepoData = (context: FunctionExecutionContext) => {
  const { selectedRepository, teamRepositories } = context;
  if (!selectedRepository) return null;

  return teamRepositories.find(
    (r) =>
      r.repositoryName === selectedRepository.name &&
      r.repositoryTag === selectedRepository.repositoryTag
  );
};

// Helper to handle fork result
const handleForkResult = (
  result: { success: boolean; taskId?: string; isQueued?: boolean; error?: string },
  context: FunctionExecutionContext,
  forkTag: string
): void => {
  const { selectedRepository, machine, onQueueItemCreated, t } = context;

  if (!result.success) {
    throw new Error(result.error ?? 'Failed to fork Repository');
  }

  if (result.taskId) {
    showMessage(
      'success',
      t('resources:repositories.forkStarted', {
        dest: `${selectedRepository?.name}:${forkTag}`,
      })
    );
    if (onQueueItemCreated) onQueueItemCreated(result.taskId, machine.machineName);
    return;
  }

  if (result.isQueued) {
    showMessage('info', t('resources:repositories.highestPriorityQueued'));
  }
};

export const handleForkFunction = async (
  functionData: ForkFunctionData,
  context: FunctionExecutionContext
): Promise<void> => {
  const {
    selectedRepository,
    teamRepositories,
    machine,
    executeDynamic,
    createRepositoryCredential,
    closeModal,
    t,
  } = context;

  if (!selectedRepository) return;

  const RepoData = findRepoData(context);
  if (!RepoData?.vaultContent) {
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
    const result = await executeDynamic('backup_push' as BridgeFunctionName, {
      params: {
        repository: RepoData.repositoryGuid,
        repositoryName: RepoData.repositoryName,
        dest: newRepo.repositoryGuid,
        destName: newRepo.repositoryName,
        destinationType: 'machine',
        to: machine.machineName,
        state: selectedRepository.mounted ? 'online' : 'offline',
        grand: RepoData.grandGuid ?? RepoData.repositoryGuid,
      },
      teamName: machine.teamName,
      machineName: machine.machineName,
      bridgeName: machine.bridgeName,
      priority: functionData.priority,
      addedVia: 'machine-Repository-list-fork',
      machineVault: machine.vaultContent ?? '{}',
      repositoryGuid: RepoData.repositoryGuid,
      vaultContent: grandRepoVault,
      repositoryNetworkId: newRepo.repositoryNetworkId,
      repositoryNetworkMode: newRepo.repositoryNetworkMode,
      repositoryTag: newRepo.repositoryTag,
    });

    closeModal();
    handleForkResult(result, context, forkTag);
  } catch {
    showMessage('error', t('resources:repositories.failedToForkRepository'));
  }
};
