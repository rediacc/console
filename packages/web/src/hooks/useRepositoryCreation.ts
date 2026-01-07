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

  const createRepository = async (data: RepoCreationData): Promise<RepoCreationResult> => {
    try {
      // Check if this is credential-only mode (repositoryGuid is provided)
      const isCredentialOnlyMode = data.repositoryGuid && data.repositoryGuid.trim() !== '';

      // Check if we have machine and size for full repository creation
      if (data.machineName && data.size && !isCredentialOnlyMode) {
        // Step 1: Create the repository credentials
        const { machineName, size, ...repositoryData } = data;
        await createRepositoryMutation.mutateAsync({
          ...repositoryData,
          vaultContent: repositoryData.vaultContent ?? '{}',
        });

        // Step 2: Queue the "repository_create" function to create the repository on the machine
        try {
          // Find the machine details from dropdown data
          const teamData = dropdownData?.machinesByTeam.find(
            (t: { teamName: string }) => t.teamName === data.teamName
          );
          const machineData = teamData?.machines.find(
            (m: { value: string }) => m.value === machineName
          );

          if (!machineData) {
            showMessage('error', t('resources:errors.machineNotFound'));
            return { success: false, error: 'Machine not found' };
          }

          // Find team vault data
          const team = teamsList.find((t) => t.teamName === data.teamName);

          // Find the full machine data to get vault content
          const fullMachine = machines.find(
            (m) => m.machineName === machineName && m.teamName === data.teamName
          );

          // Wait a bit for the repository to be fully created and indexed
          await new Promise((resolve) => setTimeout(resolve, 500));

          // Fetch the created repository to get its vault with credentials
          const repoResponse = await typedApi.GetTeamRepositories({ teamName: data.teamName });
          const repositoryList = parseGetTeamRepositories(repoResponse as never);
          const createdRepository = repositoryList.find(
            (repository) => repository.repositoryName === data.repositoryName
          );

          const repositoryVault = createdRepository?.vaultContent ?? data.vaultContent ?? '{}';
          const repositoryGuid = createdRepository?.repositoryGuid ?? '';

          if (!repositoryGuid) {
            showMessage('error', t('resources:errors.failedToGetRepoGuid'));
            return { success: false, error: 'Failed to get repository GUID' };
          }

          // Build queue vault for the "repository_create" function
          const params: Record<string, string> = {
            repository: repositoryGuid,
            size,
          };

          // Add template parameter if provided
          if (data.tmpl) {
            params.tmpl = data.tmpl;
          }

          // Add keep_open parameter if provided
          if (data.keep_open) {
            params.keep_open = 'true';
          }

          const queueVault = await buildQueueVault({
            teamName: data.teamName,
            machineName: machineData.value,
            bridgeName: machineData.bridgeName,
            functionName: 'repository_create',
            params,
            priority: 3,
            addedVia: 'repository-creation',
            teamVault: team?.vaultContent ?? '{}',
            machineVault: fullMachine?.vaultContent ?? '{}',
            repositoryVault,
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

          // Return success with taskId if available
          return {
            success: true,
            taskId: queueResponse.taskId,
            machineName: machineData.value,
          };
        } catch {
          showMessage('warning', t('repositories.repoCreatedButQueueFailed'));
          return {
            success: true, // Repository was created, just queue failed
            error: 'Queue creation failed',
          };
        }
      } else {
        // Create repository credentials only (no machine provisioning)
        await createRepositoryMutation.mutateAsync({
          ...data,
          vaultContent: data.vaultContent ?? '{}',
        });
        showMessage('success', t('repositories.createSuccess'));
        return { success: true };
      }
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
