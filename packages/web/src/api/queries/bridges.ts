import { useQuery, useQueryClient } from '@tanstack/react-query';
import { typedApi } from '@/api/client';
import { useMutationWithFeedback } from '@/hooks/useMutationWithFeedback';
import { minifyJSON } from '@/platform/utils/json';
import { parseGetRegionBridges } from '@rediacc/shared/api';
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
      const response = await typedApi.GetRegionBridges({ regionName });
      return parseGetRegionBridges(response as never);
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
      typedApi.CreateBridge({ ...params, vaultContent: params.vaultContent ?? '{}' }),
    successMessage: (_, vars) => `Bridge "${vars.bridgeName}" created successfully`,
    errorMessage: 'Failed to create bridge',
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['bridges'] });
      void queryClient.invalidateQueries({ queryKey: ['regions'] });
      void queryClient.invalidateQueries({ queryKey: ['dropdown-data'] });
    },
  });
};

// Update bridge name
export const useUpdateBridgeName = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, UpdateBridgeNameParams>({
    mutationFn: (params) => typedApi.UpdateBridgeName(params),
    successMessage: (_, vars) => `Bridge renamed to "${vars.newBridgeName}"`,
    errorMessage: 'Failed to update bridge name',
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['bridges'] });
      void queryClient.invalidateQueries({ queryKey: ['dropdown-data'] });
    },
  });
};

// Update bridge vault
export const useUpdateBridgeVault = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, UpdateBridgeVaultParams & Record<string, unknown>>(
    {
      mutationFn: (params) =>
        typedApi.UpdateBridgeVault({
          ...params,
          vaultContent: minifyJSON(params.vaultContent),
        }),
      successMessage: (_, vars) => `Bridge "${vars.bridgeName}" vault updated successfully`,
      errorMessage: 'Failed to update bridge vault',
      onSuccess: () => {
        void queryClient.invalidateQueries({ queryKey: ['bridges'] });
      },
    }
  );
};

// Delete bridge
export const useDeleteBridge = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, DeleteBridgeParams & Record<string, unknown>>({
    mutationFn: (params) => typedApi.DeleteBridge(params),
    successMessage: (_, vars) => `Bridge "${vars.bridgeName}" deleted successfully`,
    errorMessage: 'Failed to delete bridge',
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['bridges'] });
      void queryClient.invalidateQueries({ queryKey: ['regions'] });
    },
  });
};

// Reset bridge authorization
export const useResetBridgeAuthorization = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, ResetBridgeAuthorizationParams>({
    mutationFn: (params) => typedApi.ResetBridgeAuthorization(params),
    successMessage: (_, vars) => `Bridge authorization reset for "${vars.bridgeName}"`,
    errorMessage: 'Failed to reset bridge authorization',
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['bridges'] });
    },
  });
};

export type {
  GetRegionBridges_ResultSet1,
  GetRegionBridges_ResultSet1 as Bridge,
} from '@rediacc/shared/types';
