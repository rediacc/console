import React, { useState } from 'react'
import { Modal, Form, Input, Button, Steps, Alert, Space, Typography } from 'antd'
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
import { useFormStyles } from '@/hooks/useComponentStyles'
import { DESIGN_TOKENS, spacing } from '@/utils/styleConstants'
import { ModalSize } from '@/types/modal'

const { Step } = Steps
const { Text } = Typography

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
  const { t } = useTranslation(['auth', 'common'])
  const styles = useFormStyles()
  const [currentStep, setCurrentStep] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
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
    setLoading(true)
    setError(null)

    try {
      // Hash the password
      const passwordHash = await hashPassword(values.password)

      // Call CreateNewCompany with headers
      const axiosClient = (apiClient as any).client
      const response = await axiosClient.post('/CreateNewCompany', {
        companyName: values.companyName
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
    } finally {
      setLoading(false)
    }
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
    registrationForm.resetFields()
    verificationForm.resetFields()
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

      <Form.Item>
        <Button
          type="primary"
          htmlType="submit"
          block
          size="large"
          loading={loading}
          style={{
            // Button styles handled by CSS
            marginTop: spacing('SM')
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
      <Space direction="vertical" size={spacing('MD')} style={{ width: '100%' }}>
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

        <Form.Item>
          <Button
            type="primary"
            htmlType="submit"
            block
            size="large"
            loading={loading}
            style={{
              ...styles.buttonPrimary,
              height: DESIGN_TOKENS.DIMENSIONS.INPUT_HEIGHT,
              marginTop: spacing('SM')
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
    <div style={{ textAlign: 'center', padding: `${spacing('XXXL')}px 0` }} data-testid="registration-success-container">
      <CheckCircleOutlined style={{ fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_XXXL, color: '#52c41a' }} data-testid="registration-success-icon" />
      <Typography.Title level={4} style={{ marginTop: spacing('LG') }} data-testid="registration-success-title">
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
      <Space direction="vertical" size={spacing('LG')} style={{ width: '100%' }}>
        <Steps current={currentStep} size="small" data-testid="registration-steps">
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