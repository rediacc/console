import { useState } from 'react';
import apiClient from '@/api/client';
import type { useTelemetry } from '@/components/common/TelemetryProvider';
import type { useTFAVerification } from '@/features/auth/hooks/useTFAVerification';
import type { LoginFormValues } from '@/features/auth/types';
import { masterPasswordService } from '@/services/auth';
import { loginSuccess } from '@/store/auth/authSlice';
import { hashPassword, saveAuthData } from '@/utils/auth';
import { showMessage } from '@/utils/messages';
import {
  analyzeVaultProtocolState,
  isEncrypted,
  VaultProtocolState,
  validateMasterPassword,
} from '@/utils/vaultProtocol';
import { parseLoginResult as parseAuthenticationResult } from '@rediacc/shared/api';
import { parseResponse } from '@rediacc/shared/api';
import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { AuthLoginResult, VerifyTfaResult } from '@rediacc/shared/types';
import { handleProtocolState } from './useProtocolStateHandler';
import type { Dispatch, UnknownAction } from '@reduxjs/toolkit';
import type { FormInstance } from 'antd/es/form';
import type { useTranslation } from 'react-i18next';

interface PendingTFAData {
  email: string;
  authResult: AuthLoginResult;
  masterPassword?: string;
}

export const useLoginFlow = (params: {
  form: FormInstance<LoginFormValues>;
  t: TypedTFunction;
  i18n: ReturnType<typeof useTranslation>['i18n'];
  navigate: (path: string) => void;
  dispatch: Dispatch<UnknownAction>;
  trackUserAction: ReturnType<typeof useTelemetry>['trackUserAction'];
  verifyTFAMutation: ReturnType<typeof useTFAVerification>;
}) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [vaultProtocolState, setVaultProtocolState] = useState<VaultProtocolState | null>(null);
  const [showTFAModal, setShowTFAModal] = useState(false);
  const [pendingTFAData, setPendingTFAData] = useState<PendingTFAData | null>(null);
  const [twoFACode, setTwoFACode] = useState('');

  const processSuccessfulLogin = async (values: LoginFormValues, authResult: AuthLoginResult) => {
    const vaultOrganization = authResult.vaultOrganization;
    const organizationName = authResult.organizationName ?? authResult.organization ?? null;
    const organizationHasEncryption = isEncrypted(vaultOrganization);
    const userProvidedPassword = !!values.masterPassword;

    let passwordValid: boolean | undefined = undefined;
    if (organizationHasEncryption && userProvidedPassword && vaultOrganization) {
      passwordValid = await validateMasterPassword(vaultOrganization, values.masterPassword!);
    }

    const protocolState = analyzeVaultProtocolState(
      vaultOrganization,
      userProvidedPassword,
      passwordValid
    );
    const protocolResult = handleProtocolState(
      protocolState,
      params.t,
      params.form,
      setError,
      setVaultProtocolState
    );
    if (protocolResult.shouldReturn) return false;

    await saveAuthData(values.email, organizationName ?? undefined);

    if (organizationHasEncryption && values.masterPassword) {
      await masterPasswordService.setMasterPassword(values.masterPassword);
    }

    const preferredLanguage = authResult.preferredLanguage ?? undefined;
    if (preferredLanguage && preferredLanguage !== params.i18n.language) {
      await params.i18n.changeLanguage(preferredLanguage);
    }

    params.dispatch(
      loginSuccess({
        user: {
          email: values.email,
          organization: organizationName ?? undefined,
          preferredLanguage,
        },
        organization: organizationName ?? undefined,
        vaultOrganization: vaultOrganization ?? undefined,
        organizationEncryptionEnabled: organizationHasEncryption,
      })
    );

    params.trackUserAction('login_success', 'login_form', {
      email_domain: values.email.split('@')[1] ?? 'unknown',
      organization: organizationName ?? 'unknown',
      has_encryption: organizationHasEncryption,
      vault_protocol_state: vaultProtocolState?.toString() ?? 'none',
    });

    return true;
  };

  const handleLogin = async (values: LoginFormValues) => {
    setLoading(true);
    setError(null);
    setVaultProtocolState(null);

    params.trackUserAction('login_attempt', 'login_form', {
      email_domain: values.email.split('@')[1] || 'unknown',
      has_master_password: !!values.masterPassword,
      is_remember_me: !!values.rememberMe,
    });

    try {
      const passwordHash = await hashPassword(values.password);
      const loginResponse = await apiClient.login(values.email, passwordHash);

      if (loginResponse.failure !== 0) {
        const errors = loginResponse.errors;
        throw new Error(errors.length > 0 ? errors.join('; ') : 'Login failed');
      }

      const authResult = parseAuthenticationResult(loginResponse);

      if (authResult.authenticationStatus === 'TFA_REQUIRED' && !authResult.isAuthorized) {
        setPendingTFAData({
          email: values.email,
          authResult,
          masterPassword: values.masterPassword,
        });
        setShowTFAModal(true);
        setLoading(false);
        return;
      }

      const success = await processSuccessfulLogin(values, authResult);
      if (success) {
        params.navigate('/machines');
      }
    } catch (caughtError: unknown) {
      const errorMessage = caughtError instanceof Error ? caughtError.message : 'Login failed';
      params.trackUserAction('login_failure', 'login_form', {
        email_domain: values.email.split('@')[1] ?? 'unknown',
        error_message: errorMessage,
        has_master_password: !!values.masterPassword,
      });
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const completeTFALogin = async () => {
    if (!pendingTFAData) return;

    const { email, authResult: storedAuthResult, masterPassword } = pendingTFAData;
    const vaultOrganization = storedAuthResult.vaultOrganization;
    const organizationName = storedAuthResult.organizationName ?? storedAuthResult.organization ?? null;

    await saveAuthData(email, organizationName ?? undefined);

    const organizationHasEncryption = isEncrypted(vaultOrganization);
    if (organizationHasEncryption && masterPassword) {
      await masterPasswordService.setMasterPassword(masterPassword);
    }

    const preferredLanguage = storedAuthResult.preferredLanguage ?? undefined;
    if (preferredLanguage && preferredLanguage !== params.i18n.language) {
      await params.i18n.changeLanguage(preferredLanguage);
    }

    params.dispatch(
      loginSuccess({
        user: { email, organization: organizationName ?? undefined, preferredLanguage },
        organization: organizationName ?? undefined,
        vaultOrganization: vaultOrganization ?? undefined,
        organizationEncryptionEnabled: organizationHasEncryption,
      })
    );

    setShowTFAModal(false);
    params.navigate('/machines');
  };

  const handleTFAVerification = async () => {
    try {
      const response = await params.verifyTFAMutation.mutateAsync({ tFACode: twoFACode });
      const tfaResults = parseResponse<VerifyTfaResult>(response as never);
      const tfaResult = tfaResults[0] as VerifyTfaResult | undefined;

      if (tfaResult?.isAuthorized !== true) return;

      if (tfaResult.isTFAEnabled === false) {
        showMessage('info', 'Two-factor authentication is not enabled for this account.');
        setShowTFAModal(false);
        setTwoFACode('');
        return;
      }

      if (!pendingTFAData) {
        setLoading(false);
        setShowTFAModal(false);
        setTwoFACode('');
        return;
      }

      await completeTFALogin();
    } catch {
      // Error is handled by the mutation
    }
  };

  const handleTFACancel = () => {
    setShowTFAModal(false);
    setTwoFACode('');
    setPendingTFAData(null);
  };

  return {
    loading,
    error,
    clearError: () => setError(null),
    vaultProtocolState,
    showTFAModal,
    twoFACode,
    setTwoFACode,
    handleLogin,
    handleTFAVerification,
    handleTFACancel,
    isVerifyingTFA: params.verifyTFAMutation.isPending,
  };
};
