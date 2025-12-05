import { useQuery } from '@tanstack/react-query';
import { api } from '../client';
import type {
  DistributedStorageAvailableMachine,
  DistributedStorageCloneMachine,
  DistributedStorageCluster,
  DistributedStorageMachineAssignmentStatus,
  DistributedStorageMachineAssignmentValidation,
  DistributedStoragePool,
  DistributedStorageRbdClone,
  DistributedStorageRbdImage,
  DistributedStorageRbdSnapshot,
  Machine,
} from '@rediacc/shared/types';

// Query Keys - exported for use in mutations
export const DS_QUERY_KEYS = {
  clusters: (teamFilter?: string | string[]) => ['distributed-storage-clusters', teamFilter],
  pools: (teamFilter?: string | string[]) => ['distributed-storage-pools', teamFilter],
  images: (poolName?: string, teamName?: string) => [
    'distributed-storage-images',
    poolName,
    teamName,
  ],
  snapshots: (imageName?: string, poolName?: string, teamName?: string) => [
    'distributed-storage-snapshots',
    imageName,
    poolName,
    teamName,
  ],
  clones: (snapshotName?: string, imageName?: string, poolName?: string, teamName?: string) => [
    'distributed-storage-clones',
    snapshotName,
    imageName,
    poolName,
    teamName,
  ],
  clusterMachines: (clusterName: string) => ['distributed-storage-cluster-machines', clusterName],
  machineAssignmentStatus: (machineName: string, teamName: string) => [
    'machine-assignment-status',
    machineName,
    teamName,
  ],
  availableMachinesForClone: (teamName: string) => ['available-machines-for-clone', teamName],
  cloneMachines: (
    cloneName: string,
    snapshotName: string,
    imageName: string,
    poolName: string,
    teamName: string
  ) => ['clone-machines', cloneName, snapshotName, imageName, poolName, teamName],
  machineAssignmentValidation: (teamName: string, machineNames: string) => [
    'machine-assignment-validation',
    teamName,
    machineNames,
  ],
};

// =============================================================================
// QUERY HOOKS
// =============================================================================

// Clusters
export const useDistributedStorageClusters = (teamFilter?: string | string[], enabled = true) => {
  return useQuery<DistributedStorageCluster[]>({
    queryKey: DS_QUERY_KEYS.clusters(teamFilter),
    queryFn: () => api.distributedStorage.listClusters(),
    enabled: enabled,
  });
};

// Pools
export const useDistributedStoragePools = (teamFilter?: string | string[], enabled = true) => {
  return useQuery<DistributedStoragePool[]>({
    queryKey: DS_QUERY_KEYS.pools(teamFilter),
    queryFn: async () => {
      const teamName = Array.isArray(teamFilter) ? teamFilter?.[0] : teamFilter;
      if (!teamName) {
        return [];
      }
      return api.distributedStorage.listPools(teamName);
    },
    enabled: enabled && !!teamFilter,
  });
};

// RBD Images
export const useDistributedStorageRbdImages = (
  poolName?: string,
  teamName?: string,
  enabled = true
) => {
  return useQuery<DistributedStorageRbdImage[]>({
    queryKey: DS_QUERY_KEYS.images(poolName, teamName),
    queryFn: () => api.distributedStorage.listImages(poolName as string, teamName as string),
    enabled: enabled && !!poolName && !!teamName,
  });
};

// RBD Snapshots
export const useDistributedStorageRbdSnapshots = (
  imageName?: string,
  poolName?: string,
  teamName?: string,
  enabled = true
) => {
  return useQuery<DistributedStorageRbdSnapshot[]>({
    queryKey: DS_QUERY_KEYS.snapshots(imageName, poolName, teamName),
    queryFn: () =>
      api.distributedStorage.listSnapshots(
        imageName as string,
        poolName as string,
        teamName as string
      ),
    enabled: enabled && !!imageName && !!poolName && !!teamName,
  });
};

// RBD Clones
export const useDistributedStorageRbdClones = (
  snapshotName?: string,
  imageName?: string,
  poolName?: string,
  teamName?: string,
  enabled = true
) => {
  return useQuery<DistributedStorageRbdClone[]>({
    queryKey: DS_QUERY_KEYS.clones(snapshotName, imageName, poolName, teamName),
    queryFn: () =>
      api.distributedStorage.listClones(
        snapshotName as string,
        imageName as string,
        poolName as string,
        teamName as string
      ),
    enabled: enabled && !!snapshotName && !!imageName && !!poolName && !!teamName,
  });
};

// Cluster Machines
export const useDistributedStorageClusterMachines = (clusterName: string, enabled = true) => {
  return useQuery<Machine[]>({
    queryKey: DS_QUERY_KEYS.clusterMachines(clusterName),
    queryFn: () => api.distributedStorage.getClusterMachines(clusterName),
    enabled: enabled && !!clusterName,
  });
};

// Machine Assignment Status
export const useMachineAssignmentStatus = (
  machineName: string,
  teamName: string,
  enabled = true
) => {
  return useQuery<DistributedStorageMachineAssignmentStatus | null>({
    queryKey: DS_QUERY_KEYS.machineAssignmentStatus(machineName, teamName),
    queryFn: () => api.distributedStorage.getMachineAssignmentStatus(machineName, teamName),
    enabled: enabled && !!machineName && !!teamName,
  });
};

// Available Machines for Clone
export const useAvailableMachinesForClone = (teamName: string, enabled = true) => {
  return useQuery<DistributedStorageAvailableMachine[]>({
    queryKey: DS_QUERY_KEYS.availableMachinesForClone(teamName),
    queryFn: () => api.distributedStorage.getAvailableMachinesForClone(teamName),
    enabled: enabled && !!teamName,
  });
};

// Clone Machine Assignment Validation
export const useCloneMachineAssignmentValidation = (
  teamName: string,
  machineNames: string,
  enabled = true
) => {
  return useQuery<DistributedStorageMachineAssignmentValidation[]>({
    queryKey: DS_QUERY_KEYS.machineAssignmentValidation(teamName, machineNames),
    queryFn: () => api.distributedStorage.getCloneAssignmentValidation(teamName, machineNames),
    enabled: enabled && !!teamName && !!machineNames,
  });
};

// Clone Machines
export const useCloneMachines = (
  cloneName: string,
  snapshotName: string,
  imageName: string,
  poolName: string,
  teamName: string,
  enabled = true
) => {
  return useQuery<DistributedStorageCloneMachine[]>({
    queryKey: DS_QUERY_KEYS.cloneMachines(cloneName, snapshotName, imageName, poolName, teamName),
    queryFn: () =>
      api.distributedStorage.getCloneMachines(
        cloneName,
        snapshotName,
        imageName,
        poolName,
        teamName
      ),
    enabled: enabled && !!cloneName && !!snapshotName && !!imageName && !!poolName && !!teamName,
  });
};

export type {
  DistributedStorageCluster,
  DistributedStoragePool,
  DistributedStorageRbdImage,
  DistributedStorageRbdSnapshot,
  DistributedStorageRbdClone,
  DistributedStorageMachineAssignmentStatus as MachineAssignmentStatus,
  DistributedStorageAvailableMachine as AvailableMachine,
  DistributedStorageCloneMachine as CloneMachine,
  DistributedStorageMachineAssignmentValidation as MachineAssignmentValidation,
} from '@rediacc/shared/types';
