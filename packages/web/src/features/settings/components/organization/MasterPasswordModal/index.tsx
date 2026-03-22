import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import { Alert, Button, Flex, Form, Modal, Radio, Space, Typography } from 'antd';
import React, { useEffect } from 'react';
import { PasswordConfirmField, PasswordField } from '@/components/forms/FormFields';
import { ModalSize } from '@/types/modal';

interface MasterPasswordModalProps {
  t: TypedTFunction;
  open: boolean;
  currentMasterPassword: string | null;
  masterPasswordOperation: 'create' | 'update' | 'remove';
  onOperationChange: (operation: 'create' | 'update' | 'remove') => void;
  onCancel: () => void;
  onSubmit: (values: { password?: string; confirmPassword?: string }) => void | Promise<void>;
  isSubmitting: boolean;
}

export const MasterPasswordModal: React.FC<MasterPasswordModalProps> = ({
  t,
  open,
  currentMasterPassword,
  masterPasswordOperation,
  onOperationChange,
  onCancel,
  onSubmit,
  isSubmitting,
}) => {
  const [form] = Form.useForm();

  // Reset form when modal closes
  useEffect(() => {
    if (!open) {
      form.resetFields();
    }
  }, [open, form]);

  return (
    <Modal
      title={
        currentMasterPassword
          ? t('system:dangerZone.updateMasterPassword.modal.title')
          : t('system:dangerZone.updateMasterPassword.modal.operationCreate')
      }
      open={open}
      onCancel={onCancel}
      footer={null}
      className={ModalSize.Medium}
      centered
      data-testid="system-master-password-modal"
    >
      <Form layout="vertical" form={form} onFinish={onSubmit}>
        {currentMasterPassword && (
          <Form.Item label={t('system:dangerZone.updateMasterPassword.modal.operationType')}>
            <Radio.Group
              value={masterPasswordOperation}
              onChange={(e) => {
                onOperationChange(e.target.value);
                form.resetFields(['password', 'confirmPassword']);
              }}
              data-testid="system-master-password-operation-select"
            >
              <Space direction="vertical">
                <Radio value="update" data-testid="system-master-password-operation-update">
                  {t('system:dangerZone.updateMasterPassword.modal.operationUpdate')}
                </Radio>
                <Radio value="remove" data-testid="system-master-password-operation-remove">
                  {t('system:dangerZone.updateMasterPassword.modal.operationRemove')}
                </Radio>
              </Space>
            </Radio.Group>
          </Form.Item>
        )}

        <Alert
          message={
            <>
              {'\u26A0\uFE0F'}{' '}
              {t('system:dangerZone.updateMasterPassword.modal.warningTitle').replace('⚠️ ', '')}
            </>
          }
          description={
            <Space direction="vertical" size="small">
              <Typography.Text>
                {t(
                  `system:dangerZone.updateMasterPassword.modal.warningDescription${
                    masterPasswordOperation.charAt(0).toUpperCase() +
                    masterPasswordOperation.slice(1)
                  }`
                )}
              </Typography.Text>
              <ul>
                <li>{t('system:dangerZone.updateMasterPassword.modal.warningEffect1')}</li>
                <li>{t('system:dangerZone.updateMasterPassword.modal.warningEffect2')}</li>
                <li>
                  {t(
                    `system:dangerZone.updateMasterPassword.modal.warningEffect3${
                      masterPasswordOperation.charAt(0).toUpperCase() +
                      masterPasswordOperation.slice(1)
                    }`
                  )}
                </li>
                {masterPasswordOperation !== 'remove' && (
                  <li>{t('system:dangerZone.updateMasterPassword.modal.warningEffect4')}</li>
                )}
              </ul>
              <Typography.Text strong>
                {t('system:dangerZone.updateMasterPassword.modal.warningPermanent')}
              </Typography.Text>
              <Typography.Text type="danger" strong>
                {t(
                  masterPasswordOperation === 'remove'
                    ? 'system:dangerZone.updateMasterPassword.modal.warningSecureRemove'
                    : 'system:dangerZone.updateMasterPassword.modal.warningSecure'
                )}
              </Typography.Text>
            </Space>
          }
          type="warning"
        />

        {masterPasswordOperation !== 'remove' && (
          <>
            <PasswordField
              name="password"
              label={t('system:dangerZone.updateMasterPassword.modal.newPasswordLabel')}
              placeholder={t('system:dangerZone.updateMasterPassword.modal.newPasswordPlaceholder')}
              minLength={12}
              requiredMessage={t(
                'system:dangerZone.updateMasterPassword.modal.newPasswordRequired'
              )}
              minLengthMessage={t(
                'system:dangerZone.updateMasterPassword.modal.newPasswordMinLength'
              )}
              patternMessage={t('system:dangerZone.updateMasterPassword.modal.newPasswordPattern')}
            />

            <PasswordConfirmField
              name="confirmPassword"
              label={t('system:dangerZone.updateMasterPassword.modal.confirmPasswordLabel')}
              passwordFieldName="password"
              placeholder={t(
                'system:dangerZone.updateMasterPassword.modal.confirmPasswordPlaceholder'
              )}
              requiredMessage={t(
                'system:dangerZone.updateMasterPassword.modal.confirmPasswordRequired'
              )}
              mismatchMessage={t(
                'system:dangerZone.updateMasterPassword.modal.confirmPasswordMatch'
              )}
            />
          </>
        )}

        <Alert
          message={t('common:general.important')}
          description={t(
            `system:dangerZone.updateMasterPassword.modal.importantNote${(() => {
              if (masterPasswordOperation === 'create') {
                return 'Create';
              } else if (masterPasswordOperation === 'remove') {
                return 'Remove';
              }
              return '';
            })()}`
          )}
          type="info"
        />

        <Form.Item>
          <Flex justify="flex-end">
            <Button onClick={onCancel} data-testid="system-master-password-cancel-button">
              {t('system:dangerZone.updateMasterPassword.modal.cancel')}
            </Button>
            <Button
              danger
              htmlType="submit"
              loading={isSubmitting}
              disabled={isSubmitting}
              data-testid="system-master-password-submit-button"
            >
              {t(
                `system:dangerZone.updateMasterPassword.modal.submit${
                  masterPasswordOperation.charAt(0).toUpperCase() + masterPasswordOperation.slice(1)
                }`
              )}
            </Button>
          </Flex>
        </Form.Item>
      </Form>
    </Modal>
  );
};
