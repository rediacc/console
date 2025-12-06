import { endpoints } from '../../endpoints';
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
} from '../../types';
import { parseFirst, parseResponse, responseExtractors } from '../parseResponse';
import type { ApiClient } from './types';

function toMachineNamesValue(machineNames: string | string[]): string {
  return Array.isArray(machineNames) ? machineNames.join(',') : machineNames;
}

export function createCephService(client: ApiClient) {
  return {
    // Clusters
    listClusters: async (): Promise<CephCluster[]> => {
      const response = await client.post<CephCluster>(
        endpoints.ceph.getClusters,
        {}
      );
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<CephCluster>(1),
      });
    },

    createCluster: async (clusterName: string, vaultContent?: string): Promise<void> => {
      await client.post(endpoints.ceph.createCluster, { clusterName, vaultContent });
    },

    deleteCluster: async (clusterName: string): Promise<void> => {
      await client.post(endpoints.ceph.deleteCluster, { clusterName });
    },

    updateClusterVault: async (
      clusterName: string,
      vaultContent: string,
      vaultVersion: number
    ): Promise<void> => {
      await client.post(endpoints.ceph.updateClusterVault, {
        clusterName,
        vaultContent,
        vaultVersion,
      });
    },

    getClusterMachines: async (clusterName: string): Promise<Machine[]> => {
      const response = await client.post<Machine>(endpoints.ceph.getClusterMachines, {
        clusterName,
      });
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<Machine>(1),
      });
    },

    // Pools
    listPools: async (teamName: string | string[]): Promise<CephPool[]> => {
      const response = await client.post<CephPool>(
        endpoints.ceph.getPools,
        {
          teamName: toMachineNamesValue(teamName),
        }
      );
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<CephPool>(1),
      });
    },

    createPool: async (
      teamName: string,
      clusterName: string,
      poolName: string,
      vaultContent?: string
    ): Promise<void> => {
      await client.post(endpoints.ceph.createPool, {
        teamName,
        clusterName,
        poolName,
        vaultContent,
      });
    },

    deletePool: async (teamName: string, poolName: string): Promise<void> => {
      await client.post(endpoints.ceph.deletePool, {
        teamName,
        poolName,
      });
    },

    updatePoolVault: async (
      teamName: string,
      poolName: string,
      vaultContent: string,
      vaultVersion: number
    ): Promise<void> => {
      await client.post(endpoints.ceph.updatePoolVault, {
        teamName,
        poolName,
        vaultContent,
        vaultVersion,
      });
    },

    // Images
    listImages: async (
      poolName: string,
      teamName: string
    ): Promise<CephRbdImage[]> => {
      const response = await client.post<CephRbdImage>(
        endpoints.ceph.getRbdImages,
        {
          poolName,
          teamName,
        }
      );
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<CephRbdImage>(1),
      });
    },

    createImage: async (
      poolName: string,
      teamName: string,
      imageName: string,
      machineName: string,
      vaultContent?: string
    ): Promise<void> => {
      await client.post(endpoints.ceph.createRbdImage, {
        poolName,
        teamName,
        imageName,
        machineName,
        vaultContent,
      });
    },

    deleteImage: async (poolName: string, teamName: string, imageName: string): Promise<void> => {
      await client.post(endpoints.ceph.deleteRbdImage, {
        poolName,
        teamName,
        imageName,
      });
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
      });
    },

    // Snapshots
    listSnapshots: async (
      imageName: string,
      poolName: string,
      teamName: string
    ): Promise<CephRbdSnapshot[]> => {
      const response = await client.post<CephRbdSnapshot>(
        endpoints.ceph.getRbdSnapshots,
        {
          imageName,
          poolName,
          teamName,
        }
      );
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<CephRbdSnapshot>(1),
      });
    },

    createSnapshot: async (
      imageName: string,
      poolName: string,
      teamName: string,
      snapshotName: string,
      vaultContent?: string
    ): Promise<void> => {
      await client.post(endpoints.ceph.createRbdSnapshot, {
        imageName,
        poolName,
        teamName,
        snapshotName,
        vaultContent,
      });
    },

    deleteSnapshot: async (
      imageName: string,
      poolName: string,
      teamName: string,
      snapshotName: string
    ): Promise<void> => {
      await client.post(endpoints.ceph.deleteRbdSnapshot, {
        imageName,
        poolName,
        teamName,
        snapshotName,
      });
    },

    // Clones
    listClones: async (
      snapshotName: string,
      imageName: string,
      poolName: string,
      teamName: string
    ): Promise<CephRbdClone[]> => {
      const response = await client.post<CephRbdClone>(
        endpoints.ceph.getRbdClones,
        {
          snapshotName,
          imageName,
          poolName,
          teamName,
        }
      );
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<CephRbdClone>(1),
      });
    },

    createClone: async (
      snapshotName: string,
      imageName: string,
      poolName: string,
      teamName: string,
      cloneName: string,
      vaultContent?: string
    ): Promise<void> => {
      await client.post(endpoints.ceph.createRbdClone, {
        snapshotName,
        imageName,
        poolName,
        teamName,
        cloneName,
        vaultContent,
      });
    },

    deleteClone: async (
      cloneName: string,
      snapshotName: string,
      imageName: string,
      poolName: string,
      teamName: string
    ): Promise<void> => {
      await client.post(endpoints.ceph.deleteRbdClone, {
        cloneName,
        snapshotName,
        imageName,
        poolName,
        teamName,
      });
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
      });
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
      });
    },

    // Validation helpers
    getMachineAssignmentStatus: async (
      machineName: string,
      teamName: string
    ): Promise<CephMachineAssignmentStatus | null> => {
      const response = await client.post<CephMachineAssignmentStatus>(
        endpoints.machines.getMachineAssignmentStatus,
        {
          machineName,
          teamName,
        }
      );

      return (
        parseFirst(response, {
          extractor: responseExtractors.byIndex<CephMachineAssignmentStatus>(0),
        }) ?? null
      );
    },

    getAvailableMachinesForClone: async (
      teamName: string
    ): Promise<CephAvailableMachine[]> => {
      const response = await client.post<CephAvailableMachine>(
        endpoints.machines.getAvailableMachinesForClone,
        { teamName }
      );
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<CephAvailableMachine>(0),
      });
    },

    getCloneAssignmentValidation: async (
      teamName: string,
      machineNames: string | string[]
    ): Promise<CephMachineAssignmentValidation[]> => {
      const response = await client.post<CephMachineAssignmentValidation>(
        endpoints.machines.getCloneMachineAssignmentValidation,
        {
          teamName,
          machineNames: toMachineNamesValue(machineNames),
        }
      );
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<CephMachineAssignmentValidation>(0),
      });
    },

    getCloneMachines: async (
      cloneName: string,
      snapshotName: string,
      imageName: string,
      poolName: string,
      teamName: string
    ): Promise<CephCloneMachine[]> => {
      const response = await client.post<CephCloneMachine>(
        endpoints.machines.getCloneMachines,
        {
          cloneName,
          snapshotName,
          imageName,
          poolName,
          teamName,
        }
      );

      return parseResponse(response, {
        extractor: responseExtractors.byIndex<CephCloneMachine>(0),
      });
    },
  };
}
