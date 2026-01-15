import { decodeBase64, encodeBase64 } from '../utils';
import type { FieldDefinition, VaultFormValues } from '../types';
import type { FormInstance } from 'antd';

export interface FieldMovements {
  movedToExtra: string[];
  movedFromExtra: string[];
}

// Helper: Check if a field is defined in entity schema
const isSchemaField = (
  key: string,
  entityDef: { fields?: Record<string, FieldDefinition> }
): boolean => Boolean(entityDef.fields && key in entityDef.fields);

// Helper: Process a schema field
const processSchemaField = (
  key: string,
  val: unknown,
  entityDef: { fields?: Record<string, FieldDefinition> },
  extraFields: VaultFormValues,
  formData: VaultFormValues,
  movements: FieldMovements
): void => {
  const field = entityDef.fields![key];
  formData[key] = field.format === 'base64' && typeof val === 'string' ? decodeBase64(val) : val;

  if (extraFields[key] !== undefined) {
    movements.movedFromExtra.push(key);
  }
};

// Helper: Process an extra field
const processExtraField = (
  key: string,
  val: unknown,
  extraFields: VaultFormValues,
  extras: VaultFormValues,
  movements: FieldMovements
): void => {
  extras[key] = val;
  if (!extraFields[key] && val !== undefined) {
    movements.movedToExtra.push(key);
  }
};

export const processFieldMovements = (
  parsed: Record<string, unknown>,
  entityDef: { fields?: Record<string, FieldDefinition> },
  extraFields: VaultFormValues
): { formData: VaultFormValues; extras: VaultFormValues; movements: FieldMovements } => {
  const formData: VaultFormValues = {};
  const extras: VaultFormValues = {};
  const movements: FieldMovements = { movedToExtra: [], movedFromExtra: [] };

  if (parsed.extraFields && typeof parsed.extraFields === 'object') {
    Object.assign(extras, parsed.extraFields);
  }

  Object.entries(parsed).forEach(([key, val]) => {
    if (key === 'extraFields') {
      return;
    }

    if (isSchemaField(key, entityDef)) {
      processSchemaField(key, val, entityDef, extraFields, formData, movements);
    } else {
      processExtraField(key, val, extraFields, extras, movements);
    }
  });

  return { formData, extras, movements };
};

export const syncFormWithJson = (
  formData: VaultFormValues,
  extras: VaultFormValues,
  entityDef: { fields?: Record<string, FieldDefinition> }
): VaultFormValues => {
  const encodedData = { ...formData };

  Object.entries(entityDef.fields ?? {}).forEach(([key, field]) => {
    if (
      field.format === 'base64' &&
      encodedData[key] !== undefined &&
      typeof encodedData[key] === 'string'
    ) {
      encodedData[key] = encodeBase64(encodedData[key]);
    }
  });

  const completeData = { ...encodedData };
  if (Object.keys(extras).length > 0) {
    completeData.extraFields = extras;
  }

  return completeData;
};

export const handleRawJsonChange = (
  value: string | undefined,
  form: FormInstance<VaultFormValues>,
  entityDef: { fields?: Record<string, FieldDefinition> },
  extraFields: VaultFormValues,
  initialData: VaultFormValues,
  callbacks: {
    setRawJsonValue: (value: string) => void;
    setRawJsonError: (error: string | null) => void;
    setExtraFields: (fields: VaultFormValues) => void;
    setImportedData: (data: VaultFormValues) => void;
    directOnChange: (data: VaultFormValues, hasChanges: boolean) => void;
    onValidate?: (valid: boolean) => void;
    showFieldMovements: (movements: FieldMovements) => void;
  },
  t: (key: string) => string
): void => {
  if (!value) {
    return;
  }

  callbacks.setRawJsonValue(value);

  try {
    const parsed = JSON.parse(value);
    callbacks.setRawJsonError(null);

    const { formData, extras, movements } = processFieldMovements(parsed, entityDef, extraFields);

    form.setFieldsValue(formData as never);
    callbacks.setExtraFields(extras);

    callbacks.showFieldMovements(movements);

    const completeData = syncFormWithJson(formData, extras, entityDef);
    callbacks.setImportedData(completeData);

    const hasChanges = JSON.stringify(completeData) !== JSON.stringify(initialData);
    callbacks.directOnChange(completeData, hasChanges);

    callbacks.onValidate?.(true);
  } catch {
    callbacks.setRawJsonError(t('vaultEditor.invalidJsonFormat'));
  }
};
