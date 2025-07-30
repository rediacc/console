import React from 'react'
import { Form, Input, Select, Button, Space } from 'antd'
import { Controller, UseFormReturn } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { ZodSchema } from 'zod'

interface FormFieldConfig {
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

interface ResourceFormProps<T = any> {
  form: UseFormReturn<T>
  fields: FormFieldConfig[]
  onSubmit: (data: T) => void | Promise<void>
  submitText?: string
  cancelText?: string
  onCancel?: () => void
  loading?: boolean
  layout?: 'horizontal' | 'vertical' | 'inline'
}

function ResourceForm<T = any>({
  form,
  fields,
  onSubmit,
  submitText = 'Submit',
  cancelText = 'Cancel',
  onCancel,
  loading = false,
  layout = 'vertical',
}: ResourceFormProps<T>) {
  const {
    control,
    handleSubmit,
    formState: { errors },
  } = form

  const renderField = (field: FormFieldConfig) => {
    const error = errors[field.name as keyof typeof errors]

    switch (field.type) {
      case 'select':
        return (
          <Controller
            name={field.name as any}
            control={control}
            render={({ field: controllerField }) => (
              <Select
                {...controllerField}
                placeholder={field.placeholder}
                options={field.options}
                disabled={field.disabled}
                allowClear
                showSearch
                filterOption={(input, option) =>
                  (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                }
                style={{ width: '100%' }}
                data-testid={`resource-form-field-${field.name}`}
              />
            )}
          />
        )

      case 'password':
        return (
          <Controller
            name={field.name as any}
            control={control}
            render={({ field: controllerField }) => (
              <Input.Password
                {...controllerField}
                placeholder={field.placeholder}
                disabled={field.disabled}
                autoComplete="off"
                data-testid={`resource-form-field-${field.name}`}
              />
            )}
          />
        )

      default:
        return (
          <Controller
            name={field.name as any}
            control={control}
            render={({ field: controllerField }) => (
              <Input
                {...controllerField}
                type={field.type || 'text'}
                placeholder={field.placeholder}
                disabled={field.disabled}
                autoComplete="off"
                data-testid={`resource-form-field-${field.name}`}
              />
            )}
          />
        )
    }
  }

  // Force horizontal layout for popup forms to save space
  const formLayout = layout === 'vertical' ? 'horizontal' : layout
  const labelCol = { span: 6 }
  const wrapperCol = { span: 18 }

  return (
    <Form 
      layout={formLayout} 
      onFinish={handleSubmit(onSubmit)}
      labelCol={labelCol}
      wrapperCol={wrapperCol}
      labelAlign="right"
      colon={true}
      data-testid="resource-form"
    >
      {fields.map((field) => {
        if (field.hidden) return null

        const error = errors[field.name as keyof typeof errors]

        return (
          <Form.Item
            key={field.name}
            label={field.label}
            required={field.required}
            validateStatus={error ? 'error' : undefined}
            help={error?.message as string}
          >
            {renderField(field)}
          </Form.Item>
        )
      })}

      <Form.Item 
        style={{ marginBottom: 0, marginTop: 24 }}
        wrapperCol={{ offset: labelCol.span, span: wrapperCol.span }}
      >
        <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
          {onCancel && (
            <Button 
              onClick={onCancel} 
              disabled={loading}
              data-testid="resource-form-cancel-button"
            >
              {cancelText}
            </Button>
          )}
          <Button
            type="primary"
            htmlType="submit"
            loading={loading}
            style={{ background: '#556b2f', borderColor: '#556b2f' }}
            data-testid="resource-form-submit-button"
          >
            {submitText}
          </Button>
        </Space>
      </Form.Item>
    </Form>
  )
}

export default ResourceForm