import React, { useState, useEffect, useRef, useImperativeHandle, forwardRef } from 'react'
import { Divider, Alert, Button, Space, Upload, message, Form, Input, Select, InputNumber, Tooltip, Row, Col } from 'antd'
import { UploadOutlined, DownloadOutlined } from '@/utils/optimizedIcons'
import { UseFormReturn, Controller } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import VaultEditor from '../common/VaultEditor'
import { useFormStyles } from '@/hooks/useComponentStyles'
import { spacing } from '@/utils/styleConstants'

export interface ResourceFormWithVaultRef {
  submit: () => Promise<void>
}

export interface FormFieldConfig {
  name: string
  label: string
  type?: 'text' | 'select' | 'password' | 'email' | 'number' | 'size'
  placeholder?: string
  required?: boolean
  options?: Array<{ value: string; label: string }>
  rules?: any[]
  hidden?: boolean
  disabled?: boolean
  readOnly?: boolean
  helperText?: string
  sizeUnits?: string[] // For size type: ['G', 'T'] or ['percentage', 'G', 'T']
}

interface ResourceFormWithVaultProps<T extends Record<string, any> = any> {
  form: UseFormReturn<T>
  fields: FormFieldConfig[]
  onSubmit: (data: T) => void | Promise<void>
  entityType: string
  vaultFieldName: string // e.g., 'repositoryVault', 'storageVault'
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
  afterVaultContent?: React.ReactNode // Custom content to render after vault configuration
  isModalOpen?: boolean // Modal open state to handle resets
  isEditMode?: boolean // Whether we're in edit mode
  creationContext?: 'credentials-only' | 'normal' // Context for repository creation
  uiMode?: 'simple' | 'expert' // UI mode for conditional rendering
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
    afterVaultContent,
    isModalOpen,
    isEditMode = false,
    creationContext,
    uiMode = 'expert',
  }, ref) {
    const { t } = useTranslation('common')
    const styles = useFormStyles()
    const [vaultData, setVaultData] = useState<Record<string, any>>(initialVaultData)
    const [isVaultValid, setIsVaultValid] = useState(true)
    const [vaultValidationErrors, setVaultValidationErrors] = useState<string[]>([])
    const [showVaultValidationErrors, setShowVaultValidationErrors] = useState(false)
    const [forceVaultErrors, setForceVaultErrors] = useState(false)
    const importExportHandlers = useRef<{ handleImport: (file: any) => boolean; handleExport: () => void } | null>(null)

    // Track vault validation state changes
    useEffect(() => {
      // Vault validation state updated
    }, [isVaultValid, vaultValidationErrors, showVaultValidationErrors, entityType])

    useEffect(() => {
      if (!isModalOpen) {
        setForceVaultErrors(false)
      }
    }, [isModalOpen])


    const {
      control,
      handleSubmit,
      formState: { errors, touchedFields, submitCount, isSubmitted },
      setValue,
    } = form

    // Set initial vault data in form
    useEffect(() => {
      setValue(vaultFieldName as any, JSON.stringify(vaultData))
    }, [vaultData, setValue, vaultFieldName])

    const handleFormSubmit = async (formData: any) => {
      // Skip vault validation for repository credentials
      // Repository credentials only need field-level validation (regex patterns)
      // which is already handled by the form validation system
      // This applies to both creation in credentials-only mode AND edit mode for repositories
      const shouldSkipVaultValidation = entityType === 'REPOSITORY' && (creationContext === 'credentials-only' || isEditMode)

      if (!isVaultValid && !shouldSkipVaultValidation) {
        setShowVaultValidationErrors(true)
        setForceVaultErrors(true)
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
        setForceVaultErrors(false)
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
      if (valid) {
        setForceVaultErrors(false)
      }
    }

    // Expose submit method to parent
    useImperativeHandle(ref, () => ({
      submit: async () => {
        const result = await handleSubmit(handleFormSubmit)()
        return result
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
                  data-testid={`resource-modal-field-${field.name}-select`}
                  placeholder={field.placeholder}
                  options={field.options}
                  disabled={field.disabled}
                  allowClear
                  showSearch
                  filterOption={(input, option) =>
                    (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                  }
                  style={{ 
                    // Don't apply formInput styles to Select - different DOM structure
                    width: '100%' 
                  }}
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
                  data-testid={`resource-modal-field-${field.name}-password`}
                  placeholder={field.placeholder}
                  disabled={field.disabled}
                  readOnly={field.readOnly}
                  autoComplete="off"
                />
              )}
            />
          )

        case 'size': {
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
                      data-testid={`resource-modal-field-${field.name}-size-input`}
                      style={{ 
                        // Base styles handled by CSS
                        width: '65%' 
                      }}
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
                      data-testid={`resource-modal-field-${field.name}-size-unit`}
                      style={{ 
                        // Don't apply formInput styles to Select - different DOM structure
                        width: '35%' 
                      }}
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
        }

        default:
          return (
            <Controller
              name={field.name as any}
              control={control}
              render={({ field: controllerField }) => (
                <Input
                  {...controllerField}
                  data-testid={`resource-modal-field-${field.name}-input`}
                  type={field.type || 'text'}
                  placeholder={field.placeholder}
                  disabled={field.disabled}
                  readOnly={field.readOnly}
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
      <div style={{ ...styles.flexColumn as React.CSSProperties, gap: spacing('SM'), height: '100%' }}>
        {/* Form Section */}
        <Form 
          data-testid="resource-modal-form"
          layout={formLayout}
          labelCol={labelCol}
          wrapperCol={wrapperCol}
          labelAlign="right"
          colon={true}
          style={{ flexShrink: 0 }}
        >
          <Row gutter={[spacing('SM'), spacing('SM')]} wrap>
            {fields.map((field) => {
              if (field.hidden) return null

              const fieldName = field.name
              const error = errors && typeof errors === 'object' && fieldName in errors 
                ? (errors as Record<string, any>)[fieldName] 
                : undefined

              const isTouched = Boolean(
                touchedFields &&
                typeof touchedFields === 'object' &&
                fieldName in touchedFields &&
                (touchedFields as Record<string, any>)[fieldName]
              )

              const showError = Boolean(error && (isTouched || submitCount > 0 || isSubmitted))

              const errorMessage = showError ? (error?.message as string) : undefined
              const labelNode = field.label

              return (
                <Col key={field.name} xs={24} lg={12}>
                  <Form.Item
                    label={labelNode}
                    required={field.required}
                    validateStatus={showError ? 'error' : undefined}
                    help={errorMessage || field.helperText}
                    data-testid={`resource-modal-field-${field.name}`}
                  >
                    {renderField(field)}
                  </Form.Item>
                </Col>
              )
            })}
          </Row>
        </Form>

        {/* Custom content before vault configuration */}
        {beforeVaultContent}

        {/* Divider */}
        <Divider style={{ margin: `${spacing('SM')}px 0` }}>{t('vaultEditor.vaultConfiguration')}</Divider>

        {/* Vault Editor Section */}
        <div data-testid="resource-modal-vault-editor-section" style={{ flexShrink: 0 }}>
          <VaultEditor
            entityType={entityType}
            initialData={initialVaultData}
            onChange={handleVaultChange}
            onValidate={handleVaultValidate}
            forceShowErrors={forceVaultErrors}
            teamName={teamName}
            bridgeName={bridgeName}
            onTestConnectionStateChange={onTestConnectionStateChange}
            isModalOpen={isModalOpen}
            isEditMode={isEditMode}
            uiMode={uiMode}
            onImportExport={(handlers) => {
              importExportHandlers.current = handlers
              // Pass handlers to parent if callback is provided
              if (onImportExportRef) {
                onImportExportRef(handlers)
              }
            }}
          />
        </div>

        {/* Custom content after vault configuration */}
        {afterVaultContent}

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
                <Tooltip title={t('vaultEditor.importJson')}>
                  <Button size="small" icon={<UploadOutlined />} aria-label={t('vaultEditor.importJson')} />
                </Tooltip>
              </Upload>
              <Tooltip title={t('vaultEditor.exportJson')}>
                <Button 
                  size="small"
                  icon={<DownloadOutlined />} 
                  onClick={() => {
                    if (importExportHandlers.current) {
                      importExportHandlers.current.handleExport()
                    }
                  }}
                  aria-label={t('vaultEditor.exportJson')}
                />
              </Tooltip>
            </Space>
          </div>
        )}

        {/* Validation Errors */}
        {showVaultValidationErrors && vaultValidationErrors.length > 0 && (
          <Alert
            message={t('vaultEditor.validationErrors')}
            description={
              <ul style={{ margin: 0, paddingLeft: spacing('LG') }}>
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
