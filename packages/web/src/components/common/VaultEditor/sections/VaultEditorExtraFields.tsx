import React from 'react';
import { Card, Col, Space } from 'antd';
import { RediaccAlert, RediaccTooltip } from '@/components/ui';
import { ExtraFieldsWarningIcon, RawJsonPreview } from '../styles';
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
            <RediaccTooltip title={t('vaultEditor.extraFieldsTooltip')}>
              <ExtraFieldsWarningIcon />
            </RediaccTooltip>
          </Space>
        }
        variant="borderless"
        size="default"
        data-testid="vault-editor-panel-extra"
      >
        <RediaccAlert
          spacing="default"
          message={t('vaultEditor.extraFieldsWarning')}
          description={t('vaultEditor.extraFieldsWarningDescription')}
          variant="warning"
          showIcon
        />
        <Card size="small">
          <RawJsonPreview>{JSON.stringify(extraFields, null, 2)}</RawJsonPreview>
        </Card>
      </Card>
    </Col>
  );
};
