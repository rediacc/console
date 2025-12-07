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
      const response = await client.post<CephCluster>('/GetCephClusters', {});
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<CephCluster>(1),
      });
    },

    createCluster: async (params: WithOptionalVault<CreateCephClusterParams>): Promise<void> => {
      await client.post('/CreateCephCluster', params);
    },

    deleteCluster: async (params: DeleteCephClusterParams): Promise<void> => {
      await client.post('/DeleteCephCluster', params);
    },

    updateClusterVault: async (params: UpdateCephClusterVaultParams): Promise<void> => {
      await client.post('/UpdateCephClusterVault', params);
    },

    getClusterMachines: async (params: GetCephClusterMachinesParams): Promise<Machine[]> => {
      const response = await client.post<Machine>('/GetCephClusterMachines', params);
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<Machine>(1),
      });
    },

    // Pools
    listPools: async (params: GetCephPoolsParams): Promise<CephPool[]> => {
      const response = await client.post<CephPool>('/GetCephPools', params);
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<CephPool>(1),
      });
    },

    createPool: async (params: WithOptionalVault<CreateCephPoolParams>): Promise<void> => {
      await client.post('/CreateCephPool', params);
    },

    deletePool: async (params: DeleteCephPoolParams): Promise<void> => {
      await client.post('/DeleteCephPool', params);
    },

    updatePoolVault: async (params: UpdateCephPoolVaultParams): Promise<void> => {
      await client.post('/UpdateCephPoolVault', params);
    },

    // Images
    listImages: async (params: GetCephRbdImagesParams): Promise<CephRbdImage[]> => {
      const response = await client.post<CephRbdImage>('/GetCephRbdImages', params);
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<CephRbdImage>(1),
      });
    },

    createImage: async (params: WithOptionalVault<CreateCephRbdImageParams>): Promise<void> => {
      await client.post('/CreateCephRbdImage', params);
    },

    deleteImage: async (params: DeleteCephRbdImageParams): Promise<void> => {
      await client.post('/DeleteCephRbdImage', params);
    },

    assignMachineToImage: async (params: UpdateImageMachineAssignmentParams): Promise<void> => {
      await client.post('/UpdateImageMachineAssignment', params);
    },

    // Snapshots
    listSnapshots: async (params: GetCephRbdSnapshotsParams): Promise<CephRbdSnapshot[]> => {
      const response = await client.post<CephRbdSnapshot>('/GetCephRbdSnapshots', params);
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<CephRbdSnapshot>(1),
      });
    },

    createSnapshot: async (
      params: WithOptionalVault<CreateCephRbdSnapshotParams>
    ): Promise<void> => {
      await client.post('/CreateCephRbdSnapshot', params);
    },

    deleteSnapshot: async (params: DeleteCephRbdSnapshotParams): Promise<void> => {
      await client.post('/DeleteCephRbdSnapshot', params);
    },

    // Clones
    listClones: async (params: GetCephRbdClonesParams): Promise<CephRbdClone[]> => {
      const response = await client.post<CephRbdClone>('/GetCephRbdClones', params);
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<CephRbdClone>(1),
      });
    },

    createClone: async (params: WithOptionalVault<CreateCephRbdCloneParams>): Promise<void> => {
      await client.post('/CreateCephRbdClone', params);
    },

    deleteClone: async (params: DeleteCephRbdCloneParams): Promise<void> => {
      await client.post('/DeleteCephRbdClone', params);
    },

    assignMachinesToClone: async (
      params: UpdateCloneMachineAssignmentsParams & { machineNames: string | string[] }
    ): Promise<void> => {
      await client.post('/UpdateCloneMachineAssignments', {
        ...params,
        machineNames: toMachineNamesValue(params.machineNames),
      });
    },

    removeMachinesFromClone: async (
      params: UpdateCloneMachineRemovalsParams & { machineNames: string | string[] }
    ): Promise<void> => {
      await client.post('/UpdateCloneMachineRemovals', {
        ...params,
        machineNames: toMachineNamesValue(params.machineNames),
      });
    },

    // Validation helpers
    getMachineAssignmentStatus: async (
      params: GetMachineAssignmentStatusParams
    ): Promise<CephMachineAssignmentStatus | null> => {
      const response = await client.post<CephMachineAssignmentStatus>(
        '/GetMachineAssignmentStatus',
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
        '/GetAvailableMachinesForClone',
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
        '/GetCloneMachineAssignmentValidation',
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
      const response = await client.post<CephCloneMachine>('/GetCloneMachines', params);

      return parseResponse(response, {
        extractor: responseExtractors.byIndex<CephCloneMachine>(0),
      });
    },
  };
}
