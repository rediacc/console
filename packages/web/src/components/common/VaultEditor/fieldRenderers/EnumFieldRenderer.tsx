import React from 'react';
import { RediaccOption, RediaccSelect } from '@/components/ui/Form';
import { FieldFormItem } from '../components/FieldFormItem';
import type { FieldRendererProps } from './types';

export const EnumFieldRenderer: React.FC<FieldRendererProps> = ({
  fieldName,
  fieldDef,
  fieldLabel,
  fieldDescription,
  fieldPlaceholder,
  rules,
}) => (
  <FieldFormItem
    name={fieldName}
    label={fieldLabel}
    description={fieldDescription}
    rules={rules}
    initialValue={fieldDef.default}
  >
    <RediaccSelect
      fullWidth
      placeholder={fieldPlaceholder}
      data-testid={`vault-editor-field-${fieldName}`}
    >
      {fieldDef.enum?.map((option) => (
        <RediaccOption key={option} value={option}>
          {option}
        </RediaccOption>
      ))}
    </RediaccSelect>
  </FieldFormItem>
);
