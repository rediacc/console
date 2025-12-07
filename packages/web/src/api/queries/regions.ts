import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import {
  createResourceMutation,
  createVaultUpdateMutation,
  createMutation,
} from '@/hooks/api/mutationFactory';
import type {
  Region,
  Bridge,
  CreateRegionParams,
  UpdateRegionNameParams,
  UpdateRegionVaultParams,
  DeleteRegionParams,
  WithOptionalVault,
} from '@rediacc/shared/types';

// Get all regions
export const useRegions = (enabled: boolean = true) => {
  return useQuery<Region[]>({
    queryKey: ['regions'],
    queryFn: async () => {
      return api.regions.list();
    },
    enabled,
    staleTime: 30 * 1000, // 30 seconds
  });
};

// Get bridges for a region
export const useRegionBridges = (regionName: string) => {
  return useQuery<Bridge[]>({
    queryKey: ['region-bridges', regionName],
    queryFn: async () => {
      return api.regions.getBridges({ regionName });
    },
    enabled: !!regionName,
  });
};

export type { Region };

// Create region
export const useCreateRegion = createResourceMutation<WithOptionalVault<CreateRegionParams>>(
  'Region',
  'create',
  (params) => api.regions.create(params),
  'regionName'
);

// Update region name
export const useUpdateRegionName = createMutation<UpdateRegionNameParams>({
  request: (params) => api.regions.rename(params),
  invalidateKeys: ['regions', 'dropdown-data'],
  successMessage: (variables) => `Region renamed to "${variables.newRegionName}"`,
  errorMessage: 'Failed to update region name',
  operationName: 'regions.rename',
});

// Update region vault
export const useUpdateRegionVault = createVaultUpdateMutation<
  UpdateRegionVaultParams & Record<string, unknown>
>(
  'Region',
  (params) => api.regions.updateVault(params),
  'regionName',
  'vaultContent'
);

// Delete region
export const useDeleteRegion = createMutation<DeleteRegionParams>({
  request: (params) => api.regions.delete(params),
  invalidateKeys: ['regions', 'dropdown-data'],
  successMessage: (params) => `Region "${params.regionName}" deleted successfully`,
  errorMessage: 'Failed to delete region',
  operationName: 'regions.delete',
});
