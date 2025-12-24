import React from 'react';
import { Form, Input, InputNumber, Space } from 'antd';
import { FieldFormItem } from '../components/FieldFormItem';
import FieldGenerator from '../components/FieldGenerator';
import { FieldLabel } from '../components/FieldLabel';
import type { FieldRendererProps } from './types';

export const StringFieldRenderer: React.FC<FieldRendererProps> = ({
  fieldName,
  fieldDef,
  fieldLabel,
  fieldDescription,
  fieldPlaceholder,
  rules,
  entityType,
  form,
  handleFormChange,
  t,
}) => {
  // Special case: ssh_password field
  if (fieldName === 'ssh_password') {
    return (
      <Form.Item
        name={fieldName}
        label={<FieldLabel label={fieldLabel} description={fieldDescription} />}
        rules={rules}
        initialValue={fieldDef.default}
      >
        <Input.Password
          className="w-full"
          placeholder={t('vaultEditor.sshPasswordPlaceholder')}
          autoComplete="new-password"
          data-testid={`vault-editor-field-${fieldName}`}
        />
      </Form.Item>
    );
  }

  // Special case: host_entry field
  if (fieldName === 'host_entry') {
    return (
      <Form.Item
        name={fieldName}
        label={<FieldLabel label={fieldLabel} description={fieldDescription} />}
        rules={rules}
        initialValue={fieldDef.default}
        extra={t('vaultEditor.hostEntryHelp')}
      >
        <Input
          className="w-full"
          placeholder={t('vaultEditor.hostEntryPlaceholder')}
          data-testid={`vault-editor-field-${fieldName}`}
        />
      </Form.Item>
    );
  }

  // Special case: port field
  if (fieldName === 'port' || fieldDef.format === 'port') {
    return (
      <FieldFormItem
        name={fieldName}
        label={fieldLabel}
        description={fieldDescription}
        rules={rules}
        initialValue={fieldDef.default}
      >
        <InputNumber
          className="w-full"
          placeholder={t('vaultEditor.portPlaceholder')}
          min={1}
          max={65535}
          data-testid={`vault-editor-field-${fieldName}`}
        />
      </FieldFormItem>
    );
  }

  // Check if field can be generated
  const isGeneratable =
    fieldName === 'SSH_PRIVATE_KEY' ||
    fieldName === 'SSH_PUBLIC_KEY' ||
    (fieldName === 'credential' && entityType === 'REPOSITORY');

  const handleFieldGeneration = (values: Record<string, string>) => {
    if (fieldName === 'SSH_PRIVATE_KEY' || fieldName === 'SSH_PUBLIC_KEY') {
      const currentValues = form.getFieldsValue();
      form.setFieldsValue({
        ...currentValues,
        SSH_PRIVATE_KEY: values.SSH_PRIVATE_KEY,
        SSH_PUBLIC_KEY: values.SSH_PUBLIC_KEY,
      });
      handleFormChange({
        SSH_PRIVATE_KEY: values.SSH_PRIVATE_KEY,
        SSH_PUBLIC_KEY: values.SSH_PUBLIC_KEY,
      });
    } else {
      form.setFieldValue(fieldName, values[fieldName]);
      handleFormChange({ [fieldName]: values[fieldName] });
    }
  };

  return (
    <Form.Item
      name={fieldName}
      label={<FieldLabel label={fieldLabel} description={fieldDescription} />}
      rules={rules}
      initialValue={fieldDef.default}
    >
      {isGeneratable ? (
        <Space.Compact className="w-full">
          <Input
            className="w-full"
            placeholder={fieldPlaceholder}
            type={fieldDef.sensitive ? 'password' : 'text'}
            autoComplete={fieldDef.sensitive ? 'new-password' : 'off'}
            data-testid={`vault-editor-field-${fieldName}`}
          />
          <FieldGenerator
            fieldType={fieldName === 'credential' ? 'repo_credential' : 'ssh_keys'}
            onGenerate={handleFieldGeneration}
            entityType={entityType}
            data-testid={`vault-editor-generate-${fieldName}`}
          />
        </Space.Compact>
      ) : (
        <Input
          className="w-full"
          placeholder={fieldPlaceholder}
          type={fieldDef.sensitive ? 'password' : 'text'}
          autoComplete={fieldDef.sensitive ? 'new-password' : 'off'}
          data-testid={`vault-editor-field-${fieldName}`}
        />
      )}
    </Form.Item>
  );
};
