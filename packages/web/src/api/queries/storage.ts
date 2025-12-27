import { useQuery, useQueryClient } from '@tanstack/react-query';
import { typedApi } from '@/api/client';
import { useMutationWithFeedback } from '@/hooks/useMutationWithFeedback';
import { minifyJSON } from '@/platform/utils/json';
import { parseGetTeamStorages } from '@rediacc/shared/api';
import type {
  CreateStorageParams,
  DeleteStorageParams,
  GetTeamStorages_ResultSet1,
  UpdateStorageNameParams,
  UpdateStorageVaultParams,
  WithOptionalVault,
} from '@rediacc/shared/types';

// Get storage for a team or multiple teams
export const useStorage = (teamFilter?: string | string[]) => {
  return useQuery<GetTeamStorages_ResultSet1[]>({
    queryKey: ['storage', teamFilter],
    queryFn: async () => {
      if (!teamFilter || (Array.isArray(teamFilter) && teamFilter.length === 0)) return [];

      const targetTeam = Array.isArray(teamFilter) ? teamFilter.join(',') : teamFilter;
      const response = await typedApi.GetTeamStorages({ teamName: targetTeam });
      return parseGetTeamStorages(response as never);
    },
    enabled: !!teamFilter && (!Array.isArray(teamFilter) || teamFilter.length > 0),
    staleTime: 30 * 1000, // 30 seconds
  });
};

// Create storage
export const useCreateStorage = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, WithOptionalVault<CreateStorageParams>>({
    mutationFn: (params) => typedApi.CreateStorage({ ...params, vaultContent: params.vaultContent ?? '{}' }),
    successMessage: (_, vars) => `Storage "${vars.storageName}" created successfully`,
    errorMessage: 'Failed to create storage',
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['storage'] });
      void queryClient.invalidateQueries({ queryKey: ['teams'] });
    },
  });
};

// Update storage name
export const useUpdateStorageName = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, UpdateStorageNameParams>({
    mutationFn: (params) => typedApi.UpdateStorageName(params),
    successMessage: (_, vars) => `Storage renamed to "${vars.newStorageName}"`,
    errorMessage: 'Failed to update storage name',
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['storage'] });
    },
  });
};

// Update storage vault
export const useUpdateStorageVault = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<
    unknown,
    Error,
    UpdateStorageVaultParams & Record<string, unknown>
  >({
    mutationFn: (params) =>
      typedApi.UpdateStorageVault({
        ...params,
        vaultContent: minifyJSON(params.vaultContent),
      }),
    successMessage: (_, vars) => `Storage "${vars.storageName}" vault updated successfully`,
    errorMessage: 'Failed to update storage vault',
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['storage'] });
    },
  });
};

// Delete storage
export const useDeleteStorage = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, DeleteStorageParams & Record<string, unknown>>({
    mutationFn: (params) => typedApi.DeleteStorage(params),
    successMessage: (_, vars) => `Storage "${vars.storageName}" deleted successfully`,
    errorMessage: 'Failed to delete storage',
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['storage'] });
      void queryClient.invalidateQueries({ queryKey: ['teams'] });
    },
  });
};

export type { GetTeamStorages_ResultSet1 } from '@rediacc/shared/types';
