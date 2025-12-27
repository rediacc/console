import { useQueryClient } from '@tanstack/react-query';
import { typedApi } from '@/api/client';
import { QUERY_KEY_STRINGS } from '@/api/queryKeys';
import { createResourceQuery } from '@/hooks/api/queryFactory';
import { useMutationWithFeedback } from '@/hooks/useMutationWithFeedback';
import { minifyJSON } from '@/platform/utils/json';
import type { Machine } from '@/types';
import { parseGetTeamMachines } from '@rediacc/shared/api';
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
  fetcher: async (teamFilter) => {
    const teamName = teamFilter
      ? Array.isArray(teamFilter)
        ? teamFilter.join(',')
        : teamFilter
      : undefined;
    const response = await typedApi.GetTeamMachines(teamName ? { teamName } : {});
    return parseGetTeamMachines(response as never);
  },
  operationName: 'machines.list',
});

// Create machine
export const useCreateMachine = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, WithOptionalVault<CreateMachineParams>>({
    mutationFn: (params) => typedApi.CreateMachine({ ...params, vaultContent: params.vaultContent ?? '{}' }),
    successMessage: (_, vars) => `Machine "${vars.machineName}" created successfully`,
    errorMessage: 'Failed to create machine',
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.machines] });
      void queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.teams] });
      void queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.bridges] });
      void queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.dropdown] });
    },
  });
};

// Update machine name
export const useUpdateMachineName = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, UpdateMachineNameParams>({
    mutationFn: (params) => typedApi.UpdateMachineName(params),
    successMessage: (_, vars) => `Machine renamed to "${vars.newMachineName}"`,
    errorMessage: 'Failed to update machine name',
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.machines] });
      void queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.dropdown] });
    },
  });
};

// Update machine bridge assignment
export const useUpdateMachineBridge = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, UpdateMachineAssignedBridgeParams>({
    mutationFn: (params) => typedApi.UpdateMachineAssignedBridge(params),
    successMessage: (_, vars) =>
      `Machine "${vars.machineName}" reassigned to bridge "${vars.newBridgeName}"`,
    errorMessage: 'Failed to update machine bridge',
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.machines] });
      void queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.bridges] });
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
      typedApi.UpdateMachineVault({
        ...params,
        vaultContent: minifyJSON(params.vaultContent),
      }),
    successMessage: (_, vars) => `Machine "${vars.machineName}" vault updated successfully`,
    errorMessage: 'Failed to update machine vault',
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.machines] });
    },
  });
};

// Delete machine
export const useDeleteMachine = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, DeleteMachineParams & Record<string, unknown>>({
    mutationFn: (params) => typedApi.DeleteMachine(params),
    successMessage: (_, vars) => `Machine "${vars.machineName}" deleted successfully`,
    errorMessage: 'Failed to delete machine',
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.machines] });
      void queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.teams] });
      void queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.bridges] });
    },
  });
};
