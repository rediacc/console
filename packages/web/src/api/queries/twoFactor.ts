import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useSelector } from 'react-redux';
import { api } from '@/api/client';
import { useMutationWithFeedback } from '@/hooks/useMutationWithFeedback';
import i18n from '@/i18n/config';
import { RootState } from '@/store/store';
import { hashPassword } from '@/utils/auth';
import { extractErrorMessage } from '@/utils/mutationUtils';
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

  return useMutationWithFeedback({
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
    // Only show success message when confirming enable (not when generating secret)
    successMessage: (_data, variables) =>
      variables.confirmEnable ? i18n.t('settings:twoFactorAuth.success.enabled') : null,
    errorMessage: i18n.t('settings:twoFactorAuth.errors.enableFailed'),
    onSuccess: (_data, variables) => {
      // Only update cache if we're confirming enable
      if (variables.confirmEnable) {
        // Immediately update the cache with the new status
        queryClient.setQueryData(['tfa-status', userEmail], {
          isTFAEnabled: true,
          isAuthorized: true,
          authenticationStatus: i18n.t('settings:twoFactorAuth.statusMessages.enabled'),
        } as TwoFactorStatus);

        // Then invalidate to ensure fresh data on next fetch
        void queryClient.invalidateQueries({ queryKey: ['tfa-status'] });
      }
    },
    onError: (error: unknown) => {
      const fallbackMessage = i18n.t('settings:twoFactorAuth.errors.enableFailed');
      const errorMessage = extractErrorMessage(error, fallbackMessage);

      // If it's a 409 conflict error (TFA already enabled), refresh the status
      if (errorMessage.includes('already enabled')) {
        void queryClient.invalidateQueries({ queryKey: ['tfa-status'] });
      }
    },
  });
};

// Disable TFA for current user
export const useDisableTFA = () => {
  const queryClient = useQueryClient();
  const userEmail = useSelector((state: RootState) => state.auth.user?.email);

  return useMutationWithFeedback({
    mutationFn: async (data: { password: string; currentCode: string }) => {
      const passwordHash = await hashPassword(data.password);
      await api.auth.disableTfa(passwordHash, data.currentCode);
    },
    successMessage: i18n.t('settings:twoFactorAuth.success.disabled'),
    errorMessage: i18n.t('settings:twoFactorAuth.errors.disableFailed'),
    onSuccess: () => {
      // Immediately update the cache with the new status
      queryClient.setQueryData(['tfa-status', userEmail], {
        isTFAEnabled: false,
        isAuthorized: true,
        authenticationStatus: i18n.t('settings:twoFactorAuth.statusMessages.none'),
      } as TwoFactorStatus);

      // Then invalidate to ensure fresh data on next fetch
      void queryClient.invalidateQueries({ queryKey: ['tfa-status'] });
    },
  });
};

// Verify TFA code after login (privilege elevation)
export const useVerifyTFA = () => {
  const queryClient = useQueryClient();

  return useMutationWithFeedback({
    mutationFn: async (data: { code: string }): Promise<VerifyTfaResult> =>
      api.auth.verifyTfa(data.code),
    // Only show success message when verification results in authorization
    successMessage: (data) =>
      data.isAuthorized ? i18n.t('settings:twoFactorAuth.success.verified') : null,
    errorMessage: i18n.t('settings:twoFactorAuth.errors.verificationFailed'),
    onSuccess: (data) => {
      if (data.isAuthorized) {
        void queryClient.invalidateQueries({ queryKey: ['tfa-status'] });
      }
    },
  });
};
