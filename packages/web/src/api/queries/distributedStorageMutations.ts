import { useMutation, useQueryClient, QueryKey } from '@tanstack/react-query';
import { showMessage } from '@/utils/messages';
import { DS_QUERY_KEYS } from './distributedStorage';
import i18n from '@/i18n/config';
import { createErrorHandler } from '@/utils/mutationUtils';
import { api } from '../client';

type Operation = 'create' | 'update' | 'delete' | 'assign' | 'remove';

interface MutationFactoryConfig<TData> {
  request: (data: TData) => Promise<unknown>;
  operation: Operation;
  resourceKey: string;
  translationKey: string;
  getInvalidateKeys: (variables: TData) => QueryKey[];
  additionalInvalidateKeys?: (variables: TData) => QueryKey[];
}

/**
 * Factory function for creating distributed storage mutations
 * Reduces boilerplate by standardizing error handling, cache invalidation, and success messages
 */
export function createDistributedStorageMutation<TData extends object>(
  config: MutationFactoryConfig<TData>
) {
  return () => {
    const queryClient = useQueryClient();
    const operationLabel = i18n.t(`distributedStorage:mutations.operations.${config.operation}`);
    const resourceLabel = i18n.t(`distributedStorage:mutations.resources.${config.resourceKey}`);
    const fallbackError = i18n.t('distributedStorage:errors.operationFailed', {
      operation: operationLabel,
      resource: resourceLabel,
    });
    const handleError = createErrorHandler(fallbackError);

    return useMutation({
      mutationFn: async (data: TData) => {
        await config.request(data);
      },
      onSuccess: (_result: unknown, variables: TData) => {
        // Invalidate primary keys
        const keys = config.getInvalidateKeys(variables);
        keys.forEach((key) => queryClient.invalidateQueries({ queryKey: key }));

        // Invalidate additional keys if provided
        if (config.additionalInvalidateKeys) {
          const additionalKeys = config.additionalInvalidateKeys(variables);
          additionalKeys.forEach((key) => queryClient.invalidateQueries({ queryKey: key }));
        }

        showMessage('success', i18n.t(`distributedStorage:${config.translationKey}`));
      },
      onError: handleError,
    });
  };
}

// =============================================================================
// CLUSTER MUTATIONS
// =============================================================================

interface CreateClusterData {
  clusterName: string;
  clusterVault?: string;
}

export const useCreateDistributedStorageCluster =
  createDistributedStorageMutation<CreateClusterData>({
    request: (data) => api.distributedStorage.createCluster(data.clusterName, data.clusterVault),
    operation: 'create',
    resourceKey: 'cluster',
    translationKey: 'clusters.createSuccess',
    getInvalidateKeys: () => [DS_QUERY_KEYS.clusters()],
  });

interface UpdateClusterVaultData {
  clusterName: string;
  clusterVault: string;
  vaultVersion: number;
}

export const useUpdateDistributedStorageClusterVault =
  createDistributedStorageMutation<UpdateClusterVaultData>({
    request: (data) =>
      api.distributedStorage.updateClusterVault(
        data.clusterName,
        data.clusterVault,
        data.vaultVersion
      ),
    operation: 'update',
    resourceKey: 'clusterVault',
    translationKey: 'clusters.updateSuccess',
    getInvalidateKeys: () => [DS_QUERY_KEYS.clusters()],
  });

interface DeleteClusterData {
  clusterName: string;
}

export const useDeleteDistributedStorageCluster =
  createDistributedStorageMutation<DeleteClusterData>({
    request: (data) => api.distributedStorage.deleteCluster(data.clusterName),
    operation: 'delete',
    resourceKey: 'cluster',
    translationKey: 'clusters.deleteSuccess',
    getInvalidateKeys: () => [DS_QUERY_KEYS.clusters()],
  });

// =============================================================================
// POOL MUTATIONS
// =============================================================================

interface CreatePoolData {
  teamName: string;
  clusterName: string;
  poolName: string;
  poolVault?: string;
}

export const useCreateDistributedStoragePool = createDistributedStorageMutation<CreatePoolData>({
  request: (data) =>
    api.distributedStorage.createPool(
      data.teamName,
      data.clusterName,
      data.poolName,
      data.poolVault
    ),
  operation: 'create',
  resourceKey: 'pool',
  translationKey: 'pools.createSuccess',
  getInvalidateKeys: () => [DS_QUERY_KEYS.pools()],
});

interface UpdatePoolVaultData {
  poolName: string;
  teamName: string;
  poolVault: string;
  vaultVersion: number;
}

export const useUpdateDistributedStoragePoolVault =
  createDistributedStorageMutation<UpdatePoolVaultData>({
    request: (data) =>
      api.distributedStorage.updatePoolVault(
        data.teamName,
        data.poolName,
        data.poolVault,
        data.vaultVersion
      ),
    operation: 'update',
    resourceKey: 'poolVault',
    translationKey: 'pools.updateSuccess',
    getInvalidateKeys: () => [DS_QUERY_KEYS.pools()],
  });

interface DeletePoolData {
  teamName: string;
  poolName: string;
}

export const useDeleteDistributedStoragePool = createDistributedStorageMutation<DeletePoolData>({
  request: (data) => api.distributedStorage.deletePool(data.teamName, data.poolName),
  operation: 'delete',
  resourceKey: 'pool',
  translationKey: 'pools.deleteSuccess',
  getInvalidateKeys: () => [DS_QUERY_KEYS.pools()],
});

// =============================================================================
// RBD IMAGE MUTATIONS
// =============================================================================

interface CreateImageData {
  poolName: string;
  teamName: string;
  imageName: string;
  machineName: string;
  imageVault?: string;
}

export const useCreateDistributedStorageRbdImage =
  createDistributedStorageMutation<CreateImageData>({
    request: (data) =>
      api.distributedStorage.createImage(
        data.poolName,
        data.teamName,
        data.imageName,
        data.machineName,
        data.imageVault
      ),
    operation: 'create',
    resourceKey: 'rbdImage',
    translationKey: 'images.createSuccess',
    getInvalidateKeys: () => [DS_QUERY_KEYS.images()],
    additionalInvalidateKeys: () => [['distributed-storage-cluster-machines']],
  });

interface DeleteImageData {
  imageName: string;
  poolName: string;
  teamName: string;
}

export const useDeleteDistributedStorageRbdImage =
  createDistributedStorageMutation<DeleteImageData>({
    request: (data) =>
      api.distributedStorage.deleteImage(data.poolName, data.teamName, data.imageName),
    operation: 'delete',
    resourceKey: 'rbdImage',
    translationKey: 'images.deleteSuccess',
    getInvalidateKeys: () => [DS_QUERY_KEYS.images()],
  });

interface UpdateImageMachineData {
  imageName: string;
  poolName: string;
  teamName: string;
  newMachineName: string;
}

export const useUpdateImageMachineAssignment =
  createDistributedStorageMutation<UpdateImageMachineData>({
    request: (data) =>
      api.distributedStorage.assignMachineToImage(
        data.poolName,
        data.teamName,
        data.imageName,
        data.newMachineName
      ),
    operation: 'assign',
    resourceKey: 'imageMachine',
    translationKey: 'images.reassignmentSuccess',
    getInvalidateKeys: () => [DS_QUERY_KEYS.images()],
  });

// =============================================================================
// RBD SNAPSHOT MUTATIONS
// =============================================================================

interface CreateSnapshotData {
  imageName: string;
  poolName: string;
  teamName: string;
  snapshotName: string;
  snapshotVault?: string;
}

export const useCreateDistributedStorageRbdSnapshot =
  createDistributedStorageMutation<CreateSnapshotData>({
    request: (data) =>
      api.distributedStorage.createSnapshot(
        data.imageName,
        data.poolName,
        data.teamName,
        data.snapshotName,
        data.snapshotVault
      ),
    operation: 'create',
    resourceKey: 'rbdSnapshot',
    translationKey: 'snapshots.createSuccess',
    getInvalidateKeys: () => [DS_QUERY_KEYS.snapshots()],
  });

interface DeleteSnapshotData {
  snapshotName: string;
  imageName: string;
  poolName: string;
  teamName: string;
}

export const useDeleteDistributedStorageRbdSnapshot =
  createDistributedStorageMutation<DeleteSnapshotData>({
    request: (data) =>
      api.distributedStorage.deleteSnapshot(
        data.imageName,
        data.poolName,
        data.teamName,
        data.snapshotName
      ),
    operation: 'delete',
    resourceKey: 'rbdSnapshot',
    translationKey: 'snapshots.deleteSuccess',
    getInvalidateKeys: () => [DS_QUERY_KEYS.snapshots()],
  });

// =============================================================================
// RBD CLONE MUTATIONS
// =============================================================================

interface CreateCloneData {
  snapshotName: string;
  imageName: string;
  poolName: string;
  teamName: string;
  cloneName: string;
  cloneVault?: string;
}

export const useCreateDistributedStorageRbdClone =
  createDistributedStorageMutation<CreateCloneData>({
    request: (data) =>
      api.distributedStorage.createClone(
        data.snapshotName,
        data.imageName,
        data.poolName,
        data.teamName,
        data.cloneName,
        data.cloneVault
      ),
    operation: 'create',
    resourceKey: 'rbdClone',
    translationKey: 'clones.createSuccess',
    getInvalidateKeys: () => [DS_QUERY_KEYS.clones()],
  });

interface DeleteCloneData {
  cloneName: string;
  snapshotName: string;
  imageName: string;
  poolName: string;
  teamName: string;
}

export const useDeleteDistributedStorageRbdClone =
  createDistributedStorageMutation<DeleteCloneData>({
    request: (data) =>
      api.distributedStorage.deleteClone(
        data.cloneName,
        data.snapshotName,
        data.imageName,
        data.poolName,
        data.teamName
      ),
    operation: 'delete',
    resourceKey: 'rbdClone',
    translationKey: 'clones.deleteSuccess',
    getInvalidateKeys: () => [DS_QUERY_KEYS.clones()],
  });

// =============================================================================
// MACHINE ASSIGNMENT MUTATIONS
// =============================================================================

interface UpdateMachineStorageData {
  teamName: string;
  machineName: string;
  clusterName: string | null;
}

export const useUpdateMachineDistributedStorage =
  createDistributedStorageMutation<UpdateMachineStorageData>({
    request: (data) =>
      api.machines.updateDistributedStorage(data.teamName, data.machineName, data.clusterName),
    operation: 'update',
    resourceKey: 'machineClusterAssignment',
    translationKey: 'machines.updateSuccess',
    getInvalidateKeys: (variables) => [DS_QUERY_KEYS.clusterMachines(variables.clusterName || '')],
  });

interface CloneMachineAssignmentData {
  cloneName: string;
  snapshotName: string;
  imageName: string;
  poolName: string;
  teamName: string;
  machineNames: string;
}

export const useUpdateCloneMachineAssignments =
  createDistributedStorageMutation<CloneMachineAssignmentData>({
    request: (data) =>
      api.distributedStorage.assignMachinesToClone(
        data.cloneName,
        data.snapshotName,
        data.imageName,
        data.poolName,
        data.teamName,
        data.machineNames
      ),
    operation: 'assign',
    resourceKey: 'cloneMachines',
    translationKey: 'clones.machinesAssignedSuccess',
    getInvalidateKeys: (variables) => [
      DS_QUERY_KEYS.cloneMachines(
        variables.cloneName,
        variables.snapshotName,
        variables.imageName,
        variables.poolName,
        variables.teamName
      ),
      DS_QUERY_KEYS.availableMachinesForClone(variables.teamName),
    ],
  });

export const useUpdateCloneMachineRemovals =
  createDistributedStorageMutation<CloneMachineAssignmentData>({
    request: (data) =>
      api.distributedStorage.removeMachinesFromClone(
        data.cloneName,
        data.snapshotName,
        data.imageName,
        data.poolName,
        data.teamName,
        data.machineNames
      ),
    operation: 'remove',
    resourceKey: 'cloneMachines',
    translationKey: 'clones.machinesRemovedSuccess',
    getInvalidateKeys: (variables) => [
      DS_QUERY_KEYS.cloneMachines(
        variables.cloneName,
        variables.snapshotName,
        variables.imageName,
        variables.poolName,
        variables.teamName
      ),
      DS_QUERY_KEYS.availableMachinesForClone(variables.teamName),
    ],
  });

interface MachineClusterData {
  teamName: string;
  machineName: string;
  clusterName: string;
}

export const useUpdateMachineClusterAssignment =
  createDistributedStorageMutation<MachineClusterData>({
    request: (data) =>
      api.machines.updateClusterAssignment(data.teamName, data.machineName, data.clusterName),
    operation: 'assign',
    resourceKey: 'machineCluster',
    translationKey: 'machines.clusterAssignedSuccess',
    getInvalidateKeys: (variables) => [
      DS_QUERY_KEYS.clusterMachines(variables.clusterName),
      DS_QUERY_KEYS.machineAssignmentStatus(variables.machineName, variables.teamName),
    ],
  });

interface MachineClusterRemovalData {
  teamName: string;
  machineName: string;
}

export const useUpdateMachineClusterRemoval =
  createDistributedStorageMutation<MachineClusterRemovalData>({
    request: (data) => api.machines.removeFromCluster(data.teamName, data.machineName),
    operation: 'remove',
    resourceKey: 'machineCluster',
    translationKey: 'machines.clusterRemovedSuccess',
    getInvalidateKeys: (variables) => [
      ['distributed-storage-cluster-machines'],
      DS_QUERY_KEYS.machineAssignmentStatus(variables.machineName, variables.teamName),
    ],
  });
