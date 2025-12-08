import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import {
  createMutation,
  createResourceMutation,
  createVaultUpdateMutation,
} from '@/hooks/api/mutationFactory';
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
      return api.storage.list({ teamName: targetTeam });
    },
    enabled: !!teamFilter && (!Array.isArray(teamFilter) || teamFilter.length > 0),
    staleTime: 30 * 1000, // 30 seconds
  });
};

// Create storage
export const useCreateStorage = createMutation<WithOptionalVault<CreateStorageParams>>({
  request: (params) => api.storage.create(params),
  invalidateKeys: ['storage', 'teams'],
  successMessage: (vars) => `Storage "${vars.storageName}" created successfully`,
  errorMessage: 'Failed to create storage',
  transformData: (data) => ({
    ...data,
    vaultContent: data.vaultContent || '{}',
  }),
  operationName: 'storage.create',
});

// Update storage name
export const useUpdateStorageName = createMutation<UpdateStorageNameParams>({
  request: (params) => api.storage.rename(params),
  invalidateKeys: ['storage'],
  successMessage: (vars) => `Storage renamed to "${vars.newStorageName}"`,
  errorMessage: 'Failed to update storage name',
  operationName: 'storage.rename',
});

// Update storage vault
export const useUpdateStorageVault = createVaultUpdateMutation<
  UpdateStorageVaultParams & Record<string, unknown>
>('Storage', (params) => api.storage.updateVault(params), 'storageName', 'vaultContent');

// Delete storage
export const useDeleteStorage = createResourceMutation<
  DeleteStorageParams & Record<string, unknown>
>('Storage', 'delete', (params) => api.storage.delete(params), 'storageName', ['teams']);

export type { GetTeamStorages_ResultSet1 };
