import type { Rule } from 'antd/es/form';
import type {
  VaultFormValues,
  FieldDefinition,
  VaultDefinitionsConfig,
  ValidateErrorEntity,
  JsonFieldValidatorResult,
  ExtraFieldsResult,
} from './types';

/**
 * Base64 utility functions for fields with format: "base64"
 */
export const decodeBase64 = (value: string): string => {
  try {
    return atob(value).trim();
  } catch (e) {
    console.warn('Failed to decode base64 value:', e);
    return value;
  }
};

export const encodeBase64 = (value: string): string => {
  try {
    return btoa(value.trim());
  } catch (e) {
    console.warn('Failed to encode base64 value:', e);
    return value;
  }
};

/**
 * Helper to merge common types with field definitions
 */
export const getFieldDefinition = (
  field: FieldDefinition,
  vaultDefinitionConfig: VaultDefinitionsConfig
): FieldDefinition => {
  // Check if the field format matches a common type
  if (field.format && field.format in vaultDefinitionConfig.commonTypes) {
    const commonType =
      vaultDefinitionConfig.commonTypes[
        field.format as keyof typeof vaultDefinitionConfig.commonTypes
      ];
    return { ...commonType, ...field };
  }

  // Check if the field type matches a common type name
  const commonTypeKey = Object.keys(vaultDefinitionConfig.commonTypes).find(
    (key) => key === field.type || key === field.format
  );
  if (commonTypeKey) {
    const commonType =
      vaultDefinitionConfig.commonTypes[
        commonTypeKey as keyof typeof vaultDefinitionConfig.commonTypes
      ];
    return { ...commonType, ...field };
  }

  return field;
};

/**
 * Helper to process extra fields
 */
export const processExtraFields = (
  data: VaultFormValues,
  schemaFields: string[],
  currentExtras: VaultFormValues
): ExtraFieldsResult => {
  const extras: VaultFormValues = {};
  const movedToExtra: string[] = [];
  const movedFromExtra: string[] = [];

  // Check if data has extraFields structure
  if (data.extraFields && typeof data.extraFields === 'object') {
    Object.assign(extras, data.extraFields);
  }

  // Check for non-schema fields at root level
  Object.entries(data).forEach(([key, value]) => {
    if (key !== 'extraFields' && !schemaFields.includes(key)) {
      extras[key] = value;
      if (!currentExtras[key] && value !== undefined) {
        movedToExtra.push(key);
      }
    }
  });

  // Check if any fields were moved from extraFields back to regular fields
  Object.keys(currentExtras).forEach((key) => {
    if (!extras[key] && schemaFields.includes(key) && data[key] !== undefined) {
      movedFromExtra.push(key);
    }
  });

  return { extras, movedToExtra, movedFromExtra };
};

/**
 * Helper function to format validation errors
 */
export const formatValidationErrors = (
  errorInfo?: ValidateErrorEntity<VaultFormValues>
): string[] =>
  errorInfo?.errorFields?.map((field) => `${field.name.join('.')}: ${field.errors.join(', ')}`) ??
  [];

/**
 * Helper to build validation rules
 */
export const buildValidationRules = (
  field: FieldDefinition,
  required: boolean,
  fieldLabel: string,
  t: (key: string, options?: Record<string, unknown>) => string
): Rule[] => {
  const rules: Rule[] = [];

  if (required) {
    rules.push({ required: true, message: t('vaultEditor.isRequired', { field: fieldLabel }) });
  }

  const ruleBuilders = {
    pattern: (value: string) => ({
      pattern: new RegExp(value),
      message: t('vaultEditor.invalidFormat', { description: field.description || '' }),
    }),
    minLength: (value: number) => ({
      min: value,
      message: t('vaultEditor.minLength', { length: value }),
    }),
    maxLength: (value: number) => ({
      max: value,
      message: t('vaultEditor.maxLength', { length: value }),
    }),
    minimum: (value: number) => ({
      type: 'number' as const,
      min: value,
      message: t('vaultEditor.minValue', { value }),
    }),
    maximum: (value: number) => ({
      type: 'number' as const,
      max: value,
      message: t('vaultEditor.maxValue', { value }),
    }),
  };

  Object.entries(ruleBuilders).forEach(([key, ruleFn]) => {
    const fieldKey = key as keyof typeof ruleBuilders;
    if (fieldKey in field && field[fieldKey as keyof FieldDefinition] !== undefined) {
      rules.push(ruleFn(field[fieldKey as keyof FieldDefinition] as never));
    }
  });

  return rules;
};

/**
 * Helper for JSON field validation and handling
 */
export const getJsonFieldProps = (
  isArray: boolean,
  t: (key: string) => string
): JsonFieldValidatorResult => {
  const validator = (_rule: unknown, value: unknown) => {
    if (!value) {
      return Promise.resolve();
    }
    try {
      const parsed = typeof value === 'string' ? JSON.parse(value) : value;
      if (isArray && !Array.isArray(parsed)) {
        return Promise.reject(t('vaultEditor.mustBeArray'));
      }
      return Promise.resolve();
    } catch {
      return Promise.reject(
        t(isArray ? 'vaultEditor.mustBeValidJsonArray' : 'vaultEditor.mustBeValidJson')
      );
    }
  };

  const getValueFromEvent = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const { value } = e.target;
    try {
      return value ? JSON.parse(value) : undefined;
    } catch {
      return value;
    }
  };

  const getValueProps = (value: unknown) => ({
    value: (isArray ? Array.isArray(value) : typeof value === 'object' && value !== null)
      ? JSON.stringify(value, null, 2)
      : value,
  });

  return { validator, getValueFromEvent, getValueProps };
};
