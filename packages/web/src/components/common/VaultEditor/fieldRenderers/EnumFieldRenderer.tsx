import React from 'react';
import { Select } from 'antd';
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
    <Select
      className="w-full"
      placeholder={fieldPlaceholder}
      data-testid={`vault-editor-field-${fieldName}`}
    >
      {fieldDef.enum?.map((option) => (
        <Select.Option
          key={option}
          value={option}
          data-testid={`vault-editor-option-${fieldName}-${option}`}
        >
          {option}
        </Select.Option>
      ))}
    </Select>
  </FieldFormItem>
);
