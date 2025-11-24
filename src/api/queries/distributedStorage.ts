import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../client'
import { extractTableData } from '@/core/api/response'
import type { Machine } from '@/types'

// Types
export interface DistributedStorageCluster {
  clusterName: string
  teamName?: string
  vaultVersion: number
  assignedMachineCount?: number
  poolCount?: number
  clusterVault?: string
}

export interface DistributedStoragePool {
  poolName: string
  clusterName: string
  teamName: string
  vaultVersion?: number
  rbdImageCount?: number
  poolVault?: string
  poolGuid?: string
}

export interface DistributedStorageRbdImage {
  imageName: string
  poolName: string
  teamName: string
  clusterName: string
  machineName?: string
  snapshotCount?: number
  imageVault?: string
  imageGuid?: string
  vaultContent?: string
}

export interface DistributedStorageRbdSnapshot {
  snapshotName: string
  imageName: string
  poolName: string
  teamName: string
  clusterName: string
  createdDate?: string
  cloneCount?: number
  snapshotVault?: string
  snapshotGuid?: string
  vaultContent?: string
}

export interface DistributedStorageRbdClone {
  cloneName: string
  snapshotName: string
  imageName: string
  poolName: string
  teamName: string
  clusterName: string
  snapshotCreatedDate?: string
  cloneVault?: string
  vaultContent?: string
}

export interface MachineAssignmentStatus {
  machineName: string
  teamName: string
  assignmentType: string
  assignmentDetails: string
  status: string
}

export interface AvailableMachine {
  machineName: string
  status: string
  description: string
}

export interface CloneMachine {
  machineName: string
  bridgeName: string
  assignmentId: number
}

export interface MachineAssignmentValidation {
  machineName: string
  isValid: boolean
  error?: string
}

// Query Keys - exported for use in mutations
export const DS_QUERY_KEYS = {
  clusters: (teamFilter?: string | string[]) => ['distributed-storage-clusters', teamFilter],
  pools: (teamFilter?: string | string[]) => ['distributed-storage-pools', teamFilter],
  images: (poolName?: string, teamName?: string) => ['distributed-storage-images', poolName, teamName],
  snapshots: (imageName?: string, poolName?: string, teamName?: string) => ['distributed-storage-snapshots', imageName, poolName, teamName],
  clones: (snapshotName?: string, imageName?: string, poolName?: string, teamName?: string) => ['distributed-storage-clones', snapshotName, imageName, poolName, teamName],
  clusterMachines: (clusterName: string) => ['distributed-storage-cluster-machines', clusterName],
  machineAssignmentStatus: (machineName: string, teamName: string) => ['machine-assignment-status', machineName, teamName],
  availableMachinesForClone: (teamName: string) => ['available-machines-for-clone', teamName],
  cloneMachines: (cloneName: string, snapshotName: string, imageName: string, poolName: string, teamName: string) => ['clone-machines', cloneName, snapshotName, imageName, poolName, teamName],
  machineAssignmentValidation: (teamName: string, machineNames: string) => ['machine-assignment-validation', teamName, machineNames],
}

// =============================================================================
// QUERY HOOKS
// =============================================================================

// Clusters
export const useDistributedStorageClusters = (teamFilter?: string | string[], enabled = true) => {
  return useQuery({
    queryKey: DS_QUERY_KEYS.clusters(teamFilter),
    queryFn: async () => {
      const response = await apiClient.post('/GetDistributedStorageClusters', {})

      if (response.failure !== 0) {
        throw new Error(response.errors?.join(', ') || 'Failed to fetch clusters')
      }

      return extractTableData<DistributedStorageCluster[]>(response, 1, []) as DistributedStorageCluster[]
    },
    enabled: enabled,
  })
}

// Pools
export const useDistributedStoragePools = (teamFilter?: string | string[], enabled = true) => {
  return useQuery({
    queryKey: DS_QUERY_KEYS.pools(teamFilter),
    queryFn: async () => {
      const response = await apiClient.post('/GetDistributedStoragePools', {
        teamName: Array.isArray(teamFilter) ? teamFilter[0] : teamFilter,
      })

      if (response.failure !== 0) {
        throw new Error(response.errors?.join(', ') || 'Failed to fetch pools')
      }

      return extractTableData<DistributedStoragePool[]>(response, 1, []) as DistributedStoragePool[]
    },
    enabled: enabled && !!teamFilter,
  })
}

// RBD Images
export const useDistributedStorageRbdImages = (poolName?: string, teamName?: string, enabled = true) => {
  return useQuery({
    queryKey: DS_QUERY_KEYS.images(poolName, teamName),
    queryFn: async () => {
      const response = await apiClient.post('/GetDistributedStorageRbdImages', {
        poolName,
        teamName,
      })

      if (response.failure !== 0) {
        throw new Error(response.errors?.join(', ') || 'Failed to fetch RBD images')
      }

      return extractTableData<DistributedStorageRbdImage[]>(response, 1, []) as DistributedStorageRbdImage[]
    },
    enabled: enabled && !!poolName && !!teamName,
  })
}

// RBD Snapshots
export const useDistributedStorageRbdSnapshots = (imageName?: string, poolName?: string, teamName?: string, enabled = true) => {
  return useQuery({
    queryKey: DS_QUERY_KEYS.snapshots(imageName, poolName, teamName),
    queryFn: async () => {
      const response = await apiClient.post('/GetDistributedStorageRbdSnapshots', {
        imageName,
        poolName,
        teamName,
      })

      if (response.failure !== 0) {
        throw new Error(response.errors?.join(', ') || 'Failed to fetch RBD snapshots')
      }

      return extractTableData<DistributedStorageRbdSnapshot[]>(response, 1, []) as DistributedStorageRbdSnapshot[]
    },
    enabled: enabled && !!imageName && !!poolName && !!teamName,
  })
}

// RBD Clones
export const useDistributedStorageRbdClones = (snapshotName?: string, imageName?: string, poolName?: string, teamName?: string, enabled = true) => {
  return useQuery({
    queryKey: DS_QUERY_KEYS.clones(snapshotName, imageName, poolName, teamName),
    queryFn: async () => {
      const response = await apiClient.post('/GetDistributedStorageRbdClones', {
        snapshotName,
        imageName,
        poolName,
        teamName,
      })

      if (response.failure !== 0) {
        throw new Error(response.errors?.join(', ') || 'Failed to fetch RBD clones')
      }

      return extractTableData<DistributedStorageRbdClone[]>(response, 1, []) as DistributedStorageRbdClone[]
    },
    enabled: enabled && !!snapshotName && !!imageName && !!poolName && !!teamName,
  })
}

// Cluster Machines
export const useDistributedStorageClusterMachines = (clusterName: string, enabled = true) => {
  return useQuery({
    queryKey: DS_QUERY_KEYS.clusterMachines(clusterName),
    queryFn: async () => {
      const response = await apiClient.post('/GetDistributedStorageClusterMachines', {
        clusterName,
      })

      if (response.failure !== 0) {
        throw new Error(response.errors?.join(', ') || 'Failed to fetch cluster machines')
      }

      return extractTableData<Machine[]>(response, 1, []) as Machine[]
    },
    enabled: enabled && !!clusterName,
  })
}

// Machine Assignment Status
export const useGetMachineAssignmentStatus = (machineName: string, teamName: string, enabled = true) => {
  return useQuery({
    queryKey: DS_QUERY_KEYS.machineAssignmentStatus(machineName, teamName),
    queryFn: async () => {
      const response = await apiClient.post('/GetMachineAssignmentStatus', {
        machineName,
        teamName,
      })

      if (response.failure !== 0) {
        throw new Error(response.errors?.join(', ') || 'Failed to fetch machine assignment status')
      }

      const results = extractTableData<MachineAssignmentStatus[]>(response, 0, [])
      // Return first element since we're querying for a single machine
      return results[0] as MachineAssignmentStatus | undefined
    },
    enabled: enabled && !!machineName && !!teamName,
  })
}

// Available Machines for Clone
export const useGetAvailableMachinesForClone = (teamName: string, enabled = true) => {
  return useQuery({
    queryKey: DS_QUERY_KEYS.availableMachinesForClone(teamName),
    queryFn: async () => {
      const response = await apiClient.post('/GetAvailableMachinesForClone', {
        teamName,
      })

      if (response.failure !== 0) {
        throw new Error(response.errors?.join(', ') || 'Failed to fetch available machines')
      }

      return extractTableData<AvailableMachine[]>(response, 0, []) as AvailableMachine[]
    },
    enabled: enabled && !!teamName,
  })
}

// Clone Machine Assignment Validation
export const useGetCloneMachineAssignmentValidation = (teamName: string, machineNames: string, enabled = true) => {
  return useQuery({
    queryKey: DS_QUERY_KEYS.machineAssignmentValidation(teamName, machineNames),
    queryFn: async () => {
      const response = await apiClient.post('/GetCloneMachineAssignmentValidation', {
        teamName,
        machineNames,
      })

      if (response.failure !== 0) {
        throw new Error(response.errors?.join(', ') || 'Failed to validate machine assignments')
      }

      return extractTableData<MachineAssignmentValidation[]>(response, 0, []) as MachineAssignmentValidation[]
    },
    enabled: enabled && !!teamName && !!machineNames,
  })
}

// Clone Machines
export const useGetCloneMachines = (
  cloneName: string,
  snapshotName: string,
  imageName: string,
  poolName: string,
  teamName: string,
  enabled = true
) => {
  return useQuery({
    queryKey: DS_QUERY_KEYS.cloneMachines(cloneName, snapshotName, imageName, poolName, teamName),
    queryFn: async () => {
      const response = await apiClient.post('/GetCloneMachines', {
        cloneName,
        snapshotName,
        imageName,
        poolName,
        teamName,
      })

      if (response.failure !== 0) {
        throw new Error(response.errors?.join(', ') || 'Failed to fetch clone machines')
      }

      return extractTableData<CloneMachine[]>(response, 0, []) as CloneMachine[]
    },
    enabled: enabled && !!cloneName && !!snapshotName && !!imageName && !!poolName && !!teamName,
  })
}
