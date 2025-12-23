import React from 'react';
import { Alert, Button, Flex, Form, Modal, Radio, Space, Typography } from 'antd';
import { PasswordConfirmField, PasswordField } from '@/components/forms/FormFields';
import { ModalSize } from '@/types/modal';
import type { FormInstance } from 'antd';
import type { TFunction } from 'i18next';

interface MasterPasswordModalProps {
  tSystem: TFunction<'system'>;
  tCommon: TFunction<'common'>;
  open: boolean;
  currentMasterPassword: string | null;
  masterPasswordOperation: 'create' | 'update' | 'remove';
  onOperationChange: (operation: 'create' | 'update' | 'remove') => void;
  onCancel: () => void;
  onSubmit: (values: { password?: string; confirmPassword?: string }) => void | Promise<void>;
  form: FormInstance;
  isSubmitting: boolean;
}

export const MasterPasswordModal: React.FC<MasterPasswordModalProps> = ({
  tSystem,
  tCommon,
  open,
  currentMasterPassword,
  masterPasswordOperation,
  onOperationChange,
  onCancel,
  onSubmit,
  form,
  isSubmitting,
}) => (
  <Modal
    title={
      currentMasterPassword
        ? tSystem('dangerZone.updateMasterPassword.modal.title')
        : tSystem('dangerZone.updateMasterPassword.modal.operationCreate')
    }
    open={open}
    onCancel={onCancel}
    footer={null}
    className={ModalSize.Medium}
    centered
  >
    <Form layout="vertical" form={form} onFinish={onSubmit}>
      {currentMasterPassword && (
        <Form.Item label={tSystem('dangerZone.updateMasterPassword.modal.operationType')}>
          <Radio.Group
            value={masterPasswordOperation}
            onChange={(e) => {
              onOperationChange(e.target.value);
              form.resetFields(['password', 'confirmPassword']);
            }}
          >
            <Space direction="vertical">
              <Radio value="update">
                {tSystem('dangerZone.updateMasterPassword.modal.operationUpdate')}
              </Radio>
              <Radio value="remove">
                {tSystem('dangerZone.updateMasterPassword.modal.operationRemove')}
              </Radio>
            </Space>
          </Radio.Group>
        </Form.Item>
      )}

      <Alert
        message={
          <>
            {'\u26A0\uFE0F'}{' '}
            {tSystem('dangerZone.updateMasterPassword.modal.warningTitle').replace('⚠️ ', '')}
          </>
        }
        description={
          <Space direction="vertical" size="small">
            <Typography.Text>
              {tSystem(
                `dangerZone.updateMasterPassword.modal.warningDescription${
                  masterPasswordOperation.charAt(0).toUpperCase() + masterPasswordOperation.slice(1)
                }`
              )}
            </Typography.Text>
            <ul>
              <li>{tSystem('dangerZone.updateMasterPassword.modal.warningEffect1')}</li>
              <li>{tSystem('dangerZone.updateMasterPassword.modal.warningEffect2')}</li>
              <li>
                {tSystem(
                  `dangerZone.updateMasterPassword.modal.warningEffect3${
                    masterPasswordOperation.charAt(0).toUpperCase() +
                    masterPasswordOperation.slice(1)
                  }`
                )}
              </li>
              {masterPasswordOperation !== 'remove' && (
                <li>{tSystem('dangerZone.updateMasterPassword.modal.warningEffect4')}</li>
              )}
            </ul>
            <Typography.Text strong>
              {tSystem('dangerZone.updateMasterPassword.modal.warningPermanent')}
            </Typography.Text>
            <Typography.Text type="danger" strong>
              {tSystem(
                masterPasswordOperation === 'remove'
                  ? 'dangerZone.updateMasterPassword.modal.warningSecureRemove'
                  : 'dangerZone.updateMasterPassword.modal.warningSecure'
              )}
            </Typography.Text>
          </Space>
        }
        type="warning"
        showIcon
      />

      {masterPasswordOperation !== 'remove' && (
        <>
          <PasswordField
            name="password"
            label={tSystem('dangerZone.updateMasterPassword.modal.newPasswordLabel')}
            placeholder={tSystem('dangerZone.updateMasterPassword.modal.newPasswordPlaceholder')}
            minLength={12}
            requiredMessage={tSystem('dangerZone.updateMasterPassword.modal.newPasswordRequired')}
            minLengthMessage={tSystem('dangerZone.updateMasterPassword.modal.newPasswordMinLength')}
            patternMessage={tSystem('dangerZone.updateMasterPassword.modal.newPasswordPattern')}
          />

          <PasswordConfirmField
            name="confirmPassword"
            label={tSystem('dangerZone.updateMasterPassword.modal.confirmPasswordLabel')}
            passwordFieldName="password"
            placeholder={tSystem(
              'dangerZone.updateMasterPassword.modal.confirmPasswordPlaceholder'
            )}
            requiredMessage={tSystem(
              'dangerZone.updateMasterPassword.modal.confirmPasswordRequired'
            )}
            mismatchMessage={tSystem('dangerZone.updateMasterPassword.modal.confirmPasswordMatch')}
          />
        </>
      )}

      <Alert
        message={tCommon('general.important')}
        description={tSystem(
          `dangerZone.updateMasterPassword.modal.importantNote${
            masterPasswordOperation === 'create'
              ? 'Create'
              : masterPasswordOperation === 'remove'
                ? 'Remove'
                : ''
          }`
        )}
        type="info"
        showIcon
      />

      <Form.Item>
        <Flex justify="flex-end" gap={8}>
          <Button onClick={onCancel} data-testid="system-master-password-cancel-button">
            {tSystem('dangerZone.updateMasterPassword.modal.cancel')}
          </Button>
          <Button
            danger
            htmlType="submit"
            loading={isSubmitting}
            disabled={isSubmitting}
            data-testid="system-master-password-submit-button"
          >
            {tSystem(
              `dangerZone.updateMasterPassword.modal.submit${
                masterPasswordOperation.charAt(0).toUpperCase() + masterPasswordOperation.slice(1)
              }`
            )}
          </Button>
        </Flex>
      </Form.Item>
    </Form>
  </Modal>
);
