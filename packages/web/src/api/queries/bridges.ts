import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import {
  createResourceMutation,
  createVaultUpdateMutation,
  createMutation,
} from '@/hooks/api/mutationFactory';
import type { Bridge } from '@rediacc/shared/types';

// Get bridges for a region
export const useBridges = (regionName?: string) => {
  return useQuery<Bridge[]>({
    queryKey: ['bridges', regionName],
    queryFn: async () => {
      if (!regionName) return [];
      return api.bridges.list(regionName);
    },
    enabled: !!regionName,
    staleTime: 30 * 1000, // 30 seconds
  });
};

// Create bridge
export const useCreateBridge = createMutation<{
  regionName: string;
  bridgeName: string;
  vaultContent?: string;
}>({
  request: ({ regionName, bridgeName, vaultContent }) =>
    api.bridges.create(regionName, bridgeName, vaultContent),
  invalidateKeys: ['bridges', 'regions', 'dropdown-data'],
  successMessage: (vars) => `Bridge "${vars.bridgeName}" created successfully`,
  errorMessage: 'Failed to create bridge',
  transformData: (data) => ({
    ...data,
    vaultContent: data.vaultContent || '{}',
  }),
  operationName: 'bridges.create',
});

// Update bridge name
export const useUpdateBridgeName = createMutation<{
  regionName: string;
  currentBridgeName: string;
  newBridgeName: string;
}>({
  request: ({ regionName, currentBridgeName, newBridgeName }) =>
    api.bridges.rename(regionName, currentBridgeName, newBridgeName),
  invalidateKeys: ['bridges', 'dropdown-data'],
  successMessage: (vars) => `Bridge renamed to "${vars.newBridgeName}"`,
  errorMessage: 'Failed to update bridge name',
  operationName: 'bridges.rename',
});

// Update bridge vault
export const useUpdateBridgeVault = createVaultUpdateMutation<{
  regionName: string;
  bridgeName: string;
  vaultContent: string;
  vaultVersion: number;
}>(
  'Bridge',
  (data) =>
    api.bridges.updateVault(data.regionName, data.bridgeName, data.vaultContent, data.vaultVersion),
  'bridgeName',
  'vaultContent'
);

// Delete bridge
export const useDeleteBridge = createResourceMutation<{
  regionName: string;
  bridgeName: string;
}>(
  'Bridge',
  'delete',
  (variables) => api.bridges.delete(variables.regionName, variables.bridgeName),
  'bridgeName',
  ['regions']
);

// Reset bridge authorization
export const useResetBridgeAuthorization = createMutation<{
  regionName: string;
  bridgeName: string;
  isCloudManaged?: boolean;
}>({
  request: ({ regionName, bridgeName }) => api.bridges.resetAuthorization(regionName, bridgeName),
  invalidateKeys: ['bridges'],
  successMessage: (vars) => `Bridge authorization reset for "${vars.bridgeName}"`,
  errorMessage: 'Failed to reset bridge authorization',
  operationName: 'bridges.resetAuthorization',
});

export type { Bridge };
