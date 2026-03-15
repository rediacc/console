import type { FormInstance } from 'antd';
import type { FieldDefinition, VaultFormValues } from '../types';
import { encodeBase64 } from '../utils';

export const buildExportData = (
  formData: VaultFormValues,
  entityDef: { fields?: Record<string, FieldDefinition> },
  extraFields: VaultFormValues
): VaultFormValues => {
  const encodedData: VaultFormValues = { ...formData };

  Object.entries(entityDef.fields ?? {}).forEach(([key, field]) => {
    if (
      field.format === 'base64' &&
      encodedData[key] !== undefined &&
      typeof encodedData[key] === 'string'
    ) {
      encodedData[key] = encodeBase64(encodedData[key]);
    }
  });

  const exportData: VaultFormValues = { ...encodedData };

  if (Object.keys(extraFields).length > 0) {
    exportData.extraFields = extraFields;
  }

  Object.keys(exportData).forEach((key) => {
    if (exportData[key] === undefined) {
      delete exportData[key];
    }
  });

  return exportData;
};

const downloadJsonFile = (data: VaultFormValues, entityType: string): void => {
  const dataStr = JSON.stringify(data, null, 2);
  const dataBlob = new Blob([dataStr], { type: 'application/json' });
  const url = URL.createObjectURL(dataBlob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${entityType.toLowerCase()}_vault_${Date.now()}.json`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};

export const handleExport = (
  form: FormInstance<VaultFormValues>,
  entityDef: { fields?: Record<string, FieldDefinition> },
  extraFields: VaultFormValues,
  entityType: string
): void => {
  const formData = form.getFieldsValue();
  const exportData = buildExportData(formData, entityDef, extraFields);
  downloadJsonFile(exportData, entityType);
};
