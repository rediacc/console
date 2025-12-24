import React from 'react';
import { Alert, Button, Checkbox, Flex, Form, Modal } from 'antd';
import type { TFunction } from 'i18next';

interface ResetAuthModalData {
  bridgeName: string;
  regionName: string;
  isCloudManaged: boolean;
}

interface ResetAuthModalProps {
  t: TFunction<'resources'>;
  tCommon: TFunction<'common'>;
  open: boolean;
  data?: ResetAuthModalData;
  isSubmitting: boolean;
  onClose: () => void;
  onReset: () => void;
  onToggleCloudManaged: (value: boolean) => void;
}

export const ResetAuthModal: React.FC<ResetAuthModalProps> = ({
  t,
  tCommon,
  open,
  data,
  isSubmitting,
  onClose,
  onReset,
  onToggleCloudManaged,
}) => (
  <Modal
    title={t('bridges.resetAuth')}
    open={open}
    onCancel={onClose}
    footer={[
      <Button key="cancel" onClick={onClose}>
        {tCommon('actions.cancel')}
      </Button>,
      <Button key="reset" type="primary" danger loading={isSubmitting} onClick={onReset}>
        {t('bridges.resetAuthConfirm')}
      </Button>,
    ]}
    centered
  >
    {data && (
      <Flex vertical gap={16} className="w-full">
        <Alert
          message={tCommon('general.warning')}
          description={t('bridges.resetAuthWarning', { bridge: data.bridgeName })}
          type="warning"
          showIcon
        />

        <Form layout="vertical">
          <Form.Item label={t('bridges.cloudManagement')} help={t('bridges.cloudManagementHelp')}>
            <Checkbox
              checked={data.isCloudManaged}
              onChange={(e) => onToggleCloudManaged(e.target.checked)}
            >
              {t('bridges.enableCloudManagement')}
            </Checkbox>
          </Form.Item>
        </Form>
      </Flex>
    )}
  </Modal>
);
