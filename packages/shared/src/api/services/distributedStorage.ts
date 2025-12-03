import { endpoints } from '../../endpoints'
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
} from '../../types'
import { parseFirst, parseResponse, responseExtractors } from '../parseResponse'
import type { ApiClient } from './types'

function toMachineNamesValue(machineNames: string | string[]): string {
  return Array.isArray(machineNames) ? machineNames.join(',') : machineNames
}

export function createDistributedStorageService(client: ApiClient) {
  return {
    // Clusters
    listClusters: async (): Promise<DistributedStorageCluster[]> => {
      const response = await client.post<DistributedStorageCluster>(endpoints.distributedStorage.getClusters, {})
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<DistributedStorageCluster>(1),
      })
    },

    createCluster: async (clusterName: string, clusterVault?: string): Promise<void> => {
      await client.post(endpoints.distributedStorage.createCluster, { clusterName, clusterVault })
    },

    deleteCluster: async (clusterName: string): Promise<void> => {
      await client.post(endpoints.distributedStorage.deleteCluster, { clusterName })
    },

    updateClusterVault: async (clusterName: string, clusterVault: string, vaultVersion: number): Promise<void> => {
      await client.post(endpoints.distributedStorage.updateClusterVault, {
        clusterName,
        clusterVault,
        vaultVersion,
      })
    },

    getClusterMachines: async (clusterName: string): Promise<Machine[]> => {
      const response = await client.post<Machine>(endpoints.distributedStorage.getClusterMachines, { clusterName })
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<Machine>(1),
      })
    },

    // Pools
    listPools: async (teamName: string | string[]): Promise<DistributedStoragePool[]> => {
      const response = await client.post<DistributedStoragePool>(endpoints.distributedStorage.getPools, {
        teamName: toMachineNamesValue(teamName),
      })
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<DistributedStoragePool>(1),
      })
    },

    createPool: async (
      teamName: string,
      clusterName: string,
      poolName: string,
      poolVault?: string
    ): Promise<void> => {
      await client.post(endpoints.distributedStorage.createPool, {
        teamName,
        clusterName,
        poolName,
        poolVault,
      })
    },

    deletePool: async (teamName: string, poolName: string): Promise<void> => {
      await client.post(endpoints.distributedStorage.deletePool, {
        teamName,
        poolName,
      })
    },

    updatePoolVault: async (
      teamName: string,
      poolName: string,
      poolVault: string,
      vaultVersion: number
    ): Promise<void> => {
      await client.post(endpoints.distributedStorage.updatePoolVault, {
        teamName,
        poolName,
        poolVault,
        vaultVersion,
      })
    },

    // Images
    listImages: async (poolName: string, teamName: string): Promise<DistributedStorageRbdImage[]> => {
      const response = await client.post<DistributedStorageRbdImage>(endpoints.distributedStorage.getRbdImages, {
        poolName,
        teamName,
      })
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<DistributedStorageRbdImage>(1),
      })
    },

    createImage: async (
      poolName: string,
      teamName: string,
      imageName: string,
      machineName: string,
      imageVault?: string
    ): Promise<void> => {
      await client.post(endpoints.distributedStorage.createRbdImage, {
        poolName,
        teamName,
        imageName,
        machineName,
        imageVault,
      })
    },

    deleteImage: async (poolName: string, teamName: string, imageName: string): Promise<void> => {
      await client.post(endpoints.distributedStorage.deleteRbdImage, {
        poolName,
        teamName,
        imageName,
      })
    },

    assignMachineToImage: async (
      poolName: string,
      teamName: string,
      imageName: string,
      newMachineName: string
    ): Promise<void> => {
      await client.post(endpoints.machines.updateImageMachineAssignment, {
        poolName,
        teamName,
        imageName,
        newMachineName,
      })
    },

    // Snapshots
    listSnapshots: async (imageName: string, poolName: string, teamName: string): Promise<DistributedStorageRbdSnapshot[]> => {
      const response = await client.post<DistributedStorageRbdSnapshot>(endpoints.distributedStorage.getRbdSnapshots, {
        imageName,
        poolName,
        teamName,
      })
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<DistributedStorageRbdSnapshot>(1),
      })
    },

    createSnapshot: async (
      imageName: string,
      poolName: string,
      teamName: string,
      snapshotName: string,
      snapshotVault?: string
    ): Promise<void> => {
      await client.post(endpoints.distributedStorage.createRbdSnapshot, {
        imageName,
        poolName,
        teamName,
        snapshotName,
        snapshotVault,
      })
    },

    deleteSnapshot: async (
      imageName: string,
      poolName: string,
      teamName: string,
      snapshotName: string
    ): Promise<void> => {
      await client.post(endpoints.distributedStorage.deleteRbdSnapshot, {
        imageName,
        poolName,
        teamName,
        snapshotName,
      })
    },

    // Clones
    listClones: async (
      snapshotName: string,
      imageName: string,
      poolName: string,
      teamName: string
    ): Promise<DistributedStorageRbdClone[]> => {
      const response = await client.post<DistributedStorageRbdClone>(endpoints.distributedStorage.getRbdClones, {
        snapshotName,
        imageName,
        poolName,
        teamName,
      })
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<DistributedStorageRbdClone>(1),
      })
    },

    createClone: async (
      snapshotName: string,
      imageName: string,
      poolName: string,
      teamName: string,
      cloneName: string,
      cloneVault?: string
    ): Promise<void> => {
      await client.post(endpoints.distributedStorage.createRbdClone, {
        snapshotName,
        imageName,
        poolName,
        teamName,
        cloneName,
        cloneVault,
      })
    },

    deleteClone: async (
      cloneName: string,
      snapshotName: string,
      imageName: string,
      poolName: string,
      teamName: string
    ): Promise<void> => {
      await client.post(endpoints.distributedStorage.deleteRbdClone, {
        cloneName,
        snapshotName,
        imageName,
        poolName,
        teamName,
      })
    },

    assignMachinesToClone: async (
      cloneName: string,
      snapshotName: string,
      imageName: string,
      poolName: string,
      teamName: string,
      machineNames: string | string[]
    ): Promise<void> => {
      await client.post(endpoints.machines.updateCloneMachineAssignments, {
        cloneName,
        snapshotName,
        imageName,
        poolName,
        teamName,
        machineNames: toMachineNamesValue(machineNames),
      })
    },

    removeMachinesFromClone: async (
      cloneName: string,
      snapshotName: string,
      imageName: string,
      poolName: string,
      teamName: string,
      machineNames: string | string[]
    ): Promise<void> => {
      await client.post(endpoints.machines.updateCloneMachineRemovals, {
        cloneName,
        snapshotName,
        imageName,
        poolName,
        teamName,
        machineNames: toMachineNamesValue(machineNames),
      })
    },

    // Validation helpers
    getMachineAssignmentStatus: async (
      machineName: string,
      teamName: string
    ): Promise<DistributedStorageMachineAssignmentStatus | null> => {
      const response = await client.post<DistributedStorageMachineAssignmentStatus>(
        endpoints.machines.getMachineAssignmentStatus,
        {
          machineName,
          teamName,
        }
      )

      return (
        parseFirst(response, {
          extractor: responseExtractors.byIndex<DistributedStorageMachineAssignmentStatus>(0),
        }) ?? null
      )
    },

    getAvailableMachinesForClone: async (teamName: string): Promise<DistributedStorageAvailableMachine[]> => {
      const response = await client.post<DistributedStorageAvailableMachine>(
        endpoints.machines.getAvailableMachinesForClone,
        { teamName }
      )
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<DistributedStorageAvailableMachine>(0),
      })
    },

    getCloneAssignmentValidation: async (
      teamName: string,
      machineNames: string | string[]
    ): Promise<DistributedStorageMachineAssignmentValidation[]> => {
      const response = await client.post<DistributedStorageMachineAssignmentValidation>(
        endpoints.machines.getCloneMachineAssignmentValidation,
        {
          teamName,
          machineNames: toMachineNamesValue(machineNames),
        }
      )
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<DistributedStorageMachineAssignmentValidation>(0),
      })
    },

    getCloneMachines: async (
      cloneName: string,
      snapshotName: string,
      imageName: string,
      poolName: string,
      teamName: string
    ): Promise<DistributedStorageCloneMachine[]> => {
      const response = await client.post<DistributedStorageCloneMachine>(endpoints.machines.getCloneMachines, {
        cloneName,
        snapshotName,
        imageName,
        poolName,
        teamName,
      })

      return parseResponse(response, {
        extractor: responseExtractors.byIndex<DistributedStorageCloneMachine>(0),
      })
    },
  }
}
