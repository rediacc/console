import React, { useState, useEffect } from 'react'
import { Modal, Button, Space, Form, Input, Typography, Alert, Spin, Result, Tabs, Card } from 'antd'
import { SafetyCertificateOutlined, KeyOutlined, CheckCircleOutlined, WarningOutlined, CopyOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useGetTFAStatus, useEnableTFA, useDisableTFA } from '@/api/queries/twoFactor'
import { useSelector } from 'react-redux'
import { RootState } from '@/store/store'
import QRCode from 'react-qr-code'
import { message } from 'antd'
import { useComponentStyles } from '@/hooks/useComponentStyles'
import { DESIGN_TOKENS, spacing, fontSize } from '@/utils/styleConstants'
import { ModalSize } from '@/types/modal'

const { Title, Text, Paragraph } = Typography

interface TwoFactorSettingsProps {
  open: boolean
  onCancel: () => void
}

const TwoFactorSettings: React.FC<TwoFactorSettingsProps> = ({ open, onCancel }) => {
  const { t } = useTranslation('settings')
  const styles = useComponentStyles()
  const [passwordForm] = Form.useForm()
  const [disableForm] = Form.useForm()
  const userEmail = useSelector((state: RootState) => state.auth.user?.email)
  
  const { data: twoFAStatus, isLoading: statusLoading, refetch: refetchTFAStatus } = useGetTFAStatus()
  
  const enableTFAMutation = useEnableTFA()
  const disableTFAMutation = useDisableTFA()
  
  const [showEnableModal, setShowEnableModal] = useState(false)
  const [showDisableModal, setShowDisableModal] = useState(false)
  const [twoFASecret, setTwoFASecret] = useState<string>('')
  const [showSuccess, setShowSuccess] = useState(false)
  const [showVerification, setShowVerification] = useState(false)
  const [verificationForm] = Form.useForm()
  
  // Refresh TFA status when modal opens and reset states
  useEffect(() => {
    if (open) {
      // Reset states when modal opens
      setShowSuccess(false)
      setShowVerification(false)
      setTwoFASecret('')
      verificationForm.resetFields()
      // Fetch fresh status
      refetchTFAStatus()
    }
  }, [open, refetchTFAStatus, verificationForm])

  const handleEnableTFA = async (values: { password: string }) => {
    try {
      const result = await enableTFAMutation.mutateAsync({ 
        password: values.password,
        generateOnly: true  // Generate secret without saving
      })
      setTwoFASecret(result.secret)
      setShowEnableModal(false)
      setShowVerification(true)  // Show verification modal
      passwordForm.resetFields()
    } catch (error: any) {
      // Error is handled by mutation, but we should close the modal
      // if TFA is already enabled
      if (error.message?.includes('already enabled')) {
        setShowEnableModal(false)
        passwordForm.resetFields()
      }
    }
  }

  const handleVerifyTFA = async (values: { code: string }) => {
    try {
      await enableTFAMutation.mutateAsync({ 
        password: '', // Not needed for verification
        verificationCode: values.code,
        secret: twoFASecret,
        confirmEnable: true  // Confirm enabling with verification
      })
      setShowVerification(false)
      setShowSuccess(true)
      verificationForm.resetFields()
    } catch (_error) {
      // Error handled by mutation
    }
  }

  const handleDisableTFA = async (values: { password: string; code: string }) => {
    try {
      await disableTFAMutation.mutateAsync({ 
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
        <div style={{ textAlign: 'center', padding: `${spacing('XXXL')}px 0` }} data-testid="tfa-settings-loading">
          <Spin size="large" />
        </div>
      )
    }

    if (showVerification && twoFASecret) {
      return (
        <Space direction="vertical" size={spacing('LG')} style={{ width: '100%' }}>
          <div style={{ textAlign: 'center' }}>
            <SafetyCertificateOutlined style={{ fontSize: DESIGN_TOKENS.FONT_SIZE.XXXXL, color: 'var(--color-primary)' }} />
            <Title level={4} style={{ marginTop: spacing('MD') }}>
              {t('twoFactorAuth.verification.title')}
            </Title>
            <Paragraph type="secondary">
              {t('twoFactorAuth.verification.subtitle')}
            </Paragraph>
          </div>

          <Tabs
            data-testid="tfa-settings-setup-tabs"
            items={[
              {
                key: 'qrcode',
                label: t('twoFactorAuth.setupMethods.qrCode'),
                children: (
                  <Space direction="vertical" align="center" style={{ width: '100%' }}>
                    <div style={{ background: 'white', padding: spacing('MD'), borderRadius: DESIGN_TOKENS.BORDER_RADIUS.LG }}>
                      <QRCode 
                        value={generateOtpAuthUrl(twoFASecret, userEmail || '')} 
                        size={200}
                        data-testid="tfa-settings-qr-code"
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
                          <Space.Compact style={{ width: '100%', marginTop: spacing('SM') }}>
                            <Input 
                              value={twoFASecret} 
                              readOnly 
                              style={{ fontFamily: 'monospace' }}
                              data-testid="tfa-settings-secret-key-input"
                            />
                            <Button 
                              icon={<CopyOutlined />}
                              onClick={() => copyToClipboard(twoFASecret)}
                              data-testid="tfa-settings-copy-secret-button"
                            />
                          </Space.Compact>
                        </Space>
                      }
                      type="info"
                      data-testid="tfa-settings-manual-setup-alert"
                    />
                  </Space>
                ),
              },
            ]}
          />

          <Form
            form={verificationForm}
            layout="vertical"
            onFinish={handleVerifyTFA}
          >
            <Form.Item
              name="code"
              label={t('twoFactorAuth.verification.codeLabel')}
              rules={[
                { required: true, message: t('twoFactorAuth.verification.codeRequired') },
                { len: 6, message: t('twoFactorAuth.verification.codeLength') },
                { pattern: /^\d{6}$/, message: t('twoFactorAuth.verification.codeFormat') }
              ]}
            >
              <Input
                size="large"
                placeholder={t('twoFactorAuth.verification.codePlaceholder')}
                maxLength={6}
                style={{ textAlign: 'center', fontSize: DESIGN_TOKENS.FONT_SIZE.XL, letterSpacing: DESIGN_TOKENS.LETTER_SPACING.WIDER }}
                autoComplete="off"
                data-testid="tfa-settings-verification-input"
              />
            </Form.Item>

            <Form.Item style={{ marginBottom: 0 }}>
              <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                <Button 
                  onClick={() => {
                    setShowVerification(false)
                    setTwoFASecret('')
                    verificationForm.resetFields()
                  }}
                  data-testid="tfa-settings-verification-cancel-button"
                >
                  {t('common:general.cancel')}
                </Button>
                <Button
                  type="primary"
                  htmlType="submit"
                  loading={enableTFAMutation.isPending}
                  style={{
                    background: 'var(--color-primary)',
                    borderColor: 'var(--color-primary)',
                  }}
                  data-testid="tfa-settings-verification-submit-button"
                >
                  {t('twoFactorAuth.verification.submit')}
                </Button>
              </Space>
            </Form.Item>
          </Form>
        </Space>
      )
    }

    if (showSuccess) {
      return (
        <Result
          status="success"
          title={t('twoFactorAuth.enableSuccess.title')}
          subTitle={t('twoFactorAuth.enableSuccess.subtitle')}
          data-testid="tfa-settings-success-result"
          extra={
            <Space direction="vertical" size={spacing('LG')} style={{ width: '100%' }}>
              <Alert
                message={t('twoFactorAuth.enableSuccess.verified')}
                description={t('twoFactorAuth.enableSuccess.verifiedDescription')}
                type="success"
                showIcon
                icon={<CheckCircleOutlined />}
                data-testid="tfa-settings-success-alert"
              />
              
              <Button 
                type="primary" 
                size="large" 
                block
                onClick={() => {
                  setShowSuccess(false)
                  setTwoFASecret('')
                  // Refetch to ensure we have the latest status
                  refetchTFAStatus()
                }}
                style={{
                  background: 'var(--color-primary)',
                  borderColor: 'var(--color-primary)',
                }}
                data-testid="tfa-settings-success-done-button"
              >
                {t('twoFactorAuth.done')}
              </Button>
            </Space>
          }
        />
      )
    }

    // Ensure we have a boolean value for isTFAEnabled
    const isTFAEnabled = Boolean(twoFAStatus?.isTFAEnabled)

    return (
      <Space direction="vertical" size={spacing('LG')} style={{ width: '100%' }}>
        <div style={{ textAlign: 'center' }}>
          <SafetyCertificateOutlined style={{ fontSize: DESIGN_TOKENS.FONT_SIZE.XXXXXXL, color: isTFAEnabled ? 'var(--color-success)' : 'var(--color-text-quaternary)' }} />
          <Title level={4} style={{ marginTop: spacing('MD') }}>
            {isTFAEnabled ? t('twoFactorAuth.status.enabled') : t('twoFactorAuth.status.disabled')}
          </Title>
          <Paragraph type="secondary">
            {isTFAEnabled 
              ? t('twoFactorAuth.status.enabledDescription')
              : t('twoFactorAuth.status.disabledDescription')
            }
          </Paragraph>
        </div>

        <Card>
          <Space direction="vertical" size={spacing('MD')} style={{ width: '100%' }}>
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

        {isTFAEnabled ? (
          <Button
            type="primary"
            danger
            size="large"
            block
            icon={<WarningOutlined />}
            onClick={() => setShowDisableModal(true)}
            data-testid="tfa-settings-disable-button"
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
              background: 'var(--color-primary)',
              borderColor: 'var(--color-primary)',
            }}
            data-testid="tfa-settings-enable-button"
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
            <SafetyCertificateOutlined style={{ color: 'var(--color-primary)' }} />
            <span>{t('twoFactorAuth.title')}</span>
          </Space>
        }
        open={open}
        onCancel={onCancel}
        footer={null}
        className={ModalSize.Medium}
        data-testid="tfa-settings-main-modal"
      >
        {renderMainContent()}
      </Modal>

      {/* Enable TFA Modal */}
      <Modal
        title={t('twoFactorAuth.enableModal.title')}
        open={showEnableModal}
        onCancel={() => {
          setShowEnableModal(false)
          passwordForm.resetFields()
        }}
        footer={null}
        className={ModalSize.Medium}
        data-testid="tfa-settings-enable-modal"
      >
        <Form
          form={passwordForm}
          layout="vertical"
          onFinish={handleEnableTFA}
        >
          <Alert
            message={t('twoFactorAuth.enableModal.warning')}
            description={t('twoFactorAuth.enableModal.warningDescription')}
            type="warning"
            showIcon
            style={{ marginBottom: spacing('LG') }}
            data-testid="tfa-settings-enable-warning-alert"
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
              autoComplete="off"
              data-testid="tfa-settings-enable-password-input"
            />
          </Form.Item>
          
          <Form.Item style={{ marginBottom: 0 }}>
            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
              <Button 
                onClick={() => {
                  setShowEnableModal(false)
                  passwordForm.resetFields()
                }}
                data-testid="tfa-settings-enable-cancel-button"
              >
                {t('common:general.cancel')}
              </Button>
              <Button
                type="primary"
                htmlType="submit"
                loading={enableTFAMutation.isPending}
                style={{
                  background: 'var(--color-primary)',
                  borderColor: 'var(--color-primary)',
                }}
                data-testid="tfa-settings-enable-submit-button"
              >
                {t('twoFactorAuth.enableModal.submit')}
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* Disable TFA Modal */}
      <Modal
        title={t('twoFactorAuth.disableModal.title')}
        open={showDisableModal}
        onCancel={() => {
          setShowDisableModal(false)
          disableForm.resetFields()
        }}
        footer={null}
        className={ModalSize.Medium}
        data-testid="tfa-settings-disable-modal"
      >
        <Form
          form={disableForm}
          layout="vertical"
          onFinish={handleDisableTFA}
        >
          <Alert
            message={t('twoFactorAuth.disableModal.warning')}
            description={t('twoFactorAuth.disableModal.warningDescription')}
            type="error"
            showIcon
            style={{ marginBottom: spacing('LG') }}
            data-testid="tfa-settings-disable-warning-alert"
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
              autoComplete="off"
              data-testid="tfa-settings-disable-password-input"
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
              style={{ textAlign: 'center', fontSize: DESIGN_TOKENS.FONT_SIZE.XL, letterSpacing: DESIGN_TOKENS.LETTER_SPACING.WIDER }}
              autoComplete="off"
              data-testid="tfa-settings-disable-code-input"
            />
          </Form.Item>
          
          <Form.Item style={{ marginBottom: 0 }}>
            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
              <Button 
                onClick={() => {
                  setShowDisableModal(false)
                  disableForm.resetFields()
                }}
                data-testid="tfa-settings-disable-cancel-button"
              >
                {t('common:general.cancel')}
              </Button>
              <Button
                type="primary"
                danger
                htmlType="submit"
                loading={disableTFAMutation.isPending}
                data-testid="tfa-settings-disable-submit-button"
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