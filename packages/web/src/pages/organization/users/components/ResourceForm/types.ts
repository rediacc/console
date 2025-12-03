import type {
  ControllerProps,
  FieldValues,
  UseFormReturn,
} from 'react-hook-form'

export type FormFieldConfig<TFieldValues extends FieldValues = FieldValues> = {
  name: ControllerProps<TFieldValues>['name']
  label: string
  type?: 'text' | 'select' | 'password' | 'email' | 'number'
  placeholder?: string
  required?: boolean
  options?: Array<{ value: string; label: string }>
  rules?: ControllerProps<TFieldValues>['rules']
  hidden?: boolean
  disabled?: boolean
}

export interface ResourceFormProps<T extends FieldValues = FieldValues> {
  form: UseFormReturn<T>
  fields: Array<FormFieldConfig<T>>
  onSubmit: (data: T) => void | Promise<void>
  submitText?: string
  cancelText?: string
  onCancel?: () => void
  loading?: boolean
  layout?: 'horizontal' | 'vertical' | 'inline'
}
