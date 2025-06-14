import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDispatch } from 'react-redux'
import { Card, Form, Input, Button, Typography, Space, Alert, Tooltip } from 'antd'
import { UserOutlined, LockOutlined, KeyOutlined, InfoCircleOutlined } from '@ant-design/icons'
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
import { 
  isEncrypted, 
  validateMasterPassword, 
  VaultProtocolState, 
  analyzeVaultProtocolState,
  getVaultProtocolMessage 
} from '@/utils/vaultProtocol'
import { masterPasswordService } from '@/services/masterPasswordService'

const { Text } = Typography

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
  const navigate = useNavigate()
  const dispatch = useDispatch()
  const [form] = Form.useForm<LoginForm>()
  const { theme } = useTheme()
  const { t } = useTranslation(['auth', 'common'])

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
      const userData = loginResponse.tables[0].data[0]
      
      const token = userData.nextRequestCredential
      if (!token) {
        throw new Error('No authentication token received')
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

  return (
    <Card
      style={{
        width: 400,
        boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
      }}
    >
      <Space direction="vertical" size={24} style={{ width: '100%' }}>
        <div style={{ 
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: 96,
        }}>
          <img
            src={theme === 'dark' ? logoWhite : logoBlack}
            alt="Rediacc Logo"
            style={{
              height: 32,
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
            label={t('auth:login.email')}
            rules={[
              { required: true, message: t('common:messages.required') },
              { type: 'email', message: t('common:messages.invalidEmail') },
            ]}
          >
            <Input
              prefix={<UserOutlined />}
              placeholder={t('auth:login.emailPlaceholder')}
              size="large"
              autoComplete="email"
            />
          </Form.Item>

          <Form.Item
            name="password"
            label={t('auth:login.password')}
            rules={[{ required: true, message: t('common:messages.required') }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder={t('auth:login.passwordPlaceholder')}
              size="large"
              autoComplete="current-password"
            />
          </Form.Item>

          <Form.Item
            name="masterPassword"
            label={
              <Space>
                {t('auth:login.masterPassword')}
                <Tooltip title={t('auth:login.masterPasswordTooltip')}>
                  <InfoCircleOutlined style={{ color: '#8c8c8c' }} />
                </Tooltip>
              </Space>
            }
            validateStatus={vaultProtocolState === VaultProtocolState.PASSWORD_REQUIRED || vaultProtocolState === VaultProtocolState.INVALID_PASSWORD ? 'error' : undefined}
            required={vaultProtocolState === VaultProtocolState.PASSWORD_REQUIRED}
          >
            <Input.Password
              prefix={<KeyOutlined />}
              placeholder={t('auth:login.masterPasswordPlaceholder')}
              size="large"
              autoComplete="off"
            />
          </Form.Item>

          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              size="large"
              block
              loading={loading}
              style={{
                background: '#556b2f',
                borderColor: '#556b2f',
                height: 48,
              }}
            >
              {t('auth:login.signIn')}
            </Button>
          </Form.Item>
          
          <div style={{ display: 'flex', justifyContent: 'center', marginTop: 16 }}>
            <LanguageSelector />
          </div>
        </Form>

        <div style={{ textAlign: 'center' }}>
          <Text type="secondary">
            {t('auth:login.noAccount')} {t('auth:login.register')}
          </Text>
        </div>
      </Space>
    </Card>
  )
}

export default LoginPage