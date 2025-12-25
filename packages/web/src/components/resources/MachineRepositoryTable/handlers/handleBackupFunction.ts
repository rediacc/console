import { canBackupToStorage } from '@/platform';
import { showMessage } from '@/utils/messages';
import { getGrandRepoVault, showMultiTargetSummary } from '../hooks/useFunctionExecution';
import type { FunctionExecutionContext, FunctionData } from '../hooks/useFunctionExecution';

export const handleBackupFunction = async (
  functionData: FunctionData,
  context: FunctionExecutionContext
): Promise<void> => {
  const {
    selectedRepository,
    teamRepositories,
    machine,
    teamStorages,
    executeAction,
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

  if (!canBackupToStorage(RepoData).canBackup) {
    showMessage('error', t('resources:repositories.cannotBackupForkToStorage'));
    closeModal();
    return;
  }

  const storagesArray = Array.isArray(functionData.params.storages)
    ? functionData.params.storages
    : [functionData.params.storages];
  const grandRepoVault = getGrandRepoVault(RepoData, teamRepositories);
  const createdTaskIds: string[] = [];

  for (const targetStorage of storagesArray) {
    const destinationStorage = teamStorages.find((s) => s.storageName === targetStorage);
    if (!destinationStorage) {
      showMessage(
        'error',
        t('resources:repositories.destinationStorageNotFound', { storage: targetStorage })
      );
      continue;
    }

    try {
      const result = await executeAction({
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        functionName: 'backup',
        params: {
          ...functionData.params,
          storages: storagesArray.join(','),
          to: targetStorage,
          dest: RepoData.repositoryGuid,
          destName: RepoData.repositoryName,
          repository: RepoData.repositoryGuid,
          repositoryName: RepoData.repositoryName,
          grand: RepoData.grandGuid ?? RepoData.repositoryGuid,
          state: selectedRepository.mounted ? 'online' : 'offline',
        },
        priority: functionData.priority,
        addedVia: 'machine-Repository-list',
        machineVault: machine.vaultContent ?? '{}',
        destinationStorageVault: destinationStorage.vaultContent ?? '{}',
        repositoryGuid: RepoData.repositoryGuid,
        vaultContent: grandRepoVault,
        repositoryNetworkId: RepoData.repositoryNetworkId,
        repositoryNetworkMode: RepoData.repositoryNetworkMode,
        repositoryTag: RepoData.repositoryTag,
      });
      if (result.success && result.taskId) createdTaskIds.push(result.taskId);
    } catch {
      showMessage(
        'error',
        t('resources:repositories.failedToBackupTo', { storage: targetStorage })
      );
    }
  }

  closeModal();
  showMultiTargetSummary(
    createdTaskIds,
    storagesArray.length,
    {
      success: 'resources:repositories.backupQueued',
      partial: 'resources:repositories.backupPartialSuccess',
      allFailed: 'resources:repositories.allBackupsFailed',
    },
    t,
    onQueueItemCreated,
    machine.machineName
  );
};
