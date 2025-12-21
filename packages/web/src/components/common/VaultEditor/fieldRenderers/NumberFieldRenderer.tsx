import { Form, InputNumber } from 'antd';
import React from 'react';
import { FieldLabel } from '../components/FieldLabel';
import type { FieldRendererProps } from './types';

export const NumberFieldRenderer: React.FC<FieldRendererProps> = ({
  fieldName,
  fieldDef,
  fieldLabel,
  fieldDescription,
  fieldPlaceholder,
  rules,
}) => (
  <Form.Item
    name={fieldName}
    label={<FieldLabel label={fieldLabel} description={fieldDescription} />}
    rules={rules}
    initialValue={fieldDef.default}
  >
    <InputNumber
      style={{ width: '100%' }}
      placeholder={fieldPlaceholder}
      min={fieldDef.minimum}
      max={fieldDef.maximum}
      data-testid={`vault-editor-field-${fieldName}`}
    />
  </Form.Item>
);
