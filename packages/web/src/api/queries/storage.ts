import { useQuery } from '@tanstack/react-query';
import {
  createResourceMutation,
  createVaultUpdateMutation,
  createMutation,
} from '@/hooks/api/mutationFactory';
import { api } from '@/api/client';
import type { Storage } from '@rediacc/shared/types';

// Get storage for a team or multiple teams
export const useStorage = (teamFilter?: string | string[]) => {
  return useQuery<Storage[]>({
    queryKey: ['storage', teamFilter],
    queryFn: async () => {
      if (!teamFilter || (Array.isArray(teamFilter) && teamFilter.length === 0)) return [];

      const targetTeam = Array.isArray(teamFilter) ? teamFilter.join(',') : teamFilter;
      return api.storage.list(targetTeam);
    },
    enabled: !!teamFilter && (!Array.isArray(teamFilter) || teamFilter.length > 0),
    staleTime: 30 * 1000, // 30 seconds
  });
};

// Create storage
export const useCreateStorage = createMutation<{
  teamName: string;
  storageName: string;
  vaultContent?: string;
}>({
  request: ({ teamName, storageName, vaultContent }) =>
    api.storage.create(teamName, storageName, vaultContent),
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
export const useUpdateStorageName = createMutation<{
  teamName: string;
  currentStorageName: string;
  newStorageName: string;
}>({
  request: ({ teamName, currentStorageName, newStorageName }) =>
    api.storage.rename(teamName, currentStorageName, newStorageName),
  invalidateKeys: ['storage'],
  successMessage: (vars) => `Storage renamed to "${vars.newStorageName}"`,
  errorMessage: 'Failed to update storage name',
  operationName: 'storage.rename',
});

// Update storage vault
export const useUpdateStorageVault = createVaultUpdateMutation<{
  teamName: string;
  storageName: string;
  vaultContent: string;
  vaultVersion: number;
}>(
  'Storage',
  (data) =>
    api.storage.updateVault(data.teamName, data.storageName, data.vaultContent, data.vaultVersion),
  'storageName',
  'vaultContent'
);

// Delete storage
export const useDeleteStorage = createResourceMutation<{
  teamName: string;
  storageName: string;
}>(
  'Storage',
  'delete',
  (variables) => api.storage.delete(variables.teamName, variables.storageName),
  'storageName',
  ['teams']
);

export type { Storage };
