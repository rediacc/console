import React, { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useDispatch } from 'react-redux'
import { Card, Form, Input, Button, Typography, Space, Alert, Tooltip, Modal } from 'antd'
import { UserOutlined, LockOutlined, KeyOutlined, InfoCircleOutlined, SafetyCertificateOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { loginSuccess } from '@/store/auth/authSlice'
import { saveAuthData } from '@/utils/auth'
import { hashPassword } from '@/utils/auth'
import apiClient from '@/api/client'
import { showMessage } from '@/utils/messages'
import { useTheme } from '@/context/ThemeContext'
import LanguageSelector from '@/components/common/LanguageSelector'
import logoBlack from '@/assets/logo_black.png'
import logoWhite from '@/assets/logo_white.png'
import { useComponentStyles } from '@/hooks/useComponentStyles'
import { DESIGN_TOKENS, spacing, borderRadius, fontSize } from '@/utils/styleConstants'
import { 
  isEncrypted, 
  validateMasterPassword, 
  VaultProtocolState, 
  analyzeVaultProtocolState,
  getVaultProtocolMessage 
} from '@/utils/vaultProtocol'
import { masterPasswordService } from '@/services/masterPasswordService'
import { tokenService } from '@/services/tokenService'
import { useVerifyTFA } from '@/api/queries/twoFactor'
import RegistrationModal from '@/components/auth/RegistrationModal'
import { generateRandomEmail, generateRandomCompanyName, generateRandomPassword } from '@/utils/cryptoGenerators'
import { configService } from '@/services/configService'
import SandboxWarning from '@/components/common/SandboxWarning'

const { Text, Link } = Typography

interface LoginForm {
  email: string
  password: string
  masterPassword?: string
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
  const { t } = useTranslation(['auth', 'common'])
  const verifyTFAMutation = useVerifyTFA()
  const styles = useComponentStyles()

  // Check URL parameters for registration flag
  useEffect(() => {
    const checkRegistrationMode = async () => {
      const registerParam = searchParams.get('register')
      
      if (registerParam === 'quick') {
        // Check if we're in sandbox mode
        const instanceName = await configService.getInstanceName()
        
        if (instanceName.toLowerCase() === 'sandbox') {
          // Generate random registration data for quick registration
          const randomData = {
            email: generateRandomEmail(),
            password: generateRandomPassword(),
            companyName: generateRandomCompanyName(),
            activationCode: '111111' // Fixed code for sandbox quick registration
          }
          
          console.log('🚀 Quick Registration Mode (Sandbox Only)', {
            email: randomData.email,
            company: randomData.companyName,
            message: 'Using verification code: 111111'
          })
          
          setQuickRegistrationData(randomData)
          setIsQuickRegistration(true)
          setShowRegistration(true)
        } else {
          // Not in sandbox, fall back to normal registration
          console.warn('Quick registration is only available in sandbox instances')
          showMessage('warning', 'Quick registration is only available in sandbox environments')
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

  const handleLogin = async (values: LoginForm) => {
    setLoading(true)
    setError(null)
    setVaultProtocolState(null)

    try {
      // Hash password
      const passwordHash = await hashPassword(values.password)

      // Attempt login
      const loginResponse = await apiClient.login(values.email, passwordHash)
      
      if (loginResponse.failure !== 0) {
        throw new Error(loginResponse.errors?.join('; ') || 'Login failed')
      }

      // Extract token and company data
      const userData = loginResponse.resultSets[0].data[0]
      
      const token = userData.nextRequestToken
      if (!token) {
        throw new Error('No authentication token received')
      }

      // Check if TFA is required
      const isAuthorized = userData.isAuthorized
      const authenticationStatus = userData.authenticationStatus
      
      // If TFA is required but not authorized, show TFA modal
      if (authenticationStatus === 'TFA_REQUIRED' && !isAuthorized) {
        // Store the login data for after TFA verification
        setPendingTFAData({
          token,
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

      // Save auth data
      await saveAuthData(token, values.email, companyName)

      // Store master password in secure memory if encryption is enabled
      if (companyHasEncryption && values.masterPassword) {
        await masterPasswordService.setMasterPassword(values.masterPassword)
      }

      // Update Redux store with all relevant data (token and masterPassword are now stored separately for security)
      dispatch(loginSuccess({
        user: { email: values.email, company: companyName },
        company: companyName,
        vaultCompany: vaultCompany,
        companyEncryptionEnabled: companyHasEncryption,
      }))

      navigate('/dashboard')
    } catch (error: any) {
      setError(error.message || t('login.errors.invalidCredentials'))
    } finally {
      setLoading(false)
    }
  }

  const handleTFAVerification = async () => {
    try {
      // Set the token temporarily for the TFA verification request
      const { token } = pendingTFAData
      await tokenService.setToken(token)
      
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
        const { token, email, userData, masterPassword } = pendingTFAData
        
        // Extract VaultCompany and company name from stored userData
        const vaultCompany = userData.vaultCompany || null
        const companyName = userData.CompanyName || userData.company || null
        
        // Save auth data
        await saveAuthData(token, email, companyName)
        
        // Store master password if encryption is enabled
        const companyHasEncryption = isEncrypted(vaultCompany)
        if (companyHasEncryption && masterPassword) {
          await masterPasswordService.setMasterPassword(masterPassword)
        }
        
        // Update Redux store
        dispatch(loginSuccess({
          user: { email, company: companyName },
          company: companyName,
          vaultCompany: vaultCompany,
          companyEncryptionEnabled: companyHasEncryption,
        }))
        
        // Close modal and navigate
        setShowTFAModal(false)
        navigate('/dashboard')
      }
    } catch (error: any) {
      // Error is handled by the mutation
      // Clear the temporarily set token on error
      await tokenService.clearToken()
    }
  }

  return (
    <>
      <SandboxWarning />
      <Card
        style={{
          ...styles.card,
          width: DESIGN_TOKENS.DIMENSIONS.CARD_WIDTH_LG,
          backdropFilter: 'blur(8px)',
        }}
      >
      <Space direction="vertical" size={spacing('XL')} style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: -spacing('SM') }}>
          <LanguageSelector />
        </div>
        
        <div style={{ 
          ...styles.flexCenter,
          height: spacing('XXXXXL'),
          marginTop: -spacing('SM'),
        }}>
          <img
            src={theme === 'dark' ? logoWhite : logoBlack}
            alt="Rediacc Logo"
            style={{
              height: spacing('XL'),
              width: 'auto',
              maxWidth: 150,
              objectFit: 'contain',
            }}
          />
        </div>

        {error && (
          <Alert
            message={error}
            type="error"
            showIcon
            closable
            onClose={() => setError(null)}
            style={{
              borderRadius: borderRadius('LG'),
              border: '2px solid var(--color-error)',
              backgroundColor: 'var(--color-bg-error)',
              padding: spacing('MD'),
              boxShadow: DESIGN_TOKENS.SHADOWS.ERROR_FIELD,
              fontSize: DESIGN_TOKENS.FONT_SIZE.SM,
              fontWeight: DESIGN_TOKENS.FONT_WEIGHT.MEDIUM,
              marginBottom: spacing('MD')
            }}
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
              <label htmlFor="login-email-input" style={{ 
                fontSize: DESIGN_TOKENS.FONT_SIZE.SM, 
                fontWeight: DESIGN_TOKENS.FONT_WEIGHT.MEDIUM, 
                color: 'var(--color-text-primary)',
                marginBottom: spacing('SM'),
                display: 'block'
              }}>
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
              size="large"
              autoComplete="email"
              data-testid="login-email-input"
              // Styles handled by CSS
              aria-label={t('auth:login.email')}
              aria-describedby="email-error"
            />
          </Form.Item>

          <Form.Item
            name="password"
            label={
              <label htmlFor="login-password-input" style={{ 
                fontSize: DESIGN_TOKENS.FONT_SIZE.SM, 
                fontWeight: DESIGN_TOKENS.FONT_WEIGHT.MEDIUM, 
                color: 'var(--color-text-primary)',
                marginBottom: spacing('SM'),
                display: 'block'
              }}>
                {t('auth:login.password')}
              </label>
            }
            rules={[{ required: true, message: t('common:messages.required') }]}
            style={{ marginBottom: spacing('LG') }}
            validateStatus={error ? 'error' : undefined}
          >
            <Input.Password
              id="login-password-input"
              prefix={<LockOutlined />}
              placeholder={t('auth:login.passwordPlaceholder')}
              size="large"
              autoComplete="current-password"
              data-testid="login-password-input"
              // Styles handled by CSS
              aria-label={t('auth:login.password')}
              aria-describedby="password-error"
            />
          </Form.Item>

          {/* Progressive disclosure: Show master password field only when needed */}
          {(vaultProtocolState === VaultProtocolState.PASSWORD_REQUIRED || 
            vaultProtocolState === VaultProtocolState.INVALID_PASSWORD || 
            showAdvancedOptions) && (
            <Form.Item
              name="masterPassword"
              label={
                <label htmlFor="login-master-password-input" style={{ 
                  fontSize: DESIGN_TOKENS.FONT_SIZE.SM, 
                  fontWeight: DESIGN_TOKENS.FONT_WEIGHT.MEDIUM, 
                  color: 'var(--color-text-primary)',
                  marginBottom: spacing('SM'),
                  display: 'flex',
                  alignItems: 'center',
                  gap: spacing('SM')
                }}>
                  <span>{t('auth:login.masterPassword')}</span>
                  <Tooltip title={t('auth:login.masterPasswordTooltip')}>
                    <InfoCircleOutlined style={{ color: 'var(--color-text-tertiary)' }} />
                  </Tooltip>
                </label>
              }
              validateStatus={vaultProtocolState === VaultProtocolState.PASSWORD_REQUIRED || vaultProtocolState === VaultProtocolState.INVALID_PASSWORD ? 'error' : undefined}
              required={vaultProtocolState === VaultProtocolState.PASSWORD_REQUIRED}
              style={{
                animation: 'fadeIn 0.3s ease-out'
              }}
            >
              <Input.Password
                id="login-master-password-input"
                prefix={<KeyOutlined />}
                placeholder={t('auth:login.masterPasswordPlaceholder')}
                size="large"
                autoComplete="off"
                data-testid="login-master-password-input"
                style={{
                  ...styles.input,
                }}
                aria-label={t('auth:login.masterPassword')}
                aria-describedby="master-password-error"
              />
            </Form.Item>
          )}
          
          {/* Show advanced options toggle when master password is not yet shown */}
          {!(vaultProtocolState === VaultProtocolState.PASSWORD_REQUIRED || 
            vaultProtocolState === VaultProtocolState.INVALID_PASSWORD || 
            showAdvancedOptions) && (
            <div style={{ textAlign: 'center', marginBottom: spacing('MD'), marginTop: spacing('SM') }}>
              <Button
                type="text"
                size="small"
                style={{ 
                  color: 'var(--color-text-tertiary)', 
                  fontSize: DESIGN_TOKENS.FONT_SIZE.SM,
                  height: 'auto',
                  padding: `${spacing('XS')}px ${spacing('SM')}px`,
                  borderRadius: borderRadius('MD'),
                  transition: DESIGN_TOKENS.TRANSITIONS.DEFAULT
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = 'var(--color-fill-tertiary, rgba(0, 0, 0, 0.04))';
                  e.currentTarget.style.color = 'var(--color-text-secondary)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = 'transparent';
                  e.currentTarget.style.color = 'var(--color-text-tertiary)';
                }}
                onClick={() => {
                  setShowAdvancedOptions(true)
                  setTimeout(() => {
                    form.getFieldInstance('masterPassword')?.focus()
                  }, 100)
                }}
              >
                {t('auth:login.needMasterPassword')} →
              </Button>
            </div>
          )}

          <Form.Item style={{ marginBottom: spacing('LG') }}>
            <Button
              type="primary"
              htmlType="submit"
              size="large"
              block
              loading={loading}
              style={{
                background: 'var(--color-primary)',
                borderColor: 'var(--color-primary)',
                height: DESIGN_TOKENS.DIMENSIONS.INPUT_HEIGHT_LG,
                fontSize: DESIGN_TOKENS.FONT_SIZE.BASE,
                fontWeight: DESIGN_TOKENS.FONT_WEIGHT.SEMIBOLD,
                boxShadow: DESIGN_TOKENS.SHADOWS.BUTTON_DEFAULT,
                transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
              }}
              onMouseEnter={(e) => {
                if (!loading) {
                  e.currentTarget.style.transform = 'translateY(-1px)';
                  e.currentTarget.style.boxShadow = DESIGN_TOKENS.SHADOWS.BUTTON_HOVER;
                }
              }}
              onMouseLeave={(e) => {
                if (!loading) {
                  e.currentTarget.style.transform = 'translateY(0)';
                  e.currentTarget.style.boxShadow = DESIGN_TOKENS.SHADOWS.BUTTON_DEFAULT;
                }
              }}
              data-testid="login-submit-button"
            >
              {loading ? t('auth:login.signingIn') : t('auth:login.signIn')}
            </Button>
          </Form.Item>
          
        </Form>

        <div style={{ textAlign: 'center', marginTop: spacing('SM') }}>
          <Text type="secondary" style={{ fontSize: DESIGN_TOKENS.FONT_SIZE.SM }}>
            {t('auth:login.noAccount')}{' '}
            <Link 
              onClick={() => setShowRegistration(true)} 
              style={{ 
                color: 'var(--color-primary)',
                fontWeight: DESIGN_TOKENS.FONT_WEIGHT.MEDIUM,
                textDecoration: 'none',
                borderRadius: borderRadius('SM'),
                padding: '2px 4px',
                margin: '-2px -4px',
                transition: DESIGN_TOKENS.TRANSITIONS.DEFAULT
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.backgroundColor = 'var(--color-primary-bg, rgba(85, 107, 47, 0.1))';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = 'transparent';
              }}
              onFocus={(e) => {
                e.currentTarget.style.outline = '2px solid var(--color-primary)';
                e.currentTarget.style.outlineOffset = '2px';
                e.currentTarget.style.backgroundColor = 'var(--color-primary-bg, rgba(85, 107, 47, 0.1))';
              }}
              onBlur={(e) => {
                e.currentTarget.style.outline = 'none';
                e.currentTarget.style.backgroundColor = 'transparent';
              }}
              tabIndex={0}
              role="button"
              aria-label={t('auth:login.register')}
              data-testid="login-register-link"
            >
              {t('auth:login.register')}
            </Link>
          </Text>
        </div>

        {/* Version display */}
        <div style={{ textAlign: 'center', marginTop: spacing('LG') }}>
          <Text type="secondary" style={{ fontSize: DESIGN_TOKENS.FONT_SIZE.XS, opacity: 0.6 }}>
            {import.meta.env.VITE_APP_VERSION !== 'dev' ? (import.meta.env.VITE_APP_VERSION.startsWith('v') ? import.meta.env.VITE_APP_VERSION : `v${import.meta.env.VITE_APP_VERSION}`) : 'Development'}
          </Text>
        </div>
      </Space>
    </Card>

      {/* TFA Verification Modal */}
      <Modal
        title={
          <Space>
            <SafetyCertificateOutlined style={{ color: 'var(--color-primary)' }} />
            <span>{t('login.twoFactorAuth.title')}</span>
          </Space>
        }
        open={showTFAModal}
        onCancel={() => {
          setShowTFAModal(false)
          setTwoFACode('')
          setPendingTFAData(null)
        }}
        footer={null}
        width={DESIGN_TOKENS.DIMENSIONS.MODAL_WIDTH}
      >
        <Space direction="vertical" size={spacing('MD')} style={{ width: '100%' }}>
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
              <Input
                size="large"
                placeholder={t('login.twoFactorAuth.codePlaceholder')}
                value={twoFACode}
                onChange={(e) => setTwoFACode(e.target.value)}
                autoComplete="off"
                maxLength={6}
                style={{ textAlign: 'center', fontSize: DESIGN_TOKENS.FONT_SIZE.XL, letterSpacing: spacing('SM') + 'px' }}
                data-testid="tfa-code-input"
              />
            </Form.Item>
            
            <Form.Item style={{ marginBottom: 0 }}>
              <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
                <Button
                  onClick={() => {
                    setShowTFAModal(false)
                    setTwoFACode('')
                    setPendingTFAData(null)
                  }}
                >
                  {t('common:general.cancel')}
                </Button>
                <Button
                  type="primary"
                  htmlType="submit"
                  loading={verifyTFAMutation.isPending}
                  disabled={twoFACode.length !== 6}
                  style={{
                    background: 'var(--color-primary)',
                    borderColor: 'var(--color-primary)',
                    ...styles.touchTarget,
                  }}
                  data-testid="tfa-verify-button"
                >
                  {t('login.twoFactorAuth.verify')}
                </Button>
              </Space>
            </Form.Item>
          </Form>
        </Space>
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