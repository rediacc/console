import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import { useMutationWithFeedback } from '@/hooks/useMutationWithFeedback';
import { minifyJSON } from '@/utils/json';
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
export const useCreateBridge = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, WithOptionalVault<CreateBridgeParams>>({
    mutationFn: (params) =>
      api.bridges.create({
        ...params,
        vaultContent: params.vaultContent || '{}',
      }),
    successMessage: (_, vars) => `Bridge "${vars.bridgeName}" created successfully`,
    errorMessage: 'Failed to create bridge',
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bridges'] });
      queryClient.invalidateQueries({ queryKey: ['regions'] });
      queryClient.invalidateQueries({ queryKey: ['dropdown-data'] });
    },
  });
};

// Update bridge name
export const useUpdateBridgeName = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, UpdateBridgeNameParams>({
    mutationFn: (params) => api.bridges.rename(params),
    successMessage: (_, vars) => `Bridge renamed to "${vars.newBridgeName}"`,
    errorMessage: 'Failed to update bridge name',
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bridges'] });
      queryClient.invalidateQueries({ queryKey: ['dropdown-data'] });
    },
  });
};

// Update bridge vault
export const useUpdateBridgeVault = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<
    unknown,
    Error,
    UpdateBridgeVaultParams & Record<string, unknown>
  >({
    mutationFn: (params) =>
      api.bridges.updateVault({
        ...params,
        vaultContent: minifyJSON(params.vaultContent),
      }),
    successMessage: (_, vars) => `Bridge "${vars.bridgeName}" vault updated successfully`,
    errorMessage: 'Failed to update bridge vault',
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bridges'] });
    },
  });
};

// Delete bridge
export const useDeleteBridge = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, DeleteBridgeParams & Record<string, unknown>>({
    mutationFn: (params) => api.bridges.delete(params),
    successMessage: (_, vars) => `Bridge "${vars.bridgeName}" deleted successfully`,
    errorMessage: 'Failed to delete bridge',
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bridges'] });
      queryClient.invalidateQueries({ queryKey: ['regions'] });
    },
  });
};

// Reset bridge authorization
export const useResetBridgeAuthorization = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, ResetBridgeAuthorizationParams>({
    mutationFn: (params) => api.bridges.resetAuthorization(params),
    successMessage: (_, vars) => `Bridge authorization reset for "${vars.bridgeName}"`,
    errorMessage: 'Failed to reset bridge authorization',
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bridges'] });
    },
  });
};

export type { GetRegionBridges_ResultSet1, GetRegionBridges_ResultSet1 as Bridge };
