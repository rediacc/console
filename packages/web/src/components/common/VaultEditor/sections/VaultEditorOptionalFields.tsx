import React from 'react';
import { Col, Divider, Form } from 'antd';
import { VaultFieldRenderer } from '../fieldRenderers';
import type { FieldDefinition, VaultFormValues } from '../types';
import type { FormInstance } from 'antd';

interface VaultEditorOptionalFieldsProps {
  entityType: string;
  requiredFields: string[];
  optionalFields: string[];
  fields: Record<string, FieldDefinition>;
  selectedProvider?: string;
  form: FormInstance<VaultFormValues>;
  handleFormChange: (changedValues?: VaultFormValues) => void;
  t: (key: string, options?: Record<string, unknown>) => string;
}

export const VaultEditorOptionalFields: React.FC<VaultEditorOptionalFieldsProps> = ({
  entityType,
  requiredFields,
  optionalFields,
  fields,
  selectedProvider,
  form,
  handleFormChange,
  t,
}) => {
  if (entityType === 'MACHINE') {
    return (
      <>
        {optionalFields
          .filter((fieldName) => fieldName !== 'ssh_key_configured')
          .map((fieldName) => {
            const field = fields[fieldName as keyof typeof fields];
            if (!field) return null;

            return (
              <Col key={fieldName} xs={24} md={12}>
                <VaultFieldRenderer
                  fieldName={fieldName}
                  fieldDef={field}
                  required={false}
                  entityType={entityType}
                  selectedProvider={selectedProvider}
                  form={form}
                  handleFormChange={handleFormChange}
                  t={t}
                />
              </Col>
            );
          })}
      </>
    );
  }

  return (
    <>
      {requiredFields.length > 0 && optionalFields.length > 0 && (
        <div>
          <Divider />
        </div>
      )}
      {optionalFields.map((fieldName) => {
        const field = fields[fieldName as keyof typeof fields];
        if (!field) return null;

        if (entityType === 'MACHINE' && fieldName === 'ssh_password') {
          return (
            <Col key={fieldName} xs={24} lg={12}>
              <Form.Item
                noStyle
                shouldUpdate={(prevValues, currentValues) =>
                  prevValues.ssh_key_configured !== currentValues.ssh_key_configured
                }
              >
                {({ getFieldValue }) => {
                  const sshKeyConfiguredValue = getFieldValue('ssh_key_configured');
                  if (!sshKeyConfiguredValue) {
                    return null;
                  }
                  return (
                    <VaultFieldRenderer
                      fieldName={fieldName}
                      fieldDef={field}
                      required={false}
                      entityType={entityType}
                      selectedProvider={selectedProvider}
                      form={form}
                      handleFormChange={handleFormChange}
                      t={t}
                    />
                  );
                }}
              </Form.Item>
            </Col>
          );
        }

        return (
          <Col key={fieldName} xs={24} lg={12}>
            <VaultFieldRenderer
              fieldName={fieldName}
              fieldDef={field}
              required={false}
              entityType={entityType}
              selectedProvider={selectedProvider}
              form={form}
              handleFormChange={handleFormChange}
              t={t}
            />
          </Col>
        );
      })}
    </>
  );
};
