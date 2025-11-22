import type { ReactNode } from 'react'
import type {
  ControllerProps,
  FieldValues,
  UseFormReturn,
} from 'react-hook-form'
import type { UploadFile } from 'antd/es/upload/interface'

export interface ResourceFormWithVaultRef {
  submit: () => Promise<void>
}

export type ResourceFormLayout = 'horizontal' | 'vertical' | 'inline'
export type ResourceFormCreationContext = 'credentials-only' | 'normal'
export type ResourceFormUiMode = 'simple' | 'expert'

export interface FormFieldOption {
  value: string
  label: string
}

export type FormFieldConfig<TFieldValues extends FieldValues = FieldValues> = {
  name: string
  label: string
  type?: 'text' | 'select' | 'password' | 'email' | 'number' | 'size'
  placeholder?: string
  required?: boolean
  options?: FormFieldOption[]
  rules?: ControllerProps<TFieldValues>['rules']
  hidden?: boolean
  disabled?: boolean
  readOnly?: boolean
  helperText?: string
  sizeUnits?: string[]
}

export interface ImportExportHandlers {
  handleImport: (file: UploadFile) => boolean
  handleExport: () => void
}

export interface ResourceFormWithVaultProps<T extends FieldValues = FieldValues> {
  form: UseFormReturn<T>
  fields: Array<FormFieldConfig<T>>
  onSubmit: (data: T) => void | Promise<void>
  entityType: string
  vaultFieldName: string
  layout?: ResourceFormLayout
  showDefaultsAlert?: boolean
  defaultsContent?: ReactNode
  hideImportExport?: boolean
  onImportExportRef?: (handlers: ImportExportHandlers) => void
  initialVaultData?: Record<string, any>
  teamName?: string
  bridgeName?: string
  onTestConnectionStateChange?: (success: boolean) => void
  beforeVaultContent?: ReactNode
  afterVaultContent?: ReactNode
  isModalOpen?: boolean
  isEditMode?: boolean
  creationContext?: ResourceFormCreationContext
  uiMode?: ResourceFormUiMode
}
