import React from 'react';
import { Alert, Button, Flex, Input, Modal, Space, Typography } from 'antd';
import type { Bridge } from '@/api/queries/bridges';
import { ModalSize } from '@/types/modal';
import { CheckCircleOutlined, KeyOutlined } from '@/utils/optimizedIcons';
import type { TFunction } from 'i18next';

interface BridgeCredentialsModalProps {
  t: TFunction<'resources'>;
  tCommon: TFunction<'common'>;
  open: boolean;
  bridge?: Bridge;
  tokenCopied: boolean;
  onCopyToken: (token: string) => void;
  onClose: () => void;
}

export const BridgeCredentialsModal: React.FC<BridgeCredentialsModalProps> = ({
  t,
  tCommon,
  open,
  bridge,
  tokenCopied,
  onCopyToken,
  onClose,
}) => (
  <Modal
    title={`${t('bridges.bridgeToken')} - ${bridge?.bridgeName ?? ''}`}
    open={open}
    onCancel={onClose}
    footer={[
      <Button key="close" onClick={onClose}>
        {tCommon('actions.close')}
      </Button>,
    ]}
    className={ModalSize.Medium}
    centered
  >
    {(() => {
      if (!bridge) return null;

      const token = bridge.bridgeCredentials;

      if (bridge.hasAccess === 0) {
        return (
          /* eslint-disable-next-line no-restricted-syntax */
          <Flex style={{ maxWidth: 600, width: '100%' }}>
            <Alert
              message={t('bridges.accessDenied')}
              description={t('bridges.accessDeniedDescription')}
              type="error"
              showIcon
            />
          </Flex>
        );
      }

      if (!token) {
        return (
          /* eslint-disable-next-line no-restricted-syntax */
          <Flex style={{ maxWidth: 600, width: '100%' }}>
            <Alert
              message={t('bridges.noToken')}
              description={t('bridges.noTokenDescription')}
              type="info"
              showIcon
            />
          </Flex>
        );
      }

      return (
        <Flex vertical gap={16} className="w-full">
          <Alert
            message={t('bridges.tokenHeading')}
            description={t('bridges.tokenDescription')}
            type="warning"
            showIcon
          />

          <Flex vertical>
            <Typography.Text strong>{t('bridges.tokenLabel')}</Typography.Text>
            <Space.Compact className="w-full">
              <Input className="w-full" value={token} readOnly autoComplete="off" />
              <Button
                icon={tokenCopied ? <CheckCircleOutlined /> : <KeyOutlined />}
                onClick={() => onCopyToken(token)}
              >
                {tokenCopied ? tCommon('actions.copied') : tCommon('actions.copy')}
              </Button>
            </Space.Compact>
          </Flex>

          <Alert
            message={tCommon('general.important')}
            description={t('bridges.tokenImportant')}
            type="info"
            showIcon
          />
        </Flex>
      );
    })()}
  </Modal>
);
