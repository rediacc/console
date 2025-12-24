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
import { generateRandomCompanyName, generateRandomEmail, generateRandomPassword } from '@/utils/generators';
import { showMessage } from '@/utils/messages';
import { isSecureContext } from '@/utils/secureContext';
import { analyzeVaultProtocolState, isEncrypted, VaultProtocolState, validateMasterPassword } from '@/utils/vaultProtocol';
import { parseAuthenticationResult } from '@rediacc/shared/api/services/auth';
import type { ApiResponse, AuthLoginResult } from '@rediacc/shared/types';
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
  const [quickRegistrationData, setQuickRegistrationData] = useState<{
    email: string;
    password: string;
    companyName: string;
    activationCode: string;
  } | undefined>(undefined);
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
              companyName: generateRandomCompanyName(),
              activationCode: '111111',
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
    checkRegistrationMode();
  }, [searchParams]);

  // Keyboard shortcut handler for global power mode (Ctrl+Shift+E)
  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && e.key === 'E') {
        e.preventDefault();
        const onLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
        const newState = featureFlags.togglePowerMode();
        setShowAdvancedOptions(newState);
        const message = onLocalhost
          ? newState ? 'Localhost Mode - All features enabled' : 'Localhost Mode - All features disabled'
          : newState ? 'Advanced options enabled' : 'Advanced options disabled';
        showMessage('info', message);
      }
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
        throw new Error(loginResponse.errors?.join('; ') || 'Login failed');
      }

      const authResult = parseAuthenticationResult(loginResponse as ApiResponse);
      const isAuthorized = authResult.isAuthorized;
      const authenticationStatus = authResult.authenticationStatus;

      if (authenticationStatus === 'TFA_REQUIRED' && !isAuthorized) {
        setPendingTFAData({ email: values.email, authResult, masterPassword: values.masterPassword });
        setShowTFAModal(true);
        setLoading(false);
        return;
      }

      const vaultCompany = authResult.vaultCompany;
      const companyName = authResult.companyName ?? authResult.company ?? null;
      const companyHasEncryption = isEncrypted(vaultCompany);
      const userProvidedPassword = !!values.masterPassword;

      let passwordValid: boolean | undefined = undefined;
      if (companyHasEncryption && userProvidedPassword && vaultCompany) {
        passwordValid = await validateMasterPassword(vaultCompany, values.masterPassword!);
      }

      const protocolState = analyzeVaultProtocolState(vaultCompany, userProvidedPassword, passwordValid);
      const protocolResult = handleProtocolState(protocolState, t, form, setError, setVaultProtocolState);
      if (protocolResult.shouldReturn) return;

      await saveAuthData(values.email, companyName ?? undefined);

      if (companyHasEncryption && values.masterPassword) {
        await masterPasswordService.setMasterPassword(values.masterPassword);
      }

      const preferredLanguage = authResult.preferredLanguage ?? undefined;
      if (preferredLanguage && preferredLanguage !== i18n.language) {
        await i18n.changeLanguage(preferredLanguage);
      }

      dispatch(loginSuccess({
        user: { email: values.email, company: companyName ?? undefined, preferredLanguage },
        company: companyName ?? undefined,
        vaultCompany: vaultCompany ?? undefined,
        companyEncryptionEnabled: companyHasEncryption,
      }));

      trackUserAction('login_success', 'login_form', {
        email_domain: values.email.split('@')[1] || 'unknown',
        company: companyName || 'unknown',
        has_encryption: companyHasEncryption,
        vault_protocol_state: vaultProtocolState?.toString() || 'none',
      });

      navigate('/machines');
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : t('login.errors.invalidCredentials');
      trackUserAction('login_failure', 'login_form', {
        email_domain: values.email.split('@')[1] || 'unknown',
        error_message: errorMessage || 'unknown_error',
        has_master_password: !!values.masterPassword,
      });
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const handleTFAVerification = async () => {
    try {
      const result = await verifyTFAMutation.mutateAsync({ code: twoFACode });

      if (result.isAuthorized) {
        if (result.hasTFAEnabled === false) {
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

        const { email, authResult: storedAuthResult, masterPassword } = pendingTFAData;
        const vaultCompany = storedAuthResult.vaultCompany;
        const companyName = storedAuthResult.companyName || storedAuthResult.company || null;

        await saveAuthData(email, companyName ?? undefined);

        const companyHasEncryption = isEncrypted(vaultCompany);
        if (companyHasEncryption && masterPassword) {
          await masterPasswordService.setMasterPassword(masterPassword);
        }

        const preferredLanguage = storedAuthResult.preferredLanguage ?? undefined;
        if (preferredLanguage && preferredLanguage !== i18n.language) {
          await i18n.changeLanguage(preferredLanguage);
        }

        dispatch(loginSuccess({
          user: { email, company: companyName ?? undefined, preferredLanguage },
          company: companyName ?? undefined,
          vaultCompany: vaultCompany ?? undefined,
          companyEncryptionEnabled: companyHasEncryption,
        }));

        setShowTFAModal(false);
        navigate('/machines');
      }
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
      <Flex className="w-full" style={{ maxWidth: 400 }}>
        <Flex vertical gap={24} className="w-full">
          {error && (
            <Alert
              type="error"
              message={error}
              showIcon
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

          <Flex vertical align="center" gap={8}>
            {!showAdvancedOptions &&
              vaultProtocolState !== VaultProtocolState.PASSWORD_REQUIRED &&
              vaultProtocolState !== VaultProtocolState.INVALID_PASSWORD && (
                <Button
                  type="text"
                  size="small"
                  onClick={() => setShowAdvancedOptions(true)}
                  data-testid="login-advanced-options-toggle"
                >
                  {t('auth:login.advancedOptions')} →
                </Button>
              )}

            {showAdvancedOptions && (
              <Flex vertical gap={8} className="w-full" align="center">
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
