import { useQuery } from '@tanstack/react-query';
import { typedApi } from '@/api/client';
import {
  parseGetCephClusters,
  parseGetCephPools,
  parseGetCephRbdImages,
  parseGetCephRbdSnapshots,
  parseGetCephRbdClones,
  parseGetCephClusterMachines,
  parseGetMachineAssignmentStatus,
  parseGetAvailableMachinesForClone,
  parseGetCloneMachines,
} from '@rediacc/shared/api';
import type {
  CephAvailableMachine,
  CephCloneMachine,
  CephMachineAssignmentStatus,
  GetAvailableMachinesForCloneParams,
  GetCephClusterMachines_ResultSet1,
  GetCephClusterMachinesParams,
  GetCephClusters_ResultSet1,
  GetCephPools_ResultSet1,
  GetCephPoolsParams,
  GetCephRbdClones_ResultSet1,
  GetCephRbdClonesParams,
  GetCephRbdImages_ResultSet1,
  GetCephRbdImagesParams,
  GetCephRbdSnapshots_ResultSet1,
  GetCephRbdSnapshotsParams,
  GetCloneMachinesParams,
  GetMachineAssignmentStatusParams,
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
  return useQuery<GetCephClusters_ResultSet1[]>({
    queryKey: CEPH_QUERY_KEYS.clusters(teamFilter),
    queryFn: async () => {
      const response = await typedApi.GetCephClusters({});
      return parseGetCephClusters(response as never);
    },
    enabled,
  });
};

// Pools
export const useCephPools = (teamFilter?: string | string[], enabled = true) => {
  return useQuery<GetCephPools_ResultSet1[]>({
    queryKey: CEPH_QUERY_KEYS.pools(teamFilter),
    queryFn: async () => {
      const teamName = Array.isArray(teamFilter) ? teamFilter[0] : teamFilter;
      if (!teamName) {
        return [];
      }
      const params: GetCephPoolsParams = { teamName, clusterName: '' };
      const response = await typedApi.GetCephPools(params);
      return parseGetCephPools(response as never);
    },
    enabled: enabled && !!teamFilter,
  });
};

// RBD Images
export const useCephRbdImages = (poolName?: string, teamName?: string, enabled = true) => {
  return useQuery<GetCephRbdImages_ResultSet1[]>({
    queryKey: CEPH_QUERY_KEYS.images(poolName, teamName),
    queryFn: async () => {
      const params: GetCephRbdImagesParams = { poolName: poolName!, teamName: teamName! };
      const response = await typedApi.GetCephRbdImages(params);
      return parseGetCephRbdImages(response as never);
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
  return useQuery<GetCephRbdSnapshots_ResultSet1[]>({
    queryKey: CEPH_QUERY_KEYS.snapshots(imageName, poolName, teamName),
    queryFn: async () => {
      const params: GetCephRbdSnapshotsParams = {
        imageName: imageName!,
        poolName: poolName!,
        teamName: teamName!,
      };
      const response = await typedApi.GetCephRbdSnapshots(params);
      return parseGetCephRbdSnapshots(response as never);
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
  return useQuery<GetCephRbdClones_ResultSet1[]>({
    queryKey: CEPH_QUERY_KEYS.clones(snapshotName, imageName, poolName, teamName),
    queryFn: async () => {
      const params: GetCephRbdClonesParams = {
        snapshotName: snapshotName!,
        imageName: imageName!,
        poolName: poolName!,
        teamName: teamName!,
      };
      const response = await typedApi.GetCephRbdClones(params);
      return parseGetCephRbdClones(response as never);
    },
    enabled: enabled && !!snapshotName && !!imageName && !!poolName && !!teamName,
  });
};

// Cluster Machines
export const useCephClusterMachines = (clusterName: string, enabled = true) => {
  return useQuery<GetCephClusterMachines_ResultSet1[]>({
    queryKey: CEPH_QUERY_KEYS.clusterMachines(clusterName),
    queryFn: async () => {
      const params: GetCephClusterMachinesParams = { clusterName };
      const response = await typedApi.GetCephClusterMachines(params);
      return parseGetCephClusterMachines(response as never);
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
    queryFn: async () => {
      const params: GetMachineAssignmentStatusParams = { machineName, teamName };
      const response = await typedApi.GetMachineAssignmentStatus(params);
      return parseGetMachineAssignmentStatus(response as never);
    },
    enabled: enabled && !!machineName && !!teamName,
  });
};

// Available Machines for Clone
export const useAvailableMachinesForClone = (teamName: string, enabled = true) => {
  return useQuery<CephAvailableMachine[]>({
    queryKey: CEPH_QUERY_KEYS.availableMachinesForClone(teamName),
    queryFn: async () => {
      const params: GetAvailableMachinesForCloneParams = { teamName };
      const response = await typedApi.GetAvailableMachinesForClone(params);
      return parseGetAvailableMachinesForClone(response as never);
    },
    enabled: enabled && !!teamName,
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
    queryFn: async () => {
      const params: GetCloneMachinesParams = {
        cloneName,
        snapshotName,
        imageName,
        poolName,
        teamName,
      };
      const response = await typedApi.GetCloneMachines(params);
      return parseGetCloneMachines(response as never);
    },
    enabled: enabled && !!cloneName && !!snapshotName && !!imageName && !!poolName && !!teamName,
  });
};

export type {
  CephAvailableMachine as AvailableMachine,
  CephCloneMachine as CloneMachine,
  CephMachineAssignmentStatus as MachineAssignmentStatus,
  CephMachineAssignmentValidation as MachineAssignmentValidation,
  GetCephClusterMachines_ResultSet1,
  GetCephClusterMachines_ResultSet1 as CephClusterMachine,
  GetCephClusters_ResultSet1,
  GetCephClusters_ResultSet1 as CephCluster,
  GetCephPools_ResultSet1,
  GetCephPools_ResultSet1 as CephPool,
  GetCephRbdClones_ResultSet1,
  GetCephRbdClones_ResultSet1 as CephRbdClone,
  GetCephRbdImages_ResultSet1,
  GetCephRbdImages_ResultSet1 as CephRbdImage,
  GetCephRbdSnapshots_ResultSet1,
  GetCephRbdSnapshots_ResultSet1 as CephRbdSnapshot,
} from '@rediacc/shared/types';
