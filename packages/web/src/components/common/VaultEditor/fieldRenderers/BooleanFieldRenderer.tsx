import React from 'react';
import { Switch } from 'antd';
import { FieldFormItem } from '../components/FieldFormItem';
import type { FieldRendererProps } from './types';

export const BooleanFieldRenderer: React.FC<FieldRendererProps> = ({
  fieldName,
  fieldDef,
  fieldLabel,
  fieldDescription,
}) => (
  <FieldFormItem
    name={fieldName}
    label={fieldLabel}
    description={fieldDescription}
    initialValue={fieldDef.default}
    valuePropName="checked"
  >
    <Switch data-testid={`vault-editor-field-${fieldName}`} />
  </FieldFormItem>
);
