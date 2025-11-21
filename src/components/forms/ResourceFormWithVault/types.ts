import type { ReactNode } from 'react'
import type { UseFormReturn, ControllerProps, FieldValues } from 'react-hook-form'
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

export interface FormFieldConfig {
  name: string
  label: string
  type?: 'text' | 'select' | 'password' | 'email' | 'number' | 'size'
  placeholder?: string
  required?: boolean
  options?: FormFieldOption[]
  rules?: ControllerProps<FieldValues>['rules']
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

export interface ResourceFormWithVaultProps<T extends Record<string, any> = any> {
  form: UseFormReturn<T>
  fields: FormFieldConfig[]
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
