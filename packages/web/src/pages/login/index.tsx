import React, { useEffect, useState } from 'react';
import { Alert, Button, Flex, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { useDispatch } from 'react-redux';
import { useNavigate, useSearchParams } from 'react-router-dom';
import apiClient from '@/api/client';
import InsecureConnectionWarning from '@/components/common/InsecureConnectionWarning';
import SandboxWarning from '@/components/common/SandboxWarning';
import { useTelemetry } from '@/components/common/TelemetryProvider';
import { featureFlags } from '@/config/featureFlags';
import EndpointSelector from '@/features/auth/components/EndpointSelector';
import RegistrationModal from '@/features/auth/components/RegistrationModal';
import { useLoginForm } from '@/features/auth/hooks/useLoginForm';
import { useTFAVerification } from '@/features/auth/hooks/useTFAVerification';
import type { LoginFormValues } from '@/features/auth/types';
import { apiConnectionService } from '@/services/api';
import { masterPasswordService } from '@/services/auth';
import { loginSuccess } from '@/store/auth/authSlice';
import { hashPassword, saveAuthData } from '@/utils/auth';
import {
  generateRandomEmail,
  generateRandomOrganizationName,
  generateRandomPassword,
} from '@/utils/generators';
import { showMessage } from '@/utils/messages';
import { isSecureContext } from '@/utils/secureContext';
import {
  analyzeVaultProtocolState,
  isEncrypted,
  VaultProtocolState,
  validateMasterPassword,
} from '@/utils/vaultProtocol';
import { parseLoginResult as parseAuthenticationResult, parseResponse } from '@rediacc/shared/api';
import { DEFAULTS } from '@rediacc/shared/config';
import type { AuthLoginResult, VerifyTfaResult } from '@rediacc/shared/types';
import { LoginForm } from './components/LoginForm';
import { TFAModal } from './components/TFAModal';
import { handleProtocolState } from './hooks/useProtocolStateHandler';

const LoginPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [vaultProtocolState, setVaultProtocolState] = useState<VaultProtocolState | null>(null);
  const [showTFAModal, setShowTFAModal] = useState(false);
  const [pendingTFAData, setPendingTFAData] = useState<{
    email: string;
    authResult: AuthLoginResult;
    masterPassword?: string;
  } | null>(null);
  const [twoFACode, setTwoFACode] = useState('');
  const [showRegistration, setShowRegistration] = useState(false);
  const [showAdvancedOptions, setShowAdvancedOptions] = useState(false);
  const [quickRegistrationData, setQuickRegistrationData] = useState<
    | {
        email: string;
        password: string;
        organizationName: string;
        activationCode: string;
      }
    | undefined
  >(undefined);
  const [isQuickRegistration, setIsQuickRegistration] = useState(false);
  const [isConnectionSecure, setIsConnectionSecure] = useState(true);
  const [insecureWarningDismissed, setInsecureWarningDismissed] = useState(false);

  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const dispatch = useDispatch();
  const { form, twoFAForm } = useLoginForm();
  const { t, i18n } = useTranslation(['auth', 'common']);
  const verifyTFAMutation = useTFAVerification();
  const { trackUserAction } = useTelemetry();

  // Check URL parameters for registration flag
  useEffect(() => {
    const checkRegistrationMode = async () => {
      const registerParam = searchParams.get('register');

      if (registerParam === 'quick') {
        try {
          const ciMode = await apiConnectionService.isCiMode();
          if (ciMode) {
            const randomData = {
              email: generateRandomEmail(),
              password: generateRandomPassword(),
              organizationName: generateRandomOrganizationName(),
              activationCode: 'AAA111',
            };
            setQuickRegistrationData(randomData);
            setIsQuickRegistration(true);
            setShowRegistration(true);
          } else {
            console.warn('Quick registration is only available in CI/TEST mode');
            showMessage('warning', 'Quick registration is only available in CI/TEST mode');
            setShowRegistration(true);
          }
        } catch (error) {
          console.error('Could not check CI mode, falling back to normal registration', error);
          setShowRegistration(true);
        }
      } else if (registerParam === 'manual') {
        setShowRegistration(true);
      }

      if (registerParam) {
        searchParams.delete('register');
        const newUrl = searchParams.toString()
          ? `${window.location.pathname}?${searchParams.toString()}`
          : window.location.pathname;
        window.history.replaceState({}, '', newUrl);
      }
    };
    void checkRegistrationMode();
  }, [searchParams]);

  // Helper to get power mode toggle message
  const getPowerModeToggleMessage = (newState: boolean, onLocalhost: boolean): string => {
    if (onLocalhost) {
      return newState
        ? 'Localhost Mode - All features enabled'
        : 'Localhost Mode - All features disabled';
    }
    return newState ? 'Advanced options enabled' : 'Advanced options disabled';
  };

  // Keyboard shortcut handler for global power mode (Ctrl+Shift+E)
  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      if (!e.ctrlKey || !e.shiftKey || e.key !== 'E') return;
      e.preventDefault();
      const onLocalhost =
        window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
      const newState = featureFlags.togglePowerMode();
      setShowAdvancedOptions(newState);
      showMessage('info', getPowerModeToggleMessage(newState, onLocalhost));
    };
    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, []);

  // Check if connection is secure
  useEffect(() => {
    const secure = isSecureContext();
    setIsConnectionSecure(secure);
    if (!secure) {
      console.warn('[LoginPage] Insecure connection detected. Web Crypto API unavailable.');
    }
  }, []);

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
      t,
      form,
      setError,
      setVaultProtocolState
    );
    if (protocolResult.shouldReturn) return false;

    await saveAuthData(values.email, organizationName ?? undefined);

    if (organizationHasEncryption && values.masterPassword) {
      await masterPasswordService.setMasterPassword(values.masterPassword);
    }

    const preferredLanguage = authResult.preferredLanguage ?? undefined;
    if (preferredLanguage && preferredLanguage !== i18n.language) {
      await i18n.changeLanguage(preferredLanguage);
    }

    dispatch(
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

    trackUserAction('login_success', 'login_form', {
      email_domain: values.email.split('@')[1] ?? DEFAULTS.TELEMETRY.UNKNOWN,
      organization: organizationName ?? DEFAULTS.TELEMETRY.UNKNOWN,
      has_encryption: organizationHasEncryption,
      vault_protocol_state: vaultProtocolState?.toString() ?? 'none',
    });

    return true;
  };

  const handleLogin = async (values: LoginFormValues) => {
    setLoading(true);
    setError(null);
    setVaultProtocolState(null);

    trackUserAction('login_attempt', 'login_form', {
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
        void navigate('/machines');
      }
    } catch (error: unknown) {
      const errorMessage =
        error instanceof Error ? error.message : t('login.errors.invalidCredentials');
      trackUserAction('login_failure', 'login_form', {
        email_domain: values.email.split('@')[1] ?? DEFAULTS.TELEMETRY.UNKNOWN,
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
    const organizationName =
      storedAuthResult.organizationName ?? storedAuthResult.organization ?? null;

    await saveAuthData(email, organizationName ?? undefined);

    const organizationHasEncryption = isEncrypted(vaultOrganization);
    if (organizationHasEncryption && masterPassword) {
      await masterPasswordService.setMasterPassword(masterPassword);
    }

    const preferredLanguage = storedAuthResult.preferredLanguage ?? undefined;
    if (preferredLanguage && preferredLanguage !== i18n.language) {
      await i18n.changeLanguage(preferredLanguage);
    }

    dispatch(
      loginSuccess({
        user: { email, organization: organizationName ?? undefined, preferredLanguage },
        organization: organizationName ?? undefined,
        vaultOrganization: vaultOrganization ?? undefined,
        organizationEncryptionEnabled: organizationHasEncryption,
      })
    );

    setShowTFAModal(false);
    void navigate('/machines');
  };

  const handleTFAVerification = async () => {
    try {
      const response = await verifyTFAMutation.mutateAsync({ tFACode: twoFACode });
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

  return (
    <>
      <SandboxWarning />
      {/* eslint-disable-next-line no-restricted-syntax */}
      <Flex className="w-full max-w-[400px]">
        <Flex vertical className="w-full">
          {error && (
            <Alert
              type="error"
              message={error}
              closable
              onClose={() => setError(null)}
              data-testid="login-error-alert"
            />
          )}

          {!isConnectionSecure && !insecureWarningDismissed && (
            <InsecureConnectionWarning onClose={() => setInsecureWarningDismissed(true)} />
          )}

          <LoginForm
            form={form}
            onSubmit={handleLogin}
            loading={loading}
            error={error}
            isConnectionSecure={isConnectionSecure}
            vaultProtocolState={vaultProtocolState}
            showAdvancedOptions={showAdvancedOptions}
            t={t}
          />

          <Flex justify="center">
            <Typography.Text>
              {t('auth:login.noAccount')}{' '}
              <a
                onClick={() => setShowRegistration(true)}
                tabIndex={0}
                role="button"
                aria-label={t('auth:login.register')}
                data-testid="login-register-link"
                className="cursor-pointer inline-block"
              >
                {t('auth:login.register')}
              </a>
            </Typography.Text>
          </Flex>

          <Flex vertical align="center" className="gap-2">
            {!showAdvancedOptions &&
              vaultProtocolState !== VaultProtocolState.PASSWORD_REQUIRED &&
              vaultProtocolState !== VaultProtocolState.INVALID_PASSWORD && (
                <Button
                  type="text"
                  size="small"
                  onClick={() => setShowAdvancedOptions(true)}
                  data-testid="login-advanced-options-toggle"
                >
                  {t('auth:login.advancedOptions')} 
                </Button>
              )}

            {showAdvancedOptions && (
              <Flex vertical className="w-full gap-2" align="center">
                <EndpointSelector />
              </Flex>
            )}
          </Flex>
        </Flex>
      </Flex>

      <TFAModal
        open={showTFAModal}
        twoFACode={twoFACode}
        setTwoFACode={setTwoFACode}
        onVerify={handleTFAVerification}
        onCancel={handleTFACancel}
        isVerifying={verifyTFAMutation.isPending}
        twoFAForm={twoFAForm}
        t={t}
      />

      <RegistrationModal
        open={showRegistration}
        onCancel={() => {
          setShowRegistration(false);
          setIsQuickRegistration(false);
          setQuickRegistrationData(undefined);
        }}
        autoFillData={quickRegistrationData}
        autoSubmit={isQuickRegistration}
        onRegistrationComplete={async (credentials) => {
          if (isQuickRegistration) {
            setShowRegistration(false);
            await handleLogin({ email: credentials.email, password: credentials.password });
          }
        }}
      />
    </>
  );
};

export default LoginPage;
