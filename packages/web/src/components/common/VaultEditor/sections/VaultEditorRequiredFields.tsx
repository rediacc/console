import React from 'react';
import { Col } from 'antd';
import { MACHINE_BASIC_FIELD_ORDER } from '../constants';
import { VaultFieldRenderer } from '../fieldRenderers';
import type { FieldDefinition, VaultFormValues } from '../types';
import type { FormInstance } from 'antd';

interface VaultEditorRequiredFieldsProps {
  entityType: string;
  requiredFields: string[];
  fields: Record<string, FieldDefinition>;
  isEditMode: boolean;
  selectedProvider?: string;
  form: FormInstance<VaultFormValues>;
  handleFormChange: (changedValues?: VaultFormValues) => void;
  t: (key: string, options?: Record<string, unknown>) => string;
}

export const VaultEditorRequiredFields: React.FC<VaultEditorRequiredFieldsProps> = ({
  entityType,
  requiredFields,
  fields,
  isEditMode,
  selectedProvider,
  form,
  handleFormChange,
  t,
}) => {
  const fieldOrder = entityType === 'MACHINE' ? MACHINE_BASIC_FIELD_ORDER : requiredFields;

  return (
    <>
      {fieldOrder.map((fieldName) => {
        const field = fields[fieldName as keyof typeof fields];
        if (!field) return null;

        const isRequired = !(
          isEditMode &&
          entityType === 'REPOSITORY' &&
          fieldName === 'credential'
        );

        const colSpan = entityType === 'REPOSITORY' && fieldName === 'credential' ? 24 : 12;

        return (
          <Col key={fieldName} xs={24} md={colSpan}>
            <VaultFieldRenderer
              fieldName={fieldName}
              fieldDef={field}
              required={isRequired}
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
