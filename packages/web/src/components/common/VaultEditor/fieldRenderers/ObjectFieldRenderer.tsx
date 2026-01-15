import React from 'react';
import { Form } from 'antd';
import { JsonFieldRenderer } from './JsonFieldRenderer';
import { FieldLabel } from '../components/FieldLabel';
import { NestedObjectEditor } from '../components/NestedObjectEditor';
import type { FieldRendererProps } from './types';

type NestedFieldDefinition = React.ComponentProps<typeof NestedObjectEditor>['fieldDefinition'];

export const ObjectFieldRenderer: React.FC<FieldRendererProps> = (props) => {
  const { fieldName, fieldDef, fieldLabel, fieldDescription, rules } = props;

  const hasStructure =
    fieldDef.properties ??
    (fieldDef.additionalProperties && typeof fieldDef.additionalProperties === 'object');

  if (hasStructure) {
    return (
      <Form.Item
        name={fieldName}
        label={<FieldLabel label={fieldLabel} description={fieldDescription} />}
        rules={rules}
      >
        <NestedObjectEditor
          fieldDefinition={fieldDef as NestedFieldDefinition}
          title={fieldLabel}
          description={fieldDescription}
          data-testid={`vault-editor-field-${fieldName}`}
        />
      </Form.Item>
    );
  }

  return <JsonFieldRenderer {...props} isArray={false} />;
};
