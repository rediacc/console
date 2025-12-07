import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type {
  CephAvailableMachine,
  CephCloneMachine,
  CephCluster,
  CephMachineAssignmentStatus,
  CephMachineAssignmentValidation,
  CephPool,
  CephRbdClone,
  CephRbdImage,
  CephRbdSnapshot,
  Machine,
  GetCephPoolsParams,
  GetCephRbdImagesParams,
  GetCephRbdSnapshotsParams,
  GetCephRbdClonesParams,
  GetCephClusterMachinesParams,
  GetMachineAssignmentStatusParams,
  GetAvailableMachinesForCloneParams,
  GetCloneMachineAssignmentValidationParams,
  GetCloneMachinesParams,
} from '@rediacc/shared/types';

// Query Keys - exported for use in mutations
export const CEPH_QUERY_KEYS = {
  clusters: (teamFilter?: string | string[]) => ['ceph-clusters', teamFilter],
  pools: (teamFilter?: string | string[]) => ['ceph-pools', teamFilter],
  images: (poolName?: string, teamName?: string) => ['ceph-images', poolName, teamName],
  snapshots: (imageName?: string, poolName?: string, teamName?: string) => [
    'ceph-snapshots',
    imageName,
    poolName,
    teamName,
  ],
  clones: (snapshotName?: string, imageName?: string, poolName?: string, teamName?: string) => [
    'ceph-clones',
    snapshotName,
    imageName,
    poolName,
    teamName,
  ],
  clusterMachines: (clusterName: string) => ['ceph-cluster-machines', clusterName],
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
export const useCephClusters = (teamFilter?: string | string[], enabled = true) => {
  return useQuery<CephCluster[]>({
    queryKey: CEPH_QUERY_KEYS.clusters(teamFilter),
    queryFn: () => api.ceph.listClusters(),
    enabled: enabled,
  });
};

// Pools
export const useCephPools = (teamFilter?: string | string[], enabled = true) => {
  return useQuery<CephPool[]>({
    queryKey: CEPH_QUERY_KEYS.pools(teamFilter),
    queryFn: async () => {
      const teamName = Array.isArray(teamFilter) ? teamFilter?.[0] : teamFilter;
      if (!teamName) {
        return [];
      }
      const params: GetCephPoolsParams = { teamName, clusterName: '' };
      return api.ceph.listPools(params);
    },
    enabled: enabled && !!teamFilter,
  });
};

// RBD Images
export const useCephRbdImages = (poolName?: string, teamName?: string, enabled = true) => {
  return useQuery<CephRbdImage[]>({
    queryKey: CEPH_QUERY_KEYS.images(poolName, teamName),
    queryFn: () => {
      const params: GetCephRbdImagesParams = { poolName: poolName!, teamName: teamName! };
      return api.ceph.listImages(params);
    },
    enabled: enabled && !!poolName && !!teamName,
  });
};

// RBD Snapshots
export const useCephRbdSnapshots = (
  imageName?: string,
  poolName?: string,
  teamName?: string,
  enabled = true
) => {
  return useQuery<CephRbdSnapshot[]>({
    queryKey: CEPH_QUERY_KEYS.snapshots(imageName, poolName, teamName),
    queryFn: () => {
      const params: GetCephRbdSnapshotsParams = {
        imageName: imageName!,
        poolName: poolName!,
        teamName: teamName!,
      };
      return api.ceph.listSnapshots(params);
    },
    enabled: enabled && !!imageName && !!poolName && !!teamName,
  });
};

// RBD Clones
export const useCephRbdClones = (
  snapshotName?: string,
  imageName?: string,
  poolName?: string,
  teamName?: string,
  enabled = true
) => {
  return useQuery<CephRbdClone[]>({
    queryKey: CEPH_QUERY_KEYS.clones(snapshotName, imageName, poolName, teamName),
    queryFn: () => {
      const params: GetCephRbdClonesParams = {
        snapshotName: snapshotName!,
        imageName: imageName!,
        poolName: poolName!,
        teamName: teamName!,
      };
      return api.ceph.listClones(params);
    },
    enabled: enabled && !!snapshotName && !!imageName && !!poolName && !!teamName,
  });
};

// Cluster Machines
export const useCephClusterMachines = (clusterName: string, enabled = true) => {
  return useQuery<Machine[]>({
    queryKey: CEPH_QUERY_KEYS.clusterMachines(clusterName),
    queryFn: () => {
      const params: GetCephClusterMachinesParams = { clusterName };
      return api.ceph.getClusterMachines(params);
    },
    enabled: enabled && !!clusterName,
  });
};

// Machine Assignment Status
export const useMachineAssignmentStatus = (
  machineName: string,
  teamName: string,
  enabled = true
) => {
  return useQuery<CephMachineAssignmentStatus | null>({
    queryKey: CEPH_QUERY_KEYS.machineAssignmentStatus(machineName, teamName),
    queryFn: () => {
      const params: GetMachineAssignmentStatusParams = { machineName, teamName };
      return api.ceph.getMachineAssignmentStatus(params);
    },
    enabled: enabled && !!machineName && !!teamName,
  });
};

// Available Machines for Clone
export const useAvailableMachinesForClone = (teamName: string, enabled = true) => {
  return useQuery<CephAvailableMachine[]>({
    queryKey: CEPH_QUERY_KEYS.availableMachinesForClone(teamName),
    queryFn: () => {
      const params: GetAvailableMachinesForCloneParams = { teamName };
      return api.ceph.getAvailableMachinesForClone(params);
    },
    enabled: enabled && !!teamName,
  });
};

// Clone Machine Assignment Validation
export const useCloneMachineAssignmentValidation = (
  teamName: string,
  machineNames: string,
  enabled = true
) => {
  return useQuery<CephMachineAssignmentValidation[]>({
    queryKey: CEPH_QUERY_KEYS.machineAssignmentValidation(teamName, machineNames),
    queryFn: () => {
      const params: GetCloneMachineAssignmentValidationParams & { machineNames: string } = {
        teamName,
        machineNames,
      };
      return api.ceph.getCloneAssignmentValidation(params);
    },
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
  return useQuery<CephCloneMachine[]>({
    queryKey: CEPH_QUERY_KEYS.cloneMachines(cloneName, snapshotName, imageName, poolName, teamName),
    queryFn: () => {
      const params: GetCloneMachinesParams = {
        cloneName,
        snapshotName,
        imageName,
        poolName,
        teamName,
      };
      return api.ceph.getCloneMachines(params);
    },
    enabled: enabled && !!cloneName && !!snapshotName && !!imageName && !!poolName && !!teamName,
  });
};

export type {
  CephCluster,
  CephPool,
  CephRbdImage,
  CephRbdSnapshot,
  CephRbdClone,
  CephMachineAssignmentStatus as MachineAssignmentStatus,
  CephAvailableMachine as AvailableMachine,
  CephCloneMachine as CloneMachine,
  CephMachineAssignmentValidation as MachineAssignmentValidation,
} from '@rediacc/shared/types';
