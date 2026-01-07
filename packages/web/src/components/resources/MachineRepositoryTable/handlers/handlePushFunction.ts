import { canBackupToStorage } from '@/platform';
import { showMessage } from '@/utils/messages';
import type { BridgeFunctionName } from '@rediacc/shared/queue-vault';
import {
  getGrandRepoVault,
  getRequiredTag,
  showMultiTargetSummary,
} from '../hooks/useFunctionExecution';
import type { PushFunctionData } from './types';
import type { FunctionExecutionContext } from '../hooks/useFunctionExecution';

/**
 * Unified handler for backup_push function.
 * Replaces both handleBackupFunction (storage) and handleDeployFunction (machine).
 */
export const handlePushFunction = async (
  functionData: PushFunctionData,
  context: FunctionExecutionContext
): Promise<void> => {
  const { destinationType } = functionData.params;

  if (destinationType === 'machine') {
    await handlePushToMachines(functionData, context);
  } else {
    await handlePushToStorages(functionData, context);
  }
};

/**
 * Push repository to machines (parallel deployment).
 * Migrated from handleDeployFunction.
 */
async function handlePushToMachines(
  functionData: PushFunctionData,
  context: FunctionExecutionContext
): Promise<void> {
  const {
    selectedRepository,
    teamRepositories,
    machine,
    teamMachines,
    executeDynamic,
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

  if (!RepoData?.vaultContent) {
    showMessage(
      'error',
      t('resources:repositories.noCredentialsFound', { name: selectedRepository.name })
    );
    closeModal();
    return;
  }

  const machinesArray = Array.isArray(functionData.params.machines)
    ? functionData.params.machines
    : functionData.params.machines
      ? [functionData.params.machines]
      : [];

  const deployTag = getRequiredTag(
    functionData.params,
    'Tag is required for deploy',
    t,
    closeModal
  );
  if (!deployTag) return;

  let newRepo;
  try {
    newRepo = await createRepositoryCredential(selectedRepository.name, deployTag);
  } catch {
    showMessage('error', t('resources:repositories.failedToCreateRepository'));
    closeModal();
    return;
  }

  const grandRepoVault = getGrandRepoVault(RepoData, teamRepositories);
  const createdTaskIds: string[] = [];

  for (const targetMachine of machinesArray) {
    const destinationMachine = teamMachines.find((m) => m.machineName === targetMachine);
    if (!destinationMachine) {
      showMessage(
        'error',
        t('resources:repositories.destinationMachineNotFound', { machine: targetMachine })
      );
      continue;
    }

    try {
      const result = await executeDynamic('backup_push' as BridgeFunctionName, {
        params: {
          ...functionData.params,
          machines: machinesArray.join(','),
          to: targetMachine,
          dest: newRepo.repositoryGuid,
          destName: newRepo.repositoryName,
          repository: RepoData.repositoryGuid,
          repositoryName: RepoData.repositoryName,
          grand: RepoData.grandGuid ?? RepoData.repositoryGuid,
          state: selectedRepository.mounted ? 'online' : 'offline',
        },
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        priority: functionData.priority,
        addedVia: 'machine-Repository-list',
        machineVault: machine.vaultContent ?? '{}',
        destinationMachineVault: destinationMachine.vaultContent ?? '{}',
        repositoryGuid: RepoData.repositoryGuid,
        vaultContent: grandRepoVault,
        repositoryNetworkId: newRepo.repositoryNetworkId,
        repositoryNetworkMode: newRepo.repositoryNetworkMode,
        repositoryTag: newRepo.repositoryTag,
      });
      if (result.success && result.taskId) createdTaskIds.push(result.taskId);
    } catch {
      showMessage(
        'error',
        t('resources:repositories.failedToDeployTo', { machine: targetMachine })
      );
    }
  }

  closeModal();
  showMultiTargetSummary(
    createdTaskIds,
    machinesArray.length,
    {
      success: 'resources:repositories.deploymentQueued',
      partial: 'resources:repositories.deploymentPartialSuccess',
      allFailed: 'resources:repositories.allDeploymentsFailed',
    },
    t,
    onQueueItemCreated,
    machine.machineName
  );
}

/**
 * Push repository to storages (parallel backup).
 * Migrated from handleBackupFunction.
 */
async function handlePushToStorages(
  functionData: PushFunctionData,
  context: FunctionExecutionContext
): Promise<void> {
  const {
    selectedRepository,
    teamRepositories,
    machine,
    teamStorages,
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

  if (!canBackupToStorage(RepoData).canBackup) {
    showMessage('error', t('resources:repositories.cannotBackupForkToStorage'));
    closeModal();
    return;
  }

  const storagesArray = Array.isArray(functionData.params.storages)
    ? functionData.params.storages
    : functionData.params.storages
      ? [functionData.params.storages]
      : [];

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
      const result = await executeDynamic('backup_push' as BridgeFunctionName, {
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
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
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
}
