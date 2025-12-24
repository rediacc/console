import React from 'react';
import { Alert, Button, Flex, Form, Input, QRCode, Space, Tabs, Typography } from 'antd';
import { OTPCodeField } from '@/features/settings/components/profile/OTPCodeField';
import { CopyOutlined, SafetyCertificateOutlined } from '@/utils/optimizedIcons';
import type { FormInstance } from 'antd/es/form';
import type { TFunction } from 'i18next';

const { Title, Paragraph } = Typography;

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

export const VerificationContent: React.FC<VerificationContentProps> = ({
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
        <Flex vertical align="center" className="text-center" data-testid="tfa-settings-qr-tab">
          <Flex className="inline-flex">
            <QRCode value={otpUrl} size={200} data-testid="tfa-settings-qr-code" />
          </Flex>
          <Typography.Text>{t('twoFactorAuth.scanQRCode')}</Typography.Text>
        </Flex>
      ),
    },
    {
      key: 'manual',
      label: t('twoFactorAuth.setupMethods.manual'),
      children: (
        <Alert
          className="w-full"
          message={t('twoFactorAuth.manualSetup.title')}
          description={
            <Flex vertical gap={8} className="w-full">
              <Typography.Text>{t('twoFactorAuth.manualSetup.instructions')}</Typography.Text>
              <Space.Compact className="w-full">
                <Input value={secret} readOnly data-testid="tfa-settings-secret-key-input" />
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
    <Flex vertical gap={24} className="w-full">
      <Flex vertical align="center" className="text-center">
        <SafetyCertificateOutlined />
        <Title level={4}>{t('twoFactorAuth.verification.title')}</Title>
        <Paragraph>{t('twoFactorAuth.verification.subtitle')}</Paragraph>
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

        <Form.Item>
          <Flex justify="space-between" className="w-full">
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
