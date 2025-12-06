import { QueryKey } from '@tanstack/react-query';
import { CEPH_QUERY_KEYS } from './ceph';
import i18n from '@/i18n/config';
import { api } from '../client';
import { createMutation } from '@/hooks/api/mutationFactory';

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
 * Factory function for creating ceph mutations
 * Uses the main mutation factory with i18n support for ceph operations
 */
export function createCephMutation<TData extends object>(config: MutationFactoryConfig<TData>) {
  const operationLabel = i18n.t(`ceph:mutations.operations.${config.operation}`);
  const resourceLabel = i18n.t(`ceph:mutations.resources.${config.resourceKey}`);
  const fallbackError = i18n.t('ceph:errors.operationFailed', {
    operation: operationLabel,
    resource: resourceLabel,
  });

  return createMutation<TData>({
    request: config.request,
    invalidateKeys: config.getInvalidateKeys,
    additionalInvalidateKeys: config.additionalInvalidateKeys,
    successMessage: i18n.t(`ceph:${config.translationKey}`),
    errorMessage: fallbackError,
    operationName: `ceph.${config.operation}.${config.resourceKey}`,
    disableTelemetry: false,
  });
}

// =============================================================================
// CLUSTER MUTATIONS
// =============================================================================

interface CreateClusterData {
  clusterName: string;
  vaultContent?: string;
}

export const useCreateCephCluster = createCephMutation<CreateClusterData>({
  request: (data) => api.ceph.createCluster(data.clusterName, data.vaultContent),
  operation: 'create',
  resourceKey: 'cluster',
  translationKey: 'clusters.createSuccess',
  getInvalidateKeys: () => [CEPH_QUERY_KEYS.clusters()],
});

interface UpdateClusterVaultData {
  clusterName: string;
  vaultContent: string;
  vaultVersion: number;
}

export const useUpdateCephClusterVault = createCephMutation<UpdateClusterVaultData>({
  request: (data) =>
    api.ceph.updateClusterVault(data.clusterName, data.vaultContent, data.vaultVersion),
  operation: 'update',
  resourceKey: 'clusterVault',
  translationKey: 'clusters.updateSuccess',
  getInvalidateKeys: () => [CEPH_QUERY_KEYS.clusters()],
});

interface DeleteClusterData {
  clusterName: string;
}

export const useDeleteCephCluster = createCephMutation<DeleteClusterData>({
  request: (data) => api.ceph.deleteCluster(data.clusterName),
  operation: 'delete',
  resourceKey: 'cluster',
  translationKey: 'clusters.deleteSuccess',
  getInvalidateKeys: () => [CEPH_QUERY_KEYS.clusters()],
});

// =============================================================================
// POOL MUTATIONS
// =============================================================================

interface CreatePoolData {
  teamName: string;
  clusterName: string;
  poolName: string;
  vaultContent?: string;
}

export const useCreateCephPool = createCephMutation<CreatePoolData>({
  request: (data) =>
    api.ceph.createPool(data.teamName, data.clusterName, data.poolName, data.vaultContent),
  operation: 'create',
  resourceKey: 'pool',
  translationKey: 'pools.createSuccess',
  getInvalidateKeys: () => [CEPH_QUERY_KEYS.pools()],
});

interface UpdatePoolVaultData {
  poolName: string;
  teamName: string;
  vaultContent: string;
  vaultVersion: number;
}

export const useUpdateCephPoolVault = createCephMutation<UpdatePoolVaultData>({
  request: (data) =>
    api.ceph.updatePoolVault(data.teamName, data.poolName, data.vaultContent, data.vaultVersion),
  operation: 'update',
  resourceKey: 'poolVault',
  translationKey: 'pools.updateSuccess',
  getInvalidateKeys: () => [CEPH_QUERY_KEYS.pools()],
});

interface DeletePoolData {
  teamName: string;
  poolName: string;
}

export const useDeleteCephPool = createCephMutation<DeletePoolData>({
  request: (data) => api.ceph.deletePool(data.teamName, data.poolName),
  operation: 'delete',
  resourceKey: 'pool',
  translationKey: 'pools.deleteSuccess',
  getInvalidateKeys: () => [CEPH_QUERY_KEYS.pools()],
});

// =============================================================================
// RBD IMAGE MUTATIONS
// =============================================================================

interface CreateImageData {
  poolName: string;
  teamName: string;
  imageName: string;
  machineName: string;
  vaultContent?: string;
}

export const useCreateCephRbdImage = createCephMutation<CreateImageData>({
  request: (data) =>
    api.ceph.createImage(
      data.poolName,
      data.teamName,
      data.imageName,
      data.machineName,
      data.vaultContent
    ),
  operation: 'create',
  resourceKey: 'rbdImage',
  translationKey: 'images.createSuccess',
  getInvalidateKeys: () => [CEPH_QUERY_KEYS.images()],
  additionalInvalidateKeys: () => [['ceph-cluster-machines']],
});

interface DeleteImageData {
  imageName: string;
  poolName: string;
  teamName: string;
}

export const useDeleteCephRbdImage = createCephMutation<DeleteImageData>({
  request: (data) => api.ceph.deleteImage(data.poolName, data.teamName, data.imageName),
  operation: 'delete',
  resourceKey: 'rbdImage',
  translationKey: 'images.deleteSuccess',
  getInvalidateKeys: () => [CEPH_QUERY_KEYS.images()],
});

interface UpdateImageMachineData {
  imageName: string;
  poolName: string;
  teamName: string;
  newMachineName: string;
}

export const useUpdateImageMachineAssignment = createCephMutation<UpdateImageMachineData>({
  request: (data) =>
    api.ceph.assignMachineToImage(
      data.poolName,
      data.teamName,
      data.imageName,
      data.newMachineName
    ),
  operation: 'assign',
  resourceKey: 'imageMachine',
  translationKey: 'images.reassignmentSuccess',
  getInvalidateKeys: () => [CEPH_QUERY_KEYS.images()],
});

// =============================================================================
// RBD SNAPSHOT MUTATIONS
// =============================================================================

interface CreateSnapshotData {
  imageName: string;
  poolName: string;
  teamName: string;
  snapshotName: string;
  vaultContent?: string;
}

export const useCreateCephRbdSnapshot = createCephMutation<CreateSnapshotData>({
  request: (data) =>
    api.ceph.createSnapshot(
      data.imageName,
      data.poolName,
      data.teamName,
      data.snapshotName,
      data.vaultContent
    ),
  operation: 'create',
  resourceKey: 'rbdSnapshot',
  translationKey: 'snapshots.createSuccess',
  getInvalidateKeys: () => [CEPH_QUERY_KEYS.snapshots()],
});

interface DeleteSnapshotData {
  snapshotName: string;
  imageName: string;
  poolName: string;
  teamName: string;
}

export const useDeleteCephRbdSnapshot = createCephMutation<DeleteSnapshotData>({
  request: (data) =>
    api.ceph.deleteSnapshot(data.imageName, data.poolName, data.teamName, data.snapshotName),
  operation: 'delete',
  resourceKey: 'rbdSnapshot',
  translationKey: 'snapshots.deleteSuccess',
  getInvalidateKeys: () => [CEPH_QUERY_KEYS.snapshots()],
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
  vaultContent?: string;
}

export const useCreateCephRbdClone = createCephMutation<CreateCloneData>({
  request: (data) =>
    api.ceph.createClone(
      data.snapshotName,
      data.imageName,
      data.poolName,
      data.teamName,
      data.cloneName,
      data.vaultContent
    ),
  operation: 'create',
  resourceKey: 'rbdClone',
  translationKey: 'clones.createSuccess',
  getInvalidateKeys: () => [CEPH_QUERY_KEYS.clones()],
});

interface DeleteCloneData {
  cloneName: string;
  snapshotName: string;
  imageName: string;
  poolName: string;
  teamName: string;
}

export const useDeleteCephRbdClone = createCephMutation<DeleteCloneData>({
  request: (data) =>
    api.ceph.deleteClone(
      data.cloneName,
      data.snapshotName,
      data.imageName,
      data.poolName,
      data.teamName
    ),
  operation: 'delete',
  resourceKey: 'rbdClone',
  translationKey: 'clones.deleteSuccess',
  getInvalidateKeys: () => [CEPH_QUERY_KEYS.clones()],
});

// =============================================================================
// MACHINE ASSIGNMENT MUTATIONS
// =============================================================================

interface UpdateMachineStorageData {
  teamName: string;
  machineName: string;
  clusterName: string | null;
}

export const useUpdateMachineCeph = createCephMutation<UpdateMachineStorageData>({
  request: (data) => api.machines.updateCeph(data.teamName, data.machineName, data.clusterName),
  operation: 'update',
  resourceKey: 'machineClusterAssignment',
  translationKey: 'machines.updateSuccess',
  getInvalidateKeys: (variables) => [CEPH_QUERY_KEYS.clusterMachines(variables.clusterName || '')],
});

interface CloneMachineAssignmentData {
  cloneName: string;
  snapshotName: string;
  imageName: string;
  poolName: string;
  teamName: string;
  machineNames: string;
}

export const useUpdateCloneMachineAssignments = createCephMutation<CloneMachineAssignmentData>({
  request: (data) =>
    api.ceph.assignMachinesToClone(
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
    CEPH_QUERY_KEYS.cloneMachines(
      variables.cloneName,
      variables.snapshotName,
      variables.imageName,
      variables.poolName,
      variables.teamName
    ),
    CEPH_QUERY_KEYS.availableMachinesForClone(variables.teamName),
  ],
});

export const useUpdateCloneMachineRemovals = createCephMutation<CloneMachineAssignmentData>({
  request: (data) =>
    api.ceph.removeMachinesFromClone(
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
    CEPH_QUERY_KEYS.cloneMachines(
      variables.cloneName,
      variables.snapshotName,
      variables.imageName,
      variables.poolName,
      variables.teamName
    ),
    CEPH_QUERY_KEYS.availableMachinesForClone(variables.teamName),
  ],
});

interface MachineClusterData {
  teamName: string;
  machineName: string;
  clusterName: string;
}

export const useUpdateMachineClusterAssignment = createCephMutation<MachineClusterData>({
  request: (data) =>
    api.machines.updateClusterAssignment(data.teamName, data.machineName, data.clusterName),
  operation: 'assign',
  resourceKey: 'machineCluster',
  translationKey: 'machines.clusterAssignedSuccess',
  getInvalidateKeys: (variables) => [
    CEPH_QUERY_KEYS.clusterMachines(variables.clusterName),
    CEPH_QUERY_KEYS.machineAssignmentStatus(variables.machineName, variables.teamName),
  ],
});

interface MachineClusterRemovalData {
  teamName: string;
  machineName: string;
}

export const useUpdateMachineClusterRemoval = createCephMutation<MachineClusterRemovalData>({
  request: (data) => api.machines.removeFromCluster(data.teamName, data.machineName),
  operation: 'remove',
  resourceKey: 'machineCluster',
  translationKey: 'machines.clusterRemovedSuccess',
  getInvalidateKeys: (variables) => [
    ['ceph-cluster-machines'],
    CEPH_QUERY_KEYS.machineAssignmentStatus(variables.machineName, variables.teamName),
  ],
});
