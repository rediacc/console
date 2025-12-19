import React from 'react';
import { RediaccTextArea } from '@/components/ui/Form';
import { FieldLabel } from '../components/FieldLabel';
import { FieldItem } from '../styles';
import { getJsonFieldProps } from '../utils';
import type { FieldRendererProps } from './types';

interface JsonFieldRendererProps extends FieldRendererProps {
  isArray: boolean;
}

export const JsonFieldRenderer: React.FC<JsonFieldRendererProps> = ({
  fieldName,
  fieldDef,
  fieldLabel,
  fieldDescription,
  rules,
  isArray,
  t,
}) => {
  const { validator, getValueFromEvent, getValueProps } = getJsonFieldProps(isArray, t);

  return (
    <FieldItem
      name={fieldName}
      label={<FieldLabel label={fieldLabel} description={fieldDescription} />}
      rules={[...rules, { validator }]}
      getValueFromEvent={getValueFromEvent}
      getValueProps={getValueProps}
    >
      <RediaccTextArea
        fullWidth
        placeholder={
          fieldDef.example
            ? `${t('vaultEditor.example')} ${JSON.stringify(fieldDef.example, null, 2)}`
            : t(isArray ? 'vaultEditor.enterJsonArray' : 'vaultEditor.enterJsonObject')
        }
        rows={4}
        data-testid={`vault-editor-field-${fieldName}`}
      />
    </FieldItem>
  );
};
