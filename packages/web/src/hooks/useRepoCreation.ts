import { useCreateRepo } from '@/api/queries/repos';
import { useTeams } from '@/api/queries/teams';
import { useManagedQueueItem } from '@/hooks/useManagedQueueItem';
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder';
import { useDropdownData } from '@/api/queries/useDropdownData';
import { showMessage } from '@/utils/messages';
import { api } from '@/api/client';
import { useTranslation } from 'react-i18next';
import type { Machine } from '@/types';

interface RepoCreationData {
  repoName: string;
  teamName: string;
  machineName?: string;
  size?: string;
  repoGuid?: string;
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
  createRepo: (data: RepoCreationData) => Promise<RepoCreationResult>;
  isCreating: boolean;
}

/**
 * Custom hook for handling repo creation with optional queue item creation
 * Consolidates the two-step process:
 * 1. Create repo credentials
 * 2. Queue the "new" function to create repo on machine (if machine and size provided)
 */
export function useRepoCreation(machines: Machine[]): UseRepoCreationReturn {
  const { t } = useTranslation(['resources', 'repos']);
  const createRepoMutation = useCreateRepo();
  const createQueueItemMutation = useManagedQueueItem();
  const { buildQueueVault } = useQueueVaultBuilder();
  const { data: teamsList = [] } = useTeams();
  const { data: dropdownData } = useDropdownData();

  const isCreating = createRepoMutation.isPending || createQueueItemMutation.isPending;

  const createRepo = async (data: RepoCreationData): Promise<RepoCreationResult> => {
    try {
      // Check if this is credential-only mode (repoGuid is provided)
      const isCredentialOnlyMode = data.repoGuid && data.repoGuid.trim() !== '';

      // Check if we have machine and size for full repo creation
      if (data.machineName && data.size && !isCredentialOnlyMode) {
        // Step 1: Create the repo credentials
        const { machineName, size, ...repoData } = data;
        await createRepoMutation.mutateAsync(repoData);

        // Step 2: Queue the "new" function to create the repo on the machine
        try {
          // Find the machine details from dropdown data
          const teamData = dropdownData?.machinesByTeam?.find((t) => t.teamName === data.teamName);
          const machineData = teamData?.machines?.find((m) => m.value === machineName);

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

          // Wait a bit for the repo to be fully created and indexed
          await new Promise((resolve) => setTimeout(resolve, 500));

          // Fetch the created repo to get its vault with credentials
          const repoList = await api.repos.list(data.teamName);
          const createdRepo = repoList.find((repo) => repo.repoName === data.repoName);

          const repoVault = createdRepo?.vaultContent || data.vaultContent || '{}';
          const repoGuid = createdRepo?.repoGuid || '';

          if (!repoGuid) {
            showMessage('error', t('resources:errors.failedToGetRepoGuid'));
            return { success: false, error: 'Failed to get repo GUID' };
          }

          // Build queue vault for the "new" function
          const params: Record<string, string> = {
            repo: repoGuid,
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
            params: params,
            priority: 3,
            addedVia: 'repo-creation',
            teamVault: team?.vaultContent || '{}',
            machineVault: fullMachine?.vaultContent || '{}',
            repoVault: repoVault,
            repositoryGuid: repoGuid,
            repositoryNetworkId: createdRepo?.repoNetworkId,
            repositoryNetworkMode: createdRepo?.repoNetworkMode,
            repositoryTag: createdRepo?.repoTag,
          });

          const response = await createQueueItemMutation.mutateAsync({
            teamName: data.teamName,
            machineName: machineData.value,
            bridgeName: machineData.bridgeName,
            queueVault,
            priority: 3,
          });

          showMessage('success', t('repos.createSuccess'));

          // Return success with taskId if available
          return {
            success: true,
            taskId: response?.taskId,
            machineName: machineData.value,
          };
        } catch {
          showMessage('warning', t('repos.repoCreatedButQueueFailed'));
          return {
            success: true, // Repo was created, just queue failed
            error: 'Queue creation failed',
          };
        }
      } else {
        // Create repo credentials only (no machine provisioning)
        await createRepoMutation.mutateAsync(data);
        showMessage('success', t('repos.createSuccess'));
        return { success: true };
      }
    } catch (error) {
      console.error('Failed to create repo:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error',
      };
    }
  };

  return {
    createRepo,
    isCreating,
  };
}
