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

const { Step } = Steps
const { Text } = Typography

interface RegistrationModalProps {
  visible: boolean
  onClose: () => void
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

const RegistrationModal: React.FC<RegistrationModalProps> = ({ visible, onClose }) => {
  const { t } = useTranslation(['auth', 'common'])
  const [currentStep, setCurrentStep] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [registrationData, setRegistrationData] = useState<{
    email: string
    companyName: string
  } | null>(null)
  
  const [registrationForm] = Form.useForm<RegistrationForm>()
  const [verificationForm] = Form.useForm<VerificationForm>()

  const handleRegistration = async (values: RegistrationForm) => {
    setLoading(true)
    setError(null)

    try {
      // Hash the password
      const passwordHash = await hashPassword(values.password)

      // Call CreateNewCompany
      const response = await apiClient.post('/CreateNewCompany', {
        companyName: values.companyName,
        userEmail: values.email,
        userHash: passwordHash,
        subscriptionPlan: 'COMMUNITY',
        companyVaultDefaults: JSON.stringify({})
      })

      if (response.failure !== 0) {
        throw new Error(response.errors?.join('; ') || 'Registration failed')
      }

      // Store registration data for verification step
      setRegistrationData({
        email: values.email,
        companyName: values.companyName
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
        values.activationCode
      )

      if (response.failure !== 0) {
        throw new Error(response.errors?.join('; ') || 'Activation failed')
      }

      // Move to success step
      setCurrentStep(2)
      showMessage('success', t('auth:registration.activationSuccess'))

      // Close modal after 2 seconds
      setTimeout(() => {
        handleClose()
      }, 2000)
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
            background: '#556b2f',
            borderColor: '#556b2f',
            height: 48,
          }}
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
    >
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Alert
          message={t('auth:registration.verificationRequired')}
          description={t('auth:registration.verificationDescription')}
          type="info"
          showIcon
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
            style={{ textAlign: 'center', fontSize: '20px', letterSpacing: '8px' }}
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
              background: '#556b2f',
              borderColor: '#556b2f',
              height: 48,
            }}
          >
            {t('auth:registration.verifyAccount')}
          </Button>
        </Form.Item>
      </Space>
    </Form>
  )

  const renderSuccess = () => (
    <div style={{ textAlign: 'center', padding: '40px 0' }}>
      <CheckCircleOutlined style={{ fontSize: 64, color: '#52c41a' }} />
      <Typography.Title level={4} style={{ marginTop: 24 }}>
        {t('auth:registration.successTitle')}
      </Typography.Title>
      <Text type="secondary">
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
      width={480}
      destroyOnClose
    >
      <Space direction="vertical" size={24} style={{ width: '100%' }}>
        <Steps current={currentStep} size="small">
          <Step title={t('auth:registration.steps.register')} icon={<UserOutlined />} />
          <Step title={t('auth:registration.steps.verify')} icon={<SafetyCertificateOutlined />} />
          <Step title={t('auth:registration.steps.complete')} icon={<CheckCircleOutlined />} />
        </Steps>

        {error && (
          <Alert
            message={error}
            type="error"
            showIcon
            closable
            onClose={() => setError(null)}
          />
        )}

        {renderContent()}
      </Space>
    </Modal>
  )
}

export default RegistrationModal