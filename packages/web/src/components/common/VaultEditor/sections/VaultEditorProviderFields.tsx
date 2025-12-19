import React from 'react';
import { Card, Col, Divider, Space } from 'antd';
import { RediaccAlert, RediaccStack, RediaccText } from '@/components/ui';
import { QuestionCircleOutlined, InfoCircleOutlined } from '@/utils/optimizedIcons';
import { VaultFieldRenderer } from '../fieldRenderers';
import { ProviderSectionSpacer, TipsAlert, TipsDividerIcon } from '../styles';
import type { VaultFormValues, StorageProviderDefinition } from '../types';
import type { FormInstance } from 'antd';

interface VaultEditorProviderFieldsProps {
  selectedProvider?: string;
  providerFields?: StorageProviderDefinition;
  form: FormInstance<VaultFormValues>;
  handleFormChange: (changedValues?: VaultFormValues) => void;
  t: (key: string, options?: Record<string, unknown>) => string;
}

export const VaultEditorProviderFields: React.FC<VaultEditorProviderFieldsProps> = ({
  selectedProvider,
  providerFields,
  form,
  handleFormChange,
  t,
}) => {
  if (!selectedProvider || !providerFields) {
    return null;
  }

  return (
    <Col xs={24} sm={24} md={24} lg={24} xl={24}>
      <Card
        title={t('vaultEditor.providerFields', { provider: providerFields.name })}
        variant="borderless"
        size="default"
        data-testid="vault-editor-panel-provider"
      >
        <RediaccAlert
          spacing="default"
          message={providerFields.name}
          description={t(`storageProviders:storageProviders.${selectedProvider}.helpText`, {
            defaultValue: providerFields.description,
          })}
          variant="info"
          showIcon
          icon={<QuestionCircleOutlined />}
        />

        {providerFields.required && providerFields.required.length > 0 && (
          <>
            {providerFields.required.map((fieldName: string) => {
              if (!providerFields.fields || !(fieldName in providerFields.fields)) return null;
              const field = providerFields.fields[fieldName as keyof typeof providerFields.fields];
              if (!field) return null;

              return (
                <div key={fieldName}>
                  <VaultFieldRenderer
                    fieldName={fieldName}
                    fieldDef={field}
                    required={true}
                    isProviderField={true}
                    entityType="STORAGE"
                    selectedProvider={selectedProvider}
                    form={form}
                    handleFormChange={handleFormChange}
                    t={t}
                  />
                </div>
              );
            })}
          </>
        )}

        {providerFields.optional && providerFields.optional.length > 0 && (
          <>
            {providerFields.required && providerFields.required.length > 0 && (
              <ProviderSectionSpacer />
            )}
            {providerFields.optional.map((fieldName: string) => {
              if (!providerFields.fields || !(fieldName in providerFields.fields)) return null;
              const field = providerFields.fields[fieldName as keyof typeof providerFields.fields];
              if (!field) return null;

              return (
                <div key={fieldName}>
                  <VaultFieldRenderer
                    fieldName={fieldName}
                    fieldDef={field}
                    required={false}
                    isProviderField={true}
                    entityType="STORAGE"
                    selectedProvider={selectedProvider}
                    form={form}
                    handleFormChange={handleFormChange}
                    t={t}
                  />
                </div>
              );
            })}
          </>
        )}

        <Divider>
          <Space>
            <TipsDividerIcon />
            <RediaccText weight="bold">
              {t('storageProviders:common.tips', { defaultValue: 'Tips' })}
            </RediaccText>
          </Space>
        </Divider>
        <TipsAlert
          message={
            <RediaccStack direction="vertical" gap="sm" fullWidth>
              {[1, 2, 3, 4]
                .map((index) => {
                  const tip = t(
                    `storageProviders:storageProviders.${selectedProvider}.tips.${index - 1}`,
                    { defaultValue: '' }
                  );
                  return tip ? (
                    <div key={index}>
                      <RediaccText>- {tip}</RediaccText>
                    </div>
                  ) : null;
                })
                .filter(Boolean)}
            </RediaccStack>
          }
          variant="info"
          showIcon
          icon={<InfoCircleOutlined />}
        />
      </Card>
    </Col>
  );
};
