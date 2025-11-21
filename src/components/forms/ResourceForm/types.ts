import { FieldValues, UseFormReturn } from 'react-hook-form'

export interface FormFieldConfig {
  name: string
  label: string
  type?: 'text' | 'select' | 'password' | 'email' | 'number'
  placeholder?: string
  required?: boolean
  options?: Array<{ value: string; label: string }>
  rules?: any[]
  hidden?: boolean
  disabled?: boolean
}

export interface ResourceFormProps<T extends FieldValues = FieldValues> {
  form: UseFormReturn<T>
  fields: FormFieldConfig[]
  onSubmit: (data: T) => void | Promise<void>
  submitText?: string
  cancelText?: string
  onCancel?: () => void
  loading?: boolean
  layout?: 'horizontal' | 'vertical' | 'inline'
}
