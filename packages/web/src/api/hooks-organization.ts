/**
 * Organization Domain Hooks
 *
 * Non-generated organization hooks for:
 * - Organization info (subset of dashboard)
 * - Vault management
 * - Data import/export
 */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { typedApi } from '@/api/client';
import { useMutationWithFeedback } from '@/hooks/useMutationWithFeedback';
import i18n from '@/i18n/config';
import { parseGetEntityAuditTrace } from '@rediacc/shared/api/parsers/audit';
import { parseOrganizationInfo } from '@rediacc/shared/api/parsers/organization';
import type {
  AuditTraceResponse,
  OrganizationDashboardData,
  OrganizationVaultsData,
} from '@rediacc/shared/types';

const ORGANIZATION_KEYS = {
  info: () => ['organization', 'info'] as const,
  vaults: () => ['organization-vaults'] as const,
  exportData: () => ['organization-export-data'] as const,
};

/**
 * Get organization info (subset of dashboard data).
 * Returns only organizationInfo and activeSubscription.
 */
export const useOrganizationInfo = () => {
  return useQuery<Pick<OrganizationDashboardData, 'organizationInfo' | 'activeSubscription'>>({
    queryKey: ORGANIZATION_KEYS.info(),
    queryFn: async () => {
      const response = await typedApi.GetOrganizationDashboard({});
      return parseOrganizationInfo(response as never);
    },
    staleTime: 60000,
  });
};

/**
 * Get all organization vaults for backup/restore operations.
 * Enabled is false by default - call refetch() to fetch manually.
 */
export const useOrganizationVaults = () => {
  return useQuery<OrganizationVaultsData>({
    queryKey: ORGANIZATION_KEYS.vaults(),
    queryFn: async () => {
      const response = await typedApi.GetOrganizationVaults({});
      const resultSets = response.resultSets;
      const vaultsSet = resultSets.find((rs) => rs.resultSetIndex === 1);
      const rawVaults = (vaultsSet?.data ?? []) as Record<string, unknown>[];

      const allVaults = rawVaults.map((v) => ({
        entityType: String(v.entityType ?? ''),
        entityId: Number(v.entityId ?? 0),
        entityName: v.entityName ? String(v.entityName) : undefined,
        vaultId: Number(v.vaultId ?? 0),
        vaultName: String(v.vaultName ?? ''),
        credential: String(v.credential ?? ''),
        decryptedVault: v.decryptedVault ? String(v.decryptedVault) : undefined,
        version: v.version ? Number(v.version) : undefined,
      }));

      return { allVaults };
    },
    enabled: false,
  });
};

/**
 * Update organization vaults.
 */
export const useUpdateOrganizationVaults = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<
    unknown,
    Error,
    { credential: string; name: string; content: string; version: number }[]
  >({
    mutationFn: async (updates) => {
      return typedApi.UpdateOrganizationVaults({ updates: JSON.stringify(updates) });
    },
    successMessage: i18n.t('system:organization.success.vaultsUpdated'),
    errorMessage: i18n.t('system:organization.errors.vaultsUpdateFailed'),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['organization'] });
    },
  });
};

/**
 * Update organization block user requests setting.
 */
export const useUpdateOrganizationBlockUserRequests = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, boolean>({
    mutationFn: async (blockUserRequests) => {
      return typedApi.UpdateOrganizationBlockUserRequests({ blockUserRequests });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['organization'] });
      void queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });
};

/**
 * Export organization data.
 * Enabled is false by default - call refetch() to fetch manually.
 */
export const useExportOrganizationData = () => {
  return useQuery({
    queryKey: ORGANIZATION_KEYS.exportData(),
    queryFn: async () => {
      const response = await typedApi.ExportOrganizationData({});
      const resultSets = response.resultSets;
      const dataSet = resultSets.find((rs) => rs.resultSetIndex === 1);
      return dataSet?.data ?? [];
    },
    enabled: false,
  });
};

/**
 * Import organization data.
 */
export const useImportOrganizationData = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<
    unknown,
    Error,
    { organizationDataJson: string; importMode: string }
  >({
    mutationFn: async ({ organizationDataJson, importMode }) => {
      return typedApi.ImportOrganizationData({ organizationDataJson, importMode });
    },
    successMessage: i18n.t('system:organization.success.imported'),
    errorMessage: i18n.t('system:organization.errors.importFailed'),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['organization'] });
    },
  });
};

/**
 * Query entity audit trace with enabled option.
 * Wraps useEntityAuditTrace to support conditional fetching.
 */
export const useEntityAuditTraceWithEnabled = (
  entityType: string | null,
  entityIdentifier: string | null,
  enabled = true
) => {
  return useQuery<AuditTraceResponse>({
    queryKey: ['entityAuditTrace', entityType ?? '', entityIdentifier ?? ''],
    queryFn: async () => {
      if (!entityType || !entityIdentifier) {
        throw new Error('Entity type and identifier are required');
      }
      const response = await typedApi.GetEntityAuditTrace({ entityType, entityIdentifier });
      return parseGetEntityAuditTrace(response as never);
    },
    enabled: enabled && !!entityType && !!entityIdentifier,
    staleTime: 30000,
    gcTime: 5 * 60 * 1000,
  });
};
