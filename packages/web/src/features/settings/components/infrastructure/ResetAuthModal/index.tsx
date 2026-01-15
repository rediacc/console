import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import { Alert, Button, Checkbox, Flex, Form, Modal } from 'antd';
import React from 'react';

interface ResetAuthModalData {
  bridgeName: string;
  regionName: string;
  isCloudManaged: boolean;
}

interface ResetAuthModalProps {
  t: TypedTFunction;
  open: boolean;
  data?: ResetAuthModalData;
  isSubmitting: boolean;
  onClose: () => void;
  onReset: () => void;
  onToggleCloudManaged: (value: boolean) => void;
}

export const ResetAuthModal: React.FC<ResetAuthModalProps> = ({
  t,
  open,
  data,
  isSubmitting,
  onClose,
  onReset,
  onToggleCloudManaged,
}) => {
  return (
    <Modal
      title={t('bridges.resetAuth')}
      open={open}
      onCancel={onClose}
      footer={[
        <Button key="cancel" onClick={onClose} data-testid="bridge-reset-auth-cancel-button">
          {t('common:actions.cancel')}
        </Button>,
        <Button
          key="reset"
          type="primary"
          danger
          loading={isSubmitting}
          onClick={onReset}
          data-testid="bridge-reset-auth-submit-button"
        >
          {t('bridges.resetAuthConfirm')}
        </Button>,
      ]}
      centered
      data-testid="bridge-reset-auth-modal"
    >
      {data && (
        <Flex vertical className="w-full">
          <Alert
            message={t('common:general.warning')}
            description={t('bridges.resetAuthWarning', { bridge: data.bridgeName })}
            type="warning"
          />

          <Form layout="vertical">
            <Form.Item label={t('bridges.cloudManagement')} help={t('bridges.cloudManagementHelp')}>
              <Checkbox
                checked={data.isCloudManaged}
                onChange={(e) => onToggleCloudManaged(e.target.checked)}
                data-testid="bridge-reset-cloud-managed-checkbox"
              >
                {t('bridges.enableCloudManagement')}
              </Checkbox>
            </Form.Item>
          </Form>
        </Flex>
      )}
    </Modal>
  );
};
