import React, { useState, useEffect, useRef, useImperativeHandle, forwardRef } from 'react'
import { Divider, Alert, Button, Space, Upload, message, Form, Input, Select, InputNumber } from 'antd'
import { UploadOutlined, DownloadOutlined } from '@/utils/optimizedIcons'
import { UseFormReturn, Controller } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import VaultEditor from '../common/VaultEditor'

export interface ResourceFormWithVaultRef {
  submit: () => Promise<void>
}

interface FormFieldConfig {
  name: string
  label: string
  type?: 'text' | 'select' | 'password' | 'email' | 'number' | 'size'
  placeholder?: string
  required?: boolean
  options?: Array<{ value: string; label: string }>
  rules?: any[]
  hidden?: boolean
  disabled?: boolean
  helperText?: string
  sizeUnits?: string[] // For size type: ['G', 'T'] or ['percentage', 'G', 'T']
}

interface ResourceFormWithVaultProps<T extends Record<string, any> = any> {
  form: UseFormReturn<T>
  fields: FormFieldConfig[]
  onSubmit: (data: T) => void | Promise<void>
  entityType: string
  vaultFieldName: string // e.g., 'repositoryVault', 'storageVault', 'scheduleVault'
  layout?: 'horizontal' | 'vertical' | 'inline'
  showDefaultsAlert?: boolean
  defaultsContent?: React.ReactNode
  hideImportExport?: boolean
  onImportExportRef?: (handlers: { handleImport: (file: any) => boolean; handleExport: () => void }) => void
  initialVaultData?: Record<string, any>
  teamName?: string // For SSH test connection
  bridgeName?: string // For SSH test connection
  onTestConnectionStateChange?: (success: boolean) => void // Callback for test connection state
  beforeVaultContent?: React.ReactNode // Custom content to render before vault configuration
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
    hideImportExport = false,
    onImportExportRef,
    initialVaultData = {},
    teamName,
    bridgeName,
    onTestConnectionStateChange,
    beforeVaultContent,
  }, ref) {
    const { t } = useTranslation('common')
    const [vaultData, setVaultData] = useState<Record<string, any>>(initialVaultData)
    const [isVaultValid, setIsVaultValid] = useState(true)
    const [vaultValidationErrors, setVaultValidationErrors] = useState<string[]>([])
    const [showVaultValidationErrors, setShowVaultValidationErrors] = useState(false)
    const importExportHandlers = useRef<{ handleImport: (file: any) => boolean; handleExport: () => void } | null>(null)
    
    // Debug logging for vault validation
    useEffect(() => {
      console.log('=== ResourceFormWithVault vault state ===')
      console.log('Is vault valid:', isVaultValid)
      console.log('Vault validation errors:', vaultValidationErrors)
      console.log('Show vault validation errors:', showVaultValidationErrors)
      console.log('Entity type:', entityType)
    }, [isVaultValid, vaultValidationErrors, showVaultValidationErrors, entityType])
    

    const {
      control,
      handleSubmit,
      formState: { errors },
      setValue,
    } = form

    // Set initial vault data in form
    useEffect(() => {
      setValue(vaultFieldName as any, JSON.stringify(vaultData))
    }, [vaultData, setValue, vaultFieldName])

    const handleFormSubmit = async (formData: any) => {
      console.log('=== ResourceFormWithVault handleFormSubmit ===')
      console.log('Form data:', formData)
      console.log('Vault valid:', isVaultValid)
      console.log('Vault data:', vaultData)
      console.log('Show vault validation errors:', showVaultValidationErrors)
      console.log('Form errors:', form.formState.errors)
      console.log('Form isValid:', form.formState.isValid)
      
      if (!isVaultValid) {
        console.log('Validation failed: Vault is not valid')
        console.log('About to show error message: "Please fix validation errors before saving"')
        setShowVaultValidationErrors(true)
        message.error(t('vaultEditor.pleaseFixErrors'))
        return
      }

      try {
        // Update the vault field with the latest vault data
        const dataWithVault = {
          ...formData,
          [vaultFieldName]: JSON.stringify(vaultData)
        }
        await onSubmit(dataWithVault)
      } catch (error) {
        // Error handled by parent
      }
    }

    const handleVaultChange = (data: Record<string, any>) => {
      setVaultData(data)
    }

    const handleVaultValidate = (valid: boolean, errors?: string[]) => {
      setIsVaultValid(valid)
      setVaultValidationErrors(errors || [])
    }

    // Expose submit method to parent
    useImperativeHandle(ref, () => ({
      submit: async () => {
        console.log('=== ResourceFormWithVault submit called ===')
        console.log('Current form values:', form.getValues())
        console.log('Form state:', form.formState)
        console.log('Is vault valid before submit:', isVaultValid)
        
        try {
          const result = await handleSubmit(handleFormSubmit)()
          console.log('Submit result:', result)
          return result
        } catch (error) {
          console.error('Submit error:', error)
          throw error
        }
      }
    }))

    const renderField = (field: FormFieldConfig) => {
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
                  autoComplete="off"
                />
              )}
            />
          )

        case 'size':
          const units = field.sizeUnits || ['G', 'T']
          const defaultUnit = units[0] === 'percentage' ? '%' : units[0]
          
          return (
            <Controller
              name={field.name as any}
              control={control}
              render={({ field: controllerField }) => {
                // Parse the current value (e.g., "100G" -> {value: 100, unit: "G"})
                const currentValue = controllerField.value || ''
                let parsedValue: number | undefined = undefined
                let parsedUnit = defaultUnit
                
                if (currentValue) {
                  const match = currentValue.match(/^(\d+)([%GT]?)$/)
                  if (match) {
                    parsedValue = parseInt(match[1], 10)
                    parsedUnit = match[2] || defaultUnit
                  }
                }
                
                return (
                  <Space.Compact style={{ width: '100%' }}>
                    <InputNumber
                      style={{ width: '65%' }}
                      value={parsedValue}
                      onChange={(value) => {
                        // Ensure only numbers are accepted
                        if (value === null || value === undefined) {
                          controllerField.onChange('')
                        } else {
                          const numValue = typeof value === 'string' ? parseInt(value, 10) : value
                          if (!isNaN(numValue) && numValue > 0) {
                            controllerField.onChange(`${numValue}${parsedUnit}`)
                          }
                        }
                      }}
                      onKeyDown={(e) => {
                        // Only allow numbers
                        const key = e.key
                        if (!/[0-9]/.test(key) && key !== 'Backspace' && key !== 'Delete' && key !== 'Tab' && key !== 'Enter' && key !== 'ArrowLeft' && key !== 'ArrowRight') {
                          e.preventDefault()
                        }
                      }}
                      parser={(value) => {
                        // Remove any non-numeric characters
                        const parsed = value?.replace(/[^\d]/g, '')
                        return parsed ? parseInt(parsed, 10) : 0
                      }}
                      formatter={(value) => {
                        // Format as integer
                        return value ? `${value}` : ''
                      }}
                      placeholder={units.includes('percentage') ? '95' : '100'}
                      min={1}
                      max={units.includes('percentage') ? 100 : undefined}
                      disabled={field.disabled}
                      keyboard={true}
                      step={1}
                      precision={0}
                    />
                    <Select
                      style={{ width: '35%' }}
                      value={parsedUnit}
                      onChange={(unit) => {
                        const newValue = parsedValue ? `${parsedValue}${unit}` : ''
                        controllerField.onChange(newValue)
                      }}
                      options={units.map(unit => ({
                        value: unit === 'percentage' ? '%' : unit,
                        label: unit === 'percentage' ? '%' : unit === 'G' ? 'GB' : 'TB'
                      }))}
                      disabled={field.disabled}
                    />
                  </Space.Compact>
                )
              }}
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
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, height: '100%' }}>
        {/* Form Section */}
        <Form 
          layout={formLayout}
          labelCol={labelCol}
          wrapperCol={wrapperCol}
          labelAlign="right"
          colon={true}
          style={{ flexShrink: 0 }}
        >
          {fields.map((field) => {
            if (field.hidden) return null

            const fieldName = field.name
            const error = errors && typeof errors === 'object' && fieldName in errors 
              ? (errors as Record<string, any>)[fieldName] 
              : undefined

            return (
              <Form.Item
                key={field.name}
                label={field.label}
                required={field.required}
                validateStatus={error ? 'error' : undefined}
                help={error?.message as string || field.helperText}
              >
                {renderField(field)}
              </Form.Item>
            )
          })}
        </Form>

        {/* Custom content before vault configuration */}
        {beforeVaultContent}

        {/* Divider */}
        <Divider style={{ margin: '8px 0' }}>{t('vaultEditor.vaultConfiguration')}</Divider>

        {/* Vault Editor Section */}
        <div style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
          <VaultEditor
            entityType={entityType}
            initialData={initialVaultData}
            onChange={handleVaultChange}
            onValidate={handleVaultValidate}
            teamName={teamName}
            bridgeName={bridgeName}
            onTestConnectionStateChange={onTestConnectionStateChange}
            onImportExport={(handlers) => {
              importExportHandlers.current = handlers
              // Pass handlers to parent if callback is provided
              if (onImportExportRef) {
                onImportExportRef(handlers)
              }
            }}
          />
        </div>

        {/* Import/Export Buttons */}
        {!hideImportExport && (
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
        )}

        {/* Validation Errors */}
        {showVaultValidationErrors && vaultValidationErrors.length > 0 && (
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