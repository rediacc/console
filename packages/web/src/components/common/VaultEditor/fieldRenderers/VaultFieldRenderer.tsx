import React from 'react';
import { vaultDefinitionConfig } from '../constants';
import { buildValidationRules, getFieldDefinition } from '../utils';
import { BooleanFieldRenderer } from './BooleanFieldRenderer';
import { EnumFieldRenderer } from './EnumFieldRenderer';
import { JsonFieldRenderer } from './JsonFieldRenderer';
import { NumberFieldRenderer } from './NumberFieldRenderer';
import { ObjectFieldRenderer } from './ObjectFieldRenderer';
import { StringFieldRenderer } from './StringFieldRenderer';
import type { FieldRendererProps } from './types';

type VaultFieldRendererProps = Omit<
  FieldRendererProps,
  'fieldLabel' | 'fieldDescription' | 'fieldPlaceholder' | 'rules'
>;

export const VaultFieldRenderer: React.FC<VaultFieldRendererProps> = ({
  fieldName,
  fieldDef,
  required,
  isProviderField = false,
  entityType,
  selectedProvider,
  form,
  handleFormChange,
  t,
}) => {
  const field = getFieldDefinition(fieldDef, vaultDefinitionConfig);

  // Get translated field labels and descriptions
  let fieldLabel: string;
  let fieldDescription: string | undefined;
  let fieldPlaceholder: string | undefined;

  // Dynamic translation keys with runtime variables require defaultValue fallbacks
  /* eslint-disable no-restricted-syntax */
  if (entityType === 'STORAGE' && isProviderField && selectedProvider) {
    fieldLabel = t(
      `storageProviders:storageProviders.${selectedProvider}.fields.${fieldName}.label`,
      { defaultValue: fieldName }
    );
    fieldPlaceholder = t(
      `storageProviders:storageProviders.${selectedProvider}.fields.${fieldName}.placeholder`,
      { defaultValue: field.example }
    );
    const fieldHelpText = t(
      `storageProviders:storageProviders.${selectedProvider}.fields.${fieldName}.helpText`,
      { defaultValue: field.description }
    );
    fieldDescription = fieldHelpText;
  } else {
    fieldLabel = t(`vaultEditor.fields.${entityType}.${fieldName}.label`, {
      defaultValue: fieldName,
    });
    /* eslint-enable no-restricted-syntax */
    fieldDescription = t(`vaultEditor.fields.${entityType}.${fieldName}.description`);
    fieldPlaceholder = field.example;
  }

  const rules = buildValidationRules(field, required, fieldLabel, t);

  const commonProps: FieldRendererProps = {
    fieldName,
    fieldDef: field,
    required,
    isProviderField,
    fieldLabel,
    fieldDescription,
    fieldPlaceholder,
    rules,
    entityType,
    selectedProvider,
    form,
    handleFormChange,
    t,
  };

  // Strategy pattern: Select renderer based on field type
  if (field.type === 'boolean') {
    return <BooleanFieldRenderer {...commonProps} />;
  }

  if (field.enum) {
    return <EnumFieldRenderer {...commonProps} />;
  }

  if (field.type === 'number') {
    return <NumberFieldRenderer {...commonProps} />;
  }

  if (field.type === 'object') {
    return <ObjectFieldRenderer {...commonProps} />;
  }

  if (field.type === 'array') {
    return <JsonFieldRenderer {...commonProps} isArray={true} />;
  }

  // Default to string field renderer
  return <StringFieldRenderer {...commonProps} />;
};
