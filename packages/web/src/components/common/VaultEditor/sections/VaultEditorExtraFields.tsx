import { Alert, Card, Col, Space, Tooltip } from 'antd';
import React from 'react';
import { WarningOutlined } from '@/utils/optimizedIcons';
import type { VaultFormValues } from '../types';

interface VaultEditorExtraFieldsProps {
  extraFields: VaultFormValues;
  uiMode?: string;
  t: (key: string, options?: Record<string, unknown>) => string;
}

export const VaultEditorExtraFields: React.FC<VaultEditorExtraFieldsProps> = ({
  extraFields,
  uiMode,
  t,
}) => {
  if (Object.keys(extraFields).length === 0 || uiMode === 'simple') {
    return null;
  }

  return (
    <Col xs={24} sm={24} md={24} lg={24} xl={24}>
      <Card
        title={
          <Space>
            {t('vaultEditor.extraFields')}
            <Tooltip title={t('vaultEditor.extraFieldsTooltip')}>
              <WarningOutlined className="text-base" />
            </Tooltip>
          </Space>
        }
        variant="borderless"
        size="default"
        data-testid="vault-editor-panel-extra"
      >
        <Alert
          message={t('vaultEditor.extraFieldsWarning')}
          description={t('vaultEditor.extraFieldsWarningDescription')}
          type="warning"
        />
        <Card size="small">
          <pre className="overflow-auto">{JSON.stringify(extraFields, null, 2)}</pre>
        </Card>
      </Card>
    </Col>
  );
};
