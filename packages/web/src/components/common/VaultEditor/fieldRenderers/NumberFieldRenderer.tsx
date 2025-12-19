import React from 'react';
import { RediaccInputNumber } from '@/components/ui/Form';
import { FieldLabel } from '../components/FieldLabel';
import { FieldItem } from '../styles';
import type { FieldRendererProps } from './types';

export const NumberFieldRenderer: React.FC<FieldRendererProps> = ({
  fieldName,
  fieldDef,
  fieldLabel,
  fieldDescription,
  fieldPlaceholder,
  rules,
}) => (
  <FieldItem
    name={fieldName}
    label={<FieldLabel label={fieldLabel} description={fieldDescription} />}
    rules={rules}
    initialValue={fieldDef.default}
  >
    <RediaccInputNumber
      fullWidth
      placeholder={fieldPlaceholder}
      min={fieldDef.minimum}
      max={fieldDef.maximum}
      data-testid={`vault-editor-field-${fieldName}`}
    />
  </FieldItem>
);
