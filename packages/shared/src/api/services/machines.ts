import { parseResponse, responseExtractors } from '../parseResponse';
import type { ApiClient } from './types';
import type {
  Machine,
  CreateMachineParams,
  UpdateMachineNameParams,
  DeleteMachineParams,
  UpdateMachineVaultParams,
  UpdateMachineAssignedBridgeParams,
  UpdateMachineClusterAssignmentParams,
  UpdateMachineClusterRemovalParams,
  UpdateCloneMachineAssignmentsParams,
  UpdateCloneMachineRemovalsParams,
  UpdateMachineCephParams,
  UpdateImageMachineAssignmentParams,
  GetCloneMachinesParams,
  GetMachineAssignmentStatusParams,
  GetCloneMachineAssignmentValidationParams,
  GetAvailableMachinesForCloneParams,
  WithOptionalVault,
} from '../../types';

function normalizeTeamName(teamName?: string | string[]) {
  if (!teamName) return undefined;
  return Array.isArray(teamName) ? teamName.join(',') : teamName;
}

export function createMachinesService(client: ApiClient) {
  return {
    list: async (teamName?: string | string[]): Promise<Machine[]> => {
      const response = await client.get<Machine>(
        '/GetTeamMachines',
        teamName ? { teamName: normalizeTeamName(teamName) } : undefined
      );

      return parseResponse(response, {
        extractor: responseExtractors.primaryOrSecondary,
        filter: (machine) => Boolean(machine.machineName),
      });
    },

    getAssignmentStatus: (params: GetMachineAssignmentStatusParams) =>
      client.get('/GetMachineAssignmentStatus', params),

    create: (params: WithOptionalVault<CreateMachineParams>) =>
      client.post('/CreateMachine', {
        ...params,
        vaultContent: params.vaultContent ?? '{}',
      }),

    rename: (params: UpdateMachineNameParams) => client.post('/UpdateMachineName', params),

    delete: (params: DeleteMachineParams) => client.post('/DeleteMachine', params),

    updateVault: (params: UpdateMachineVaultParams) => client.post('/UpdateMachineVault', params),

    assignBridge: (params: UpdateMachineAssignedBridgeParams) =>
      client.post('/UpdateMachineAssignedBridge', params),

    updateClusterAssignment: (params: UpdateMachineClusterAssignmentParams) =>
      client.post('/UpdateMachineClusterAssignment', params),

    removeFromCluster: (params: UpdateMachineClusterRemovalParams) =>
      client.post('/UpdateMachineClusterRemoval', params),

    updateCloneAssignments: (params: UpdateCloneMachineAssignmentsParams) =>
      client.post('/UpdateCloneMachineAssignments', params),

    removeCloneAssignments: (params: UpdateCloneMachineRemovalsParams) =>
      client.post('/UpdateCloneMachineRemovals', params),

    updateCeph: (params: UpdateMachineCephParams) => client.post('/UpdateMachineCeph', params),

    updateImageAssignment: (params: UpdateImageMachineAssignmentParams) =>
      client.post('/UpdateImageMachineAssignment', params),

    getCloneMachines: (params: GetCloneMachinesParams) => client.get('/GetCloneMachines', params),

    getCloneAssignmentValidation: (params: GetCloneMachineAssignmentValidationParams) =>
      client.get('/GetCloneMachineAssignmentValidation', params),

    getAvailableMachinesForClone: (params: GetAvailableMachinesForCloneParams) =>
      client.get('/GetAvailableMachinesForClone', params),
  };
}
