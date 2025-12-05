import { useMutation, useQueryClient } from '@tanstack/react-query';
import { showMessage } from '@/utils/messages';
import { useAppSelector, useAppDispatch } from '@/store/store';
import { selectCompany } from '@/store/auth/authSelectors';
import { setVaultCompany } from '@/store/auth/authSlice';
import { createVaultCompanySentinel } from '@/utils/vaultProtocol';
import i18n from '@/i18n/config';
import { createErrorHandler } from '@/utils/mutationUtils';
import { api } from '@/api/client';

/**
 * Enable vault encryption for a company by setting VaultCompany
 * This should be called when the company admin first sets up encryption
 */
export const useEnableCompanyEncryption = () => {
  const queryClient = useQueryClient();
  const dispatch = useAppDispatch();
  const company = useAppSelector(selectCompany);
  const enableErrorHandler = createErrorHandler(i18n.t('system:vaultProtocol.errors.enableFailed'));

  return useMutation({
    mutationFn: async (masterPassword: string) => {
      if (!company) {
        throw new Error(i18n.t('system:vaultProtocol.errors.noCompanySelected'));
      }

      // Create the encrypted sentinel value
      const encryptedSentinel = await createVaultCompanySentinel(company, masterPassword);

      // Update VaultCompany in the database
      await api.company.updateVaultProtocol(encryptedSentinel);

      return { encryptedSentinel, company };
    },
    onSuccess: (data) => {
      // Update Redux store
      dispatch(
        setVaultCompany({
          vaultCompany: data.encryptedSentinel,
          companyEncryptionEnabled: true,
        })
      );

      // Invalidate relevant queries
      queryClient.invalidateQueries({ queryKey: ['company-vault'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });

      showMessage('success', i18n.t('system:vaultProtocol.success.enabled'));
    },
    onError: enableErrorHandler,
  });
};

/**
 * Disable vault encryption for a company by clearing VaultCompany
 * This should only be allowed by company admins
 */
export const useDisableCompanyEncryption = () => {
  const queryClient = useQueryClient();
  const dispatch = useAppDispatch();
  const disableErrorHandler = createErrorHandler(
    i18n.t('system:vaultProtocol.errors.disableFailed')
  );

  return useMutation({
    mutationFn: async () => {
      // Clear VaultCompany in the database
      await api.company.updateVaultProtocol(null);

      return true;
    },
    onSuccess: () => {
      // Update Redux store
      dispatch(
        setVaultCompany({
          vaultCompany: null,
          companyEncryptionEnabled: false,
        })
      );

      // Invalidate relevant queries
      queryClient.invalidateQueries({ queryKey: ['company-vault'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });

      showMessage('success', i18n.t('system:vaultProtocol.success.disabled'));
    },
    onError: disableErrorHandler,
  });
};

/**
 * Check if the current user can manage encryption settings
 * (typically only company admins)
 */
export const useCanManageEncryption = () => {
  // This would check user permissions
  // For now, we'll assume it's based on user role
  const user = useAppSelector((state) => state.auth.user);
  return user?.role === 'admin' || user?.role === 'owner';
};
