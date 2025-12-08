import { QueryKey } from '@tanstack/react-query';
import { api } from '@/api/client';
import { createMutation } from '@/hooks/api/mutationFactory';
import i18n from '@/i18n/config';
import type {
  CreateCephClusterParams,
  CreateCephPoolParams,
  CreateCephRbdCloneParams,
  CreateCephRbdImageParams,
  CreateCephRbdSnapshotParams,
  DeleteCephClusterParams,
  DeleteCephPoolParams,
  DeleteCephRbdCloneParams,
  DeleteCephRbdImageParams,
  DeleteCephRbdSnapshotParams,
  UpdateCephClusterVaultParams,
  UpdateCephPoolVaultParams,
  UpdateCloneMachineAssignmentsParams,
  UpdateCloneMachineRemovalsParams,
  UpdateImageMachineAssignmentParams,
  UpdateMachineCephParams,
  UpdateMachineClusterAssignmentParams,
  UpdateMachineClusterRemovalParams,
  WithOptionalVault,
} from '@rediacc/shared/types';
import { CEPH_QUERY_KEYS } from './ceph';

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

export const useCreateCephCluster = createCephMutation<WithOptionalVault<CreateCephClusterParams>>({
  request: (params) => api.ceph.createCluster(params),
  operation: 'create',
  resourceKey: 'cluster',
  translationKey: 'clusters.createSuccess',
  getInvalidateKeys: () => [CEPH_QUERY_KEYS.clusters()],
});

export const useUpdateCephClusterVault = createCephMutation<UpdateCephClusterVaultParams>({
  request: (params) => api.ceph.updateClusterVault(params),
  operation: 'update',
  resourceKey: 'clusterVault',
  translationKey: 'clusters.updateSuccess',
  getInvalidateKeys: () => [CEPH_QUERY_KEYS.clusters()],
});

export const useDeleteCephCluster = createCephMutation<DeleteCephClusterParams>({
  request: (params) => api.ceph.deleteCluster(params),
  operation: 'delete',
  resourceKey: 'cluster',
  translationKey: 'clusters.deleteSuccess',
  getInvalidateKeys: () => [CEPH_QUERY_KEYS.clusters()],
});

// =============================================================================
// POOL MUTATIONS
// =============================================================================

export const useCreateCephPool = createCephMutation<WithOptionalVault<CreateCephPoolParams>>({
  request: (params) => api.ceph.createPool(params),
  operation: 'create',
  resourceKey: 'pool',
  translationKey: 'pools.createSuccess',
  getInvalidateKeys: () => [CEPH_QUERY_KEYS.pools()],
});

export const useUpdateCephPoolVault = createCephMutation<UpdateCephPoolVaultParams>({
  request: (params) => api.ceph.updatePoolVault(params),
  operation: 'update',
  resourceKey: 'poolVault',
  translationKey: 'pools.updateSuccess',
  getInvalidateKeys: () => [CEPH_QUERY_KEYS.pools()],
});

export const useDeleteCephPool = createCephMutation<DeleteCephPoolParams>({
  request: (params) => api.ceph.deletePool(params),
  operation: 'delete',
  resourceKey: 'pool',
  translationKey: 'pools.deleteSuccess',
  getInvalidateKeys: () => [CEPH_QUERY_KEYS.pools()],
});

// =============================================================================
// RBD IMAGE MUTATIONS
// =============================================================================

export const useCreateCephRbdImage = createCephMutation<
  WithOptionalVault<CreateCephRbdImageParams>
>({
  request: (params) => api.ceph.createImage(params),
  operation: 'create',
  resourceKey: 'rbdImage',
  translationKey: 'images.createSuccess',
  getInvalidateKeys: () => [CEPH_QUERY_KEYS.images()],
  additionalInvalidateKeys: () => [['ceph-cluster-machines']],
});

export const useDeleteCephRbdImage = createCephMutation<DeleteCephRbdImageParams>({
  request: (params) => api.ceph.deleteImage(params),
  operation: 'delete',
  resourceKey: 'rbdImage',
  translationKey: 'images.deleteSuccess',
  getInvalidateKeys: () => [CEPH_QUERY_KEYS.images()],
});

export const useUpdateImageMachineAssignment =
  createCephMutation<UpdateImageMachineAssignmentParams>({
    request: (params) => api.ceph.assignMachineToImage(params),
    operation: 'assign',
    resourceKey: 'imageMachine',
    translationKey: 'images.reassignmentSuccess',
    getInvalidateKeys: () => [CEPH_QUERY_KEYS.images()],
  });

// =============================================================================
// RBD SNAPSHOT MUTATIONS
// =============================================================================

export const useCreateCephRbdSnapshot = createCephMutation<
  WithOptionalVault<CreateCephRbdSnapshotParams>
>({
  request: (params) => api.ceph.createSnapshot(params),
  operation: 'create',
  resourceKey: 'rbdSnapshot',
  translationKey: 'snapshots.createSuccess',
  getInvalidateKeys: () => [CEPH_QUERY_KEYS.snapshots()],
});

export const useDeleteCephRbdSnapshot = createCephMutation<DeleteCephRbdSnapshotParams>({
  request: (params) => api.ceph.deleteSnapshot(params),
  operation: 'delete',
  resourceKey: 'rbdSnapshot',
  translationKey: 'snapshots.deleteSuccess',
  getInvalidateKeys: () => [CEPH_QUERY_KEYS.snapshots()],
});

// =============================================================================
// RBD CLONE MUTATIONS
// =============================================================================

export const useCreateCephRbdClone = createCephMutation<
  WithOptionalVault<CreateCephRbdCloneParams>
>({
  request: (params) => api.ceph.createClone(params),
  operation: 'create',
  resourceKey: 'rbdClone',
  translationKey: 'clones.createSuccess',
  getInvalidateKeys: () => [CEPH_QUERY_KEYS.clones()],
});

export const useDeleteCephRbdClone = createCephMutation<DeleteCephRbdCloneParams>({
  request: (params) => api.ceph.deleteClone(params),
  operation: 'delete',
  resourceKey: 'rbdClone',
  translationKey: 'clones.deleteSuccess',
  getInvalidateKeys: () => [CEPH_QUERY_KEYS.clones()],
});

// =============================================================================
// MACHINE ASSIGNMENT MUTATIONS
// =============================================================================

export const useUpdateMachineCeph = createCephMutation<UpdateMachineCephParams>({
  request: (params) => api.machines.updateCeph(params),
  operation: 'update',
  resourceKey: 'machineClusterAssignment',
  translationKey: 'machines.updateSuccess',
  getInvalidateKeys: (variables) => [CEPH_QUERY_KEYS.clusterMachines(variables.clusterName || '')],
});

export const useUpdateCloneMachineAssignments = createCephMutation<
  UpdateCloneMachineAssignmentsParams & { machineNames: string }
>({
  request: (params) => api.ceph.assignMachinesToClone(params),
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

export const useUpdateCloneMachineRemovals = createCephMutation<
  UpdateCloneMachineRemovalsParams & { machineNames: string }
>({
  request: (params) => api.ceph.removeMachinesFromClone(params),
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

export const useUpdateMachineClusterAssignment =
  createCephMutation<UpdateMachineClusterAssignmentParams>({
    request: (params) => api.machines.updateClusterAssignment(params),
    operation: 'assign',
    resourceKey: 'machineCluster',
    translationKey: 'machines.clusterAssignedSuccess',
    getInvalidateKeys: (variables) => [
      CEPH_QUERY_KEYS.clusterMachines(variables.clusterName),
      CEPH_QUERY_KEYS.machineAssignmentStatus(variables.machineName, variables.teamName),
    ],
  });

export const useUpdateMachineClusterRemoval = createCephMutation<UpdateMachineClusterRemovalParams>(
  {
    request: (params) => api.machines.removeFromCluster(params),
    operation: 'remove',
    resourceKey: 'machineCluster',
    translationKey: 'machines.clusterRemovedSuccess',
    getInvalidateKeys: (variables) => [
      ['ceph-cluster-machines'],
      CEPH_QUERY_KEYS.machineAssignmentStatus(variables.machineName, variables.teamName),
    ],
  }
);
