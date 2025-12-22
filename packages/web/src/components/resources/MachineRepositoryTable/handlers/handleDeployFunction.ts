import { showMessage } from '@/utils/messages';
import {
  getGrandRepoVault,
  getRequiredTag,
  showMultiTargetSummary,
} from '../hooks/useFunctionExecution';
import type { FunctionExecutionContext, FunctionData } from '../hooks/useFunctionExecution';

export const handleDeployFunction = async (
  functionData: FunctionData,
  context: FunctionExecutionContext
): Promise<void> => {
  const {
    selectedRepository,
    teamRepositories,
    machine,
    teamMachines,
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

  const machinesArray = Array.isArray(functionData.params.machines)
    ? functionData.params.machines
    : [functionData.params.machines];
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
      const result = await executeAction({
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        functionName: 'deploy',
        params: {
          ...functionData.params,
          machines: machinesArray.join(','),
          to: targetMachine,
          dest: newRepo.repositoryGuid,
          destName: newRepo.repositoryName,
          repository: RepoData.repositoryGuid,
          repositoryName: RepoData.repositoryName,
          grand: RepoData.grandGuid || RepoData.repositoryGuid || '',
          state: selectedRepository.mounted ? 'online' : 'offline',
        },
        priority: functionData.priority,
        addedVia: 'machine-Repository-list',
        machineVault: machine.vaultContent || '{}',
        destinationMachineVault: destinationMachine.vaultContent || '{}',
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
};
