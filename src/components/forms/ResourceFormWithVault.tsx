import React, { useState, useEffect, useRef, useImperativeHandle, forwardRef } from 'react'
import { Divider, Alert, Button, Space, Upload, message, Form, Input, Select } from 'antd'
import { UploadOutlined, DownloadOutlined } from '@ant-design/icons'
import { UseFormReturn, Controller } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import VaultEditor from '../common/VaultEditor'

export interface ResourceFormWithVaultRef {
  submit: () => Promise<void>
}

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

interface ResourceFormWithVaultProps<T = any> {
  form: UseFormReturn<T>
  fields: FormFieldConfig[]
  onSubmit: (data: T) => void | Promise<void>
  entityType: string
  vaultFieldName: string // e.g., 'repositoryVault', 'storageVault', 'scheduleVault'
  layout?: 'horizontal' | 'vertical' | 'inline'
  showDefaultsAlert?: boolean
  defaultsContent?: React.ReactNode
}

const ResourceFormWithVault = forwardRef<ResourceFormWithVaultRef, ResourceFormWithVaultProps<any>>(
  function ResourceFormWithVault({
    form,
    fields,
    onSubmit,
    entityType,
    vaultFieldName,
    layout = 'vertical',
    showDefaultsAlert = false,
    defaultsContent,
  }, ref) {
    const { t } = useTranslation('common')
    const [vaultData, setVaultData] = useState<Record<string, any>>({})
    const [isVaultValid, setIsVaultValid] = useState(true)
    const [vaultValidationErrors, setVaultValidationErrors] = useState<string[]>([])
    const importExportHandlers = useRef<{ handleImport: (file: any) => boolean; handleExport: () => void } | null>(null)

    const {
      control,
      handleSubmit,
      formState: { errors },
      setValue,
    } = form

    // Set initial vault data in form
    useEffect(() => {
      setValue(vaultFieldName as any, JSON.stringify(vaultData, null, 2))
    }, [vaultData, setValue, vaultFieldName])

    const handleFormSubmit = async (formData: any) => {
      if (!isVaultValid) {
        message.error(t('vaultEditor.pleaseFixErrors'))
        return
      }

      try {
        // Update the vault field with the latest vault data
        const dataWithVault = {
          ...formData,
          [vaultFieldName]: JSON.stringify(vaultData, null, 2)
        }
        await onSubmit(dataWithVault)
      } catch (error) {
        // Error handled by parent
      }
    }

    const handleVaultChange = (data: Record<string, any>, hasChanges: boolean) => {
      setVaultData(data)
    }

    const handleVaultValidate = (valid: boolean, errors?: string[]) => {
      setIsVaultValid(valid)
      setVaultValidationErrors(errors || [])
    }

    // Expose submit method to parent
    useImperativeHandle(ref, () => ({
      submit: async () => {
        await handleSubmit(handleFormSubmit)()
      }
    }))

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
                />
              )}
            />
          )
      }
    }

    // Force horizontal layout for popup forms to save space
    const formLayout = layout === 'vertical' ? 'horizontal' : layout
    const labelCol = { span: 8 }
    const wrapperCol = { span: 16 }

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {/* Form Section */}
        <Form 
          layout={formLayout}
          labelCol={labelCol}
          wrapperCol={wrapperCol}
          labelAlign="left"
          colon={true}
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
        </Form>

        {/* Divider */}
        <Divider style={{ margin: '8px 0' }}>{t('vaultEditor.vaultConfiguration')}</Divider>

        {/* Vault Editor Section */}
        <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
          <VaultEditor
            entityType={entityType}
            initialData={vaultData}
            onChange={handleVaultChange}
            onValidate={handleVaultValidate}
            onImportExport={(handlers) => {
              importExportHandlers.current = handlers
            }}
          />
        </div>

        {/* Import/Export Buttons */}
        <div style={{ 
          display: 'flex', 
          justifyContent: 'space-between', 
          alignItems: 'center',
          paddingTop: 16,
          borderTop: '1px solid #f0f0f0'
        }}>
          <Space>
            <Upload
              accept=".json"
              showUploadList={false}
              beforeUpload={(file) => {
                if (importExportHandlers.current) {
                  return importExportHandlers.current.handleImport(file)
                }
                return false
              }}
            >
              <Button size="small" icon={<UploadOutlined />}>{t('vaultEditor.importJson')}</Button>
            </Upload>
            <Button 
              size="small"
              icon={<DownloadOutlined />} 
              onClick={() => {
                if (importExportHandlers.current) {
                  importExportHandlers.current.handleExport()
                }
              }}
            >
              {t('vaultEditor.exportJson')}
            </Button>
          </Space>
        </div>

        {/* Validation Errors */}
        {vaultValidationErrors.length > 0 && (
          <Alert
            message={t('vaultEditor.validationErrors')}
            description={
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {vaultValidationErrors.map((error, index) => (
                  <li key={index}>{error}</li>
                ))}
              </ul>
            }
            type="error"
            showIcon
          />
        )}

        {/* Defaults Alert (for Simple mode) */}
        {showDefaultsAlert && defaultsContent && (
          <div style={{ 
            borderTop: '1px solid #f0f0f0', 
            paddingTop: 16,
            marginTop: 8
          }}>
            <Alert
              message={t('general.defaultsApplied')}
              description={defaultsContent}
              type="info"
              showIcon
            />
          </div>
        )}
      </div>
    )
  }
)

export default ResourceFormWithVault