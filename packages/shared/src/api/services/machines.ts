import { endpoints } from '../../endpoints';
import { parseResponse, responseExtractors } from '../parseResponse';
import type { ApiClient } from './types';
import type { Machine } from '../../types';

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

    getAssignmentStatus: (machineName: string, teamName: string) =>
      client.get(endpoints.machines.getMachineAssignmentStatus, { machineName, teamName }),

    create: (teamName: string, machineName: string, bridgeName: string, vaultContent?: string) =>
      client.post(endpoints.machines.createMachine, {
        teamName,
        machineName,
        bridgeName,
        vaultContent: vaultContent ?? '{}',
      }),

    rename: (teamName: string, currentName: string, newName: string) =>
      client.post(endpoints.machines.updateMachineName, {
        teamName,
        currentMachineName: currentName,
        newMachineName: newName,
      }),

    delete: (teamName: string, machineName: string) =>
      client.post(endpoints.machines.deleteMachine, { teamName, machineName }),

    updateVault: (teamName: string, machineName: string, vault: string, vaultVersion: number) =>
      client.post(endpoints.machines.updateMachineVault, {
        teamName,
        machineName,
        vaultContent: vault,
        vaultVersion,
      }),

    assignBridge: (teamName: string, machineName: string, bridgeName: string) =>
      client.post(endpoints.machines.updateMachineAssignedBridge, {
        teamName,
        machineName,
        bridgeName,
      }),

    updateClusterAssignment: (teamName: string, machineName: string, clusterName: string | null) =>
      client.post(endpoints.machines.updateMachineClusterAssignment, {
        teamName,
        machineName,
        clusterName,
      }),

    removeFromCluster: (teamName: string, machineName: string) =>
      client.post(endpoints.machines.updateMachineClusterRemoval, {
        teamName,
        machineName,
      }),

    updateCloneAssignment: (teamName: string, machineName: string, cloneName: string) =>
      client.post(endpoints.machines.updateMachineCloneAssignment, {
        teamName,
        machineName,
        cloneName,
      }),

    updateCloneAssignments: (
      cloneName: string,
      snapshotName: string,
      imageName: string,
      poolName: string,
      teamName: string,
      machineNames: string
    ) =>
      client.post(endpoints.machines.updateCloneMachineAssignments, {
        cloneName,
        snapshotName,
        imageName,
        poolName,
        teamName,
        machineNames,
      }),

    removeCloneAssignments: (
      cloneName: string,
      snapshotName: string,
      imageName: string,
      poolName: string,
      teamName: string,
      machineNames: string
    ) =>
      client.post(endpoints.machines.updateCloneMachineRemovals, {
        cloneName,
        snapshotName,
        imageName,
        poolName,
        teamName,
        machineNames,
      }),

    updateCeph: (teamName: string, machineName: string, clusterName: string | null) =>
      client.post(endpoints.machines.updateMachineCeph, {
        teamName,
        machineName,
        clusterName,
      }),

    updateImageAssignment: (
      teamName: string,
      poolName: string,
      imageName: string,
      newMachineName: string
    ) =>
      client.post(endpoints.machines.updateImageMachineAssignment, {
        teamName,
        poolName,
        imageName,
        newMachineName,
      }),

    getCloneMachines: (
      cloneName: string,
      snapshotName: string,
      imageName: string,
      poolName: string,
      teamName: string
    ) =>
      client.get(endpoints.machines.getCloneMachines, {
        cloneName,
        snapshotName,
        imageName,
        poolName,
        teamName,
      }),

    getCloneAssignmentValidation: (teamName: string, machineNames: string) =>
      client.get(endpoints.machines.getCloneMachineAssignmentValidation, {
        teamName,
        machineNames,
      }),

    getAvailableMachinesForClone: (teamName: string) =>
      client.get(endpoints.machines.getAvailableMachinesForClone, { teamName }),
  };
}
