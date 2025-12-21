import React, { useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Flex,
  Form,
  Input,
  Modal,
  Result,
  Space,
  Tabs,
  Typography,
} from 'antd';
import { useTranslation } from 'react-i18next';
import QRCode from 'react-qr-code';
import { useSelector } from 'react-redux';
import {
  useDisableTFA,
  useEnableTFA,
  useTFAStatus,
  type EnableTwoFactorResponse,
} from '@/api/queries/twoFactor';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { useCopyToClipboard } from '@/hooks';
import { useDialogState } from '@/hooks/useDialogState';
import { OTPCodeField } from '@/pages/settings/profile/components/OTPCodeField';
import { RootState } from '@/store/store';
import { ModalSize } from '@/types/modal';
import {
  CheckCircleOutlined,
  CopyOutlined,
  KeyOutlined,
  SafetyCertificateOutlined,
  WarningOutlined,
} from '@/utils/optimizedIcons';
import type { FormInstance } from 'antd/es/form';
import type { TFunction } from 'i18next';

const { Title, Paragraph } = Typography;

interface TwoFactorSettingsProps {
  open: boolean;
  onCancel: () => void;
}

const TwoFactorSettings: React.FC<TwoFactorSettingsProps> = ({ open, onCancel }) => {
  const { t } = useTranslation('settings');
  const { copy: copyToClipboard } = useCopyToClipboard({
    successMessage: 'settings:twoFactorAuth.secretCopied',
  });
  const [passwordForm] = Form.useForm();
  const [disableForm] = Form.useForm();
  const [verificationForm] = Form.useForm();
  const userEmail = useSelector((state: RootState) => state.auth.user?.email) || '';

  const { data: twoFAStatus, isLoading: statusLoading, refetch: refetchTFAStatus } = useTFAStatus();
  const enableTFAMutation = useEnableTFA();
  const disableTFAMutation = useDisableTFA();

  const enableModal = useDialogState<void>();
  const disableModal = useDialogState<void>();
  const [twoFASecret, setTwoFASecret] = useState('');
  const [showSuccess, setShowSuccess] = useState(false);
  const [showVerification, setShowVerification] = useState(false);
  const [prevOpen, setPrevOpen] = useState(open);

  if (open !== prevOpen) {
    setPrevOpen(open);
    if (open) {
      setShowSuccess(false);
      setShowVerification(false);
      setTwoFASecret('');
      verificationForm.resetFields();
    }
  }

  useEffect(() => {
    if (open) {
      refetchTFAStatus();
    }
  }, [open, refetchTFAStatus]);

  const handleEnableTFA = async (values: { password: string }) => {
    try {
      const result = (await enableTFAMutation.mutateAsync({
        password: values.password,
        generateOnly: true,
      })) as EnableTwoFactorResponse;
      setTwoFASecret(result.secret ?? '');
      enableModal.close();
      setShowVerification(true);
      passwordForm.resetFields();
    } catch (error: unknown) {
      if (error instanceof Error && error.message?.includes('already enabled')) {
        enableModal.close();
        passwordForm.resetFields();
      }
    }
  };

  const handleVerifyTFA = async (values: { code: string }) => {
    try {
      await enableTFAMutation.mutateAsync({
        password: '',
        verificationCode: values.code,
        secret: twoFASecret,
        confirmEnable: true,
      });
      setShowVerification(false);
      setShowSuccess(true);
      verificationForm.resetFields();
    } catch {
      // handled via mutation notifications
    }
  };

  const handleDisableTFA = async (values: { password: string; code: string }) => {
    try {
      await disableTFAMutation.mutateAsync({
        password: values.password,
        currentCode: values.code,
      });
      disableModal.close();
      disableForm.resetFields();
    } catch {
      // handled via mutation notifications
    }
  };

  const generateOtpAuthUrl = (secret: string, email: string) => {
    const issuer = 'Rediacc';
    const encodedIssuer = encodeURIComponent(issuer);
    const encodedEmail = encodeURIComponent(email);
    return `otpauth://totp/${encodedIssuer}:${encodedEmail}?secret=${secret}&issuer=${encodedIssuer}`;
  };

  const mainContent = (() => {
    if (statusLoading) {
      return <LoadingState />;
    }

    if (showVerification && twoFASecret) {
      return (
        <VerificationContent
          secret={twoFASecret}
          userEmail={userEmail}
          verificationForm={verificationForm}
          onCancel={() => {
            setShowVerification(false);
            setTwoFASecret('');
            verificationForm.resetFields();
          }}
          onSubmit={handleVerifyTFA}
          isSubmitting={enableTFAMutation.isPending}
          copySecret={copyToClipboard}
          generateOtpAuthUrl={generateOtpAuthUrl}
          t={t}
        />
      );
    }

    if (showSuccess) {
      return (
        <SuccessContent
          t={t}
          onDone={() => {
            setShowSuccess(false);
            setTwoFASecret('');
            refetchTFAStatus();
          }}
        />
      );
    }

    return (
      <StatusOverview
        t={t}
        isEnabled={Boolean(twoFAStatus?.isTFAEnabled)}
        onEnable={() => enableModal.open()}
        onDisable={() => disableModal.open()}
      />
    );
  })();

  return (
    <>
      <Modal
        title={
          <Typography.Text style={{ display: 'inline-flex', alignItems: 'center' }}>
            <SafetyCertificateOutlined style={{ fontSize: 16 }} />
            <Typography.Text>{t('twoFactorAuth.title')}</Typography.Text>
          </Typography.Text>
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
        open={enableModal.isOpen}
        onCancel={() => {
          enableModal.close();
          passwordForm.resetFields();
        }}
        form={passwordForm}
        onSubmit={handleEnableTFA}
        isSubmitting={enableTFAMutation.isPending}
        t={t}
      />

      <DisableTwoFactorModal
        open={disableModal.isOpen}
        onCancel={() => {
          disableModal.close();
          disableForm.resetFields();
        }}
        form={disableForm}
        onSubmit={handleDisableTFA}
        isSubmitting={disableTFAMutation.isPending}
        t={t}
      />
    </>
  );
};

export default TwoFactorSettings;

const LoadingState = () => (
  <LoadingWrapper loading centered minHeight={160} data-testid="tfa-settings-loading">
    <Flex />
  </LoadingWrapper>
);

interface VerificationContentProps {
  secret: string;
  userEmail: string;
  verificationForm: FormInstance;
  onCancel: () => void;
  onSubmit: (values: { code: string }) => void;
  isSubmitting: boolean;
  copySecret: (value: string) => void;
  generateOtpAuthUrl: (secret: string, email: string) => string;
  t: TFunction<'settings'>;
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
  const otpUrl = generateOtpAuthUrl(secret, userEmail);

  const tabItems = [
    {
      key: 'qrcode',
      label: t('twoFactorAuth.setupMethods.qrCode'),
      children: (
        <Flex
          vertical
          align="center"
          style={{ textAlign: 'center', alignItems: 'center' }}
          data-testid="tfa-settings-qr-tab"
        >
          <Flex style={{ display: 'inline-flex' }}>
            <QRCode value={otpUrl} size={200} data-testid="tfa-settings-qr-code" />
          </Flex>
          <Typography.Text>
            {t('twoFactorAuth.scanQRCode')}
          </Typography.Text>
        </Flex>
      ),
    },
    {
      key: 'manual',
      label: t('twoFactorAuth.setupMethods.manual'),
      children: (
        <Alert
          style={{ width: '100%' }}
          message={t('twoFactorAuth.manualSetup.title')}
          description={
            <Flex vertical gap={8} style={{ width: '100%' }}>
              <Typography.Text>{t('twoFactorAuth.manualSetup.instructions')}</Typography.Text>
              <Space.Compact style={{ width: '100%' }}>
                <Input
                  style={{ fontFamily: 'monospace' }}
                  value={secret}
                  readOnly
                  data-testid="tfa-settings-secret-key-input"
                />
                <Button
                  icon={<CopyOutlined />}
                  onClick={() => copySecret(secret)}
                  data-testid="tfa-settings-copy-secret-button"
                />
              </Space.Compact>
            </Flex>
          }
          type="info"
          data-testid="tfa-settings-manual-setup-alert"
        />
      ),
    },
  ];

  return (
    <Flex vertical gap={24} style={{ width: '100%' }}>
      <Flex vertical align="center" style={{ textAlign: 'center', alignItems: 'center' }}>
        <SafetyCertificateOutlined
          style={{ fontSize: 32 }}
        />
        <Title level={4}>{t('twoFactorAuth.verification.title')}</Title>
        <Paragraph color="secondary">{t('twoFactorAuth.verification.subtitle')}</Paragraph>
      </Flex>

      <Tabs data-testid="tfa-settings-setup-tabs" items={tabItems} />

      <Form form={verificationForm} layout="vertical" onFinish={onSubmit}>
        <OTPCodeField
          name="code"
          label={t('twoFactorAuth.verification.codeLabel')}
          placeholder={t('twoFactorAuth.verification.codePlaceholder')}
          requiredMessage={t('twoFactorAuth.verification.codeRequired')}
          lengthMessage={t('twoFactorAuth.verification.codeLength')}
          formatMessage={t('twoFactorAuth.verification.codeFormat')}
          data-testid="tfa-settings-verification-input"
        />

        <Form.Item style={{ marginBottom: 0 }}>
          <Flex justify="space-between" style={{ width: '100%' }}>
            <Button onClick={onCancel} data-testid="tfa-settings-verification-cancel-button">
              {t('common:general.cancel')}
            </Button>
            <Button
              htmlType="submit"
              loading={isSubmitting}
              data-testid="tfa-settings-verification-submit-button"
            >
              {t('twoFactorAuth.verification.submit')}
            </Button>
          </Flex>
        </Form.Item>
      </Form>
    </Flex>
  );
};

interface SuccessContentProps {
  t: TFunction<'settings'>;
  onDone: () => void;
}

const SuccessContent: React.FC<SuccessContentProps> = ({ t, onDone }) => (
  <Result
    status="success"
    title={t('twoFactorAuth.enableSuccess.title')}
    subTitle={t('twoFactorAuth.enableSuccess.subtitle')}
    data-testid="tfa-settings-success-result"
    extra={
      <Flex vertical gap={24} style={{ width: '100%' }}>
        <Alert
          message={t('twoFactorAuth.enableSuccess.verified')}
          description={t('twoFactorAuth.enableSuccess.verifiedDescription')}
          type="success"
          showIcon
          icon={<CheckCircleOutlined />}
          data-testid="tfa-settings-success-alert"
        />

        <Button block onClick={onDone} data-testid="tfa-settings-success-done-button">
          {t('twoFactorAuth.done')}
        </Button>
      </Flex>
    }
  />
);

interface StatusOverviewProps {
  isEnabled: boolean;
  onEnable: () => void;
  onDisable: () => void;
  t: TFunction<'settings'>;
}

const StatusOverview: React.FC<StatusOverviewProps> = ({ isEnabled, onEnable, onDisable, t }) => (
  <Flex vertical gap={24} style={{ width: '100%' }}>
    <Flex vertical align="center" style={{ textAlign: 'center', alignItems: 'center' }}>
      <SafetyCertificateOutlined
        style={{
          fontSize: 64,
          color: isEnabled ? 'var(--ant-color-success)' : 'var(--ant-color-text-tertiary)',
        }}
      />
      <Title level={4}>
        {isEnabled ? t('twoFactorAuth.status.enabled') : t('twoFactorAuth.status.disabled')}
      </Title>
      <Paragraph color="secondary">
        {isEnabled
          ? t('twoFactorAuth.status.enabledDescription')
          : t('twoFactorAuth.status.disabledDescription')}
      </Paragraph>
    </Flex>

    <Card>
      <Flex vertical gap={8}>
        <Title level={5}>{t('twoFactorAuth.whatIs.title')}</Title>
        <Paragraph>{t('twoFactorAuth.whatIs.description')}</Paragraph>
        <ul>
          <li>{t('twoFactorAuth.whatIs.benefit1')}</li>
          <li>{t('twoFactorAuth.whatIs.benefit2')}</li>
          <li>{t('twoFactorAuth.whatIs.benefit3')}</li>
        </ul>
      </Flex>
    </Card>

    {isEnabled ? (
      <Button
        type="primary"
        danger
        block
        icon={<WarningOutlined />}
        onClick={onDisable}
        data-testid="tfa-settings-disable-button"
      >
        {t('twoFactorAuth.disable')}
      </Button>
    ) : (
      <Button
        type="primary"
        block
        icon={<CheckCircleOutlined />}
        onClick={onEnable}
        data-testid="tfa-settings-enable-button"
      >
        {t('twoFactorAuth.enable')}
      </Button>
    )}
  </Flex>
);

interface EnableModalProps {
  open: boolean;
  onCancel: () => void;
  form: FormInstance;
  onSubmit: (values: { password: string }) => void;
  isSubmitting: boolean;
  t: TFunction<'settings'>;
}

const EnableTwoFactorModal: React.FC<EnableModalProps> = ({
  open,
  onCancel,
  form,
  onSubmit,
  isSubmitting,
  t,
}) => (
  <Modal
    title={t('twoFactorAuth.enableModal.title')}
    open={open}
    onCancel={onCancel}
    footer={null}
    className={ModalSize.Medium}
    data-testid="tfa-settings-enable-modal"
  >
    <Form form={form} layout="vertical" onFinish={onSubmit}>
      <Alert
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
          autoComplete="off"
          data-testid="tfa-settings-enable-password-input"
        />
      </Form.Item>

      <Form.Item style={{ marginBottom: 0 }}>
        <Flex justify="flex-end" style={{ width: '100%' }}>
          <Button onClick={onCancel} data-testid="tfa-settings-enable-cancel-button">
            {t('common:general.cancel')}
          </Button>
          <Button
            htmlType="submit"
            loading={isSubmitting}
            data-testid="tfa-settings-enable-submit-button"
          >
            {t('twoFactorAuth.enableModal.submit')}
          </Button>
        </Flex>
      </Form.Item>
    </Form>
  </Modal>
);

interface DisableModalProps {
  open: boolean;
  onCancel: () => void;
  form: FormInstance;
  onSubmit: (values: { password: string; code: string }) => void;
  isSubmitting: boolean;
  t: TFunction<'settings'>;
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
      <Alert
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
          autoComplete="off"
          data-testid="tfa-settings-disable-password-input"
        />
      </Form.Item>

      <OTPCodeField
        name="code"
        label={t('twoFactorAuth.disableModal.codeLabel')}
        placeholder={t('twoFactorAuth.disableModal.codePlaceholder')}
        requiredMessage={t('twoFactorAuth.disableModal.codeRequired')}
        lengthMessage={t('twoFactorAuth.disableModal.codeLength')}
        formatMessage={t('twoFactorAuth.disableModal.codeFormat')}
        data-testid="tfa-settings-disable-code-input"
      />

      <Form.Item style={{ marginBottom: 0 }}>
        <Flex justify="flex-end" style={{ width: '100%' }}>
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
        </Flex>
      </Form.Item>
    </Form>
  </Modal>
);
