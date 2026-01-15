import React from 'react';
import { Alert, Button, Flex, Form, Input, Modal, Typography } from 'antd';
import { ModalSize } from '@/types/modal';
import { SafetyCertificateOutlined } from '@/utils/optimizedIcons';
import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { FormInstance } from 'antd/es/form';

interface TFAModalProps {
  open: boolean;
  twoFACode: string;
  setTwoFACode: (code: string) => void;
  onVerify: () => void;
  onCancel: () => void;
  isVerifying: boolean;
  twoFAForm: FormInstance;
  t: TypedTFunction;
}

export const TFAModal: React.FC<TFAModalProps> = ({
  open,
  twoFACode,
  setTwoFACode,
  onVerify,
  onCancel,
  isVerifying,
  twoFAForm,
  t,
}) => {
  return (
    <Modal
      title={
        <Flex align="center">
          <SafetyCertificateOutlined />
          <Typography.Text>{t('login.twoFactorAuth.title')}</Typography.Text>
        </Flex>
      }
      open={open}
      onCancel={onCancel}
      footer={null}
      className={ModalSize.Medium}
      centered
      data-testid="tfa-modal"
    >
      <Flex vertical className="w-full">
        <Alert
          message={t('login.twoFactorAuth.required')}
          description={t('login.twoFactorAuth.description')}
          type="info"
          data-testid="tfa-info-alert"
        />

        <Form form={twoFAForm} onFinish={onVerify} layout="vertical">
          <Form.Item
            name="twoFACode"
            label={t('login.twoFactorAuth.codeLabel')}
            rules={[
              { required: true, message: t('common:messages.required') },
              { len: 6, message: t('login.twoFactorAuth.codeLength') },
              { pattern: /^\d{6}$/, message: t('login.twoFactorAuth.codeFormat') },
            ]}
          >
            <Input
              placeholder={t('login.twoFactorAuth.codePlaceholder')}
              value={twoFACode}
              onChange={(e) => setTwoFACode(e.target.value)}
              autoComplete="off"
              maxLength={6}
              data-testid="tfa-code-input"
            />
          </Form.Item>

          <Form.Item>
            <Flex justify="flex-end" className="w-full">
              <Button onClick={onCancel} data-testid="tfa-cancel-button">
                {t('common:general.cancel')}
              </Button>
              <Button
                type="primary"
                htmlType="submit"
                loading={isVerifying}
                disabled={twoFACode.length !== 6}
                data-testid="tfa-verify-button"
              >
                {t('login.twoFactorAuth.verify')}
              </Button>
            </Flex>
          </Form.Item>
        </Form>
      </Flex>
    </Modal>
  );
};
