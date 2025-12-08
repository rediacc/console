import { parseFirst, parseResponse, responseExtractors } from '../parseResponse';
import type { ApiClient } from './types';
import type {
  CephAvailableMachine,
  CephCloneMachine,
  CephMachineAssignmentStatus,
  CephMachineAssignmentValidation,
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
  GetCloneMachineAssignmentValidationParams,
  GetCloneMachinesParams,
  GetMachineAssignmentStatusParams,
  UpdateCephClusterVaultParams,
  UpdateCephPoolVaultParams,
  UpdateCloneMachineAssignmentsParams,
  UpdateCloneMachineRemovalsParams,
  UpdateImageMachineAssignmentParams,
  WithOptionalVault,
} from '../../types';

function toMachineNamesValue(machineNames: string | string[]): string {
  return Array.isArray(machineNames) ? machineNames.join(',') : machineNames;
}

export function createCephService(client: ApiClient) {
  return {
    // Clusters
    listClusters: async (): Promise<GetCephClusters_ResultSet1[]> => {
      const response = await client.post<GetCephClusters_ResultSet1>('/GetCephClusters', {});
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<GetCephClusters_ResultSet1>(1),
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

    getClusterMachines: async (
      params: GetCephClusterMachinesParams
    ): Promise<GetCephClusterMachines_ResultSet1[]> => {
      const response = await client.post<GetCephClusterMachines_ResultSet1>(
        '/GetCephClusterMachines',
        params
      );
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<GetCephClusterMachines_ResultSet1>(1),
      });
    },

    // Pools
    listPools: async (params: GetCephPoolsParams): Promise<GetCephPools_ResultSet1[]> => {
      const response = await client.post<GetCephPools_ResultSet1>('/GetCephPools', params);
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<GetCephPools_ResultSet1>(1),
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
    listImages: async (params: GetCephRbdImagesParams): Promise<GetCephRbdImages_ResultSet1[]> => {
      const response = await client.post<GetCephRbdImages_ResultSet1>('/GetCephRbdImages', params);
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<GetCephRbdImages_ResultSet1>(1),
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
    listSnapshots: async (
      params: GetCephRbdSnapshotsParams
    ): Promise<GetCephRbdSnapshots_ResultSet1[]> => {
      const response = await client.post<GetCephRbdSnapshots_ResultSet1>(
        '/GetCephRbdSnapshots',
        params
      );
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<GetCephRbdSnapshots_ResultSet1>(1),
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
    listClones: async (params: GetCephRbdClonesParams): Promise<GetCephRbdClones_ResultSet1[]> => {
      const response = await client.post<GetCephRbdClones_ResultSet1>('/GetCephRbdClones', params);
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<GetCephRbdClones_ResultSet1>(1),
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
