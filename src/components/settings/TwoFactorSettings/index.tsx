import React, { useState, useEffect } from 'react'
import { Modal, Button, Form, Input, Typography, Spin, Result, Tabs, Card } from 'antd'
import type { FormInstance } from 'antd/es/form'
import type { TFunction } from 'i18next'
import { KeyOutlined, CheckCircleOutlined, WarningOutlined, CopyOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useGetTFAStatus, useEnableTFA, useDisableTFA } from '@/api/queries/twoFactor'
import { useSelector } from 'react-redux'
import { RootState } from '@/store/store'
import QRCode from 'react-qr-code'
import { message } from 'antd'
import { DESIGN_TOKENS } from '@/utils/styleConstants'
import { ModalSize } from '@/types/modal'
import {
  LoadingContainer,
  FullWidthStack,
  CenteredStack,
  StatusIcon,
  SectionTitle,
  QRCodeContainer,
  ManualSetupAlert,
  SecretInputRow,
  SecretInput,
  CenteredCodeInput,
  FormActionRow,
  PrimaryButton,
  AlertSpacer,
  CardContent,
  FormItemNoMargin,
  ModalTitleIcon,
  ModalTitleWrapper,
} from './styles'

const { Title, Text, Paragraph } = Typography

interface TwoFactorSettingsProps {
  open: boolean
  onCancel: () => void
}

const TwoFactorSettings: React.FC<TwoFactorSettingsProps> = ({ open, onCancel }) => {
  const { t } = useTranslation('settings')
  const [passwordForm] = Form.useForm()
  const [disableForm] = Form.useForm()
  const [verificationForm] = Form.useForm()
  const userEmail = useSelector((state: RootState) => state.auth.user?.email) || ''

  const { data: twoFAStatus, isLoading: statusLoading, refetch: refetchTFAStatus } = useGetTFAStatus()
  const enableTFAMutation = useEnableTFA()
  const disableTFAMutation = useDisableTFA()

  const [showEnableModal, setShowEnableModal] = useState(false)
  const [showDisableModal, setShowDisableModal] = useState(false)
  const [twoFASecret, setTwoFASecret] = useState('')
  const [showSuccess, setShowSuccess] = useState(false)
  const [showVerification, setShowVerification] = useState(false)
  const [prevOpen, setPrevOpen] = useState(open)

  if (open !== prevOpen) {
    setPrevOpen(open)
    if (open) {
      setShowSuccess(false)
      setShowVerification(false)
      setTwoFASecret('')
      verificationForm.resetFields()
    }
  }

  useEffect(() => {
    if (open) {
      refetchTFAStatus()
    }
  }, [open, refetchTFAStatus])

  const handleEnableTFA = async (values: { password: string }) => {
    try {
      const result = await enableTFAMutation.mutateAsync({
        password: values.password,
        generateOnly: true,
      })
      setTwoFASecret(result.secret)
      setShowEnableModal(false)
      setShowVerification(true)
      passwordForm.resetFields()
    } catch (error: any) {
      if (error.message?.includes('already enabled')) {
        setShowEnableModal(false)
        passwordForm.resetFields()
      }
    }
  }

  const handleVerifyTFA = async (values: { code: string }) => {
    try {
      await enableTFAMutation.mutateAsync({
        password: '',
        verificationCode: values.code,
        secret: twoFASecret,
        confirmEnable: true,
      })
      setShowVerification(false)
      setShowSuccess(true)
      verificationForm.resetFields()
    } catch (_error) {
      // handled via mutation notifications
    }
  }

  const handleDisableTFA = async (values: { password: string; code: string }) => {
    try {
      await disableTFAMutation.mutateAsync({
        password: values.password,
        currentCode: values.code,
      })
      setShowDisableModal(false)
      disableForm.resetFields()
    } catch (_error) {
      // handled via mutation notifications
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

  const mainContent = (() => {
    if (statusLoading) {
      return <LoadingState />
    }

    if (showVerification && twoFASecret) {
      return (
        <VerificationContent
          secret={twoFASecret}
          userEmail={userEmail}
          verificationForm={verificationForm}
          onCancel={() => {
            setShowVerification(false)
            setTwoFASecret('')
            verificationForm.resetFields()
          }}
          onSubmit={handleVerifyTFA}
          isSubmitting={enableTFAMutation.isPending}
          copySecret={copyToClipboard}
          generateOtpAuthUrl={generateOtpAuthUrl}
          t={t}
        />
      )
    }

    if (showSuccess) {
      return (
        <SuccessContent
          t={t}
          onDone={() => {
            setShowSuccess(false)
            setTwoFASecret('')
            refetchTFAStatus()
          }}
        />
      )
    }

    return (
      <StatusOverview
        t={t}
        isEnabled={Boolean(twoFAStatus?.isTFAEnabled)}
        onEnable={() => setShowEnableModal(true)}
        onDisable={() => setShowDisableModal(true)}
      />
    )
  })()

  return (
    <>
      <Modal
        title={
          <ModalTitleWrapper>
            <ModalTitleIcon />
            <span>{t('twoFactorAuth.title')}</span>
          </ModalTitleWrapper>
        }
        open={open}
        onCancel={onCancel}
        footer={null}
        className={ModalSize.Medium}
        data-testid="tfa-settings-main-modal"
      >
        {mainContent}
      </Modal>

      <EnableTwoFactorModal
        open={showEnableModal}
        onCancel={() => {
          setShowEnableModal(false)
          passwordForm.resetFields()
        }}
        form={passwordForm}
        onSubmit={handleEnableTFA}
        isSubmitting={enableTFAMutation.isPending}
        t={t}
      />

      <DisableTwoFactorModal
        open={showDisableModal}
        onCancel={() => {
          setShowDisableModal(false)
          disableForm.resetFields()
        }}
        form={disableForm}
        onSubmit={handleDisableTFA}
        isSubmitting={disableTFAMutation.isPending}
        t={t}
      />
    </>
  )
}

export default TwoFactorSettings

const LoadingState = () => (
  <LoadingContainer data-testid="tfa-settings-loading">
    <Spin size="large" />
  </LoadingContainer>
)

interface VerificationContentProps {
  secret: string
  userEmail: string
  verificationForm: FormInstance
  onCancel: () => void
  onSubmit: (values: { code: string }) => void
  isSubmitting: boolean
  copySecret: (value: string) => void
  generateOtpAuthUrl: (secret: string, email: string) => string
  t: TFunction<'settings'>
}

const VerificationContent: React.FC<VerificationContentProps> = ({
  secret,
  userEmail,
  verificationForm,
  onCancel,
  onSubmit,
  isSubmitting,
  copySecret,
  generateOtpAuthUrl,
  t,
}) => {
  const otpUrl = generateOtpAuthUrl(secret, userEmail)

  const tabItems = [
    {
      key: 'qrcode',
      label: t('twoFactorAuth.setupMethods.qrCode'),
      children: (
        <CenteredStack data-testid="tfa-settings-qr-tab">
          <QRCodeContainer>
            <QRCode value={otpUrl} size={200} data-testid="tfa-settings-qr-code" />
          </QRCodeContainer>
          <Text type="secondary">{t('twoFactorAuth.scanQRCode')}</Text>
        </CenteredStack>
      ),
    },
    {
      key: 'manual',
      label: t('twoFactorAuth.setupMethods.manual'),
      children: (
        <ManualSetupAlert
          message={t('twoFactorAuth.manualSetup.title')}
          description={
            <FullWidthStack>
              <Text>{t('twoFactorAuth.manualSetup.instructions')}</Text>
              <SecretInputRow>
                <SecretInput value={secret} readOnly data-testid="tfa-settings-secret-key-input" />
                <Button
                  icon={<CopyOutlined />}
                  onClick={() => copySecret(secret)}
                  data-testid="tfa-settings-copy-secret-button"
                />
              </SecretInputRow>
            </FullWidthStack>
          }
          type="info"
          data-testid="tfa-settings-manual-setup-alert"
        />
      ),
    },
  ]

  return (
    <FullWidthStack $gap="LG">
      <CenteredStack>
        <StatusIcon />
        <SectionTitle level={4}>{t('twoFactorAuth.verification.title')}</SectionTitle>
        <Paragraph type="secondary">{t('twoFactorAuth.verification.subtitle')}</Paragraph>
      </CenteredStack>

      <Tabs data-testid="tfa-settings-setup-tabs" items={tabItems} />

      <Form form={verificationForm} layout="vertical" onFinish={onSubmit}>
        <Form.Item
          name="code"
          label={t('twoFactorAuth.verification.codeLabel')}
          rules={[
            { required: true, message: t('twoFactorAuth.verification.codeRequired') },
            { len: 6, message: t('twoFactorAuth.verification.codeLength') },
            { pattern: /^\d{6}$/, message: t('twoFactorAuth.verification.codeFormat') },
          ]}
        >
          <CenteredCodeInput
            size="large"
            placeholder={t('twoFactorAuth.verification.codePlaceholder')}
            maxLength={6}
            autoComplete="off"
            data-testid="tfa-settings-verification-input"
          />
        </Form.Item>

        <FormItemNoMargin>
          <FormActionRow $align="space-between">
            <Button onClick={onCancel} data-testid="tfa-settings-verification-cancel-button">
              {t('common:general.cancel')}
            </Button>
            <PrimaryButton
              type="primary"
              htmlType="submit"
              loading={isSubmitting}
              data-testid="tfa-settings-verification-submit-button"
            >
              {t('twoFactorAuth.verification.submit')}
            </PrimaryButton>
          </FormActionRow>
        </FormItemNoMargin>
      </Form>
    </FullWidthStack>
  )
}

interface SuccessContentProps {
  t: TFunction<'settings'>
  onDone: () => void
}

const SuccessContent: React.FC<SuccessContentProps> = ({ t, onDone }) => (
  <Result
    status="success"
    title={t('twoFactorAuth.enableSuccess.title')}
    subTitle={t('twoFactorAuth.enableSuccess.subtitle')}
    data-testid="tfa-settings-success-result"
    extra={
      <FullWidthStack $gap="LG">
        <AlertSpacer
          message={t('twoFactorAuth.enableSuccess.verified')}
          description={t('twoFactorAuth.enableSuccess.verifiedDescription')}
          type="success"
          showIcon
          icon={<CheckCircleOutlined />}
          data-testid="tfa-settings-success-alert"
        />

        <PrimaryButton
          type="primary"
          size="large"
          block
          onClick={onDone}
          data-testid="tfa-settings-success-done-button"
        >
          {t('twoFactorAuth.done')}
        </PrimaryButton>
      </FullWidthStack>
    }
  />
)

interface StatusOverviewProps {
  isEnabled: boolean
  onEnable: () => void
  onDisable: () => void
  t: TFunction<'settings'>
}

const StatusOverview: React.FC<StatusOverviewProps> = ({ isEnabled, onEnable, onDisable, t }) => (
  <FullWidthStack $gap="LG">
    <CenteredStack>
      <StatusIcon $tone={isEnabled ? 'success' : 'muted'} $size={DESIGN_TOKENS.FONT_SIZE.XXXXXXL} />
      <SectionTitle level={4}>
        {isEnabled ? t('twoFactorAuth.status.enabled') : t('twoFactorAuth.status.disabled')}
      </SectionTitle>
      <Paragraph type="secondary">
        {isEnabled ? t('twoFactorAuth.status.enabledDescription') : t('twoFactorAuth.status.disabledDescription')}
      </Paragraph>
    </CenteredStack>

    <Card>
      <CardContent>
        <Title level={5}>{t('twoFactorAuth.whatIs.title')}</Title>
        <Paragraph>{t('twoFactorAuth.whatIs.description')}</Paragraph>
        <ul>
          <li>{t('twoFactorAuth.whatIs.benefit1')}</li>
          <li>{t('twoFactorAuth.whatIs.benefit2')}</li>
          <li>{t('twoFactorAuth.whatIs.benefit3')}</li>
        </ul>
      </CardContent>
    </Card>

    {isEnabled ? (
      <Button
        type="primary"
        danger
        size="large"
        block
        icon={<WarningOutlined />}
        onClick={onDisable}
        data-testid="tfa-settings-disable-button"
      >
        {t('twoFactorAuth.disable')}
      </Button>
    ) : (
      <PrimaryButton
        type="primary"
        size="large"
        block
        icon={<CheckCircleOutlined />}
        onClick={onEnable}
        data-testid="tfa-settings-enable-button"
      >
        {t('twoFactorAuth.enable')}
      </PrimaryButton>
    )}
  </FullWidthStack>
)

interface EnableModalProps {
  open: boolean
  onCancel: () => void
  form: FormInstance
  onSubmit: (values: { password: string }) => void
  isSubmitting: boolean
  t: TFunction<'settings'>
}

const EnableTwoFactorModal: React.FC<EnableModalProps> = ({ open, onCancel, form, onSubmit, isSubmitting, t }) => (
  <Modal
    title={t('twoFactorAuth.enableModal.title')}
    open={open}
    onCancel={onCancel}
    footer={null}
    className={ModalSize.Medium}
    data-testid="tfa-settings-enable-modal"
  >
    <Form form={form} layout="vertical" onFinish={onSubmit}>
      <AlertSpacer
        message={t('twoFactorAuth.enableModal.warning')}
        description={t('twoFactorAuth.enableModal.warningDescription')}
        type="warning"
        showIcon
        data-testid="tfa-settings-enable-warning-alert"
      />

      <Form.Item
        name="password"
        label={t('twoFactorAuth.enableModal.passwordLabel')}
        rules={[{ required: true, message: t('twoFactorAuth.enableModal.passwordRequired') }]}
      >
        <Input.Password
          prefix={<KeyOutlined />}
          placeholder={t('twoFactorAuth.enableModal.passwordPlaceholder')}
          size="large"
          autoComplete="off"
          data-testid="tfa-settings-enable-password-input"
        />
      </Form.Item>

      <FormItemNoMargin>
        <FormActionRow>
          <Button onClick={onCancel} data-testid="tfa-settings-enable-cancel-button">
            {t('common:general.cancel')}
          </Button>
          <PrimaryButton
            type="primary"
            htmlType="submit"
            loading={isSubmitting}
            data-testid="tfa-settings-enable-submit-button"
          >
            {t('twoFactorAuth.enableModal.submit')}
          </PrimaryButton>
        </FormActionRow>
      </FormItemNoMargin>
    </Form>
  </Modal>
)

interface DisableModalProps {
  open: boolean
  onCancel: () => void
  form: FormInstance
  onSubmit: (values: { password: string; code: string }) => void
  isSubmitting: boolean
  t: TFunction<'settings'>
}

const DisableTwoFactorModal: React.FC<DisableModalProps> = ({
  open,
  onCancel,
  form,
  onSubmit,
  isSubmitting,
  t,
}) => (
  <Modal
    title={t('twoFactorAuth.disableModal.title')}
    open={open}
    onCancel={onCancel}
    footer={null}
    className={ModalSize.Medium}
    data-testid="tfa-settings-disable-modal"
  >
    <Form form={form} layout="vertical" onFinish={onSubmit}>
      <AlertSpacer
        message={t('twoFactorAuth.disableModal.warning')}
        description={t('twoFactorAuth.disableModal.warningDescription')}
        type="error"
        showIcon
        data-testid="tfa-settings-disable-warning-alert"
      />

      <Form.Item
        name="password"
        label={t('twoFactorAuth.disableModal.passwordLabel')}
        rules={[{ required: true, message: t('twoFactorAuth.disableModal.passwordRequired') }]}
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
          { pattern: /^\d{6}$/, message: t('twoFactorAuth.disableModal.codeFormat') },
        ]}
      >
        <CenteredCodeInput
          size="large"
          placeholder={t('twoFactorAuth.disableModal.codePlaceholder')}
          maxLength={6}
          autoComplete="off"
          data-testid="tfa-settings-disable-code-input"
        />
      </Form.Item>

      <FormItemNoMargin>
        <FormActionRow>
          <Button onClick={onCancel} data-testid="tfa-settings-disable-cancel-button">
            {t('common:general.cancel')}
          </Button>
          <Button
            type="primary"
            danger
            htmlType="submit"
            loading={isSubmitting}
            data-testid="tfa-settings-disable-submit-button"
          >
            {t('twoFactorAuth.disableModal.submit')}
          </Button>
        </FormActionRow>
      </FormItemNoMargin>
    </Form>
  </Modal>
)
