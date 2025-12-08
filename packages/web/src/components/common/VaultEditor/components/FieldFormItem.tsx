import React from 'react';
import { FieldItem } from '../styles';
import { FieldLabel } from './FieldLabel';
import type { FieldFormItemProps } from '../types';

export const FieldFormItem: React.FC<FieldFormItemProps> = ({
  name,
  label,
  description,
  rules,
  initialValue,
  valuePropName,
  children,
}) => (
  <FieldItem
    name={name}
    label={<FieldLabel label={label} description={description} />}
    rules={rules}
    initialValue={initialValue}
    valuePropName={valuePropName}
  >
    {children}
  </FieldItem>
);
