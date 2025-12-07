import { api } from '@/api/client';
import { QUERY_KEY_STRINGS } from '@/api/queryKeys';
import {
  createResourceMutation,
  createVaultUpdateMutation,
  createMutation,
} from '@/hooks/api/mutationFactory';
import { createResourceQuery } from '@/hooks/api/queryFactory';
import type { Machine } from '@/types';
import type {
  CreateMachineParams,
  UpdateMachineNameParams,
  UpdateMachineAssignedBridgeParams,
  UpdateMachineVaultParams,
  DeleteMachineParams,
  WithOptionalVault,
} from '@rediacc/shared/types';

// Get machines for a team, multiple teams, or all machines
export const useMachines = createResourceQuery<Machine>({
  queryKey: QUERY_KEY_STRINGS.machines,
  fetcher: (teamFilter) => api.machines.list(teamFilter),
  operationName: 'machines.list',
});

// Create machine
export const useCreateMachine = createMutation<WithOptionalVault<CreateMachineParams>>({
  request: (params) => api.machines.create(params),
  invalidateKeys: [
    QUERY_KEY_STRINGS.machines,
    QUERY_KEY_STRINGS.teams,
    QUERY_KEY_STRINGS.bridges,
    QUERY_KEY_STRINGS.dropdown,
  ],
  successMessage: (vars) => `Machine "${vars.machineName}" created successfully`,
  errorMessage: 'Failed to create machine',
  transformData: ({ teamName, bridgeName, machineName, vaultContent }) => ({
    teamName,
    bridgeName,
    machineName,
    vaultContent: vaultContent || '{}',
  }),
  operationName: 'machines.create',
});

// Update machine name
export const useUpdateMachineName = createMutation<UpdateMachineNameParams>({
  request: (params) => api.machines.rename(params),
  invalidateKeys: [QUERY_KEY_STRINGS.machines, QUERY_KEY_STRINGS.dropdown],
  successMessage: (vars) => `Machine renamed to "${vars.newMachineName}"`,
  errorMessage: 'Failed to update machine name',
  operationName: 'machines.rename',
});

// Update machine bridge assignment
export const useUpdateMachineBridge = createMutation<UpdateMachineAssignedBridgeParams>({
  request: (params) => api.machines.assignBridge(params),
  invalidateKeys: [QUERY_KEY_STRINGS.machines, QUERY_KEY_STRINGS.bridges],
  successMessage: (vars) =>
    `Machine "${vars.machineName}" reassigned to bridge "${vars.newBridgeName}"`,
  errorMessage: 'Failed to update machine bridge',
  operationName: 'machines.assignBridge',
});

// Update machine vault
export const useUpdateMachineVault = createVaultUpdateMutation<
  UpdateMachineVaultParams & Record<string, unknown>
>(
  'Machine',
  (data) => api.machines.updateVault(data),
  'machineName',
  'vaultContent'
);

// Delete machine
export const useDeleteMachine = createResourceMutation<
  DeleteMachineParams & Record<string, unknown>
>(
  'Machine',
  'delete',
  (variables) => api.machines.delete(variables),
  'machineName',
  [QUERY_KEY_STRINGS.teams, QUERY_KEY_STRINGS.bridges]
);
