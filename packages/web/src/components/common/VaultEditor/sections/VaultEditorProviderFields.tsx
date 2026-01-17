import React from 'react';
import { Alert, Card, Col, Divider, Flex, Space, Typography } from 'antd';
import { BulbOutlined, InfoCircleOutlined, QuestionCircleOutlined } from '@/utils/optimizedIcons';
import { VaultFieldRenderer } from '../fieldRenderers';
import type { StorageProviderDefinition, VaultFormValues } from '../types';
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
        {/* eslint-disable no-restricted-syntax -- Dynamic keys with runtime variables */}
        <Alert
          message={providerFields.name}
          description={t(`storageProviders:storageProviders.${selectedProvider}.helpText`, {
            defaultValue: providerFields.description,
          })}
          type="info"
          icon={<QuestionCircleOutlined />}
        />

        {providerFields.required && providerFields.required.length > 0 && (
          <>
            {providerFields.required.map((fieldName: string) => {
              const field = providerFields.fields?.[fieldName];
              if (!field) return null;

              return (
                <Flex key={fieldName}>
                  <VaultFieldRenderer
                    fieldName={fieldName}
                    fieldDef={field}
                    required
                    isProviderField
                    entityType="STORAGE"
                    selectedProvider={selectedProvider}
                    form={form}
                    handleFormChange={handleFormChange}
                    t={t}
                  />
                </Flex>
              );
            })}
          </>
        )}

        {providerFields.optional && providerFields.optional.length > 0 && (
          <>
            {providerFields.required && providerFields.required.length > 0 && <Flex />}
            {providerFields.optional.map((fieldName: string) => {
              const field = providerFields.fields?.[fieldName];
              if (!field) return null;

              return (
                <Flex key={fieldName}>
                  <VaultFieldRenderer
                    fieldName={fieldName}
                    fieldDef={field}
                    required={false}
                    isProviderField
                    entityType="STORAGE"
                    selectedProvider={selectedProvider}
                    form={form}
                    handleFormChange={handleFormChange}
                    t={t}
                  />
                </Flex>
              );
            })}
          </>
        )}

        <Divider>
          <Space>
            <BulbOutlined />
            <Typography.Text strong>{t('storageProviders:common.tips')}</Typography.Text>
          </Space>
        </Divider>
        <Alert
          message={
            <Flex vertical className="gap-sm w-full">
              {[1, 2, 3, 4]
                .map((index) => {
                  const tip = t(
                    `storageProviders:storageProviders.${selectedProvider}.tips.${index - 1}`,
                    { defaultValue: '' }
                  );
                  return tip ? (
                    <Flex key={index}>
                      <Typography.Text>- {tip}</Typography.Text>
                    </Flex>
                  ) : null;
                })
                .filter(Boolean)}
            </Flex>
          }
          type="info"
          icon={<InfoCircleOutlined />}
        />
        {/* eslint-enable no-restricted-syntax */}
      </Card>
    </Col>
  );
};
