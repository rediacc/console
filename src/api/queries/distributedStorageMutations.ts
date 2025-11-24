import { useMutation, useQueryClient, QueryKey } from '@tanstack/react-query'
import { apiClient } from '../client'
import { showMessage } from '@/utils/messages'
import { useTranslation } from 'react-i18next'
import { DS_QUERY_KEYS } from './distributedStorage'

// Response validation helper
function validateResponse(response: any, errorMessage: string): void {
  if (response.failure !== 0) {
    throw new Error(response.errors?.join(', ') || errorMessage)
  }
}

type Operation = 'create' | 'update' | 'delete' | 'assign' | 'remove'

interface MutationFactoryConfig<TData> {
  endpoint: string
  operation: Operation
  resourceType: string
  translationKey: string
  getInvalidateKeys: (variables: TData) => QueryKey[]
  additionalInvalidateKeys?: (variables: TData) => QueryKey[]
}

/**
 * Factory function for creating distributed storage mutations
 * Reduces boilerplate by standardizing error handling, cache invalidation, and success messages
 */
export function createDistributedStorageMutation<TData extends Record<string, any>>(
  config: MutationFactoryConfig<TData>
) {
  return () => {
    const queryClient = useQueryClient()
    const { t } = useTranslation('distributedStorage')

    return useMutation({
      mutationFn: async (data: TData) => {
        const response = await apiClient.post(config.endpoint, data)
        validateResponse(response, `Failed to ${config.operation} ${config.resourceType}`)
        return response
      },
      onSuccess: (_: any, variables: TData) => {
        // Invalidate primary keys
        const keys = config.getInvalidateKeys(variables)
        keys.forEach(key => queryClient.invalidateQueries({ queryKey: key }))

        // Invalidate additional keys if provided
        if (config.additionalInvalidateKeys) {
          const additionalKeys = config.additionalInvalidateKeys(variables)
          additionalKeys.forEach(key => queryClient.invalidateQueries({ queryKey: key }))
        }

        showMessage('success', t(config.translationKey))
      },
      onError: (error: Error) => {
        showMessage('error', error.message)
      },
    })
  }
}

// =============================================================================
// CLUSTER MUTATIONS
// =============================================================================

interface CreateClusterData {
  clusterName: string
  clusterVault?: string
}

export const useCreateDistributedStorageCluster = createDistributedStorageMutation<CreateClusterData>({
  endpoint: '/CreateDistributedStorageCluster',
  operation: 'create',
  resourceType: 'cluster',
  translationKey: 'clusters.createSuccess',
  getInvalidateKeys: () => [DS_QUERY_KEYS.clusters()]
})

interface UpdateClusterVaultData {
  clusterName: string
  clusterVault: string
  vaultVersion: number
}

export const useUpdateDistributedStorageClusterVault = createDistributedStorageMutation<UpdateClusterVaultData>({
  endpoint: '/UpdateDistributedStorageClusterVault',
  operation: 'update',
  resourceType: 'cluster vault',
  translationKey: 'clusters.updateSuccess',
  getInvalidateKeys: () => [DS_QUERY_KEYS.clusters()]
})

interface DeleteClusterData {
  clusterName: string
}

export const useDeleteDistributedStorageCluster = createDistributedStorageMutation<DeleteClusterData>({
  endpoint: '/DeleteDistributedStorageCluster',
  operation: 'delete',
  resourceType: 'cluster',
  translationKey: 'clusters.deleteSuccess',
  getInvalidateKeys: () => [DS_QUERY_KEYS.clusters()]
})

// =============================================================================
// POOL MUTATIONS
// =============================================================================

interface CreatePoolData {
  teamName: string
  clusterName: string
  poolName: string
  poolVault?: string
}

export const useCreateDistributedStoragePool = createDistributedStorageMutation<CreatePoolData>({
  endpoint: '/CreateDistributedStoragePool',
  operation: 'create',
  resourceType: 'pool',
  translationKey: 'pools.createSuccess',
  getInvalidateKeys: () => [DS_QUERY_KEYS.pools()]
})

interface UpdatePoolVaultData {
  poolName: string
  teamName: string
  poolVault: string
  vaultVersion: number
}

export const useUpdateDistributedStoragePoolVault = createDistributedStorageMutation<UpdatePoolVaultData>({
  endpoint: '/UpdateDistributedStoragePoolVault',
  operation: 'update',
  resourceType: 'pool vault',
  translationKey: 'pools.updateSuccess',
  getInvalidateKeys: () => [DS_QUERY_KEYS.pools()]
})

interface DeletePoolData {
  teamName: string
  poolName: string
}

export const useDeleteDistributedStoragePool = createDistributedStorageMutation<DeletePoolData>({
  endpoint: '/DeleteDistributedStoragePool',
  operation: 'delete',
  resourceType: 'pool',
  translationKey: 'pools.deleteSuccess',
  getInvalidateKeys: () => [DS_QUERY_KEYS.pools()]
})

// =============================================================================
// RBD IMAGE MUTATIONS
// =============================================================================

interface CreateImageData {
  poolName: string
  teamName: string
  imageName: string
  machineName: string
  imageVault?: string
}

export const useCreateDistributedStorageRbdImage = createDistributedStorageMutation<CreateImageData>({
  endpoint: '/CreateDistributedStorageRbdImage',
  operation: 'create',
  resourceType: 'RBD image',
  translationKey: 'images.createSuccess',
  getInvalidateKeys: () => [DS_QUERY_KEYS.images()],
  additionalInvalidateKeys: () => [['distributed-storage-cluster-machines']]
})

interface DeleteImageData {
  imageName: string
  poolName: string
  teamName: string
}

export const useDeleteDistributedStorageRbdImage = createDistributedStorageMutation<DeleteImageData>({
  endpoint: '/DeleteDistributedStorageRbdImage',
  operation: 'delete',
  resourceType: 'RBD image',
  translationKey: 'images.deleteSuccess',
  getInvalidateKeys: () => [DS_QUERY_KEYS.images()]
})

interface UpdateImageMachineData {
  imageName: string
  poolName: string
  teamName: string
  newMachineName: string
}

export const useUpdateImageMachineAssignment = createDistributedStorageMutation<UpdateImageMachineData>({
  endpoint: '/UpdateImageMachineAssignment',
  operation: 'assign',
  resourceType: 'image machine',
  translationKey: 'images.reassignmentSuccess',
  getInvalidateKeys: () => [DS_QUERY_KEYS.images()]
})

// =============================================================================
// RBD SNAPSHOT MUTATIONS
// =============================================================================

interface CreateSnapshotData {
  imageName: string
  poolName: string
  teamName: string
  snapshotName: string
  snapshotVault?: string
}

export const useCreateDistributedStorageRbdSnapshot = createDistributedStorageMutation<CreateSnapshotData>({
  endpoint: '/CreateDistributedStorageRbdSnapshot',
  operation: 'create',
  resourceType: 'RBD snapshot',
  translationKey: 'snapshots.createSuccess',
  getInvalidateKeys: () => [DS_QUERY_KEYS.snapshots()]
})

interface DeleteSnapshotData {
  snapshotName: string
  imageName: string
  poolName: string
  teamName: string
}

export const useDeleteDistributedStorageRbdSnapshot = createDistributedStorageMutation<DeleteSnapshotData>({
  endpoint: '/DeleteDistributedStorageRbdSnapshot',
  operation: 'delete',
  resourceType: 'RBD snapshot',
  translationKey: 'snapshots.deleteSuccess',
  getInvalidateKeys: () => [DS_QUERY_KEYS.snapshots()]
})

// =============================================================================
// RBD CLONE MUTATIONS
// =============================================================================

interface CreateCloneData {
  snapshotName: string
  imageName: string
  poolName: string
  teamName: string
  cloneName: string
  cloneVault?: string
}

export const useCreateDistributedStorageRbdClone = createDistributedStorageMutation<CreateCloneData>({
  endpoint: '/CreateDistributedStorageRbdClone',
  operation: 'create',
  resourceType: 'RBD clone',
  translationKey: 'clones.createSuccess',
  getInvalidateKeys: () => [DS_QUERY_KEYS.clones()]
})

interface DeleteCloneData {
  cloneName: string
  snapshotName: string
  imageName: string
  poolName: string
  teamName: string
}

export const useDeleteDistributedStorageRbdClone = createDistributedStorageMutation<DeleteCloneData>({
  endpoint: '/DeleteDistributedStorageRbdClone',
  operation: 'delete',
  resourceType: 'RBD clone',
  translationKey: 'clones.deleteSuccess',
  getInvalidateKeys: () => [DS_QUERY_KEYS.clones()]
})

// =============================================================================
// MACHINE ASSIGNMENT MUTATIONS
// =============================================================================

interface UpdateMachineStorageData {
  teamName: string
  machineName: string
  clusterName: string | null
}

export const useUpdateMachineDistributedStorage = createDistributedStorageMutation<UpdateMachineStorageData>({
  endpoint: '/UpdateMachineDistributedStorage',
  operation: 'update',
  resourceType: 'machine cluster assignment',
  translationKey: 'machines.updateSuccess',
  getInvalidateKeys: (variables) => [DS_QUERY_KEYS.clusterMachines(variables.clusterName || '')]
})

interface CloneMachineAssignmentData {
  cloneName: string
  snapshotName: string
  imageName: string
  poolName: string
  teamName: string
  machineNames: string
}

export const useUpdateCloneMachineAssignments = createDistributedStorageMutation<CloneMachineAssignmentData>({
  endpoint: '/UpdateCloneMachineAssignments',
  operation: 'assign',
  resourceType: 'clone machines',
  translationKey: 'clones.machinesAssignedSuccess',
  getInvalidateKeys: (variables) => [
    DS_QUERY_KEYS.cloneMachines(variables.cloneName, variables.snapshotName, variables.imageName, variables.poolName, variables.teamName),
    DS_QUERY_KEYS.availableMachinesForClone(variables.teamName)
  ]
})

export const useUpdateCloneMachineRemovals = createDistributedStorageMutation<CloneMachineAssignmentData>({
  endpoint: '/UpdateCloneMachineRemovals',
  operation: 'remove',
  resourceType: 'clone machines',
  translationKey: 'clones.machinesRemovedSuccess',
  getInvalidateKeys: (variables) => [
    DS_QUERY_KEYS.cloneMachines(variables.cloneName, variables.snapshotName, variables.imageName, variables.poolName, variables.teamName),
    DS_QUERY_KEYS.availableMachinesForClone(variables.teamName)
  ]
})

interface MachineClusterData {
  teamName: string
  machineName: string
  clusterName: string
}

export const useUpdateMachineClusterAssignment = createDistributedStorageMutation<MachineClusterData>({
  endpoint: '/UpdateMachineClusterAssignment',
  operation: 'assign',
  resourceType: 'machine cluster',
  translationKey: 'machines.clusterAssignedSuccess',
  getInvalidateKeys: (variables) => [
    DS_QUERY_KEYS.clusterMachines(variables.clusterName),
    DS_QUERY_KEYS.machineAssignmentStatus(variables.machineName, variables.teamName)
  ]
})

interface MachineClusterRemovalData {
  teamName: string
  machineName: string
}

export const useUpdateMachineClusterRemoval = createDistributedStorageMutation<MachineClusterRemovalData>({
  endpoint: '/UpdateMachineClusterRemoval',
  operation: 'remove',
  resourceType: 'machine cluster',
  translationKey: 'machines.clusterRemovedSuccess',
  getInvalidateKeys: (variables) => [
    ['distributed-storage-cluster-machines'],
    DS_QUERY_KEYS.machineAssignmentStatus(variables.machineName, variables.teamName)
  ]
})
