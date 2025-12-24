import { decodeBase64 } from '../utils';
import type { FieldDefinition, VaultFormValues } from '../types';
import type { FormInstance } from 'antd';
import type { UploadFile } from 'antd/es/upload/interface';

export const readJsonFile = (
  file: UploadFile,
  onSuccess: (data: VaultFormValues) => void,
  onError: () => void
): void => {
  const reader = new FileReader();

  reader.onload = (e: ProgressEvent<FileReader>) => {
    try {
      const data = JSON.parse((e.target?.result as string) || '{}') as VaultFormValues;
      onSuccess(data);
    } catch {
      onError();
    }
  };

  const fileSource: Blob = file.originFileObj ?? (file as unknown as Blob);
  reader.readAsText(fileSource);
};

export const applyImportedData = (
  data: VaultFormValues,
  entityDef: { fields?: Record<string, FieldDefinition> },
  form: FormInstance<VaultFormValues>,
  callbacks: {
    setExtraFields: (fields: VaultFormValues) => void;
    setImportedData: (data: VaultFormValues) => void;
    handleFormChange: () => void;
  }
): void => {
  const extras: VaultFormValues = {};
  const schemaFields = Object.keys(entityDef.fields || {});

  if (data.extraFields && typeof data.extraFields === 'object') {
    Object.assign(extras, data.extraFields as Record<string, unknown>);
  }

  Object.entries(data).forEach(([key, value]) => {
    if (key !== 'extraFields' && !schemaFields.includes(key)) {
      extras[key] = value;
    }
  });

  callbacks.setExtraFields(extras);
  callbacks.setImportedData(data);

  const formData: VaultFormValues = {};
  Object.entries(entityDef.fields || {}).forEach(([key, field]) => {
    if (data[key] !== undefined) {
      formData[key] =
        field.format === 'base64' && typeof data[key] === 'string'
          ? decodeBase64(data[key] as string)
          : data[key];
    }
  });

  form.setFieldsValue(formData as never);
  callbacks.handleFormChange();
};

export const handleImport = (
  file: UploadFile,
  entityDef: { fields?: Record<string, FieldDefinition> } | undefined,
  form: FormInstance<VaultFormValues>,
  callbacks: {
    setExtraFields: (fields: VaultFormValues) => void;
    setImportedData: (data: VaultFormValues) => void;
    handleFormChange: () => void;
  }
): boolean => {
  if (!entityDef) {
    return false;
  }

  readJsonFile(
    file,
    (data) => applyImportedData(data, entityDef, form, callbacks),
    () => {
      // Failed to parse JSON file - silent fail
    }
  );

  return false;
};
