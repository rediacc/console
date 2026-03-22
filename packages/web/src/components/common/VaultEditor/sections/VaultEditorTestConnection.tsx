import type { FormInstance } from 'antd';
import { Alert, Button, Col, Flex, Form } from 'antd';
import React from 'react';
import { InfoCircleOutlined, WifiOutlined } from '@/utils/optimizedIcons';
import { FieldLabel } from '../components/FieldLabel';
import type { VaultFormValues } from '../types';

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
      <Form.Item
        label={
          <FieldLabel
            label={t('vaultEditor.testConnection.label')}
            description={t('vaultEditor.testConnection.description')}
          />
        }
      >
        <Flex vertical className="w-full gap-sm">
          {!testConnectionSuccess && (
            <Alert
              message={t('vaultEditor.testConnection.required')}
              type="info"
              icon={<InfoCircleOutlined />}
              data-testid="vault-editor-connection-required-alert"
            />
          )}
          <Button
            className="w-full"
            type="primary"
            icon={<WifiOutlined />}
            loading={isCreatingQueueItem || isTestingConnection}
            data-testid="vault-editor-test-connection"
            onClick={onTestConnection}
          >
            {t('vaultEditor.testConnection.button')}
          </Button>
        </Flex>
      </Form.Item>
    </Col>
  );
};
