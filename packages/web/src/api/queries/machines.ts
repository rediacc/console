import { createResourceQuery } from '@/hooks/api/queryFactory';
import {
  createResourceMutation,
  createVaultUpdateMutation,
  createMutation,
} from '@/hooks/api/mutationFactory';
import { QUERY_KEY_STRINGS } from '@/api/queryKeys';
import type { Machine } from '@/types';
import { api } from '@/api/client';

// Get machines for a team, multiple teams, or all machines
export const useMachines = createResourceQuery<Machine>({
  queryKey: QUERY_KEY_STRINGS.machines,
  fetcher: (teamFilter) => api.machines.list(teamFilter),
  operationName: 'machines.list',
});

// Create machine
export const useCreateMachine = createMutation<{
  teamName: string;
  bridgeName: string;
  machineName: string;
  machineVault?: string;
}>({
  request: ({ teamName, bridgeName, machineName, machineVault }) =>
    api.machines.create(teamName, machineName, bridgeName, machineVault),
  invalidateKeys: [
    QUERY_KEY_STRINGS.machines,
    QUERY_KEY_STRINGS.teams,
    QUERY_KEY_STRINGS.bridges,
    QUERY_KEY_STRINGS.dropdown,
  ],
  successMessage: (vars) => `Machine "${vars.machineName}" created successfully`,
  errorMessage: 'Failed to create machine',
  transformData: ({ teamName, bridgeName, machineName, machineVault }) => ({
    teamName,
    bridgeName,
    machineName,
    machineVault: machineVault || '{}',
  }),
  operationName: 'machines.create',
});

// Update machine name
export const useUpdateMachineName = createMutation<{
  teamName: string;
  currentMachineName: string;
  newMachineName: string;
}>({
  request: ({ teamName, currentMachineName, newMachineName }) =>
    api.machines.rename(teamName, currentMachineName, newMachineName),
  invalidateKeys: [QUERY_KEY_STRINGS.machines, QUERY_KEY_STRINGS.dropdown],
  successMessage: (vars) => `Machine renamed to "${vars.newMachineName}"`,
  errorMessage: 'Failed to update machine name',
  operationName: 'machines.rename',
});

// Update machine bridge assignment
export const useUpdateMachineBridge = createMutation<{
  teamName: string;
  machineName: string;
  newBridgeName: string;
}>({
  request: ({ teamName, machineName, newBridgeName }) =>
    api.machines.assignBridge(teamName, machineName, newBridgeName),
  invalidateKeys: [QUERY_KEY_STRINGS.machines, QUERY_KEY_STRINGS.bridges],
  successMessage: (vars) =>
    `Machine "${vars.machineName}" reassigned to bridge "${vars.newBridgeName}"`,
  errorMessage: 'Failed to update machine bridge',
  operationName: 'machines.assignBridge',
});

// Update machine vault
export const useUpdateMachineVault = createVaultUpdateMutation<{
  teamName: string;
  machineName: string;
  machineVault: string;
  vaultVersion: number;
}>(
  'Machine',
  (data) =>
    api.machines.updateVault(data.teamName, data.machineName, data.machineVault, data.vaultVersion),
  'machineName',
  'machineVault'
);

// Delete machine
export const useDeleteMachine = createResourceMutation<{
  teamName: string;
  machineName: string;
}>(
  'Machine',
  'delete',
  (variables) => api.machines.delete(variables.teamName, variables.machineName),
  'machineName',
  [QUERY_KEY_STRINGS.teams, QUERY_KEY_STRINGS.bridges]
);
