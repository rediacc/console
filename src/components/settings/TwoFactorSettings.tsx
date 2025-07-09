import React, { useState, useEffect } from 'react'
import { Modal, Button, Space, Form, Input, Typography, Alert, Spin, Result, Tabs, Card } from 'antd'
import { SafetyCertificateOutlined, KeyOutlined, CheckCircleOutlined, WarningOutlined, CopyOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useGet2FAStatus, useEnable2FA, useDisable2FA } from '@/api/queries/twoFactor'
import { useSelector } from 'react-redux'
import { RootState } from '@/store/store'
import QRCode from 'react-qr-code'
import { message } from 'antd'
import { useQueryClient } from '@tanstack/react-query'

const { Title, Text, Paragraph } = Typography

interface TwoFactorSettingsProps {
  open: boolean
  onCancel: () => void
}

const TwoFactorSettings: React.FC<TwoFactorSettingsProps> = ({ open, onCancel }) => {
  const { t } = useTranslation('settings')
  const [passwordForm] = Form.useForm()
  const [disableForm] = Form.useForm()
  const userEmail = useSelector((state: RootState) => state.auth.user?.email)
  const queryClient = useQueryClient()
  
  const { data: twoFAStatus, isLoading: statusLoading, refetch: refetch2FAStatus } = useGet2FAStatus()
  
  const enable2FAMutation = useEnable2FA()
  const disable2FAMutation = useDisable2FA()
  
  const [showEnableModal, setShowEnableModal] = useState(false)
  const [showDisableModal, setShowDisableModal] = useState(false)
  const [twoFASecret, setTwoFASecret] = useState<string>('')
  const [showSuccess, setShowSuccess] = useState(false)
  
  // Refresh 2FA status when modal opens and reset states
  useEffect(() => {
    if (open) {
      // Reset states when modal opens
      setShowSuccess(false)
      setTwoFASecret('')
      // Fetch fresh status
      refetch2FAStatus()
    }
  }, [open, refetch2FAStatus])

  const handleEnable2FA = async (values: { password: string }) => {
    try {
      const result = await enable2FAMutation.mutateAsync({ password: values.password })
      setTwoFASecret(result.secret)
      setShowSuccess(true)
      passwordForm.resetFields()
      setShowEnableModal(false)
    } catch (error: any) {
      // Error is handled by mutation, but we should close the modal
      // if 2FA is already enabled
      if (error.message?.includes('already enabled')) {
        setShowEnableModal(false)
        passwordForm.resetFields()
      }
    }
  }

  const handleDisable2FA = async (values: { password: string; code: string }) => {
    try {
      await disable2FAMutation.mutateAsync({ 
        password: values.password, 
        currentCode: values.code 
      })
      setShowDisableModal(false)
      disableForm.resetFields()
    } catch (error) {
      // Error handled by mutation
    }
  }

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
    message.success(t('twoFactorAuth.secretCopied'))
  }

  const generateOtpAuthUrl = (secret: string, email: string) => {
    const issuer = 'Rediacc'
    const encodedIssuer = encodeURIComponent(issuer)
    const encodedEmail = encodeURIComponent(email)
    return `otpauth://totp/${encodedIssuer}:${encodedEmail}?secret=${secret}&issuer=${encodedIssuer}`
  }

  const renderMainContent = () => {
    if (statusLoading) {
      return (
        <div style={{ textAlign: 'center', padding: '40px 0' }}>
          <Spin size="large" />
        </div>
      )
    }

    if (showSuccess && twoFASecret) {
      return (
        <Result
          status="success"
          title={t('twoFactorAuth.enableSuccess.title')}
          subTitle={t('twoFactorAuth.enableSuccess.subtitle')}
          extra={
            <Space direction="vertical" size={24} style={{ width: '100%' }}>
              <Tabs
                items={[
                  {
                    key: 'qrcode',
                    label: t('twoFactorAuth.setupMethods.qrCode'),
                    children: (
                      <Space direction="vertical" align="center" style={{ width: '100%' }}>
                        <div style={{ background: 'white', padding: 16, borderRadius: 8 }}>
                          <QRCode 
                            value={generateOtpAuthUrl(twoFASecret, userEmail || '')} 
                            size={200}
                          />
                        </div>
                        <Text type="secondary">{t('twoFactorAuth.scanQRCode')}</Text>
                      </Space>
                    ),
                  },
                  {
                    key: 'manual',
                    label: t('twoFactorAuth.setupMethods.manual'),
                    children: (
                      <Space direction="vertical" style={{ width: '100%' }}>
                        <Alert
                          message={t('twoFactorAuth.manualSetup.title')}
                          description={
                            <Space direction="vertical" style={{ width: '100%' }}>
                              <Text>{t('twoFactorAuth.manualSetup.instructions')}</Text>
                              <Space.Compact style={{ width: '100%', marginTop: 8 }}>
                                <Input 
                                  value={twoFASecret} 
                                  readOnly 
                                  style={{ fontFamily: 'monospace' }}
                                />
                                <Button 
                                  icon={<CopyOutlined />}
                                  onClick={() => copyToClipboard(twoFASecret)}
                                />
                              </Space.Compact>
                            </Space>
                          }
                          type="info"
                        />
                      </Space>
                    ),
                  },
                ]}
              />
              
              <Alert
                message={t('twoFactorAuth.important')}
                description={t('twoFactorAuth.saveSecretWarning')}
                type="warning"
                showIcon
              />
              
              <Button 
                type="primary" 
                size="large" 
                block
                onClick={() => {
                  setShowSuccess(false)
                  setTwoFASecret('')
                  // Refetch to ensure we have the latest status
                  refetch2FAStatus()
                }}
                style={{
                  background: '#556b2f',
                  borderColor: '#556b2f',
                }}
              >
                {t('twoFactorAuth.done')}
              </Button>
            </Space>
          }
        />
      )
    }

    // Ensure we have a boolean value for is2FAEnabled
    const is2FAEnabled = Boolean(twoFAStatus?.is2FAEnabled)

    return (
      <Space direction="vertical" size={24} style={{ width: '100%' }}>
        <div style={{ textAlign: 'center' }}>
          <SafetyCertificateOutlined style={{ fontSize: 64, color: is2FAEnabled ? '#52c41a' : '#8c8c8c' }} />
          <Title level={4} style={{ marginTop: 16 }}>
            {is2FAEnabled ? t('twoFactorAuth.status.enabled') : t('twoFactorAuth.status.disabled')}
          </Title>
          <Paragraph type="secondary">
            {is2FAEnabled 
              ? t('twoFactorAuth.status.enabledDescription')
              : t('twoFactorAuth.status.disabledDescription')
            }
          </Paragraph>
        </div>

        <Card>
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Title level={5}>{t('twoFactorAuth.whatIs.title')}</Title>
            <Paragraph>
              {t('twoFactorAuth.whatIs.description')}
            </Paragraph>
            <ul>
              <li>{t('twoFactorAuth.whatIs.benefit1')}</li>
              <li>{t('twoFactorAuth.whatIs.benefit2')}</li>
              <li>{t('twoFactorAuth.whatIs.benefit3')}</li>
            </ul>
          </Space>
        </Card>

        {is2FAEnabled ? (
          <Button
            type="primary"
            danger
            size="large"
            block
            icon={<WarningOutlined />}
            onClick={() => setShowDisableModal(true)}
          >
            {t('twoFactorAuth.disable')}
          </Button>
        ) : (
          <Button
            type="primary"
            size="large"
            block
            icon={<CheckCircleOutlined />}
            onClick={() => setShowEnableModal(true)}
            style={{
              background: '#556b2f',
              borderColor: '#556b2f',
            }}
          >
            {t('twoFactorAuth.enable')}
          </Button>
        )}
      </Space>
    )
  }

  return (
    <>
      <Modal
        title={
          <Space>
            <SafetyCertificateOutlined style={{ color: '#556b2f' }} />
            <span>{t('twoFactorAuth.title')}</span>
          </Space>
        }
        open={open}
        onCancel={onCancel}
        footer={null}
        width={600}
      >
        {renderMainContent()}
      </Modal>

      {/* Enable 2FA Modal */}
      <Modal
        title={t('twoFactorAuth.enableModal.title')}
        open={showEnableModal}
        onCancel={() => {
          setShowEnableModal(false)
          passwordForm.resetFields()
        }}
        footer={null}
        width={500}
      >
        <Form
          form={passwordForm}
          layout="vertical"
          onFinish={handleEnable2FA}
        >
          <Alert
            message={t('twoFactorAuth.enableModal.warning')}
            description={t('twoFactorAuth.enableModal.warningDescription')}
            type="warning"
            showIcon
            style={{ marginBottom: 24 }}
          />
          
          <Form.Item
            name="password"
            label={t('twoFactorAuth.enableModal.passwordLabel')}
            rules={[
              { required: true, message: t('twoFactorAuth.enableModal.passwordRequired') },
            ]}
          >
            <Input.Password
              prefix={<KeyOutlined />}
              placeholder={t('twoFactorAuth.enableModal.passwordPlaceholder')}
              size="large"
            />
          </Form.Item>
          
          <Form.Item style={{ marginBottom: 0 }}>
            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
              <Button onClick={() => {
                setShowEnableModal(false)
                passwordForm.resetFields()
              }}>
                {t('common:general.cancel')}
              </Button>
              <Button
                type="primary"
                htmlType="submit"
                loading={enable2FAMutation.isPending}
                style={{
                  background: '#556b2f',
                  borderColor: '#556b2f',
                }}
              >
                {t('twoFactorAuth.enableModal.submit')}
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* Disable 2FA Modal */}
      <Modal
        title={t('twoFactorAuth.disableModal.title')}
        open={showDisableModal}
        onCancel={() => {
          setShowDisableModal(false)
          disableForm.resetFields()
        }}
        footer={null}
        width={500}
      >
        <Form
          form={disableForm}
          layout="vertical"
          onFinish={handleDisable2FA}
        >
          <Alert
            message={t('twoFactorAuth.disableModal.warning')}
            description={t('twoFactorAuth.disableModal.warningDescription')}
            type="error"
            showIcon
            style={{ marginBottom: 24 }}
          />
          
          <Form.Item
            name="password"
            label={t('twoFactorAuth.disableModal.passwordLabel')}
            rules={[
              { required: true, message: t('twoFactorAuth.disableModal.passwordRequired') },
            ]}
          >
            <Input.Password
              prefix={<KeyOutlined />}
              placeholder={t('twoFactorAuth.disableModal.passwordPlaceholder')}
              size="large"
            />
          </Form.Item>
          
          <Form.Item
            name="code"
            label={t('twoFactorAuth.disableModal.codeLabel')}
            rules={[
              { required: true, message: t('twoFactorAuth.disableModal.codeRequired') },
              { len: 6, message: t('twoFactorAuth.disableModal.codeLength') },
              { pattern: /^\d{6}$/, message: t('twoFactorAuth.disableModal.codeFormat') }
            ]}
          >
            <Input
              size="large"
              placeholder={t('twoFactorAuth.disableModal.codePlaceholder')}
              maxLength={6}
              style={{ textAlign: 'center', fontSize: '20px', letterSpacing: '8px' }}
            />
          </Form.Item>
          
          <Form.Item style={{ marginBottom: 0 }}>
            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
              <Button onClick={() => {
                setShowDisableModal(false)
                disableForm.resetFields()
              }}>
                {t('common:general.cancel')}
              </Button>
              <Button
                type="primary"
                danger
                htmlType="submit"
                loading={disable2FAMutation.isPending}
              >
                {t('twoFactorAuth.disableModal.submit')}
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}

export default TwoFactorSettings