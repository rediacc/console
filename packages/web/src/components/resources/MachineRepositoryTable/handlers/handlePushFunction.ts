import { canBackupToStorage } from '@/platform';
import { showMessage } from '@/utils/messages';
import type { BridgeFunctionName } from '@rediacc/shared/queue-vault';
import {
  getGrandRepoVault,
  getRequiredTag,
  showMultiTargetSummary,
} from '../hooks/useFunctionExecution';
import type { FunctionExecutionContext } from '../hooks/useFunctionExecution';
import type { RepositoryTableRow } from '../types';
import type { PushFunctionData } from './types';

// Type alias for team repository data from context
type TeamRepositoryData = FunctionExecutionContext['teamRepositories'][number];

// Helper to find repository data
const findRepoData = (
  selectedRepository: RepositoryTableRow | null,
  teamRepositories: TeamRepositoryData[]
): TeamRepositoryData | undefined => {
  if (!selectedRepository) return undefined;

  return teamRepositories.find(
    (r) =>
      r.repositoryName === selectedRepository.name &&
      r.repositoryTag === selectedRepository.repositoryTag
  );
};

// Helper to normalize array input
const normalizeArrayParam = (input: unknown): unknown[] => {
  if (Array.isArray(input)) return input;
  if (input) return [input];
  return [];
};

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

// Helper to deploy to a single machine
async function deployToSingleMachine(
  targetMachine: unknown,
  functionData: PushFunctionData,
  context: FunctionExecutionContext,
  repoData: TeamRepositoryData,
  newRepo: {
    repositoryGuid: string;
    repositoryName: string;
    repositoryNetworkId?: number;
    repositoryNetworkMode?: string;
    repositoryTag: string;
  },
  grandRepoVault: string,
  machinesArray: unknown[]
): Promise<string | null> {
  const { selectedRepository, machine, teamMachines, executeDynamic, t } = context;

  const destinationMachine = teamMachines.find((m) => m.machineName === targetMachine);
  if (!destinationMachine) {
    showMessage(
      'error',
      t('resources:repositories.destinationMachineNotFound', { machine: targetMachine })
    );
    return null;
  }

  const result = await executeDynamic('backup_push' as BridgeFunctionName, {
    params: {
      ...functionData.params,
      machines: machinesArray.join(','),
      to: targetMachine,
      dest: newRepo.repositoryGuid,
      destName: newRepo.repositoryName,
      repository: repoData.repositoryGuid,
      repositoryName: repoData.repositoryName,
      grand: repoData.grandGuid ?? repoData.repositoryGuid,
      state: selectedRepository?.mounted ? 'online' : 'offline',
    },
    teamName: machine.teamName,
    machineName: machine.machineName,
    bridgeName: machine.bridgeName,
    priority: functionData.priority,
    addedVia: 'machine-Repository-list',
    machineVault: machine.vaultContent ?? '{}',
    destinationMachineVault: destinationMachine.vaultContent ?? '{}',
    repositoryGuid: repoData.repositoryGuid,
    vaultContent: grandRepoVault,
    repositoryNetworkId: newRepo.repositoryNetworkId,
    repositoryNetworkMode: newRepo.repositoryNetworkMode,
    repositoryTag: newRepo.repositoryTag,
  });

  return result.success && result.taskId ? result.taskId : null;
}

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
    createRepositoryCredential,
    onQueueItemCreated,
    closeModal,
    t,
  } = context;

  if (!selectedRepository) return;

  const RepoData = findRepoData(selectedRepository, teamRepositories);
  if (!RepoData?.vaultContent) {
    showMessage(
      'error',
      t('resources:repositories.noCredentialsFound', { name: selectedRepository.name })
    );
    closeModal();
    return;
  }

  const machinesArray = normalizeArrayParam(functionData.params.machines);

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
    try {
      const taskId = await deployToSingleMachine(
        targetMachine,
        functionData,
        context,
        RepoData,
        newRepo,
        grandRepoVault,
        machinesArray
      );
      if (taskId) createdTaskIds.push(taskId);
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

// Helper to backup to a single storage
async function backupToSingleStorage(
  targetStorage: unknown,
  functionData: PushFunctionData,
  context: FunctionExecutionContext,
  repoData: TeamRepositoryData,
  grandRepoVault: string,
  storagesArray: unknown[]
): Promise<string | null> {
  const { selectedRepository, machine, teamStorages, executeDynamic, t } = context;

  const destinationStorage = teamStorages.find((s) => s.storageName === targetStorage);
  if (!destinationStorage) {
    showMessage(
      'error',
      t('resources:repositories.destinationStorageNotFound', { storage: targetStorage })
    );
    return null;
  }

  const result = await executeDynamic('backup_push' as BridgeFunctionName, {
    params: {
      ...functionData.params,
      storages: storagesArray.join(','),
      to: targetStorage,
      dest: repoData.repositoryGuid,
      destName: repoData.repositoryName,
      repository: repoData.repositoryGuid,
      repositoryName: repoData.repositoryName,
      grand: repoData.grandGuid ?? repoData.repositoryGuid,
      state: selectedRepository?.mounted ? 'online' : 'offline',
    },
    teamName: machine.teamName,
    machineName: machine.machineName,
    bridgeName: machine.bridgeName,
    priority: functionData.priority,
    addedVia: 'machine-Repository-list',
    machineVault: machine.vaultContent ?? '{}',
    destinationStorageVault: destinationStorage.vaultContent ?? '{}',
    repositoryGuid: repoData.repositoryGuid,
    vaultContent: grandRepoVault,
    repositoryNetworkId: repoData.repositoryNetworkId ?? undefined,
    repositoryNetworkMode: repoData.repositoryNetworkMode ?? undefined,
    repositoryTag: repoData.repositoryTag,
  });

  return result.success && result.taskId ? result.taskId : null;
}

/**
 * Push repository to storages (parallel backup).
 * Migrated from handleBackupFunction.
 */
async function handlePushToStorages(
  functionData: PushFunctionData,
  context: FunctionExecutionContext
): Promise<void> {
  const { selectedRepository, teamRepositories, machine, onQueueItemCreated, closeModal, t } =
    context;

  if (!selectedRepository) return;

  const RepoData = findRepoData(selectedRepository, teamRepositories);
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

  const storagesArray = normalizeArrayParam(functionData.params.storages);
  const grandRepoVault = getGrandRepoVault(RepoData, teamRepositories);
  const createdTaskIds: string[] = [];

  for (const targetStorage of storagesArray) {
    try {
      const taskId = await backupToSingleStorage(
        targetStorage,
        functionData,
        context,
        RepoData,
        grandRepoVault,
        storagesArray
      );
      if (taskId) createdTaskIds.push(taskId);
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
