import { useTranslation } from 'react-i18next';
import { api } from '@/api/client';
import { useCreateRepository } from '@/api/queries/repositories';
import { useTeams } from '@/api/queries/teams';
import { useDropdownData } from '@/api/queries/useDropdownData';
import { useManagedQueueItem } from '@/hooks/useManagedQueueItem';
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder';
import type { Machine } from '@/types';
import { showMessage } from '@/utils/messages';

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
 * 2. Queue the "new" function to create repository on machine (if machine and size provided)
 */
export function useRepositoryCreation(machines: Machine[]): UseRepoCreationReturn {
  const { t } = useTranslation(['resources', 'repositories']);
  const createRepositoryMutation = useCreateRepository();
  const createQueueItemMutation = useManagedQueueItem();
  const { buildQueueVault } = useQueueVaultBuilder();
  const { data: teamsList = [] } = useTeams();
  const { data: dropdownData } = useDropdownData();

  const isCreating = createRepositoryMutation.isPending || createQueueItemMutation.isPending;

  const createRepository = async (data: RepoCreationData): Promise<RepoCreationResult> => {
    try {
      // Check if this is credential-only mode (repositoryGuid is provided)
      const isCredentialOnlyMode = data.repositoryGuid && data.repositoryGuid.trim() !== '';

      // Check if we have machine and size for full repository creation
      if (data.machineName && data.size && !isCredentialOnlyMode) {
        // Step 1: Create the repository credentials
        const { machineName, size, ...repositoryData } = data;
        await createRepositoryMutation.mutateAsync(repositoryData);

        // Step 2: Queue the "new" function to create the repository on the machine
        try {
          // Find the machine details from dropdown data
          const teamData = dropdownData?.machinesByTeam.find((t) => t.teamName === data.teamName);
          const machineData = teamData?.machines.find((m) => m.value === machineName);

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
          const repositoryList = await api.repositories.list({ teamName: data.teamName });
          const createdRepository = repositoryList.find(
            (repository) => repository.repositoryName === data.repositoryName
          );

          const repositoryVault = createdRepository?.vaultContent ?? data.vaultContent ?? '{}';
          const repositoryGuid = createdRepository?.repositoryGuid ?? '';

          if (!repositoryGuid) {
            showMessage('error', t('resources:errors.failedToGetRepoGuid'));
            return { success: false, error: 'Failed to get repository GUID' };
          }

          // Build queue vault for the "new" function
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
            functionName: 'new',
            params,
            priority: 3,
            addedVia: 'repository-creation',
            teamVault: team?.vaultContent ?? '{}',
            machineVault: fullMachine?.vaultContent ?? '{}',
            repositoryVault,
            repositoryGuid,
            repositoryNetworkId: createdRepository?.repositoryNetworkId,
            repositoryNetworkMode: createdRepository?.repositoryNetworkMode,
            repositoryTag: createdRepository?.repositoryTag,
          });

          const response = await createQueueItemMutation.mutateAsync({
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
            taskId: response.taskId,
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
        await createRepositoryMutation.mutateAsync(data);
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
