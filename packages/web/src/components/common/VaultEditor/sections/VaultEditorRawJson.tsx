import React, { useRef } from 'react';
import { Card, Col, Space } from 'antd';
import { RediaccAlert, RediaccTooltip } from '@/components/ui';
import { featureFlags } from '@/config/featureFlags';
import { CodeOutlined } from '@/utils/optimizedIcons';
import { SimpleJsonEditor } from '../components/SimpleJsonEditor';
import { DangerAlertIcon, FormatActions, FormatButton } from '../styles';

interface VaultEditorRawJsonProps {
  rawJsonValue: string;
  rawJsonError?: string;
  uiMode: string;
  onChange: (value: string | undefined) => void;
  t: (key: string, options?: Record<string, unknown>) => string;
}

export const VaultEditorRawJson: React.FC<VaultEditorRawJsonProps> = ({
  rawJsonValue,
  rawJsonError,
  uiMode,
  onChange,
  t,
}) => {
  const formatJsonRef = useRef<(() => void) | null>(null);

  if (!featureFlags.isEnabled('advancedVaultEditor') || uiMode === 'simple') {
    return null;
  }

  return (
    <Col xs={24} sm={24} md={24} lg={24} xl={24}>
      <Card
        title={
          <Space>
            <CodeOutlined />
            {t('vaultEditor.rawJsonEditor')}
            <RediaccTooltip title={t('vaultEditor.rawJsonTooltip')}>
              <DangerAlertIcon />
            </RediaccTooltip>
          </Space>
        }
        variant="borderless"
        size="default"
        data-testid="vault-editor-panel-rawjson"
      >
        <RediaccAlert
          spacing="default"
          message={t('vaultEditor.expertModeOnly')}
          description={t('vaultEditor.expertModeDescription')}
          variant="error"
          showIcon
          icon={<DangerAlertIcon />}
        />

        {rawJsonError && (
          <RediaccAlert
            spacing="default"
            message={t('vaultEditor.jsonError')}
            description={rawJsonError}
            variant="error"
            showIcon
          />
        )}

        <FormatActions>
          <FormatButton
            variant="default"
            onClick={() => formatJsonRef.current?.()}
            data-testid="vault-editor-format-json"
          >
            Format
          </FormatButton>
        </FormatActions>

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
