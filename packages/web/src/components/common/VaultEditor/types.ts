import type { FormInstance } from 'antd';
import type { Rule } from 'antd/es/form';
import type { UploadFile } from 'antd/es/upload/interface';

export type VaultFieldValue =
  | string
  | number
  | boolean
  | Record<string, unknown>
  | unknown[]
  | null;

export type VaultFormValues = Record<string, unknown>;

export interface FieldDefinition {
  type: string;
  description?: string;
  example?: string;
  default?: VaultFieldValue;
  enum?: string[];
  pattern?: string;
  format?: string;
  sensitive?: boolean;
  minLength?: number;
  maxLength?: number;
  minimum?: number;
  maximum?: number;
  properties?: Record<string, FieldDefinition>;
  items?: FieldDefinition;
  additionalProperties?: boolean | FieldDefinition;
}

export interface VaultEntityDefinition {
  descriptionKey: string;
  required?: string[];
  optional?: string[];
  fields?: Record<string, FieldDefinition>;
  dynamicFields?: boolean;
  providerSchema?: string;
}

export interface StorageProviderDefinition {
  name: string;
  description?: string;
  required?: string[];
  optional?: string[];
  fields?: Record<string, FieldDefinition>;
}

export type VaultDefinitionsConfig = {
  entities: Record<string, VaultEntityDefinition>;
  commonTypes: Record<string, FieldDefinition>;
};

export type StorageProvidersConfig = {
  providers: Record<string, StorageProviderDefinition>;
};

export interface VaultEditorProps {
  entityType: string;
  initialData?: VaultFormValues;
  onChange?: (data: VaultFormValues, hasChanges: boolean) => void;
  onValidate?: (isValid: boolean, errors?: string[]) => void;
  onImportExport?: (handlers: {
    handleImport: (file: UploadFile) => boolean;
    handleExport: () => void;
  }) => void;
  onFieldMovement?: (movedToExtra: string[], movedFromExtra: string[]) => void;
  onFormReady?: (form: FormInstance<VaultFormValues>) => void;
  showValidationErrors?: boolean;
  teamName?: string;
  bridgeName?: string;
  onTestConnectionStateChange?: (success: boolean) => void;
  onOsSetupStatusChange?: (completed: boolean | null) => void;
  isModalOpen?: boolean;
  isEditMode?: boolean;
  uiMode?: 'simple' | 'expert';
}

export interface ValidateErrorEntity<T = unknown> {
  values: T;
  errorFields: { name: (string | number)[]; errors: string[] }[];
  outOfDate: boolean;
}

export interface FieldLabelProps {
  label: string;
  description?: string;
}

export interface FieldFormItemProps {
  name: string;
  label: string;
  description?: string;
  rules?: Rule[];
  initialValue?: VaultFieldValue;
  valuePropName?: string;
  children: React.ReactNode;
}

export interface JsonFieldValidatorResult {
  validator: (rule: unknown, value: unknown) => Promise<void>;
  getValueFromEvent: (e: React.ChangeEvent<HTMLTextAreaElement>) => unknown;
  getValueProps: (value: unknown) => { value: string | unknown };
}

export interface ExtraFieldsResult {
  extras: VaultFormValues;
  movedToExtra: string[];
  movedFromExtra: string[];
}
