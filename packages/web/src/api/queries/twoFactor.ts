import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSelector } from 'react-redux';
import { RootState } from '@/store/store';
import { showMessage } from '@/utils/messages';
import { hashPassword } from '@/utils/auth';
import i18n from '@/i18n/config';
import { createErrorHandler, extractErrorMessage } from '@/utils/mutationUtils';
import { api } from '@/api/client';
import type { AuthRequestStatus, EnableTfaResponse, VerifyTfaResult } from '@rediacc/shared/types';

export type TwoFactorStatus = AuthRequestStatus;
export type EnableTwoFactorResponse = EnableTfaResponse;

// Get TFA status for current user
export const useTFAStatus = () => {
  const userEmail = useSelector((state: RootState) => state.auth.user?.email);

  return useQuery<AuthRequestStatus>({
    queryKey: ['tfa-status', userEmail],
    queryFn: async () => {
      try {
        return await api.auth.getRequestStatus();
      } catch {
        return {
          isTFAEnabled: false,
          isAuthorized: false,
          authenticationStatus: i18n.t('settings:twoFactorAuth.statusMessages.unknown'),
        };
      }
    },
    enabled: !!userEmail,
  });
};

// Enable TFA for current user
export const useEnableTFA = () => {
  const queryClient = useQueryClient();
  const userEmail = useSelector((state: RootState) => state.auth.user?.email);

  return useMutation({
    mutationFn: async (data: {
      password?: string;
      generateOnly?: boolean;
      verificationCode?: string;
      secret?: string;
      confirmEnable?: boolean;
    }) => {
      // Generate only mode - get secret without saving
      if (data.generateOnly && data.password) {
        const passwordHash = await hashPassword(data.password);
        const responseData = await api.auth.enableTfa(passwordHash, { generateOnly: true });
        if (!responseData?.secret) {
          throw new Error(i18n.t('settings:twoFactorAuth.errors.missingData'));
        }

        return responseData;
      }

      // Confirm enable mode - verify code and save
      if (data.confirmEnable && data.verificationCode && data.secret) {
        return api.auth.enableTfa(undefined, {
          verificationCode: data.verificationCode,
          secret: data.secret,
          confirmEnable: true,
        });
      }

      throw new Error(i18n.t('settings:twoFactorAuth.errors.invalidParameters'));
    },
    onSuccess: (_data, variables) => {
      // Only update cache and show success if we're confirming enable
      if (variables.confirmEnable) {
        // Immediately update the cache with the new status
        queryClient.setQueryData(['tfa-status', userEmail], {
          isTFAEnabled: true,
          isAuthorized: true,
          authenticationStatus: i18n.t('settings:twoFactorAuth.statusMessages.enabled'),
        } as TwoFactorStatus);

        // Then invalidate to ensure fresh data on next fetch
        queryClient.invalidateQueries({ queryKey: ['tfa-status'] });
        showMessage('success', i18n.t('settings:twoFactorAuth.success.enabled'));
      }
    },
    onError: (error: unknown) => {
      const fallbackMessage = i18n.t('settings:twoFactorAuth.errors.enableFailed');
      const errorMessage = extractErrorMessage(error, fallbackMessage);

      // If it's a 409 conflict error (TFA already enabled), refresh the status
      if (errorMessage.includes('already enabled')) {
        queryClient.invalidateQueries({ queryKey: ['tfa-status'] });
      }

      createErrorHandler(fallbackMessage)(error);
    },
  });
};

// Disable TFA for current user
export const useDisableTFA = () => {
  const queryClient = useQueryClient();
  const userEmail = useSelector((state: RootState) => state.auth.user?.email);

  return useMutation({
    mutationFn: async (data: { password: string; currentCode: string }) => {
      const passwordHash = await hashPassword(data.password);
      await api.auth.disableTfa(passwordHash, data.currentCode);
    },
    onSuccess: () => {
      // Immediately update the cache with the new status
      queryClient.setQueryData(['tfa-status', userEmail], {
        isTFAEnabled: false,
        isAuthorized: true,
        authenticationStatus: i18n.t('settings:twoFactorAuth.statusMessages.none'),
      } as TwoFactorStatus);

      // Then invalidate to ensure fresh data on next fetch
      queryClient.invalidateQueries({ queryKey: ['tfa-status'] });
      showMessage('success', i18n.t('settings:twoFactorAuth.success.disabled'));
    },
    onError: createErrorHandler(i18n.t('settings:twoFactorAuth.errors.disableFailed')),
  });
};

// Verify TFA code after login (privilege elevation)
export const useVerifyTFA = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: { code: string }): Promise<VerifyTfaResult> =>
      api.auth.verifyTfa(data.code),
    onSuccess: (data) => {
      if (data.isAuthorized) {
        queryClient.invalidateQueries({ queryKey: ['tfa-status'] });
        showMessage('success', i18n.t('settings:twoFactorAuth.success.verified'));
      }
    },
    onError: createErrorHandler(i18n.t('settings:twoFactorAuth.errors.verificationFailed')),
  });
};
