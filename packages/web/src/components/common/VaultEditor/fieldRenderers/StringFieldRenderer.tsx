import { Form, Input, InputNumber, Space } from 'antd';
import React from 'react';
import { FieldFormItem } from '../components/FieldFormItem';
import FieldGenerator from '../components/FieldGenerator';
import { FieldLabel } from '../components/FieldLabel';
import type { FieldRendererProps } from './types';

// Special field names that require custom rendering
const SPECIAL_FIELDS = {
  SSH_PASSWORD: 'ssh_password',
  KNOWN_HOSTS: 'known_hosts',
  SSH_PRIVATE_KEY: 'SSH_PRIVATE_KEY',
  SSH_PUBLIC_KEY: 'SSH_PUBLIC_KEY',
  CREDENTIAL: 'credential',
} as const;

// Check if field is generatable (SSH keys or repository credential)
const isGeneratableField = (fieldName: string, entityType: string): boolean =>
  fieldName === SPECIAL_FIELDS.SSH_PRIVATE_KEY ||
  fieldName === SPECIAL_FIELDS.SSH_PUBLIC_KEY ||
  (fieldName === SPECIAL_FIELDS.CREDENTIAL && entityType === 'REPOSITORY');

// Password field component
const SshPasswordField: React.FC<
  Pick<
    FieldRendererProps,
    'fieldName' | 'fieldLabel' | 'fieldDescription' | 'rules' | 'fieldDef' | 't'
  >
> = ({ fieldName, fieldLabel, fieldDescription, rules, fieldDef, t }) => (
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

// Known hosts field component
const KnownHostsField: React.FC<
  Pick<
    FieldRendererProps,
    'fieldName' | 'fieldLabel' | 'fieldDescription' | 'rules' | 'fieldDef' | 't'
  >
> = ({ fieldName, fieldLabel, fieldDescription, rules, fieldDef, t }) => (
  <Form.Item
    name={fieldName}
    label={<FieldLabel label={fieldLabel} description={fieldDescription} />}
    rules={rules}
    initialValue={fieldDef.default}
    extra={t('vaultEditor.knownHostsHelp')}
  >
    <Input
      className="w-full"
      placeholder={t('vaultEditor.knownHostsPlaceholder')}
      data-testid={`vault-editor-field-${fieldName}`}
    />
  </Form.Item>
);

// Port field component
const PortField: React.FC<
  Pick<
    FieldRendererProps,
    'fieldName' | 'fieldLabel' | 'fieldDescription' | 'rules' | 'fieldDef' | 't'
  >
> = ({ fieldName, fieldLabel, fieldDescription, rules, fieldDef, t }) => (
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

// Generatable field component with field generator
const GeneratableField: React.FC<FieldRendererProps> = ({
  fieldName,
  fieldDef,
  fieldLabel,
  fieldDescription,
  fieldPlaceholder,
  rules,
  entityType,
  form,
  handleFormChange,
}) => {
  const fieldType = fieldName === SPECIAL_FIELDS.CREDENTIAL ? 'repo_credential' : 'ssh_keys';
  const isSshKey =
    fieldName === SPECIAL_FIELDS.SSH_PRIVATE_KEY || fieldName === SPECIAL_FIELDS.SSH_PUBLIC_KEY;

  const handleFieldGeneration = (values: Record<string, string>) => {
    if (isSshKey) {
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
      return;
    }

    form.setFieldValue(fieldName, values[fieldName]);
    handleFormChange({ [fieldName]: values[fieldName] });
  };

  return (
    <Form.Item
      label={<FieldLabel label={fieldLabel} description={fieldDescription} />}
      required={rules.some((r) => 'required' in r && r.required)}
    >
      <Space.Compact className="w-full">
        <Form.Item name={fieldName} noStyle rules={rules} initialValue={fieldDef.default}>
          <Input
            className="w-full"
            placeholder={fieldPlaceholder}
            type={fieldDef.sensitive ? 'password' : 'text'}
            autoComplete={fieldDef.sensitive ? 'new-password' : 'off'}
            data-testid={`vault-editor-field-${fieldName}`}
          />
        </Form.Item>
        <FieldGenerator
          fieldType={fieldType}
          onGenerate={handleFieldGeneration}
          entityType={entityType}
          data-testid={`vault-editor-generate-${fieldName}`}
        />
      </Space.Compact>
    </Form.Item>
  );
};

// Default string field component
const DefaultStringField: React.FC<
  Omit<FieldRendererProps, 'form' | 'handleFormChange' | 't' | 'entityType'>
> = ({ fieldName, fieldDef, fieldLabel, fieldDescription, fieldPlaceholder, rules }) => (
  <Form.Item
    name={fieldName}
    label={<FieldLabel label={fieldLabel} description={fieldDescription} />}
    rules={rules}
    initialValue={fieldDef.default}
  >
    <Input
      className="w-full"
      placeholder={fieldPlaceholder}
      type={fieldDef.sensitive ? 'password' : 'text'}
      autoComplete={fieldDef.sensitive ? 'new-password' : 'off'}
      data-testid={`vault-editor-field-${fieldName}`}
    />
  </Form.Item>
);

export const StringFieldRenderer: React.FC<FieldRendererProps> = (props) => {
  const { fieldName, fieldDef, entityType } = props;

  // Route to special field renderers using early returns
  if (fieldName === SPECIAL_FIELDS.SSH_PASSWORD) {
    return <SshPasswordField {...props} />;
  }

  if (fieldName === SPECIAL_FIELDS.KNOWN_HOSTS) {
    return <KnownHostsField {...props} />;
  }

  if (fieldName === 'port' || fieldDef.format === 'port') {
    return <PortField {...props} />;
  }

  if (isGeneratableField(fieldName, entityType)) {
    return <GeneratableField {...props} />;
  }

  return <DefaultStringField {...props} />;
};
