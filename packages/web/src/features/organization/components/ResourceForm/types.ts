import type { FormInstance, Rule } from 'antd/es/form';

export type FormFieldConfig = {
  name: string;
  label: string;
  type?: 'text' | 'select' | 'password' | 'email' | 'number';
  placeholder?: string;
  required?: boolean;
  options?: { value: string; label: string }[];
  rules?: Rule[];
  hidden?: boolean;
  disabled?: boolean;
};

export interface ResourceFormProps {
  form: FormInstance;
  fields: FormFieldConfig[];
  onSubmit: (data: Record<string, unknown>) => void | Promise<void>;
  submitText?: string;
  cancelText?: string;
  onCancel?: () => void;
  loading?: boolean;
}
