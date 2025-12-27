import { useQuery, useQueryClient } from '@tanstack/react-query';
import { typedApi } from '@/api/client';
import { useMutationWithFeedback } from '@/hooks/useMutationWithFeedback';
import i18n from '@/i18n/config';
import { minifyJSON } from '@/platform/utils/json';
import { selectCompany } from '@/store/auth/authSelectors';
import { useAppSelector } from '@/store/store';
import { showMessage } from '@/utils/messages';
import { extractFirstByIndex, extractByIndex } from '@rediacc/shared/api/typedApi';
import type {
  CompanyImportResult,
  CompanyVaultUpdateResult,
  ImportCompanyDataParams,
  UpdateCompanyBlockUserRequestsParams,
  UpdateCompanyVaultParams,
  UpdateCompanyVaultsParams,
  GetCompanyVault_ResultSet1,
  GetCompanyVaults_ResultSet1,
} from '@rediacc/shared/types';

// Get company vault configuration
export const useCompanyVault = () => {
  const company = useAppSelector(selectCompany);

  return useQuery({
    queryKey: ['company-vault', company],
    queryFn: async () => {
      const response = await typedApi.GetCompanyVault({});
      return (
        extractFirstByIndex<GetCompanyVault_ResultSet1>(response, 1) ??
        extractFirstByIndex<GetCompanyVault_ResultSet1>(response, 0)
      );
    },
    enabled: !!company,
  });
};

// Update company vault configuration
export const useUpdateCompanyVault = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, UpdateCompanyVaultParams>({
    mutationFn: (params) =>
      typedApi.UpdateCompanyVault({
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

  return useMutationWithFeedback<{ deactivatedCount: number }, Error, boolean>({
    mutationFn: async (blockUserRequests: boolean) => {
      const params: UpdateCompanyBlockUserRequestsParams = { blockUserRequests };
      const response = await typedApi.UpdateCompanyBlockUserRequests(params);
      const result = extractFirstByIndex<{ deactivatedCount: number }>(response, 0);
      if (!result) throw new Error('No result returned from UpdateCompanyBlockUserRequests');
      return result;
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
      const response = await typedApi.GetCompanyVaults({});
      const vaults = extractByIndex<GetCompanyVaults_ResultSet1>(response, 1);

      // Extract bridgesWithRequestToken from second result set
      const bridgesWithRequestToken = extractByIndex(response, 2);
      const allVaults = vaults;

      // Dynamically organize vaults by entity type
      const vaultsByType: Record<string, GetCompanyVaults_ResultSet1[]> = {};

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
      const response = await typedApi.UpdateCompanyVaults(params);
      const result = extractFirstByIndex<CompanyVaultUpdateResult>(response, 0);
      if (!result) throw new Error('No result returned from UpdateCompanyVaults');
      return result;
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
      const response = await typedApi.ExportCompanyData({});
      // ExportCompanyData returns two result sets - extract the second one (index 1) which contains the export data
      return extractFirstByIndex(response, 1) ?? extractFirstByIndex(response, 0);
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
      const response = await typedApi.ImportCompanyData(params);
      const result = extractFirstByIndex<CompanyImportResult>(response, 0);
      if (!result) throw new Error('No result returned from ImportCompanyData');
      return result;
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
