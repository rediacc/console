import { endpoints } from '../../endpoints';
import { parseFirst, parseResponse, responseExtractors } from '../parseResponse';
import type { ApiClient } from './types';
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
  CreateCephClusterParams,
  DeleteCephClusterParams,
  UpdateCephClusterVaultParams,
  GetCephClusterMachinesParams,
  GetCephPoolsParams,
  CreateCephPoolParams,
  DeleteCephPoolParams,
  UpdateCephPoolVaultParams,
  GetCephRbdImagesParams,
  CreateCephRbdImageParams,
  DeleteCephRbdImageParams,
  GetCephRbdSnapshotsParams,
  CreateCephRbdSnapshotParams,
  DeleteCephRbdSnapshotParams,
  GetCephRbdClonesParams,
  CreateCephRbdCloneParams,
  DeleteCephRbdCloneParams,
  UpdateCloneMachineAssignmentsParams,
  UpdateCloneMachineRemovalsParams,
  GetMachineAssignmentStatusParams,
  GetAvailableMachinesForCloneParams,
  GetCloneMachineAssignmentValidationParams,
  GetCloneMachinesParams,
  UpdateImageMachineAssignmentParams,
  WithOptionalVault,
} from '../../types';

function toMachineNamesValue(machineNames: string | string[]): string {
  return Array.isArray(machineNames) ? machineNames.join(',') : machineNames;
}

export function createCephService(client: ApiClient) {
  return {
    // Clusters
    listClusters: async (): Promise<CephCluster[]> => {
      const response = await client.post<CephCluster>(endpoints.ceph.getClusters, {});
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<CephCluster>(1),
      });
    },

    createCluster: async (params: WithOptionalVault<CreateCephClusterParams>): Promise<void> => {
      await client.post(endpoints.ceph.createCluster, params);
    },

    deleteCluster: async (params: DeleteCephClusterParams): Promise<void> => {
      await client.post(endpoints.ceph.deleteCluster, params);
    },

    updateClusterVault: async (params: UpdateCephClusterVaultParams): Promise<void> => {
      await client.post(endpoints.ceph.updateClusterVault, params);
    },

    getClusterMachines: async (params: GetCephClusterMachinesParams): Promise<Machine[]> => {
      const response = await client.post<Machine>(endpoints.ceph.getClusterMachines, params);
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<Machine>(1),
      });
    },

    // Pools
    listPools: async (params: GetCephPoolsParams): Promise<CephPool[]> => {
      const response = await client.post<CephPool>(endpoints.ceph.getPools, params);
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<CephPool>(1),
      });
    },

    createPool: async (params: WithOptionalVault<CreateCephPoolParams>): Promise<void> => {
      await client.post(endpoints.ceph.createPool, params);
    },

    deletePool: async (params: DeleteCephPoolParams): Promise<void> => {
      await client.post(endpoints.ceph.deletePool, params);
    },

    updatePoolVault: async (params: UpdateCephPoolVaultParams): Promise<void> => {
      await client.post(endpoints.ceph.updatePoolVault, params);
    },

    // Images
    listImages: async (params: GetCephRbdImagesParams): Promise<CephRbdImage[]> => {
      const response = await client.post<CephRbdImage>(endpoints.ceph.getRbdImages, params);
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<CephRbdImage>(1),
      });
    },

    createImage: async (params: WithOptionalVault<CreateCephRbdImageParams>): Promise<void> => {
      await client.post(endpoints.ceph.createRbdImage, params);
    },

    deleteImage: async (params: DeleteCephRbdImageParams): Promise<void> => {
      await client.post(endpoints.ceph.deleteRbdImage, params);
    },

    assignMachineToImage: async (params: UpdateImageMachineAssignmentParams): Promise<void> => {
      await client.post(endpoints.machines.updateImageMachineAssignment, params);
    },

    // Snapshots
    listSnapshots: async (params: GetCephRbdSnapshotsParams): Promise<CephRbdSnapshot[]> => {
      const response = await client.post<CephRbdSnapshot>(endpoints.ceph.getRbdSnapshots, params);
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<CephRbdSnapshot>(1),
      });
    },

    createSnapshot: async (
      params: WithOptionalVault<CreateCephRbdSnapshotParams>
    ): Promise<void> => {
      await client.post(endpoints.ceph.createRbdSnapshot, params);
    },

    deleteSnapshot: async (params: DeleteCephRbdSnapshotParams): Promise<void> => {
      await client.post(endpoints.ceph.deleteRbdSnapshot, params);
    },

    // Clones
    listClones: async (params: GetCephRbdClonesParams): Promise<CephRbdClone[]> => {
      const response = await client.post<CephRbdClone>(endpoints.ceph.getRbdClones, params);
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<CephRbdClone>(1),
      });
    },

    createClone: async (params: WithOptionalVault<CreateCephRbdCloneParams>): Promise<void> => {
      await client.post(endpoints.ceph.createRbdClone, params);
    },

    deleteClone: async (params: DeleteCephRbdCloneParams): Promise<void> => {
      await client.post(endpoints.ceph.deleteRbdClone, params);
    },

    assignMachinesToClone: async (
      params: UpdateCloneMachineAssignmentsParams & { machineNames: string | string[] }
    ): Promise<void> => {
      await client.post(endpoints.machines.updateCloneMachineAssignments, {
        ...params,
        machineNames: toMachineNamesValue(params.machineNames),
      });
    },

    removeMachinesFromClone: async (
      params: UpdateCloneMachineRemovalsParams & { machineNames: string | string[] }
    ): Promise<void> => {
      await client.post(endpoints.machines.updateCloneMachineRemovals, {
        ...params,
        machineNames: toMachineNamesValue(params.machineNames),
      });
    },

    // Validation helpers
    getMachineAssignmentStatus: async (
      params: GetMachineAssignmentStatusParams
    ): Promise<CephMachineAssignmentStatus | null> => {
      const response = await client.post<CephMachineAssignmentStatus>(
        endpoints.machines.getMachineAssignmentStatus,
        params
      );

      return (
        parseFirst(response, {
          extractor: responseExtractors.byIndex<CephMachineAssignmentStatus>(0),
        }) ?? null
      );
    },

    getAvailableMachinesForClone: async (
      params: GetAvailableMachinesForCloneParams
    ): Promise<CephAvailableMachine[]> => {
      const response = await client.post<CephAvailableMachine>(
        endpoints.machines.getAvailableMachinesForClone,
        params
      );
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<CephAvailableMachine>(0),
      });
    },

    getCloneAssignmentValidation: async (
      params: GetCloneMachineAssignmentValidationParams & { machineNames: string | string[] }
    ): Promise<CephMachineAssignmentValidation[]> => {
      const response = await client.post<CephMachineAssignmentValidation>(
        endpoints.machines.getCloneMachineAssignmentValidation,
        {
          ...params,
          machineNames: toMachineNamesValue(params.machineNames),
        }
      );
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<CephMachineAssignmentValidation>(0),
      });
    },

    getCloneMachines: async (params: GetCloneMachinesParams): Promise<CephCloneMachine[]> => {
      const response = await client.post<CephCloneMachine>(
        endpoints.machines.getCloneMachines,
        params
      );

      return parseResponse(response, {
        extractor: responseExtractors.byIndex<CephCloneMachine>(0),
      });
    },
  };
}
