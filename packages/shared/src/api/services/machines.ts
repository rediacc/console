import { endpoints } from '../../endpoints';
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
        endpoints.machines.getTeamMachines,
        teamName ? { teamName: normalizeTeamName(teamName) } : undefined
      );

      return parseResponse(response, {
        extractor: responseExtractors.primaryOrSecondary,
        filter: (machine) => Boolean(machine.machineName),
      });
    },

    getAssignmentStatus: (params: GetMachineAssignmentStatusParams) =>
      client.get(endpoints.machines.getMachineAssignmentStatus, params),

    create: (params: WithOptionalVault<CreateMachineParams>) =>
      client.post(endpoints.machines.createMachine, {
        ...params,
        vaultContent: params.vaultContent ?? '{}',
      }),

    rename: (params: UpdateMachineNameParams) =>
      client.post(endpoints.machines.updateMachineName, params),

    delete: (params: DeleteMachineParams) =>
      client.post(endpoints.machines.deleteMachine, params),

    updateVault: (params: UpdateMachineVaultParams) =>
      client.post(endpoints.machines.updateMachineVault, params),

    assignBridge: (params: UpdateMachineAssignedBridgeParams) =>
      client.post(endpoints.machines.updateMachineAssignedBridge, params),

    updateClusterAssignment: (params: UpdateMachineClusterAssignmentParams) =>
      client.post(endpoints.machines.updateMachineClusterAssignment, params),

    removeFromCluster: (params: UpdateMachineClusterRemovalParams) =>
      client.post(endpoints.machines.updateMachineClusterRemoval, params),

    updateCloneAssignment: (teamName: string, machineName: string, cloneName: string) =>
      client.post(endpoints.machines.updateMachineCloneAssignment, {
        teamName,
        machineName,
        cloneName,
      }),

    updateCloneAssignments: (params: UpdateCloneMachineAssignmentsParams) =>
      client.post(endpoints.machines.updateCloneMachineAssignments, params),

    removeCloneAssignments: (params: UpdateCloneMachineRemovalsParams) =>
      client.post(endpoints.machines.updateCloneMachineRemovals, params),

    updateCeph: (params: UpdateMachineCephParams) =>
      client.post(endpoints.machines.updateMachineCeph, params),

    updateImageAssignment: (params: UpdateImageMachineAssignmentParams) =>
      client.post(endpoints.machines.updateImageMachineAssignment, params),

    getCloneMachines: (params: GetCloneMachinesParams) =>
      client.get(endpoints.machines.getCloneMachines, params),

    getCloneAssignmentValidation: (params: GetCloneMachineAssignmentValidationParams) =>
      client.get(endpoints.machines.getCloneMachineAssignmentValidation, params),

    getAvailableMachinesForClone: (params: GetAvailableMachinesForCloneParams) =>
      client.get(endpoints.machines.getAvailableMachinesForClone, params),
  };
}
