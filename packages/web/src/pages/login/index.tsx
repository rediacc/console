import React, { useEffect, useState } from 'react';
import { Alert, Button, Flex, Form, Input, Modal, Tooltip, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { useDispatch } from 'react-redux';
import { useNavigate, useSearchParams } from 'react-router-dom';
import apiClient from '@/api/client';
import { useVerifyTFA } from '@/api/queries/twoFactor';
import logoBlack from '@/assets/logo_black.png';
import logoWhite from '@/assets/logo_white.png';
import InsecureConnectionWarning from '@/components/common/InsecureConnectionWarning';
import SandboxWarning from '@/components/common/SandboxWarning';
import { useTelemetry } from '@/components/common/TelemetryProvider';
import { featureFlags } from '@/config/featureFlags';
import { useTheme } from '@/context/ThemeContext';
import EndpointSelector from '@/pages/login/components/EndpointSelector';
import RegistrationModal from '@/pages/login/components/RegistrationModal';
import VersionSelector from '@/pages/login/components/VersionSelector';
import { apiConnectionService } from '@/services/apiConnectionService';
import { masterPasswordService } from '@/services/masterPasswordService';
import { loginSuccess } from '@/store/auth/authSlice';
import { ModalSize } from '@/types/modal';
import { hashPassword, saveAuthData } from '@/utils/auth';
import {
  generateRandomCompanyName,
  generateRandomEmail,
  generateRandomPassword,
} from '@/utils/cryptoGenerators';
import { showMessage } from '@/utils/messages';
import {
  InfoCircleOutlined,
  KeyOutlined,
  LockOutlined,
  SafetyCertificateOutlined,
  UserOutlined,
} from '@/utils/optimizedIcons';
import { isSecureContext } from '@/utils/secureContext';
import {
  analyzeVaultProtocolState,
  getVaultProtocolMessage,
  isEncrypted,
  VaultProtocolState,
  validateMasterPassword,
} from '@/utils/vaultProtocol';
import { parseAuthenticationResult } from '@rediacc/shared/api/services/auth';
import type { ApiResponse, AuthLoginResult } from '@rediacc/shared/types';
import type { FormInstance } from 'antd/es/form';

interface LoginForm {
  email: string;
  password: string;
  masterPassword?: string;
  rememberMe?: boolean;
}

const FIELD_FOCUS_DELAY_MS = 100;

interface ProtocolHandlerResult {
  shouldReturn: boolean;
}

const handleProtocolState = (
  protocolState: VaultProtocolState,
  t: (key: string) => string,
  form: FormInstance<LoginForm>,
  setError: (error: string) => void,
  setVaultProtocolState: (state: VaultProtocolState) => void
): ProtocolHandlerResult => {
  const protocolMessage = getVaultProtocolMessage(protocolState);
  const messageKey = protocolMessage.messageKey.replace('auth:', '');
  const translatedMessage = t(messageKey) || protocolMessage.message;

  switch (protocolState) {
    case VaultProtocolState.PASSWORD_REQUIRED:
      setError(translatedMessage);
      setVaultProtocolState(protocolState);
      setTimeout(() => {
        form.getFieldInstance('masterPassword')?.focus();
      }, FIELD_FOCUS_DELAY_MS);
      return { shouldReturn: true };

    case VaultProtocolState.INVALID_PASSWORD:
      setError(translatedMessage);
      setVaultProtocolState(protocolState);
      form.setFieldValue('masterPassword', '');
      setTimeout(() => {
        form.getFieldInstance('masterPassword')?.focus();
      }, FIELD_FOCUS_DELAY_MS);
      return { shouldReturn: true };

    case VaultProtocolState.PASSWORD_NOT_NEEDED:
      if (translatedMessage && translatedMessage !== messageKey) {
        showMessage('warning', translatedMessage);
      } else {
        showMessage('warning', protocolMessage.message);
      }
      return { shouldReturn: false };

    case VaultProtocolState.VALID:
      return { shouldReturn: false };

    default:
      return { shouldReturn: false };
  }
};

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
  const [endpointSelectorVisible, setEndpointSelectorVisible] = useState(() => {
    // Default visibility based on build type
    return featureFlags.getBuildType() === 'DEBUG';
  });
  const [quickRegistrationData, setQuickRegistrationData] = useState<
    | {
        email: string;
        password: string;
        companyName: string;
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
  const [form] = Form.useForm<LoginForm>();
  const [twoFAForm] = Form.useForm();
  const { theme } = useTheme();
  const { t, i18n } = useTranslation(['auth', 'common']);
  const verifyTFAMutation = useVerifyTFA();
  const { trackUserAction } = useTelemetry();

  // Check URL parameters for registration flag
  useEffect(() => {
    const checkRegistrationMode = async () => {
      const registerParam = searchParams.get('register');

      if (registerParam === 'quick') {
        // Check if we're in CI/TEST mode
        try {
          const ciMode = await apiConnectionService.isCiMode();

          if (ciMode) {
            // Generate random registration data for quick registration
            const randomData = {
              email: generateRandomEmail(),
              password: generateRandomPassword(),
              companyName: generateRandomCompanyName(),
              activationCode: '111111', // Fixed code for CI/TEST mode
            };

            setQuickRegistrationData(randomData);
            setIsQuickRegistration(true);
            setShowRegistration(true);
          } else {
            // Not in CI mode, fall back to normal registration
            console.warn('Quick registration is only available in CI/TEST mode');
            showMessage('warning', 'Quick registration is only available in CI/TEST mode');
            setShowRegistration(true);
          }
        } catch (error) {
          console.error('Could not check CI mode, falling back to normal registration', error);
          setShowRegistration(true);
        }
      } else if (registerParam === 'manual') {
        // Manual registration mode
        setShowRegistration(true);
      }

      // Clean up the URL to remove the parameter
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

        // Check if running on localhost
        const onLocalhost =
          window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';

        // Toggle global power mode (or localhost mode if on localhost)
        const newState = featureFlags.togglePowerMode();

        // Update visibility for endpoint selector
        setEndpointSelectorVisible(newState);

        // Show toast with current state - different message for localhost vs non-localhost
        const message = onLocalhost
          ? newState
            ? 'Localhost Mode - All features enabled'
            : 'Localhost Mode - All features disabled'
          : newState
            ? 'Advanced options enabled'
            : 'Advanced options disabled';

        showMessage('info', message);

        // Console log for debugging
      }
    };

    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, []);

  // Check if connection is secure (required for Web Crypto API)
  useEffect(() => {
    const secure = isSecureContext();
    setIsConnectionSecure(secure);
    if (!secure) {
      console.warn('[LoginPage] Insecure connection detected. Web Crypto API unavailable.');
    }
  }, []);

  // Health check completion callback
  const handleHealthCheckComplete = (hasHealthyEndpoint: boolean) => {
    const buildType = featureFlags.getBuildType();
    const powerModeEnabled = featureFlags.isPowerModeEnabled();

    // Determine visibility based on build type and health status
    if (buildType === 'DEBUG') {
      // DEBUG: Always show endpoint selector
      setEndpointSelectorVisible(true);
    } else if (buildType === 'RELEASE') {
      if (powerModeEnabled) {
        // Power mode overrides everything
        setEndpointSelectorVisible(true);
      } else if (hasHealthyEndpoint) {
        // Hide when healthy and no power mode
        setEndpointSelectorVisible(false);
      } else {
        // Fallback: show when endpoint health fails
        setEndpointSelectorVisible(true);
      }
    }
  };

  const handleLogin = async (values: LoginForm) => {
    setLoading(true);
    setError(null);
    setVaultProtocolState(null);

    // Track login attempt
    trackUserAction('login_attempt', 'login_form', {
      email_domain: values.email.split('@')[1] || 'unknown',
      has_master_password: !!values.masterPassword,
      is_remember_me: !!values.rememberMe,
    });

    try {
      // Hash password
      const passwordHash = await hashPassword(values.password);

      // Attempt login
      const loginResponse = await apiClient.login(values.email, passwordHash);

      if (loginResponse.failure !== 0) {
        throw new Error(loginResponse.errors?.join('; ') || 'Login failed');
      }

      // Extract user data from response
      const authResult = parseAuthenticationResult(loginResponse as ApiResponse);

      // Check if TFA is required
      const isAuthorized = authResult.isAuthorized;
      const authenticationStatus = authResult.authenticationStatus;

      // If TFA is required but not authorized, show TFA modal
      if (authenticationStatus === 'TFA_REQUIRED' && !isAuthorized) {
        // Store the login data for after TFA verification
        // Note: Token is already saved by response interceptor
        setPendingTFAData({
          email: values.email,
          authResult,
          masterPassword: values.masterPassword,
        });
        setShowTFAModal(true);
        setLoading(false);
        return;
      }

      // Extract VaultCompany and company name from response
      const vaultCompany = authResult.vaultCompany;
      const companyName = authResult.companyName ?? authResult.company ?? null;

      // Analyze vault protocol state
      const companyHasEncryption = isEncrypted(vaultCompany);
      const userProvidedPassword = !!values.masterPassword;

      // Validate master password if company has encryption and user provided password
      let passwordValid: boolean | undefined = undefined;
      if (companyHasEncryption && userProvidedPassword && vaultCompany) {
        passwordValid = await validateMasterPassword(vaultCompany, values.masterPassword!);
      }

      // Determine protocol state
      const protocolState = analyzeVaultProtocolState(
        vaultCompany,
        userProvidedPassword,
        passwordValid
      );

      // Handle different protocol states
      const protocolResult = handleProtocolState(
        protocolState,
        t,
        form,
        setError,
        setVaultProtocolState
      );
      if (protocolResult.shouldReturn) {
        return;
      }

      // Save auth data (email and company only - token is managed by interceptor)
      await saveAuthData(values.email, companyName ?? undefined);

      // Store master password in secure memory if encryption is enabled
      if (companyHasEncryption && values.masterPassword) {
        await masterPasswordService.setMasterPassword(values.masterPassword);
      }

      // Apply user's preferred language if available
      const preferredLanguage = authResult.preferredLanguage ?? undefined;
      if (preferredLanguage && preferredLanguage !== i18n.language) {
        await i18n.changeLanguage(preferredLanguage);
      }

      // Update Redux store with all relevant data (token and masterPassword are now stored separately for security)
      dispatch(
        loginSuccess({
          user: { email: values.email, company: companyName ?? undefined, preferredLanguage },
          company: companyName ?? undefined,
          vaultCompany: vaultCompany ?? undefined,
          companyEncryptionEnabled: companyHasEncryption,
        })
      );

      // Track successful login
      trackUserAction('login_success', 'login_form', {
        email_domain: values.email.split('@')[1] || 'unknown',
        company: companyName || 'unknown',
        has_encryption: companyHasEncryption,
        vault_protocol_state: vaultProtocolState?.toString() || 'none',
      });

      navigate('/machines');
    } catch (error: unknown) {
      const errorMessage =
        error instanceof Error ? error.message : t('login.errors.invalidCredentials');
      // Track login failure
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
      // Token is already set by login response interceptor
      // No manual token management needed - interceptor handles rotation

      // Verify the TFA code
      const result = await verifyTFAMutation.mutateAsync({ code: twoFACode });

      if (result.isAuthorized) {
        // Check if this is because TFA is not enabled
        if (result.hasTFAEnabled === false) {
          showMessage('info', 'Two-factor authentication is not enabled for this account.');
          setShowTFAModal(false);
          setTwoFACode('');
          return;
        }

        // Continue with the login process using stored data
        if (!pendingTFAData) {
          setLoading(false);
          setShowTFAModal(false);
          setTwoFACode('');
          return;
        }
        const { email, authResult: storedAuthResult, masterPassword } = pendingTFAData;

        // Extract VaultCompany and company name from stored userData
        const vaultCompany = storedAuthResult.vaultCompany;
        const companyName = storedAuthResult.companyName || storedAuthResult.company || null;

        // Save auth data (email and company only - token is managed by interceptor)
        await saveAuthData(email, companyName ?? undefined);

        // Store master password if encryption is enabled
        const companyHasEncryption = isEncrypted(vaultCompany);
        if (companyHasEncryption && masterPassword) {
          await masterPasswordService.setMasterPassword(masterPassword);
        }

        // Apply user's preferred language if available
        const preferredLanguage = storedAuthResult.preferredLanguage ?? undefined;
        if (preferredLanguage && preferredLanguage !== i18n.language) {
          await i18n.changeLanguage(preferredLanguage);
        }

        // Update Redux store
        dispatch(
          loginSuccess({
            user: { email, company: companyName ?? undefined, preferredLanguage },
            company: companyName ?? undefined,
            vaultCompany: vaultCompany ?? undefined,
            companyEncryptionEnabled: companyHasEncryption,
          })
        );

        // Close modal and navigate
        setShowTFAModal(false);
        navigate('/machines');
      }
    } catch {
      // Error is handled by the mutation
      // No need to clear token - it's managed by interceptor
    }
  };

  return (
    <>
      <SandboxWarning />
      <Flex style={{ width: '100%', maxWidth: 520 }}>
        <Flex vertical gap={24} style={{ width: '100%' }}>
          <Flex
            style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 64 }}
          >
            <img src={theme === 'dark' ? logoWhite : logoBlack} alt="Rediacc Logo" />
          </Flex>

          {error && (
            <Alert
              type="error"
              style={{ fontSize: 14, fontWeight: 500 }}
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

          <Form
            form={form}
            name="login"
            onFinish={handleLogin}
            layout="vertical"
            requiredMark={false}
          >
            <Form.Item
              name="email"
              label={
                <label
                  htmlFor="login-email-input"
                  style={{ fontSize: 14, fontWeight: 500, display: 'block' }}
                >
                  {t('auth:login.email')}
                </label>
              }
              rules={[
                { required: true, message: t('common:messages.required') },
                { type: 'email', message: t('common:messages.invalidEmail') },
              ]}
              validateStatus={error ? 'error' : undefined}
            >
              <Input
                id="login-email-input"
                prefix={<UserOutlined />}
                placeholder={t('auth:login.emailPlaceholder')}
                autoComplete="email"
                data-testid="login-email-input"
                aria-label={t('auth:login.email')}
                aria-describedby="email-error"
              />
            </Form.Item>

            <Form.Item
              name="password"
              label={
                <label
                  htmlFor="login-password-input"
                  style={{ fontSize: 14, fontWeight: 500, display: 'block' }}
                >
                  {t('auth:login.password')}
                </label>
              }
              rules={[{ required: true, message: t('common:messages.required') }]}
              validateStatus={error ? 'error' : undefined}
            >
              <Input.Password
                id="login-password-input"
                prefix={<LockOutlined />}
                placeholder={t('auth:login.passwordPlaceholder')}
                autoComplete="current-password"
                data-testid="login-password-input"
                aria-label={t('auth:login.password')}
                aria-describedby="password-error"
              />
            </Form.Item>

            {/* Progressive disclosure: Show master password field only when needed */}
            {(vaultProtocolState === VaultProtocolState.PASSWORD_REQUIRED ||
              vaultProtocolState === VaultProtocolState.INVALID_PASSWORD ||
              (showAdvancedOptions && featureFlags.isEnabled('loginAdvancedOptions'))) && (
              <Flex vertical>
                <Form.Item
                  name="masterPassword"
                  label={
                    <label
                      htmlFor="login-master-password-input"
                      style={{ display: 'flex', alignItems: 'center', gap: 8 }}
                    >
                      <Typography.Text>{t('auth:login.masterPassword')}</Typography.Text>
                      <Tooltip title={t('auth:login.masterPasswordTooltip')}>
                        <InfoCircleOutlined />
                      </Tooltip>
                    </label>
                  }
                  validateStatus={
                    vaultProtocolState === VaultProtocolState.PASSWORD_REQUIRED ||
                    vaultProtocolState === VaultProtocolState.INVALID_PASSWORD
                      ? 'error'
                      : undefined
                  }
                  required={vaultProtocolState === VaultProtocolState.PASSWORD_REQUIRED}
                >
                  <Input.Password
                    id="login-master-password-input"
                    prefix={<KeyOutlined />}
                    placeholder={t('auth:login.masterPasswordPlaceholder')}
                    autoComplete="off"
                    data-testid="login-master-password-input"
                    aria-label={t('auth:login.masterPassword')}
                    aria-describedby="master-password-error"
                  />
                </Form.Item>
              </Flex>
            )}

            {/* Show advanced options toggle when master password is not yet shown */}
            {featureFlags.isEnabled('loginAdvancedOptions') &&
              !(
                vaultProtocolState === VaultProtocolState.PASSWORD_REQUIRED ||
                vaultProtocolState === VaultProtocolState.INVALID_PASSWORD ||
                showAdvancedOptions
              ) && (
                <Flex style={{ textAlign: 'center' }} justify="center">
                  <Button
                    type="text"
                    size="small"
                    style={{ height: 'auto' }}
                    onClick={() => {
                      setShowAdvancedOptions(true);
                      setTimeout(() => {
                        form.getFieldInstance('masterPassword')?.focus();
                      }, 100);
                    }}
                  >
                    {t('auth:login.needMasterPassword')} →
                  </Button>
                </Flex>
              )}

            <Form.Item>
              <Tooltip
                title={
                  !isConnectionSecure
                    ? t('auth:login.insecureConnection.buttonDisabled')
                    : undefined
                }
              >
                <Button
                  type="primary"
                  htmlType="submit"
                  block
                  loading={loading}
                  disabled={!isConnectionSecure}
                  data-testid="login-submit-button"
                >
                  {loading ? t('auth:login.signingIn') : t('auth:login.signIn')}
                </Button>
              </Tooltip>
            </Form.Item>
          </Form>

          <Flex style={{ textAlign: 'center' }} justify="center">
            <Typography.Text>
              {t('auth:login.noAccount')}{' '}
              <a
                onClick={() => setShowRegistration(true)}
                tabIndex={0}
                role="button"
                aria-label={t('auth:login.register')}
                data-testid="login-register-link"
                style={{
                  fontWeight: 500,
                  textDecoration: 'none',
                  cursor: 'pointer',
                  display: 'inline-block',
                }}
              >
                {t('auth:login.register')}
              </a>
            </Typography.Text>
          </Flex>

          {/* Endpoint selector and version display */}
          <Flex vertical style={{ textAlign: 'center' }} align="center">
            {/* Endpoint Selector - Power Mode Feature */}
            {endpointSelectorVisible && (
              <Flex style={{ textAlign: 'center' }} justify="center">
                <EndpointSelector onHealthCheckComplete={handleHealthCheckComplete} />
              </Flex>
            )}

            {/* Always-visible version display */}
            <VersionSelector />
          </Flex>
        </Flex>
      </Flex>

      {/* TFA Verification Modal */}
      <Modal
        title={
          <Flex align="center" gap={8}>
            <SafetyCertificateOutlined />
            <Typography.Text>{t('login.twoFactorAuth.title')}</Typography.Text>
          </Flex>
        }
        open={showTFAModal}
        onCancel={() => {
          setShowTFAModal(false);
          setTwoFACode('');
          setPendingTFAData(null);
        }}
        footer={null}
        className={ModalSize.Medium}
      >
        <Flex vertical gap={16} style={{ width: '100%' }}>
          <Alert
            message={t('login.twoFactorAuth.required')}
            description={t('login.twoFactorAuth.description')}
            type="info"
            showIcon
            data-testid="tfa-info-alert"
          />

          <Form form={twoFAForm} onFinish={() => handleTFAVerification()} layout="vertical">
            <Form.Item
              name="twoFACode"
              label={t('login.twoFactorAuth.codeLabel')}
              rules={[
                { required: true, message: t('common:messages.required') },
                { len: 6, message: t('login.twoFactorAuth.codeLength') },
                { pattern: /^\d{6}$/, message: t('login.twoFactorAuth.codeFormat') },
              ]}
            >
              <Input
                style={{ fontSize: 16, letterSpacing: '0.5em', textAlign: 'center' }}
                placeholder={t('login.twoFactorAuth.codePlaceholder')}
                value={twoFACode}
                onChange={(e) => setTwoFACode(e.target.value)}
                autoComplete="off"
                maxLength={6}
                data-testid="tfa-code-input"
              />
            </Form.Item>

            <Form.Item style={{ marginBottom: 0 }}>
              <Flex justify="flex-end" style={{ width: '100%' }}>
                <Button
                  onClick={() => {
                    setShowTFAModal(false);
                    setTwoFACode('');
                    setPendingTFAData(null);
                  }}
                >
                  {t('common:general.cancel')}
                </Button>
                <Button
                  type="primary"
                  htmlType="submit"
                  loading={verifyTFAMutation.isPending}
                  disabled={twoFACode.length !== 6}
                  data-testid="tfa-verify-button"
                >
                  {t('login.twoFactorAuth.verify')}
                </Button>
              </Flex>
            </Form.Item>
          </Form>
        </Flex>
      </Modal>

      {/* Registration Modal */}
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
          // Auto-login after quick registration
          if (isQuickRegistration) {
            setShowRegistration(false);

            // Perform login with the registration credentials
            await handleLogin({
              email: credentials.email,
              password: credentials.password,
            });
          }
        }}
      />
    </>
  );
};

export default LoginPage;
