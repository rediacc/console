import type {
  ExtraFieldsResult,
  FieldDefinition,
  JsonFieldValidatorResult,
  ValidateErrorEntity,
  VaultDefinitionsConfig,
  VaultFormValues,
} from './types';
import type { Rule } from 'antd/es/form';

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
 * Move non-schema fields to extraFields
 */
export const moveToExtraFields = (
  data: VaultFormValues,
  schemaFields: string[],
  currentExtras: VaultFormValues
): { extras: VaultFormValues; movedToExtra: string[] } => {
  const extras: VaultFormValues = {};
  const movedToExtra: string[] = [];

  if (data.extraFields && typeof data.extraFields === 'object') {
    Object.assign(extras, data.extraFields);
  }

  Object.entries(data).forEach(([key, value]) => {
    if (key === 'extraFields' || schemaFields.includes(key)) {
      return;
    }

    extras[key] = value;
    if (!currentExtras[key] && value !== undefined) {
      movedToExtra.push(key);
    }
  });

  return { extras, movedToExtra };
};

/**
 * Move fields from extraFields back to regular fields
 */
export const moveFromExtraFields = (
  data: VaultFormValues,
  schemaFields: string[],
  currentExtras: VaultFormValues,
  extras: VaultFormValues
): string[] => {
  const movedFromExtra: string[] = [];

  Object.keys(currentExtras).forEach((key) => {
    if (!extras[key] && schemaFields.includes(key) && data[key] !== undefined) {
      movedFromExtra.push(key);
    }
  });

  return movedFromExtra;
};

/**
 * Helper to process extra fields
 */
export const processExtraFields = (
  data: VaultFormValues,
  schemaFields: string[],
  currentExtras: VaultFormValues
): ExtraFieldsResult => {
  const { extras, movedToExtra } = moveToExtraFields(data, schemaFields, currentExtras);
  const movedFromExtra = moveFromExtraFields(data, schemaFields, currentExtras, extras);

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

type RuleBuilder = (value: never) => Rule;

const createRuleBuilderMap = (
  field: FieldDefinition,
  t: (key: string, options?: Record<string, unknown>) => string
): Map<keyof FieldDefinition, RuleBuilder> => {
  const builders = new Map<keyof FieldDefinition, RuleBuilder>([
    [
      'pattern',
      (value: string) => ({
        pattern: new RegExp(value),
        message: t('vaultEditor.invalidFormat', { description: field.description || '' }),
      }),
    ],
    [
      'minLength',
      (value: number) => ({
        min: value,
        message: t('vaultEditor.minLength', { length: value }),
      }),
    ],
    [
      'maxLength',
      (value: number) => ({
        max: value,
        message: t('vaultEditor.maxLength', { length: value }),
      }),
    ],
    [
      'minimum',
      (value: number) => ({
        type: 'number' as const,
        min: value,
        message: t('vaultEditor.minValue', { value }),
      }),
    ],
    [
      'maximum',
      (value: number) => ({
        type: 'number' as const,
        max: value,
        message: t('vaultEditor.maxValue', { value }),
      }),
    ],
  ]);

  return builders;
};

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

  const ruleBuilders = createRuleBuilderMap(field, t);

  ruleBuilders.forEach((ruleFn, key) => {
    if (key in field && field[key] !== undefined) {
      rules.push(ruleFn(field[key] as never));
    }
  });

  return rules;
};

const validateJsonField = (value: unknown, isArray: boolean, t: (key: string) => string): void => {
  if (!value) {
    return;
  }

  const parsed = typeof value === 'string' ? JSON.parse(value) : value;

  if (isArray && !Array.isArray(parsed)) {
    throw new Error(t('vaultEditor.mustBeArray'));
  }
};

const formatJsonValue = (value: unknown, isArray: boolean): string | unknown => {
  const shouldFormat = isArray ? Array.isArray(value) : typeof value === 'object' && value !== null;
  return shouldFormat ? JSON.stringify(value, null, 2) : value;
};

/**
 * Helper for JSON field validation and handling
 */
export const getJsonFieldProps = (
  isArray: boolean,
  t: (key: string) => string
): JsonFieldValidatorResult => {
  const validator = (_rule: unknown, value: unknown) => {
    try {
      validateJsonField(value, isArray, t);
      return Promise.resolve();
    } catch {
      throw new Error(
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
    value: formatJsonValue(value, isArray),
  });

  return { validator, getValueFromEvent, getValueProps };
};
