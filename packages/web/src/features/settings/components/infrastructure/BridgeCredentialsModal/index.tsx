import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { GetRegionBridges_ResultSet1 } from '@rediacc/shared/types';
import { Alert, Button, Flex, Input, Modal, Space, Typography } from 'antd';
import React from 'react';
import { ModalSize } from '@/types/modal';
import { CheckCircleOutlined, KeyOutlined } from '@/utils/optimizedIcons';

interface BridgeCredentialsModalProps {
  t: TypedTFunction;
  open: boolean;
  bridge?: GetRegionBridges_ResultSet1;
  tokenCopied: boolean;
  onCopyToken: (token: string) => void;
  onClose: () => void;
}

export const BridgeCredentialsModal: React.FC<BridgeCredentialsModalProps> = ({
  t,
  open,
  bridge,
  tokenCopied,
  onCopyToken,
  onClose,
}) => {
  return (
    <Modal
      title={`${t('bridges.bridgeToken')} - ${bridge?.bridgeName ?? ''}`}
      open={open}
      onCancel={onClose}
      footer={[
        <Button key="close" onClick={onClose} data-testid="bridge-credentials-close-button">
          {t('common:actions.close')}
        </Button>,
      ]}
      className={ModalSize.Medium}
      centered
      data-testid="bridge-credentials-modal"
    >
      {(() => {
        if (!bridge) return null;

        const token = bridge.bridgeCredentials;

        if (bridge.hasAccess === false) {
          return (
            <Flex className="w-full-max-md">
              <Alert
                message={t('bridges.accessDenied')}
                description={t('bridges.accessDeniedDescription')}
                type="error"
              />
            </Flex>
          );
        }

        if (!token) {
          return (
            <Flex className="w-full-max-md">
              <Alert
                message={t('bridges.noToken')}
                description={t('bridges.noTokenDescription')}
                type="info"
              />
            </Flex>
          );
        }

        return (
          <Flex vertical className="w-full">
            <Alert
              message={t('bridges.tokenHeading')}
              description={t('bridges.tokenDescription')}
              type="warning"
            />

            <Flex vertical>
              <Typography.Text strong>{t('bridges.tokenLabel')}</Typography.Text>
              <Space.Compact className="w-full">
                <Input
                  className="w-full"
                  value={token}
                  readOnly
                  autoComplete="off"
                  data-testid="bridge-credentials-token-input"
                />
                <Button
                  icon={tokenCopied ? <CheckCircleOutlined /> : <KeyOutlined />}
                  onClick={() => onCopyToken(token)}
                  data-testid="bridge-credentials-copy-button"
                >
                  {tokenCopied ? t('common:actions.copied') : t('common:actions.copy')}
                </Button>
              </Space.Compact>
            </Flex>

            <Alert
              message={t('common:general.important')}
              description={t('bridges.tokenImportant')}
              type="info"
            />
          </Flex>
        );
      })()}
    </Modal>
  );
};
