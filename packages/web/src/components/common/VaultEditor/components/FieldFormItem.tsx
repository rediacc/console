import { Form } from 'antd';
import React from 'react';
import type { FieldFormItemProps } from '../types';
import { FieldLabel } from './FieldLabel';

export const FieldFormItem: React.FC<FieldFormItemProps> = ({
  name,
  label,
  description,
  rules,
  initialValue,
  valuePropName,
  children,
}) => (
  <Form.Item
    name={name}
    label={<FieldLabel label={label} description={description} />}
    rules={rules}
    initialValue={initialValue}
    valuePropName={valuePropName}
  >
    {children}
  </Form.Item>
);
