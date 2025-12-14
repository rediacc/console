import { useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import { QUERY_KEY_STRINGS } from '@/api/queryKeys';
import { createResourceQuery } from '@/hooks/api/queryFactory';
import { useMutationWithFeedback } from '@/hooks/useMutationWithFeedback';
import type { Machine } from '@/types';
import { minifyJSON } from '@/utils/json';
import type {
  CreateMachineParams,
  DeleteMachineParams,
  UpdateMachineAssignedBridgeParams,
  UpdateMachineNameParams,
  UpdateMachineVaultParams,
  WithOptionalVault,
} from '@rediacc/shared/types';

// Get machines for a team, multiple teams, or all machines
export const useMachines = createResourceQuery<Machine>({
  queryKey: QUERY_KEY_STRINGS.machines,
  fetcher: (teamFilter) => api.machines.list(teamFilter),
  operationName: 'machines.list',
});

// Create machine
export const useCreateMachine = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, WithOptionalVault<CreateMachineParams>>({
    mutationFn: ({ teamName, bridgeName, machineName, vaultContent }) =>
      api.machines.create({
        teamName,
        bridgeName,
        machineName,
        vaultContent: vaultContent || '{}',
      }),
    successMessage: (_, vars) => `Machine "${vars.machineName}" created successfully`,
    errorMessage: 'Failed to create machine',
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.machines] });
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.teams] });
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.bridges] });
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.dropdown] });
    },
  });
};

// Update machine name
export const useUpdateMachineName = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, UpdateMachineNameParams>({
    mutationFn: (params) => api.machines.rename(params),
    successMessage: (_, vars) => `Machine renamed to "${vars.newMachineName}"`,
    errorMessage: 'Failed to update machine name',
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.machines] });
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.dropdown] });
    },
  });
};

// Update machine bridge assignment
export const useUpdateMachineBridge = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, UpdateMachineAssignedBridgeParams>({
    mutationFn: (params) => api.machines.assignBridge(params),
    successMessage: (_, vars) =>
      `Machine "${vars.machineName}" reassigned to bridge "${vars.newBridgeName}"`,
    errorMessage: 'Failed to update machine bridge',
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.machines] });
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.bridges] });
    },
  });
};

// Update machine vault
export const useUpdateMachineVault = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<
    unknown,
    Error,
    UpdateMachineVaultParams & Record<string, unknown>
  >({
    mutationFn: (params) =>
      api.machines.updateVault({
        ...params,
        vaultContent: minifyJSON(params.vaultContent),
      }),
    successMessage: (_, vars) => `Machine "${vars.machineName}" vault updated successfully`,
    errorMessage: 'Failed to update machine vault',
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.machines] });
    },
  });
};

// Delete machine
export const useDeleteMachine = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, DeleteMachineParams & Record<string, unknown>>({
    mutationFn: (params) => api.machines.delete(params),
    successMessage: (_, vars) => `Machine "${vars.machineName}" deleted successfully`,
    errorMessage: 'Failed to delete machine',
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.machines] });
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.teams] });
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.bridges] });
    },
  });
};
