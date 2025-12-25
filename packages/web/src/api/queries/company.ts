import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import { useMutationWithFeedback } from '@/hooks/useMutationWithFeedback';
import i18n from '@/i18n/config';
import { minifyJSON } from '@/platform/utils/json';
import { selectCompany } from '@/store/auth/authSelectors';
import { useAppSelector } from '@/store/store';
import { showMessage } from '@/utils/messages';
import type {
  CompanyImportResult,
  CompanyVaultRecord,
  CompanyVaultUpdateResult,
  ImportCompanyDataParams,
  UpdateCompanyBlockUserRequestsParams,
  UpdateCompanyVaultParams,
  UpdateCompanyVaultsParams,
} from '@rediacc/shared/types';

// Get company vault configuration
export const useCompanyVault = () => {
  const company = useAppSelector(selectCompany);

  return useQuery({
    queryKey: ['company-vault', company],
    queryFn: async () => {
      const vault = await api.company.getVault();
      return vault;
    },
    enabled: !!company,
  });
};

// Update company vault configuration
export const useUpdateCompanyVault = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, UpdateCompanyVaultParams>({
    mutationFn: (params) =>
      api.company.updateVault({
        ...params,
        vaultContent: minifyJSON(params.vaultContent),
      }),
    successMessage: () => i18n.t('system:company.success.vaultUpdated'),
    errorMessage: i18n.t('system:company.errors.vaultUpdateFailed'),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['company-vault'] });
    },
  });
};

// Block or unblock user requests - Special case with dynamic success message
export const useUpdateCompanyBlockUserRequests = () => {
  const queryClient = useQueryClient();

  return useMutationWithFeedback({
    mutationFn: async (blockUserRequests: boolean) => {
      const params: UpdateCompanyBlockUserRequestsParams = { blockUserRequests };
      return api.company.updateBlockUserRequests(params);
    },
    successMessage: (data, variables) => {
      const deactivatedCount = data.deactivatedCount;

      if (variables === true) {
        return deactivatedCount > 0
          ? i18n.t('system:company.success.requestsBlockedWithTerminations', {
              count: deactivatedCount,
            })
          : i18n.t('system:company.success.requestsBlocked');
      }
      return i18n.t('system:company.success.requestsUnblocked');
    },
    errorMessage: i18n.t('system:company.errors.blockRequestsFailed'),
    onSuccess: () => {
      // Invalidate relevant queries
      void queryClient.invalidateQueries({ queryKey: ['company'] });
      void queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });
};

// Get all company vaults for export
export const useCompanyVaults = () => {
  return useQuery({
    queryKey: ['company-all-vaults'],
    queryFn: async () => {
      const { vaults, bridgesWithRequestToken } = await api.company.getAllVaults();
      const allVaults = vaults;

      // Dynamically organize vaults by entity type
      const vaultsByType: Record<string, CompanyVaultRecord[]> = {};

      allVaults.forEach((vault) => {
        const entityType = vault.entityType;
        if (entityType) {
          // Create a key based on entity type (e.g., "User" -> "users", "Company" -> "company")
          const key =
            entityType.charAt(0).toLowerCase() +
            entityType.slice(1) +
            (entityType === 'Company' ? '' : 's');

          vaultsByType[key] = vaultsByType[key] ?? [];
          vaultsByType[key].push(vault);
        }
      });

      // Return dynamic structure with bridgesWithRequestToken as a special case
      return {
        ...vaultsByType,
        bridgesWithRequestToken,
        allVaults, // Include raw data for maximum flexibility
      };
    },
    enabled: false, // Only fetch when manually triggered
  });
};

// Update all company vaults with new master password
export const useUpdateCompanyVaults = () => {
  const queryClient = useQueryClient();

  return useMutationWithFeedback<CompanyVaultUpdateResult, Error, Record<string, unknown>[]>({
    mutationFn: async (vaultUpdates) => {
      const params: UpdateCompanyVaultsParams = { updates: JSON.stringify(vaultUpdates) };
      return api.company.updateAllVaults(params);
    },
    // No success toast - handled by modal in SystemPage
    successMessage: () => null,
    errorMessage: i18n.t('system:dangerZone.updateMasterPassword.error.updateFailed'),
    onSuccess: (data) => {
      const totalUpdated = data.totalUpdated;
      const failedCount = data.failedCount;

      // Show error for partial failure
      if (failedCount > 0) {
        const message = i18n.t('system:dangerZone.updateMasterPassword.error.partialSuccess', {
          updated: totalUpdated,
          failed: failedCount,
        });
        showMessage('error', message);
      }

      // Invalidate all queries to refresh data
      void queryClient.invalidateQueries();
    },
  });
};

// Export company data
export const useExportCompanyData = () => {
  return useQuery({
    queryKey: ['company-export-data'],
    queryFn: async () => {
      const exportData = await api.company.exportData();
      return exportData;
    },
    enabled: false, // Only fetch when manually triggered
  });
};

// Import company data
export const useImportCompanyData = () => {
  const queryClient = useQueryClient();

  return useMutationWithFeedback<
    CompanyImportResult,
    Error,
    { companyDataJson: string; importMode?: 'skip' | 'override' }
  >({
    mutationFn: async (data) => {
      const params: ImportCompanyDataParams = {
        companyDataJson: data.companyDataJson,
        importMode: data.importMode ?? 'skip',
      };
      return api.company.importData(params);
    },
    successMessage: (data) => {
      const importedCount = data.importedCount;
      const skippedCount = data.skippedCount;
      const errorCount = data.errorCount;

      const parts = [
        i18n.t('system:company.success.importedCount', { count: importedCount }),
        skippedCount > 0
          ? i18n.t('system:company.success.skippedCount', { count: skippedCount })
          : null,
        errorCount > 0 ? i18n.t('system:company.success.errorCount', { count: errorCount }) : null,
      ].filter(Boolean);

      return i18n.t('system:company.success.importComplete', { summary: parts.join(', ') });
    },
    errorMessage: i18n.t('system:company.errors.importFailed'),
    onSuccess: () => {
      // Invalidate all queries to refresh data
      void queryClient.invalidateQueries();
    },
  });
};
