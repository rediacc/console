import React, { useState, useRef } from 'react'
import { Modal, Form, Input, Button, Steps, Alert, Space, Typography, Checkbox } from 'antd'
import { 
  UserOutlined, 
  LockOutlined, 
  MailOutlined, 
  BankOutlined,
  SafetyCertificateOutlined,
  CheckCircleOutlined 
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { showMessage } from '@/utils/messages'
import { hashPassword } from '@/utils/auth'
import apiClient from '@/api/client'
import HCaptcha from '@hcaptcha/react-hcaptcha'
import { useFormStyles } from '@/hooks/useComponentStyles'
import { DESIGN_TOKENS, spacing } from '@/utils/styleConstants'
import { ModalSize } from '@/types/modal'
import { LanguageLink } from '@/components/common/languageLink'


const { Step } = Steps
const { Text } = Typography
const hCaptchaSiteKey = import.meta.env.VITE_HCAPTCHA_SITE_KEY || ''
const isCaptchaEnabled = !!hCaptchaSiteKey 

interface RegistrationModalProps {
  visible: boolean
  onClose: () => void
  autoFillData?: {
    email: string
    password: string
    companyName: string
    activationCode?: string
  }
  autoSubmit?: boolean
  onRegistrationComplete?: (credentials: { email: string; password: string }) => void
}

interface RegistrationForm {
  email: string
  password: string
  passwordConfirm: string
  companyName: string
  termsAccepted?: boolean
}

interface VerificationForm {
  activationCode: string
}

const RegistrationModal: React.FC<RegistrationModalProps> = ({ 
  visible, 
  onClose, 
  autoFillData,
  autoSubmit = false,
  onRegistrationComplete 
}) => {
  const { t, i18n } = useTranslation(['auth', 'common'])
  const styles = useFormStyles()
  const [currentStep, setCurrentStep] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hCaptchaToken, setHCaptchaToken] = useState<string | null>(null)
  const hCaptchaRef = useRef<HCaptcha>(null)
  
  const [registrationData, setRegistrationData] = useState<{
    email: string
    companyName: string
    passwordHash: string
    password?: string // Store password for auto-login
  } | null>(null)
  
  const [registrationForm] = Form.useForm<RegistrationForm>()
  const [verificationForm] = Form.useForm<VerificationForm>()

  // Auto-fill and auto-submit logic
  React.useEffect(() => {
    if (visible && autoFillData && autoSubmit) {
      // Auto-fill registration form
      registrationForm.setFieldsValue({
        email: autoFillData.email,
        password: autoFillData.password,
        passwordConfirm: autoFillData.password,
        companyName: autoFillData.companyName
      })
      
      // Auto-submit registration form after a short delay
      setTimeout(() => {
        registrationForm.submit()
      }, 500)
    }
  }, [visible, autoFillData, autoSubmit, registrationForm])

  // Auto-fill and auto-submit verification code
  React.useEffect(() => {
    if (currentStep === 1 && autoFillData?.activationCode && autoSubmit) {
      verificationForm.setFieldsValue({
        activationCode: autoFillData.activationCode
      })
      
      // Auto-submit verification form after a short delay
      setTimeout(() => {
        verificationForm.submit()
      }, 500)
    }
  }, [currentStep, autoFillData, autoSubmit, verificationForm])

  const handleRegistration = async (values: RegistrationForm) => {
    // Check hCaptcha token only if captcha is enabled
    if (isCaptchaEnabled && !hCaptchaToken) {
      setError(t('auth:registration.captchaRequired', 'Please complete the captcha'))
      return
    }

    // Check terms acceptance
    if (!values.termsAccepted) {
      setError(t('auth:registration.termsRequired', 'You must accept the terms and conditions'))
      return
    }

    setLoading(true)
    setError(null)

    try {
      // Hash the password
      const passwordHash = await hashPassword(values.password)

      // Call CreateNewCompany with headers and captcha token
      const axiosClient = (apiClient as any).client
      const response = await axiosClient.post('/CreateNewCompany', {
        companyName: values.companyName,
        captchaToken: hCaptchaToken,
        userEmailAddress: values.email,
        languagePreference: i18n.language || 'en'
      }, {
        headers: {
          'Rediacc-UserEmail': values.email,
          'Rediacc-UserHash': passwordHash
        }
      })

      if (response.data.failure !== 0) {
        throw new Error(response.data.errors?.join('; ') || 'Registration failed')
      }

      // Store registration data for verification step
      setRegistrationData({
        email: values.email,
        companyName: values.companyName,
        passwordHash: passwordHash,
        password: values.password // Store for auto-login if needed
      })

      // Move to verification step
      setCurrentStep(1)
      showMessage('success', t('auth:registration.registrationSuccess'))
    } catch (error: any) {
      const errorMessage = error.message || t('auth:registration.registrationFailed')
      setError(errorMessage)
      showMessage('error', errorMessage)
      
      // Reset captcha on error
      if (hCaptchaRef.current) {
        hCaptchaRef.current.resetCaptcha()
        setHCaptchaToken(null)
      }
    } finally {
      setLoading(false)
    }
  }

  // HCaptcha handlers
  const onHCaptchaChange = (token: string | null) => {
    setHCaptchaToken(token)
    if (token) {
      setError(null) // Clear error when captcha is completed
    }
  }

  const onHCaptchaExpire = () => {
    setHCaptchaToken(null)
  }

  const onHCaptchaError = (err: string) => {
    console.error('HCaptcha error:', err)
    setHCaptchaToken(null)
  }

  const handleVerification = async (values: VerificationForm) => {
    if (!registrationData) return

    setLoading(true)
    setError(null)

    try {
      // Use the updated activateUser method with authentication
      const response = await apiClient.activateUser(
        registrationData.email,
        values.activationCode,
        registrationData.passwordHash
      )

      if (response.failure !== 0) {
        throw new Error(response.errors?.join('; ') || 'Activation failed')
      }

      // Move to success step
      setCurrentStep(2)
      showMessage('success', t('auth:registration.activationSuccess'))

      // Call completion callback if provided (for auto-login)
      if (onRegistrationComplete && registrationData?.password) {
        onRegistrationComplete({
          email: registrationData.email,
          password: registrationData.password
        })
      }

      // Close modal immediately after success
      handleClose()
    } catch (error: any) {
      const errorMessage = error.message || t('auth:registration.activationFailed')
      setError(errorMessage)
      showMessage('error', errorMessage)
    } finally {
      setLoading(false)
    }
  }

  const handleClose = () => {
    setCurrentStep(0)
    setError(null)
    setRegistrationData(null)
    setHCaptchaToken(null)
    registrationForm.resetFields()
    verificationForm.resetFields()
    
    // Reset captcha when closing
    if (hCaptchaRef.current) {
      hCaptchaRef.current.resetCaptcha()
    }
    
    onClose()
  }

  const renderRegistrationForm = () => (
    <Form
      form={registrationForm}
      layout="vertical"
      onFinish={handleRegistration}
      requiredMark={false}
      data-testid="registration-form"
    >
      <Form.Item
        name="companyName"
        label={t('auth:registration.companyName')}
        rules={[
          { required: true, message: t('common:messages.required') },
          { min: 3, message: t('auth:registration.companyNameMin') }
        ]}
        style={{ marginBottom: 12 }}
      >
        <Input
          prefix={<BankOutlined />}
          placeholder={t('auth:registration.companyNamePlaceholder')}
          size="large"
          // Styles handled by CSS
          data-testid="registration-company-input"
        />
      </Form.Item>

      <Form.Item
        name="email"
        label={t('auth:registration.email')}
        rules={[
          { required: true, message: t('common:messages.required') },
          { type: 'email', message: t('common:messages.invalidEmail') }
        ]}
        style={{ marginBottom: 12 }}
      >
        <Input
          prefix={<MailOutlined />}
          placeholder={t('auth:registration.emailPlaceholder')}
          size="large"
          autoComplete="email"
          // Styles handled by CSS
          data-testid="registration-email-input"
        />
      </Form.Item>

      <Form.Item
        name="password"
        label={t('auth:registration.password')}
        rules={[
          { required: true, message: t('common:messages.required') },
          { min: 8, message: t('auth:registration.passwordMin') }
        ]}
        style={{ marginBottom: 12 }}
      >
        <Input.Password
          prefix={<LockOutlined />}
          placeholder={t('auth:registration.passwordPlaceholder')}
          size="large"
          autoComplete="new-password"
          // Styles handled by CSS
          data-testid="registration-password-input"
        />
      </Form.Item>

      <Form.Item
        name="passwordConfirm"
        label={t('auth:registration.passwordConfirm')}
        dependencies={['password']}
        rules={[
          { required: true, message: t('common:messages.required') },
          ({ getFieldValue }) => ({
            validator(_, value) {
              if (!value || getFieldValue('password') === value) {
                return Promise.resolve()
              }
              return Promise.reject(new Error(t('auth:registration.passwordMismatch')))
            },
          }),
        ]}
        style={{ marginBottom: 12 }}
      >
        <Input.Password
          prefix={<LockOutlined />}
          placeholder={t('auth:registration.passwordConfirmPlaceholder')}
          size="large"
          autoComplete="new-password"
          // Styles handled by CSS
          data-testid="registration-password-confirm-input"
        />
      </Form.Item>

      {/* Terms and HCaptcha side by side */}
      <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-start', marginBottom: 12 }}>
        {/* Terms and Conditions */}
        <Form.Item
          name="termsAccepted"
          valuePropName="checked"
          rules={[
            {
              validator: (_, value) =>
                value ? Promise.resolve() : Promise.reject(new Error(t('auth:registration.termsRequired', 'You must accept the terms and conditions')))
            }
          ]}
          style={{ marginBottom: 0, flex: 1 }}
        >
          <Checkbox>
            {t('auth:registration.termsText', 'I accept the terms and conditions {terms} and {privacy}').split('{terms}')[0]}
            <LanguageLink to="/terms" className="underline" target='_blank'>
              {t('auth:registration.termsLink', 'Terms of Use')}
            </LanguageLink>
            {t('auth:registration.termsText', 'I accept the terms and conditions {terms} and {privacy}').split('{terms}')[1].split('{privacy}')[0]}
            <LanguageLink to="/privacy" className="underline" target='_blank'>
              {t('auth:registration.privacyLink', 'Privacy Policy')}
            </LanguageLink>
            {t('auth:registration.termsText', 'I accept the terms and conditions {terms} and {privacy}').split('{privacy}')[1]}
          </Checkbox>
        </Form.Item>

        {/* HCaptcha - only render if enabled */}
        {isCaptchaEnabled && (
          <div style={{ flex: '0 0 auto' }}>
            <HCaptcha
              sitekey={hCaptchaSiteKey}
              onVerify={onHCaptchaChange}
              onExpire={onHCaptchaExpire}
              onError={onHCaptchaError}
              ref={hCaptchaRef}
              theme="light"
              size="normal"
            />
          </div>
        )}
      </div>

      <Form.Item style={{ marginBottom: 0 }}>
        <Button
          type="primary"
          htmlType="submit"
          block
          size="large"
          loading={loading}
          disabled={isCaptchaEnabled && !hCaptchaToken}
          style={{
            // Button styles handled by CSS
            marginTop: 8
          }}
          data-testid="registration-submit-button"
        >
          {t('auth:registration.createAccount')}
        </Button>
      </Form.Item>
    </Form>
  )

  const renderVerificationForm = () => (
    <Form
      form={verificationForm}
      layout="vertical"
      onFinish={handleVerification}
      requiredMark={false}
      data-testid="registration-verification-form"
    >
      <Space direction="vertical" size={spacing('SM')} style={{ width: '100%' }}>
        <Alert
          message={t('auth:registration.verificationRequired')}
          description={t('auth:registration.verificationDescription')}
          type="info"
          showIcon
          data-testid="registration-verification-alert"
        />

        <Form.Item
          name="activationCode"
          label={t('auth:registration.activationCode')}
          rules={[
            { required: true, message: t('common:messages.required') },
            { len: 6, message: t('auth:registration.activationCodeLength') },
            { pattern: /^\d{6}$/, message: t('auth:registration.activationCodeFormat') }
          ]}
          style={{ marginBottom: 12 }}
        >
          <Input
            size="large"
            placeholder={t('auth:registration.activationCodePlaceholder')}
            autoComplete="off"
            maxLength={6}
            style={{
              // Base styles handled by CSS
              textAlign: 'center',
              fontSize: '20px',
              letterSpacing: '8px'
            }}
            data-testid="registration-activation-code-input"
          />
        </Form.Item>

        <Form.Item style={{ marginBottom: 0 }}>
          <Button
            type="primary"
            htmlType="submit"
            block
            size="large"
            loading={loading}
            style={{
              ...styles.buttonPrimary,
              height: DESIGN_TOKENS.DIMENSIONS.INPUT_HEIGHT,
              marginTop: 8
            }}
            data-testid="registration-verify-button"
          >
            {t('auth:registration.verifyAccount')}
          </Button>
        </Form.Item>
      </Space>
    </Form>
  )

  const renderSuccess = () => (
    <div style={{ textAlign: 'center', padding: `${spacing('LG')}px 0` }} data-testid="registration-success-container">
      <CheckCircleOutlined style={{ fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_XXXL, color: '#4a4a4a' }} data-testid="registration-success-icon" />
      <Typography.Title level={4} style={{ marginTop: spacing('MD') }} data-testid="registration-success-title">
        {t('auth:registration.successTitle')}
      </Typography.Title>
      <Text type="secondary" data-testid="registration-success-description">
        {t('auth:registration.successDescription')}
      </Text>
    </div>
  )

  const renderContent = () => {
    switch (currentStep) {
      case 0:
        return renderRegistrationForm()
      case 1:
        return renderVerificationForm()
      case 2:
        return renderSuccess()
      default:
        return null
    }
  }

  return (
    <Modal
      title={t('auth:registration.title')}
      open={visible}
      onCancel={handleClose}
      footer={null}
      className={ModalSize.Medium}
      destroyOnHidden
      data-testid="registration-modal"
    >
      <Space direction="vertical" size={spacing('SM')} style={{ width: '100%' }}>
        <Steps current={currentStep} size="small" style={{ marginBottom: 8 }} data-testid="registration-steps">
          <Step title={t('auth:registration.steps.register')} icon={<UserOutlined />} data-testid="registration-step-register" />
          <Step title={t('auth:registration.steps.verify')} icon={<SafetyCertificateOutlined />} data-testid="registration-step-verify" />
          <Step title={t('auth:registration.steps.complete')} icon={<CheckCircleOutlined />} data-testid="registration-step-complete" />
        </Steps>

        {error && (
          <Alert
            message={error}
            type="error"
            showIcon
            closable
            onClose={() => setError(null)}
            data-testid="registration-error-alert"
          />
        )}

        {renderContent()}
      </Space>
    </Modal>
  )
}

export default RegistrationModal