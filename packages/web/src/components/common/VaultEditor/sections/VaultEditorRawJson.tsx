import React, { useRef } from 'react';
import { Alert, Button, Card, Col, Flex, Space, Tooltip } from 'antd';
import { featureFlags } from '@/config/featureFlags';
import { CodeOutlined, ExclamationCircleOutlined } from '@/utils/optimizedIcons';
import { SimpleJsonEditor } from '../components/SimpleJsonEditor';

interface VaultEditorRawJsonProps {
  rawJsonValue: string;
  rawJsonError?: string;
  onChange: (value: string | undefined) => void;
  t: (key: string, options?: Record<string, unknown>) => string;
}

export const VaultEditorRawJson: React.FC<VaultEditorRawJsonProps> = ({
  rawJsonValue,
  rawJsonError,
  onChange,
  t,
}) => {
  const formatJsonRef = useRef<(() => void) | null>(null);

  if (!featureFlags.isEnabled('advancedVaultEditor')) {
    return null;
  }

  return (
    <Col xs={24} sm={24} md={24} lg={24} xl={24}>
      <Card
        title={
          <Space>
            <CodeOutlined />
            {t('vaultEditor.rawJsonEditor')}
            <Tooltip title={t('vaultEditor.rawJsonTooltip')}>
              <ExclamationCircleOutlined className="text-base" />
            </Tooltip>
          </Space>
        }
        variant="borderless"
        size="default"
        data-testid="vault-editor-panel-rawjson"
      >
        <Alert
          message={t('vaultEditor.expertModeOnly')}
          description={t('vaultEditor.expertModeDescription')}
          type="error"
          icon={<ExclamationCircleOutlined className="text-base" />}
        />

        {rawJsonError && (
          <Alert message={t('vaultEditor.jsonError')} description={rawJsonError} type="error" />
        )}

        <Flex justify="flex-end">
          <Button
            type="default"
            onClick={() => formatJsonRef.current?.()}
            data-testid="vault-editor-format-json"
          >
            {t('common:actions.format')}
          </Button>
        </Flex>

        <SimpleJsonEditor
          value={rawJsonValue}
          onChange={onChange}
          height="400px"
          data-testid="vault-editor-raw-json"
          onFormatReady={(formatFn) => {
            formatJsonRef.current = formatFn;
          }}
        />
      </Card>
    </Col>
  );
};
