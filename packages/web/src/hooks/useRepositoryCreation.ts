import { useTranslation } from 'react-i18next';
import { useCreateRepository } from '@/api/api-hooks.generated';
import { useGetOrganizationTeams } from '@/api/api-hooks.generated';
import { typedApi } from '@/api/client';
import { useDropdownData } from '@/api/queries/useDropdownData';
import { useManagedQueueItem } from '@/hooks/useManagedQueueItem';
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder';
import type { Machine } from '@/types';
import { showMessage } from '@/utils/messages';
import { parseGetTeamRepositories } from '@rediacc/shared/api';

interface RepoCreationData {
  repositoryName: string;
  teamName: string;
  machineName?: string;
  size?: string;
  repositoryGuid?: string;
  vaultContent?: string;
  tmpl?: string;
  keep_open?: boolean;
}

interface RepoCreationResult {
  success: boolean;
  taskId?: string;
  machineName?: string;
  error?: string;
}

interface UseRepoCreationReturn {
  createRepository: (data: RepoCreationData) => Promise<RepoCreationResult>;
  isCreating: boolean;
}

/**
 * Custom hook for handling repository creation with optional queue item creation
 * Consolidates the two-step process:
 * 1. Create repository credentials
 * 2. Queue the "repository_create" function to create repository on machine (if machine and size provided)
 */
export function useRepositoryCreation(machines: Machine[]): UseRepoCreationReturn {
  const { t } = useTranslation(['resources', 'repositories']);
  const createRepositoryMutation = useCreateRepository();
  const createQueueItemMutation = useManagedQueueItem();
  const { buildQueueVault } = useQueueVaultBuilder();
  const { data: teamsList = [] } = useGetOrganizationTeams();
  const { data: dropdownData } = useDropdownData();

  const isCreating = [createRepositoryMutation.isPending, createQueueItemMutation.isPending].some(
    Boolean
  );

  const createCredentialsOnly = async (data: RepoCreationData): Promise<RepoCreationResult> => {
    await createRepositoryMutation.mutateAsync({
      ...data,
      vaultContent: data.vaultContent ?? '{}',
    });
    showMessage('success', t('repositories.createSuccess'));
    return { success: true };
  };

  const findMachineData = (machineName: string, teamName: string) => {
    const teamData = dropdownData?.machinesByTeam.find(
      (t: { teamName: string }) => t.teamName === teamName
    );
    return teamData?.machines.find((m: { value: string }) => m.value === machineName);
  };

  const buildRepositoryParams = (data: RepoCreationData, repositoryGuid: string) => {
    const params: Record<string, string> = {
      repository: repositoryGuid,
      size: data.size!,
    };
    if (data.tmpl) params.tmpl = data.tmpl;
    if (data.keep_open) params.keep_open = 'true';
    return params;
  };

  const createWithMachineProvisioning = async (
    data: RepoCreationData
  ): Promise<RepoCreationResult> => {
    const { machineName, size: _size, ...repositoryData } = data;
    await createRepositoryMutation.mutateAsync({
      ...repositoryData,
      vaultContent: repositoryData.vaultContent ?? '{}',
    });

    try {
      const machineData = findMachineData(machineName!, data.teamName);
      if (!machineData) {
        showMessage('error', t('resources:errors.machineNotFound'));
        return { success: false, error: 'Machine not found' };
      }

      const team = teamsList.find((t) => t.teamName === data.teamName);
      const fullMachine = machines.find(
        (m) => m.machineName === machineName && m.teamName === data.teamName
      );

      await new Promise((resolve) => setTimeout(resolve, 500));

      const repoResponse = await typedApi.GetTeamRepositories({ teamName: data.teamName });
      const repositoryList = parseGetTeamRepositories(repoResponse as never);
      const createdRepository = repositoryList.find(
        (repository) => repository.repositoryName === data.repositoryName
      );

      const repositoryGuid = createdRepository?.repositoryGuid ?? '';
      if (!repositoryGuid) {
        showMessage('error', t('resources:errors.failedToGetRepoGuid'));
        return { success: false, error: 'Failed to get repository GUID' };
      }

      const queueVault = await buildQueueVault({
        teamName: data.teamName,
        machineName: machineData.value,
        bridgeName: machineData.bridgeName,
        functionName: 'repository_create',
        params: buildRepositoryParams(data, repositoryGuid),
        priority: 3,
        addedVia: 'repository-creation',
        teamVault: team?.vaultContent ?? '{}',
        machineVault: fullMachine?.vaultContent ?? '{}',
        repositoryVault: createdRepository?.vaultContent ?? data.vaultContent ?? '{}',
        repositoryGuid,
        repositoryNetworkId: createdRepository?.repositoryNetworkId ?? undefined,
        repositoryNetworkMode: createdRepository?.repositoryNetworkMode ?? undefined,
        repositoryTag: createdRepository?.repositoryTag,
      });

      const queueResponse = await createQueueItemMutation.mutateAsync({
        teamName: data.teamName,
        machineName: machineData.value,
        bridgeName: machineData.bridgeName,
        queueVault,
        priority: 3,
      });

      showMessage('success', t('repositories.createSuccess'));
      return { success: true, taskId: queueResponse.taskId, machineName: machineData.value };
    } catch {
      showMessage('warning', t('repositories.repoCreatedButQueueFailed'));
      return { success: true, error: 'Queue creation failed' };
    }
  };

  const createRepository = async (data: RepoCreationData): Promise<RepoCreationResult> => {
    try {
      const isCredentialOnlyMode = data.repositoryGuid && data.repositoryGuid.trim() !== '';
      const shouldProvisionOnMachine = data.machineName && data.size && !isCredentialOnlyMode;

      if (shouldProvisionOnMachine) {
        return await createWithMachineProvisioning(data);
      }
      return await createCredentialsOnly(data);
    } catch (error) {
      console.error('Failed to create repository:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error',
      };
    }
  };

  return {
    createRepository,
    isCreating,
  };
}
