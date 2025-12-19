import React from 'react';
import { Col } from 'antd';
import { RediaccStack } from '@/components/ui';
import { InfoCircleOutlined, WifiOutlined } from '@/utils/optimizedIcons';
import { FieldLabel } from '../components/FieldLabel';
import { FieldItem, TestConnectionAlert, TestConnectionButton } from '../styles';
import type { VaultFormValues } from '../types';
import type { FormInstance } from 'antd';

interface VaultEditorTestConnectionProps {
  form: FormInstance<VaultFormValues>;
  testConnectionSuccess: boolean;
  isCreatingQueueItem: boolean;
  isTestingConnection: boolean;
  teamName: string;
  bridgeName: string;
  onTestConnection: () => Promise<void>;
  t: (key: string, options?: Record<string, unknown>) => string;
}

export const VaultEditorTestConnection: React.FC<VaultEditorTestConnectionProps> = ({
  testConnectionSuccess,
  isCreatingQueueItem,
  isTestingConnection,
  onTestConnection,
  t,
}) => {
  return (
    <Col xs={24}>
      <FieldItem
        label={
          <FieldLabel
            label={t('vaultEditor.testConnection.label')}
            description={t('vaultEditor.testConnection.description')}
          />
        }
      >
        <RediaccStack direction="vertical" gap="sm" fullWidth>
          {!testConnectionSuccess && (
            <TestConnectionAlert
              message={t('vaultEditor.testConnection.required')}
              variant="info"
              showIcon
              icon={<InfoCircleOutlined />}
              data-testid="vault-editor-connection-required-alert"
            />
          )}
          <TestConnectionButton
            variant="primary"
            icon={<WifiOutlined />}
            loading={isCreatingQueueItem || isTestingConnection}
            data-testid="vault-editor-test-connection"
            onClick={onTestConnection}
          >
            {t('vaultEditor.testConnection.button')}
          </TestConnectionButton>
        </RediaccStack>
      </FieldItem>
    </Col>
  );
};
