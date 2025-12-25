import type { ReactNode } from 'react';
import type { FormInstance, Rule } from 'antd/es/form';
import type { UploadFile } from 'antd/es/upload/interface';

export interface ResourceFormWithVaultRef {
  submit: () => Promise<void>;
}

export type ResourceFormLayout = 'horizontal' | 'vertical' | 'inline';
export type ResourceFormUiMode = 'simple' | 'expert';

export interface FormFieldOption {
  value: string;
  label: string;
}

export type FormFieldConfig = {
  name: string;
  label: string;
  type?: 'text' | 'select' | 'password' | 'email' | 'number' | 'size';
  placeholder?: string;
  required?: boolean;
  options?: FormFieldOption[];
  rules?: Rule[];
  hidden?: boolean;
  disabled?: boolean;
  readOnly?: boolean;
  helperText?: string;
  sizeUnits?: string[];
};

export interface ImportExportHandlers {
  handleImport: (file: UploadFile) => boolean;
  handleExport: () => void;
}

export interface ResourceFormWithVaultProps {
  form: FormInstance;
  fields: FormFieldConfig[];
  onSubmit: (data: Record<string, unknown>) => void | Promise<void>;
  entityType: string;
  vaultFieldName: string;
  layout?: ResourceFormLayout;
  showDefaultsAlert?: boolean;
  defaultsContent?: ReactNode;
  hideImportExport?: boolean;
  onImportExportRef?: (handlers: ImportExportHandlers) => void;
  initialVaultData?: Record<string, unknown>;
  teamName?: string;
  bridgeName?: string;
  onTestConnectionStateChange?: (success: boolean) => void;
  beforeVaultContent?: ReactNode;
  afterVaultContent?: ReactNode;
  isModalOpen?: boolean;
  isEditMode?: boolean;
  uiMode?: ResourceFormUiMode;
}
