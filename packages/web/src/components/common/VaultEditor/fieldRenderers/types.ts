import type { FormInstance } from 'antd';
import type { Rule } from 'antd/es/form';
import type { FieldDefinition, VaultFormValues } from '../types';

export interface FieldRendererProps {
  fieldName: string;
  fieldDef: FieldDefinition;
  required: boolean;
  isProviderField?: boolean;
  fieldLabel: string;
  fieldDescription?: string;
  fieldPlaceholder?: string;
  rules: Rule[];
  entityType: string;
  selectedProvider?: string;
  form: FormInstance<VaultFormValues>;
  handleFormChange: (changedValues?: VaultFormValues) => void;
  t: (key: string, options?: Record<string, unknown>) => string;
}
