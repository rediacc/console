import { useQuery } from '@tanstack/react-query';
import {
  createResourceMutation,
  createVaultUpdateMutation,
  createMutation,
} from '@/hooks/api/mutationFactory';
import { api } from '@/api/client';
import type { Region, Bridge } from '@rediacc/shared/types';

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
      return api.regions.getBridges(regionName);
    },
    enabled: !!regionName,
  });
};

export type { Region };

// Create region
export const useCreateRegion = createResourceMutation<{ regionName: string; regionVault?: string }>(
  'Region',
  'create',
  (variables) => api.regions.create(variables.regionName),
  'regionName'
);

// Update region name
export const useUpdateRegionName = createMutation<{
  currentRegionName: string;
  newRegionName: string;
}>({
  request: ({ currentRegionName, newRegionName }) =>
    api.regions.rename(currentRegionName, newRegionName),
  invalidateKeys: ['regions', 'dropdown-data'],
  successMessage: (variables) => `Region renamed to "${variables.newRegionName}"`,
  errorMessage: 'Failed to update region name',
  operationName: 'regions.rename',
});

// Update region vault
export const useUpdateRegionVault = createVaultUpdateMutation<{
  regionName: string;
  regionVault: string;
  vaultVersion: number;
}>(
  'Region',
  (data) => api.regions.updateVault(data.regionName, data.regionVault, data.vaultVersion),
  'regionName',
  'regionVault'
);

// Delete region
export const useDeleteRegion = createMutation<string>({
  request: (regionName) => api.regions.delete(regionName),
  invalidateKeys: ['regions', 'dropdown-data'],
  successMessage: (regionName) => `Region "${regionName}" deleted successfully`,
  errorMessage: 'Failed to delete region',
  operationName: 'regions.delete',
});
