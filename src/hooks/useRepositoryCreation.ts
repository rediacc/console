import { useCreateRepository } from '@/api/queries/repositories'
import { useTeams } from '@/api/queries/teams'
import { useManagedQueueItem } from '@/hooks/useManagedQueueItem'
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder'
import { useDropdownData } from '@/api/queries/useDropdownData'
import { showMessage } from '@/utils/messages'
import apiClient from '@/api/client'
import { useTranslation } from 'react-i18next'
import type { Machine } from '@/types'

interface RepositoryCreationData {
  repositoryName: string
  teamName: string
  machineName?: string
  size?: string
  repositoryGuid?: string
  repositoryVault?: string
  tmpl?: string
  keep_open?: boolean
  [key: string]: any
}

interface RepositoryCreationResult {
  success: boolean
  taskId?: string
  machineName?: string
  error?: string
}

interface UseRepositoryCreationReturn {
  createRepository: (data: RepositoryCreationData) => Promise<RepositoryCreationResult>
  isCreating: boolean
}

/**
 * Custom hook for handling repository creation with optional queue item creation
 * Consolidates the two-step process:
 * 1. Create repository credentials
 * 2. Queue the "new" function to create repository on machine (if machine and size provided)
 */
export function useRepositoryCreation(
  machines: Machine[]
): UseRepositoryCreationReturn {
  const { t } = useTranslation(['resources', 'repositories'])
  const createRepositoryMutation = useCreateRepository()
  const createQueueItemMutation = useManagedQueueItem()
  const { buildQueueVault } = useQueueVaultBuilder()
  const { data: teamsList = [] } = useTeams()
  const { data: dropdownData } = useDropdownData()

  const isCreating = createRepositoryMutation.isPending || createQueueItemMutation.isPending

  const createRepository = async (
    data: RepositoryCreationData
  ): Promise<RepositoryCreationResult> => {
    try {
      // Check if this is credential-only mode (repositoryGuid is provided)
      const isCredentialOnlyMode = data.repositoryGuid && data.repositoryGuid.trim() !== ''

      // Check if we have machine and size for full repository creation
      if (data.machineName && data.size && !isCredentialOnlyMode) {
        // Step 1: Create the repository credentials
        const { machineName, size, ...repoData } = data
        await createRepositoryMutation.mutateAsync(repoData)

        // Step 2: Queue the "new" function to create the repository on the machine
        try {
          // Find the machine details from dropdown data
          const teamData = dropdownData?.machinesByTeam?.find(
            t => t.teamName === data.teamName
          )
          const machineData = teamData?.machines?.find(
            m => m.value === machineName
          )

          if (!machineData) {
            showMessage('error', t('resources:errors.machineNotFound'))
            return { success: false, error: 'Machine not found' }
          }

          // Find team vault data
          const team = teamsList.find(t => t.teamName === data.teamName)

          // Find the full machine data to get vault content
          const fullMachine = machines.find(
            m => m.machineName === machineName && m.teamName === data.teamName
          )

          // Wait a bit for the repository to be fully created and indexed
          await new Promise(resolve => setTimeout(resolve, 500))

          // Fetch the created repository to get its vault with credentials
          const repoResponse = await apiClient.get('/GetTeamRepositories', {
            teamName: data.teamName
          })

          // The repository data is in the second table (index 1)
          const createdRepo = repoResponse.resultSets[1]?.data?.find(
            (r: any) => r.repoName === data.repositoryName
          )

          const repositoryVault = createdRepo?.vaultContent || data.repositoryVault || '{}'
          const repositoryGuid = createdRepo?.repoGuid || ''

          if (!repositoryGuid) {
            showMessage('error', t('resources:errors.failedToGetRepositoryGuid'))
            return { success: false, error: 'Failed to get repository GUID' }
          }

          // Build queue vault for the "new" function
          const params: any = {
            repo: repositoryGuid,
            size: size
          }

          // Add template parameter if provided
          if (data.tmpl) {
            params.tmpl = data.tmpl
          }

          // Add keep_open parameter if provided
          if (data.keep_open) {
            params.keep_open = 'true'
          }

          const queueVault = await buildQueueVault({
            teamName: data.teamName,
            machineName: machineData.value,
            bridgeName: machineData.bridgeName,
            functionName: 'new',
            params: params,
            priority: 3,
            addedVia: 'repository-creation',
            teamVault: team?.vaultContent || '{}',
            machineVault: fullMachine?.vaultContent || '{}',
            repositoryVault: repositoryVault,
            repositoryGuid: repositoryGuid,
            repositoryLoopbackIp: createdRepo?.repoLoopbackIP,
            repositoryNetworkMode: createdRepo?.repoNetworkMode,
            repositoryTag: createdRepo?.repoTag
          })

          const response = await createQueueItemMutation.mutateAsync({
            teamName: data.teamName,
            machineName: machineData.value,
            bridgeName: machineData.bridgeName,
            queueVault,
            priority: 3
          })

          showMessage('success', t('repositories.createSuccess'))

          // Return success with taskId if available
          return {
            success: true,
            taskId: response?.taskId,
            machineName: machineData.value
          }
        } catch (error) {
          showMessage('warning', t('repositories.repoCreatedButQueueFailed'))
          return {
            success: true, // Repository was created, just queue failed
            error: 'Queue creation failed'
          }
        }
      } else {
        // Create repository credentials only (no machine provisioning)
        await createRepositoryMutation.mutateAsync(data)
        showMessage('success', t('repositories.createSuccess'))
        return { success: true }
      }
    } catch (error) {
      console.error('Failed to create repository:', error)
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error'
      }
    }
  }

  return {
    createRepository,
    isCreating
  }
}
