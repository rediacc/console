/**
 * TFA (Two-Factor Authentication) hooks.
 * Split from hooks-extended.ts for file size management.
 */

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useSelector } from 'react-redux';
import { typedApi } from '@/api/client';
import { useMutationWithFeedback } from '@/hooks/useMutationWithFeedback';
import i18n from '@/i18n/config';
import type { RootState } from '@/store/store';
import { hashPassword } from '@/utils/auth';
import { extractErrorMessage } from '@/utils/mutationUtils';
import type { AuthRequestStatus, EnableTfaResponse } from '@rediacc/shared/types';

export type TwoFactorStatus = AuthRequestStatus;
export type EnableTwoFactorResponse = EnableTfaResponse;

const TFA_KEYS = {
  status: (email: string | undefined) => ['tfa-status', email] as const,
};

export const useGetTFAStatus = () => {
  const userEmail = useSelector((state: RootState) => state.auth.user?.email);
  return useQuery<AuthRequestStatus>({
    queryKey: TFA_KEYS.status(userEmail),
    queryFn: async () => {
      try {
        const response = await typedApi.GetRequestAuthenticationStatus({});
        // Extract status from result set 1
        const resultSets = response.resultSets;
        const statusSet = resultSets.find((rs) => rs.resultSetIndex === 1);
        const data = statusSet?.data[0] as
          | { isTFAEnabled?: boolean; isAuthorized?: boolean }
          | undefined;
        return {
          isTFAEnabled: data?.isTFAEnabled ?? false,
          isAuthorized: data?.isAuthorized ?? false,
          authenticationStatus: data?.isAuthorized
            ? i18n.t('settings:twoFactorAuth.statusMessages.authorized')
            : i18n.t('settings:twoFactorAuth.statusMessages.none'),
        };
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
        const response = await typedApi.UpdateUserTFA({
          enable: true,
          userHash: passwordHash,
          generateOnly: true,
        });
        const resultSets = response.resultSets;
        const secretSet = resultSets.find((rs) => rs.resultSetIndex === 1);
        const secretData = secretSet?.data[0] as { secret?: string } | undefined;
        if (!secretData?.secret) {
          throw new Error(i18n.t('settings:twoFactorAuth.errors.missingData'));
        }
        const result: EnableTfaResponse = { secret: secretData.secret };
        return result;
      }

      // Confirm enable mode - verify code and save
      if (data.confirmEnable && data.verificationCode && data.secret) {
        const response = await typedApi.UpdateUserTFA({
          enable: true,
          verificationCode: data.verificationCode,
          secret: data.secret,
          confirmEnable: true,
        });
        return response;
      }

      throw new Error(i18n.t('settings:twoFactorAuth.errors.invalidParameters'));
    },
    successMessage: (_data, variables) =>
      variables.confirmEnable ? i18n.t('settings:twoFactorAuth.success.enabled') : null,
    errorMessage: i18n.t('settings:twoFactorAuth.errors.enableFailed'),
    onSuccess: (_data, variables) => {
      if (variables.confirmEnable) {
        queryClient.setQueryData(TFA_KEYS.status(userEmail), {
          isTFAEnabled: true,
          isAuthorized: true,
          authenticationStatus: i18n.t('settings:twoFactorAuth.statusMessages.enabled'),
        } as TwoFactorStatus);
        void queryClient.invalidateQueries({ queryKey: ['tfa-status'] });
      }
    },
    onError: (error: unknown) => {
      const fallbackMessage = i18n.t('settings:twoFactorAuth.errors.enableFailed');
      const errorMessage = extractErrorMessage(error, fallbackMessage);
      if (errorMessage.includes('already enabled')) {
        void queryClient.invalidateQueries({ queryKey: ['tfa-status'] });
      }
    },
  });
};

export const useDisableTFA = () => {
  const queryClient = useQueryClient();
  const userEmail = useSelector((state: RootState) => state.auth.user?.email);
  return useMutationWithFeedback({
    mutationFn: async (data: { password: string; currentCode: string }) => {
      const passwordHash = await hashPassword(data.password);
      await typedApi.UpdateUserTFA({
        enable: false,
        userHash: passwordHash,
        currentCode: data.currentCode,
      });
    },
    successMessage: i18n.t('settings:twoFactorAuth.success.disabled'),
    errorMessage: i18n.t('settings:twoFactorAuth.errors.disableFailed'),
    onSuccess: () => {
      queryClient.setQueryData(TFA_KEYS.status(userEmail), {
        isTFAEnabled: false,
        isAuthorized: true,
        authenticationStatus: i18n.t('settings:twoFactorAuth.statusMessages.none'),
      } as TwoFactorStatus);
      void queryClient.invalidateQueries({ queryKey: ['tfa-status'] });
    },
  });
};

export const useVerifyTFA = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback({
    mutationFn: async (data: { code: string }) => {
      const response = await typedApi.PrivilegeAuthenticationRequest({
        tFACode: data.code,
      });
      const resultSets = response.resultSets;
      const statusSet = resultSets.find((rs) => rs.resultSetIndex === 1);
      const statusData = statusSet?.data[0] as { isAuthorized?: boolean } | undefined;
      return {
        isAuthorized: statusData?.isAuthorized ?? false,
      };
    },
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
