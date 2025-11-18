import React, { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useDispatch } from 'react-redux'
import { Form, Button, Typography, Alert, Tooltip, Modal } from 'antd'
import { UserOutlined, LockOutlined, KeyOutlined, InfoCircleOutlined, SafetyCertificateOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { loginSuccess } from '@/store/auth/authSlice'
import { saveAuthData } from '@/utils/auth'
import { hashPassword } from '@/utils/auth'
import apiClient from '@/api/client'
import { showMessage } from '@/utils/messages'
import { useTheme } from '@/context/ThemeContext'
import VersionSelector from '@/components/common/VersionSelector'
import EndpointSelector from '@/components/common/EndpointSelector'
import logoBlack from '@/assets/logo_black.png'
import logoWhite from '@/assets/logo_white.png'
import { spacing } from '@/utils/styleConstants'
import { ModalSize } from '@/types/modal'
import { featureFlags } from '@/config/featureFlags'
import { 
  isEncrypted, 
  validateMasterPassword, 
  VaultProtocolState, 
  analyzeVaultProtocolState,
  getVaultProtocolMessage 
} from '@/utils/vaultProtocol'
import { masterPasswordService } from '@/services/masterPasswordService'
import { useTelemetry } from '@/components/common/TelemetryProvider'
import { useVerifyTFA } from '@/api/queries/twoFactor'
import RegistrationModal from '@/components/auth/RegistrationModal'
import { generateRandomEmail, generateRandomCompanyName, generateRandomPassword } from '@/utils/cryptoGenerators'
import SandboxWarning from '@/components/common/SandboxWarning'
import {
  LoginContainer,
  LogoContainer,
  StyledAlert,
  FormLabel,
  MasterPasswordLabel,
  MasterPasswordFormItem,
  AdvancedOptionsContainer,
  AdvancedOptionsButton,
  LoginButton,
  RegisterContainer,
  RegisterLink,
  SelectorsContainer,
  TFAModalTitle,
  TFACodeInput,
  TFAButtonContainer,
  TFAVerifyButton,
  StyledInput,
  StyledPasswordInput,
  FullWidthStack,
  LargeGapFormItem,
  NoMarginFormItem,
  SelectorSpacer,
} from './styles'

const { Text } = Typography

interface LoginForm {
  email: string
  password: string
  masterPassword?: string
  rememberMe?: boolean
}

const FIELD_FOCUS_DELAY_MS = 100

interface ProtocolHandlerResult {
  shouldReturn: boolean
}

const handleProtocolState = (
  protocolState: VaultProtocolState,
  t: (key: string) => string,
  form: any,
  setError: (error: string) => void,
  setVaultProtocolState: (state: VaultProtocolState) => void
): ProtocolHandlerResult => {
  const protocolMessage = getVaultProtocolMessage(protocolState)
  const messageKey = protocolMessage.messageKey.replace('auth:', '')
  const translatedMessage = t(messageKey) || protocolMessage.message

  switch (protocolState) {
    case VaultProtocolState.PASSWORD_REQUIRED:
      setError(translatedMessage)
      setVaultProtocolState(protocolState)
      setTimeout(() => {
        form.getFieldInstance('masterPassword')?.focus()
      }, FIELD_FOCUS_DELAY_MS)
      return { shouldReturn: true }
      
    case VaultProtocolState.INVALID_PASSWORD:
      setError(translatedMessage)
      setVaultProtocolState(protocolState)
      form.setFieldValue('masterPassword', '')
      setTimeout(() => {
        form.getFieldInstance('masterPassword')?.focus()
      }, FIELD_FOCUS_DELAY_MS)
      return { shouldReturn: true }
      
    case VaultProtocolState.PASSWORD_NOT_NEEDED:
      if (translatedMessage && translatedMessage !== messageKey) {
        showMessage('warning', translatedMessage)
      } else {
        showMessage('warning', protocolMessage.message)
      }
      return { shouldReturn: false }
      
    case VaultProtocolState.VALID:
      return { shouldReturn: false }
      
    default:
      return { shouldReturn: false }
  }
}

const LoginPage: React.FC = () => {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [vaultProtocolState, setVaultProtocolState] = useState<VaultProtocolState | null>(null)
  const [showTFAModal, setShowTFAModal] = useState(false)
  const [pendingTFAData, setPendingTFAData] = useState<any>(null)
  const [twoFACode, setTwoFACode] = useState('')
  const [showRegistration, setShowRegistration] = useState(false)
  const [showAdvancedOptions, setShowAdvancedOptions] = useState(false)
  const [endpointSelectorVisible, setEndpointSelectorVisible] = useState(() => {
    // Default visibility based on build type
    return featureFlags.getBuildType() === 'DEBUG'
  })
  const [versionSelectorVisible, setVersionSelectorVisible] = useState(() => {
    // Default visibility based on build type
    return featureFlags.getBuildType() === 'DEBUG'
  })
  const [quickRegistrationData, setQuickRegistrationData] = useState<{
    email: string
    password: string
    companyName: string
    activationCode: string
  } | undefined>(undefined)
  const [isQuickRegistration, setIsQuickRegistration] = useState(false)
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const dispatch = useDispatch()
  const [form] = Form.useForm<LoginForm>()
  const [twoFAForm] = Form.useForm()
  const { theme } = useTheme()
  const { t, i18n } = useTranslation(['auth', 'common'])
  const verifyTFAMutation = useVerifyTFA()
  const { trackUserAction } = useTelemetry()

  // Check URL parameters for registration flag
  useEffect(() => {
    const checkRegistrationMode = async () => {
      const registerParam = searchParams.get('register')

      if (registerParam === 'quick') {
        // Check if we're in CI/TEST mode
        try {
          const response = await (apiClient as any).client.get('/health')
          const ciMode = response.data?.ciMode === true

          if (ciMode) {
            // Generate random registration data for quick registration
            const randomData = {
              email: generateRandomEmail(),
              password: generateRandomPassword(),
              companyName: generateRandomCompanyName(),
              activationCode: '111111' // Fixed code for CI/TEST mode
            }

            console.log('🚀 Quick Registration Mode (CI/TEST Only)', {
              email: randomData.email,
              company: randomData.companyName,
              message: 'Using verification code: 111111'
            })

            setQuickRegistrationData(randomData)
            setIsQuickRegistration(true)
            setShowRegistration(true)
          } else {
            // Not in CI mode, fall back to normal registration
            console.warn('Quick registration is only available in CI/TEST mode')
            showMessage('warning', 'Quick registration is only available in CI/TEST mode')
            setShowRegistration(true)
          }
        } catch (error) {
          console.error('Could not check CI mode, falling back to normal registration', error)
          setShowRegistration(true)
        }
      } else if (registerParam === 'manual') {
        // Manual registration mode
        setShowRegistration(true)
      }
      
      // Clean up the URL to remove the parameter
      if (registerParam) {
        searchParams.delete('register')
        const newUrl = searchParams.toString() 
          ? `${window.location.pathname}?${searchParams.toString()}`
          : window.location.pathname
        window.history.replaceState({}, '', newUrl)
      }
    }
    
    checkRegistrationMode()
  }, [searchParams])

  // Keyboard shortcut handler for global power mode (Ctrl+Shift+E)
  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && e.key === 'E') {
        e.preventDefault()

        // Check if running on localhost
        const onLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'

        // Toggle global power mode (or localhost mode if on localhost)
        const newState = featureFlags.togglePowerMode()

        // Update visibility for both selectors
        setEndpointSelectorVisible(newState)
        setVersionSelectorVisible(newState)

        // Show toast with current state - different message for localhost vs non-localhost
        const message = onLocalhost
          ? (newState ? 'Localhost Mode - All features enabled' : 'Localhost Mode - All features disabled')
          : (newState ? 'Advanced options enabled' : 'Advanced options disabled')

        showMessage('info', message)

        // Console log for debugging
        const mode = onLocalhost ? 'Localhost mode' : 'Power mode'
        console.log(`[${onLocalhost ? 'LocalhostMode' : 'PowerMode'}] ${mode} ${newState ? 'enabled' : 'disabled'} via Ctrl+Shift+E`)
      }
    }

    window.addEventListener('keydown', handleKeyPress)
    return () => window.removeEventListener('keydown', handleKeyPress)
  }, [])

  // Health check completion callback
  const handleHealthCheckComplete = (hasHealthyEndpoint: boolean) => {
    const buildType = featureFlags.getBuildType()
    const powerModeEnabled = featureFlags.isPowerModeEnabled()

    console.log('[LoginPage] Health check complete:', {
      buildType,
      hasHealthyEndpoint,
      powerModeEnabled,
      currentVisibility: {
        endpoint: endpointSelectorVisible,
        version: versionSelectorVisible
      }
    })

    // Determine visibility based on build type and health status
    if (buildType === 'DEBUG') {
      // DEBUG: Always show both
      setEndpointSelectorVisible(true)
      setVersionSelectorVisible(true)
    } else if (buildType === 'RELEASE') {
      if (powerModeEnabled) {
        // Power mode overrides everything - show both
        setEndpointSelectorVisible(true)
        setVersionSelectorVisible(true)
      } else if (!hasHealthyEndpoint) {
        // Fallback: show both when endpoint health fails
        setEndpointSelectorVisible(true)
        setVersionSelectorVisible(true)
      } else {
        // Hide both when healthy and no power mode
        setEndpointSelectorVisible(false)
        setVersionSelectorVisible(false)
      }
    }
  }

  const handleLogin = async (values: LoginForm) => {
    setLoading(true)
    setError(null)
    setVaultProtocolState(null)

    // Track login attempt
    trackUserAction('login_attempt', 'login_form', {
      email_domain: values.email.split('@')[1] || 'unknown',
      has_master_password: !!values.masterPassword,
      is_remember_me: !!values.rememberMe
    })

    try {
      // Hash password
      const passwordHash = await hashPassword(values.password)

      // Attempt login
      const loginResponse = await apiClient.login(values.email, passwordHash)
      
      if (loginResponse.failure !== 0) {
        throw new Error(loginResponse.errors?.join('; ') || 'Login failed')
      }

      // Extract user data from response
      const userData = loginResponse.resultSets[0].data[0]

      // Check if TFA is required
      const isAuthorized = userData.isAuthorized
      const authenticationStatus = userData.authenticationStatus

      // If TFA is required but not authorized, show TFA modal
      if (authenticationStatus === 'TFA_REQUIRED' && !isAuthorized) {
        // Store the login data for after TFA verification
        // Note: Token is already saved by response interceptor
        setPendingTFAData({
          email: values.email,
          userData,
          masterPassword: values.masterPassword
        })
        setShowTFAModal(true)
        setLoading(false)
        return
      }

      // Extract VaultCompany and company name from response
      const vaultCompany = userData.vaultCompany || null
      const companyName = userData.CompanyName || userData.company || null

      // Analyze vault protocol state
      const companyHasEncryption = isEncrypted(vaultCompany)
      const userProvidedPassword = !!values.masterPassword

      // Validate master password if company has encryption and user provided password
      let passwordValid: boolean | undefined = undefined
      if (companyHasEncryption && userProvidedPassword) {
        passwordValid = await validateMasterPassword(
          vaultCompany,
          values.masterPassword!
        )
      }

      // Determine protocol state
      const protocolState = analyzeVaultProtocolState(
        vaultCompany,
        userProvidedPassword,
        passwordValid
      )

      // Handle different protocol states
      const protocolResult = handleProtocolState(protocolState, t, form, setError, setVaultProtocolState)
      if (protocolResult.shouldReturn) {
        return
      }

      // Save auth data (email and company only - token is managed by interceptor)
      await saveAuthData(values.email, companyName)

      // Store master password in secure memory if encryption is enabled
      if (companyHasEncryption && values.masterPassword) {
        await masterPasswordService.setMasterPassword(values.masterPassword)
      }

      // Apply user's preferred language if available
      const preferredLanguage = userData.preferredLanguage
      if (preferredLanguage && preferredLanguage !== i18n.language) {
        await i18n.changeLanguage(preferredLanguage)
      }

      // Update Redux store with all relevant data (token and masterPassword are now stored separately for security)
      dispatch(loginSuccess({
        user: { email: values.email, company: companyName, preferredLanguage },
        company: companyName,
        vaultCompany: vaultCompany,
        companyEncryptionEnabled: companyHasEncryption,
      }))

      // Track successful login
      trackUserAction('login_success', 'login_form', {
        email_domain: values.email.split('@')[1] || 'unknown',
        company: companyName || 'unknown',
        has_encryption: companyHasEncryption,
        vault_protocol_state: vaultProtocolState?.toString() || 'none'
      })

      navigate('/machines')
    } catch (error: any) {
      // Track login failure
      trackUserAction('login_failure', 'login_form', {
        email_domain: values.email.split('@')[1] || 'unknown',
        error_message: error.message || 'unknown_error',
        has_master_password: !!values.masterPassword
      })

      setError(error.message || t('login.errors.invalidCredentials'))
    } finally {
      setLoading(false)
    }
  }

  const handleTFAVerification = async () => {
    try {
      // Token is already set by login response interceptor
      // No manual token management needed - interceptor handles rotation

      // Verify the TFA code
      const result = await verifyTFAMutation.mutateAsync({ code: twoFACode })

      if (result.isAuthorized) {
        // Check if this is because TFA is not enabled
        if (result.hasTFAEnabled === false) {
          showMessage('info', 'Two-factor authentication is not enabled for this account.')
          setShowTFAModal(false)
          setTwoFACode('')
          return
        }

        // Continue with the login process using stored data
        const { email, userData, masterPassword } = pendingTFAData

        // Extract VaultCompany and company name from stored userData
        const vaultCompany = userData.vaultCompany || null
        const companyName = userData.CompanyName || userData.company || null

        // Save auth data (email and company only - token is managed by interceptor)
        await saveAuthData(email, companyName)

        // Store master password if encryption is enabled
        const companyHasEncryption = isEncrypted(vaultCompany)
        if (companyHasEncryption && masterPassword) {
          await masterPasswordService.setMasterPassword(masterPassword)
        }

        // Apply user's preferred language if available
        const preferredLanguage = userData.preferredLanguage
        if (preferredLanguage && preferredLanguage !== i18n.language) {
          await i18n.changeLanguage(preferredLanguage)
        }

        // Update Redux store
        dispatch(loginSuccess({
          user: { email, company: companyName, preferredLanguage },
          company: companyName,
          vaultCompany: vaultCompany,
          companyEncryptionEnabled: companyHasEncryption,
        }))

        // Close modal and navigate
        setShowTFAModal(false)
        navigate('/machines')
      }
    } catch (error: any) {
      // Error is handled by the mutation
      // No need to clear token - it's managed by interceptor
    }
  }

  return (
    <>
      <SandboxWarning />
      <LoginContainer>
          <FullWidthStack direction="vertical" size={spacing('XL')}>
            <LogoContainer>
              <img
                src={theme === 'dark' ? logoWhite : logoBlack}
                alt="Rediacc Logo"
              />
            </LogoContainer>

            {error && (
              <StyledAlert
                message={error}
                type="error"
                showIcon
                closable
                onClose={() => setError(null)}
                data-testid="login-error-alert"
                id="login-error-message"
                role="alert"
                aria-live="polite"
              />
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
                <FormLabel htmlFor="login-email-input">
                  {t('auth:login.email')}
                </FormLabel>
              }
            rules={[
              { required: true, message: t('common:messages.required') },
              { type: 'email', message: t('common:messages.invalidEmail') },
            ]}
            validateStatus={error ? 'error' : undefined}
          >
            <StyledInput
              id="login-email-input"
              prefix={<UserOutlined />}
              placeholder={t('auth:login.emailPlaceholder')}
              size="large"
              autoComplete="email"
              data-testid="login-email-input"
              aria-label={t('auth:login.email')}
              aria-describedby="email-error"
            />
          </Form.Item>

            <LargeGapFormItem
              name="password"
              label={
                <FormLabel htmlFor="login-password-input">
                  {t('auth:login.password')}
                </FormLabel>
              }
            rules={[{ required: true, message: t('common:messages.required') }]}
            validateStatus={error ? 'error' : undefined}
          >
            <StyledPasswordInput
              id="login-password-input"
              prefix={<LockOutlined />}
              placeholder={t('auth:login.passwordPlaceholder')}
              size="large"
              autoComplete="current-password"
              data-testid="login-password-input"
              aria-label={t('auth:login.password')}
              aria-describedby="password-error"
            />
          </LargeGapFormItem>

            {/* Progressive disclosure: Show master password field only when needed */}
            {(vaultProtocolState === VaultProtocolState.PASSWORD_REQUIRED ||
              vaultProtocolState === VaultProtocolState.INVALID_PASSWORD ||
              (showAdvancedOptions && featureFlags.isEnabled('loginAdvancedOptions'))) && (
              <MasterPasswordFormItem>
                <Form.Item
                  name="masterPassword"
                  label={
                    <MasterPasswordLabel htmlFor="login-master-password-input">
                      <span>{t('auth:login.masterPassword')}</span>
                      <Tooltip title={t('auth:login.masterPasswordTooltip')}>
                        <InfoCircleOutlined />
                      </Tooltip>
                    </MasterPasswordLabel>
                  }
                  validateStatus={vaultProtocolState === VaultProtocolState.PASSWORD_REQUIRED || vaultProtocolState === VaultProtocolState.INVALID_PASSWORD ? 'error' : undefined}
                  required={vaultProtocolState === VaultProtocolState.PASSWORD_REQUIRED}
                >
                  <StyledPasswordInput
                    id="login-master-password-input"
                    prefix={<KeyOutlined />}
                    placeholder={t('auth:login.masterPasswordPlaceholder')}
                    size="large"
                    autoComplete="off"
                    data-testid="login-master-password-input"
                    aria-label={t('auth:login.masterPassword')}
                    aria-describedby="master-password-error"
                  />
                </Form.Item>
              </MasterPasswordFormItem>
            )}
          
            {/* Show advanced options toggle when master password is not yet shown */}
            {featureFlags.isEnabled('loginAdvancedOptions') &&
             !(vaultProtocolState === VaultProtocolState.PASSWORD_REQUIRED ||
              vaultProtocolState === VaultProtocolState.INVALID_PASSWORD ||
              showAdvancedOptions) && (
              <AdvancedOptionsContainer>
                <AdvancedOptionsButton
                  type="text"
                  size="small"
                  onClick={() => {
                    setShowAdvancedOptions(true)
                    setTimeout(() => {
                      form.getFieldInstance('masterPassword')?.focus()
                    }, 100)
                  }}
                >
                  {t('auth:login.needMasterPassword')} →
                </AdvancedOptionsButton>
              </AdvancedOptionsContainer>
            )}

            <LargeGapFormItem>
              <LoginButton
                type="primary"
                htmlType="submit"
                size="large"
                block
                loading={loading}
                data-testid="login-submit-button"
              >
                {loading ? t('auth:login.signingIn') : t('auth:login.signIn')}
              </LoginButton>
            </LargeGapFormItem>
          
          </Form>

            <RegisterContainer>
              <Text type="secondary">
                {t('auth:login.noAccount')}{' '}
                <RegisterLink
                  onClick={() => setShowRegistration(true)}
                  tabIndex={0}
                  role="button"
                  aria-label={t('auth:login.register')}
                  data-testid="login-register-link"
                >
                  {t('auth:login.register')}
                </RegisterLink>
              </Text>
            </RegisterContainer>

            {/* Endpoint and Version selectors */}
            <SelectorsContainer>
              {/* Advanced Options Container - Power Mode Features */}
              {(endpointSelectorVisible || versionSelectorVisible) && (
                <AdvancedOptionsContainer>
                  {/* Endpoint Selector */}
                  {endpointSelectorVisible && (
                    <SelectorSpacer $hasSpacing={versionSelectorVisible}>
                      <EndpointSelector onHealthCheckComplete={handleHealthCheckComplete} />
                    </SelectorSpacer>
                  )}

                  {/* Version Selector (Dropdown Mode) */}
                  {versionSelectorVisible && (
                    <VersionSelector showDropdown={true} />
                  )}
                </AdvancedOptionsContainer>
              )}

              {/* Always-visible version display (Static Text Mode) */}
              <VersionSelector showDropdown={false} />
            </SelectorsContainer>
          </FullWidthStack>
        </LoginContainer>

      {/* TFA Verification Modal */}
      <Modal
        title={
          <TFAModalTitle>
            <SafetyCertificateOutlined />
            <span>{t('login.twoFactorAuth.title')}</span>
          </TFAModalTitle>
        }
        open={showTFAModal}
        onCancel={() => {
          setShowTFAModal(false)
          setTwoFACode('')
          setPendingTFAData(null)
        }}
        footer={null}
        className={ModalSize.Medium}
      >
        <FullWidthStack direction="vertical" size={spacing('MD')}>
          <Alert
            message={t('login.twoFactorAuth.required')}
            description={t('login.twoFactorAuth.description')}
            type="info"
            showIcon
            data-testid="tfa-info-alert"
          />
          
          <Form
            form={twoFAForm}
            onFinish={() => handleTFAVerification()}
            layout="vertical"
          >
            <Form.Item
              name="twoFACode"
              label={t('login.twoFactorAuth.codeLabel')}
              rules={[
                { required: true, message: t('common:messages.required') },
                { len: 6, message: t('login.twoFactorAuth.codeLength') },
                { pattern: /^\d{6}$/, message: t('login.twoFactorAuth.codeFormat') }
              ]}
            >
              <TFACodeInput
                size="large"
                placeholder={t('login.twoFactorAuth.codePlaceholder')}
                value={twoFACode}
                onChange={(e) => setTwoFACode(e.target.value)}
                autoComplete="off"
                maxLength={6}
                data-testid="tfa-code-input"
              />
            </Form.Item>
            
            <NoMarginFormItem>
              <TFAButtonContainer>
                <Button
                  onClick={() => {
                    setShowTFAModal(false)
                    setTwoFACode('')
                    setPendingTFAData(null)
                  }}
                >
                  {t('common:general.cancel')}
                </Button>
                <TFAVerifyButton
                  type="primary"
                  htmlType="submit"
                  loading={verifyTFAMutation.isPending}
                  disabled={twoFACode.length !== 6}
                  data-testid="tfa-verify-button"
                >
                  {t('login.twoFactorAuth.verify')}
                </TFAVerifyButton>
              </TFAButtonContainer>
            </NoMarginFormItem>
          </Form>
        </FullWidthStack>
      </Modal>

      {/* Registration Modal */}
      <RegistrationModal
        visible={showRegistration}
        onClose={() => {
          setShowRegistration(false)
          setIsQuickRegistration(false)
          setQuickRegistrationData(undefined)
        }}
        autoFillData={quickRegistrationData}
        autoSubmit={isQuickRegistration}
        onRegistrationComplete={async (credentials) => {
          // Auto-login after quick registration
          if (isQuickRegistration) {
            console.log('🔐 Auto-login after quick registration...')
            setShowRegistration(false)
            
            // Perform login with the registration credentials
            await handleLogin({
              email: credentials.email,
              password: credentials.password
            })
          }
        }}
      />
    </>
  )
}

export default LoginPage
