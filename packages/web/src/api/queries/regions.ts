import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import { useMutationWithFeedback } from '@/hooks/useMutationWithFeedback';
import { minifyJSON } from '@/utils/json';
import type {
  CreateRegionParams,
  DeleteRegionParams,
  GetCompanyRegions_ResultSet1,
  GetRegionBridges_ResultSet1,
  UpdateRegionNameParams,
  UpdateRegionVaultParams,
  WithOptionalVault,
} from '@rediacc/shared/types';

// Get all regions
export const useRegions = (enabled: boolean = true) => {
  return useQuery<GetCompanyRegions_ResultSet1[]>({
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
  return useQuery<GetRegionBridges_ResultSet1[]>({
    queryKey: ['region-bridges', regionName],
    queryFn: async () => {
      return api.regions.getBridges({ regionName });
    },
    enabled: !!regionName,
  });
};

export type { GetCompanyRegions_ResultSet1, GetCompanyRegions_ResultSet1 as Region };

// Create region
export const useCreateRegion = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, WithOptionalVault<CreateRegionParams>>({
    mutationFn: (params) =>
      api.regions.create({
        ...params,
        vaultContent: params.vaultContent || '{}',
      }),
    successMessage: (_, vars) => `Region "${vars.regionName}" created successfully`,
    errorMessage: 'Failed to create region',
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['regions'] });
    },
  });
};

// Update region name
export const useUpdateRegionName = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, UpdateRegionNameParams>({
    mutationFn: (params) => api.regions.rename(params),
    successMessage: (_, vars) => `Region renamed to "${vars.newRegionName}"`,
    errorMessage: 'Failed to update region name',
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['regions'] });
      queryClient.invalidateQueries({ queryKey: ['dropdown-data'] });
    },
  });
};

// Update region vault
export const useUpdateRegionVault = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, UpdateRegionVaultParams & Record<string, unknown>>(
    {
      mutationFn: (params) =>
        api.regions.updateVault({
          ...params,
          vaultContent: minifyJSON(params.vaultContent),
        }),
      successMessage: (_, vars) => `Region "${vars.regionName}" vault updated successfully`,
      errorMessage: 'Failed to update region vault',
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['regions'] });
      },
    }
  );
};

// Delete region
export const useDeleteRegion = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, DeleteRegionParams>({
    mutationFn: (params) => api.regions.delete(params),
    successMessage: (_, vars) => `Region "${vars.regionName}" deleted successfully`,
    errorMessage: 'Failed to delete region',
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['regions'] });
      queryClient.invalidateQueries({ queryKey: ['dropdown-data'] });
    },
  });
};
