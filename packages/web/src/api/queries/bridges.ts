import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import {
  createMutation,
  createResourceMutation,
  createVaultUpdateMutation,
} from '@/hooks/api/mutationFactory';
import type {
  CreateBridgeParams,
  DeleteBridgeParams,
  GetRegionBridges_ResultSet1,
  ResetBridgeAuthorizationParams,
  UpdateBridgeNameParams,
  UpdateBridgeVaultParams,
  WithOptionalVault,
} from '@rediacc/shared/types';

// Get bridges for a region
export const useBridges = (regionName?: string) => {
  return useQuery<GetRegionBridges_ResultSet1[]>({
    queryKey: ['bridges', regionName],
    queryFn: async () => {
      if (!regionName) return [];
      return api.bridges.list({ regionName });
    },
    enabled: !!regionName,
    staleTime: 30 * 1000, // 30 seconds
  });
};

// Create bridge
export const useCreateBridge = createMutation<WithOptionalVault<CreateBridgeParams>>({
  request: (params) => api.bridges.create(params),
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
export const useUpdateBridgeName = createMutation<UpdateBridgeNameParams>({
  request: (params) => api.bridges.rename(params),
  invalidateKeys: ['bridges', 'dropdown-data'],
  successMessage: (vars) => `Bridge renamed to "${vars.newBridgeName}"`,
  errorMessage: 'Failed to update bridge name',
  operationName: 'bridges.rename',
});

// Update bridge vault
export const useUpdateBridgeVault = createVaultUpdateMutation<
  UpdateBridgeVaultParams & Record<string, unknown>
>('Bridge', (params) => api.bridges.updateVault(params), 'bridgeName', 'vaultContent');

// Delete bridge
export const useDeleteBridge = createResourceMutation<DeleteBridgeParams & Record<string, unknown>>(
  'Bridge',
  'delete',
  (params) => api.bridges.delete(params),
  'bridgeName',
  ['regions']
);

// Reset bridge authorization
export const useResetBridgeAuthorization = createMutation<ResetBridgeAuthorizationParams>({
  request: (params) => api.bridges.resetAuthorization(params),
  invalidateKeys: ['bridges'],
  successMessage: (vars) => `Bridge authorization reset for "${vars.bridgeName}"`,
  errorMessage: 'Failed to reset bridge authorization',
  operationName: 'bridges.resetAuthorization',
});

export type { GetRegionBridges_ResultSet1, GetRegionBridges_ResultSet1 as Bridge };
