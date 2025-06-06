import React, { useState, useEffect, useMemo } from 'react'
import {
  Form,
  Input,
  InputNumber,
  Select,
  Switch,
  Button,
  Space,
  Divider,
  Alert,
  Upload,
  Card,
  Collapse,
  Tag,
  Tooltip,
  message,
} from 'antd'
import {
  UploadOutlined,
  DownloadOutlined,
  InfoCircleOutlined,
  WarningOutlined,
  CodeOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons'
import Editor from '@monaco-editor/react'
import type { UploadFile } from 'antd/es/upload/interface'
import { useTranslation } from 'react-i18next'
import vaultDefinitions from '../../data/vaults.json'
import { useAppSelector } from '@/store/store'

interface VaultEditorProps {
  entityType: string
  initialData?: Record<string, any>
  onChange?: (data: Record<string, any>, hasChanges: boolean) => void
  onValidate?: (isValid: boolean, errors?: string[]) => void
  onImportExport?: (handlers: { handleImport: (file: any) => boolean; handleExport: () => void }) => void
  onFieldMovement?: (movedToExtra: string[], movedFromExtra: string[]) => void
}

interface FieldDefinition {
  type: string
  description?: string
  example?: string
  default?: any
  enum?: string[]
  pattern?: string
  format?: string
  sensitive?: boolean
  minLength?: number
  maxLength?: number
  minimum?: number
  maximum?: number
  properties?: Record<string, any>
  items?: any
}

const VaultEditor: React.FC<VaultEditorProps> = ({
  entityType,
  initialData = {},
  onChange,
  onValidate,
  onImportExport,
  onFieldMovement,
}) => {
  const { t } = useTranslation('common')
  const [form] = Form.useForm()
  const [extraFields, setExtraFields] = useState<Record<string, any>>({})
  const [importedData, setImportedData] = useState<Record<string, any>>(initialData)
  const [rawJsonValue, setRawJsonValue] = useState<string>('')
  const [rawJsonError, setRawJsonError] = useState<string | null>(null)
  
  const uiMode = useAppSelector((state) => state.ui.uiMode)

  // Get entity definition from JSON
  const entityDef = useMemo(() => {
    return vaultDefinitions.entities[entityType as keyof typeof vaultDefinitions.entities]
  }, [entityType])

  // Helper to merge common types with field definitions
  const getFieldDefinition = (field: FieldDefinition): FieldDefinition => {
    // Check if the field format matches a common type
    if (field.format && field.format in vaultDefinitions.commonTypes) {
      const commonType = vaultDefinitions.commonTypes[field.format as keyof typeof vaultDefinitions.commonTypes]
      // Merge common type with field definition, field definition takes precedence
      return { ...commonType, ...field }
    }
    
    // Check if the field type matches a common type name
    const commonTypeKey = Object.keys(vaultDefinitions.commonTypes).find(
      key => key === field.type || key === field.format
    )
    if (commonTypeKey) {
      const commonType = vaultDefinitions.commonTypes[commonTypeKey as keyof typeof vaultDefinitions.commonTypes]
      return { ...commonType, ...field }
    }
    
    return field
  }

  // Update importedData when initialData prop changes
  useEffect(() => {
    setImportedData(initialData)
  }, [initialData])

  // Calculate extra fields not in schema
  useEffect(() => {
    if (!entityDef) return

    const schemaFields = Object.keys(entityDef.fields || {})
    const extras: Record<string, any> = {}
    const movedToExtra: string[] = []
    const movedFromExtra: string[] = []

    // Check if importedData has extraFields structure
    if (importedData.extraFields && typeof importedData.extraFields === 'object') {
      Object.assign(extras, importedData.extraFields)
    }

    // Also check for non-schema fields at root level
    Object.entries(importedData).forEach(([key, value]) => {
      if (key !== 'extraFields' && !schemaFields.includes(key)) {
        extras[key] = value
        // Track fields that are being moved to extraFields
        if (!extraFields[key] && value !== undefined) {
          movedToExtra.push(key)
        }
      }
    })

    // Check if any fields were moved from extraFields back to regular fields
    Object.keys(extraFields).forEach(key => {
      if (!extras[key] && schemaFields.includes(key) && importedData[key] !== undefined) {
        movedFromExtra.push(key)
      }
    })

    setExtraFields(extras)

    // Notify about field movements
    if ((movedToExtra.length > 0 || movedFromExtra.length > 0) && onFieldMovement) {
      onFieldMovement(movedToExtra, movedFromExtra)
    }

    // Show toast messages for field movements
    if (movedToExtra.length > 0) {
      message.info(t('vaultEditor.fieldsMovedToExtra', { 
        count: movedToExtra.length,
        fields: movedToExtra.join(', ')
      }))
    }
    if (movedFromExtra.length > 0) {
      message.success(t('vaultEditor.fieldsMovedFromExtra', { 
        count: movedFromExtra.length,
        fields: movedFromExtra.join(', ')
      }))
    }
  }, [importedData, entityDef])

  // Initialize form with data
  useEffect(() => {
    if (entityDef && importedData) {
      const formData: Record<string, any> = {}
      Object.entries(entityDef.fields || {}).forEach(([key, field]) => {
        if (importedData[key] !== undefined) {
          formData[key] = importedData[key]
        } else if (field.default !== undefined) {
          formData[key] = field.default
        }
      })
      form.setFieldsValue(formData)
      
      // Build complete data structure for raw JSON
      const completeData = { ...formData }
      if (Object.keys(extraFields).length > 0) {
        completeData.extraFields = extraFields
      }
      
      // Initialize raw JSON with proper structure
      updateRawJson(completeData)
      
      // Validate initial data
      setTimeout(() => {
        form.validateFields()
          .then(() => onValidate?.(true))
          .catch((errorInfo) => {
            const errors = errorInfo.errorFields?.map((field: any) => 
              `${field.name.join('.')}: ${field.errors.join(', ')}`
            )
            onValidate?.(false, errors)
          })
      }, 0)
    }
  }, [form, entityDef, importedData, extraFields])

  // Pass import/export handlers to parent
  useEffect(() => {
    if (onImportExport) {
      onImportExport({
        handleImport,
        handleExport,
      })
    }
  }, [onImportExport])

  if (!entityDef) {
    return (
      <Alert
        message={t('vaultEditor.unknownEntityType')}
        description={t('vaultEditor.unknownEntityDescription', { type: entityType })}
        type="error"
        showIcon
      />
    )
  }

  // Update raw JSON when form data changes
  const updateRawJson = (data: Record<string, any>) => {
    try {
      setRawJsonValue(JSON.stringify(data, null, 2))
      setRawJsonError(null)
    } catch (error) {
      setRawJsonError(t('vaultEditor.failedToSerialize'))
    }
  }

  const handleFormChange = () => {
    const formData = form.getFieldsValue()
    
    // Build complete data with extraFields structure
    const completeData = { ...formData }
    if (Object.keys(extraFields).length > 0) {
      completeData.extraFields = extraFields
    }
    
    // Update raw JSON view
    updateRawJson(completeData)
    
    // Check if there are any changes
    const hasChanges = JSON.stringify(completeData) !== JSON.stringify(initialData)
    
    // Always call onChange first to update hasChanges state
    onChange?.(completeData, hasChanges)

    // Then validate
    form
      .validateFields()
      .then(() => {
        onValidate?.(true)
      })
      .catch((errorInfo) => {
        const errors = errorInfo.errorFields?.map((field: any) => 
          `${field.name.join('.')}: ${field.errors.join(', ')}`
        )
        onValidate?.(false, errors)
      })
  }

  const handleRawJsonChange = (value: string | undefined) => {
    if (!value) return
    
    // Update the raw JSON value immediately to preserve user input
    setRawJsonValue(value)
    
    try {
      const parsed = JSON.parse(value)
      setRawJsonError(null)
      
      // Update form with known fields
      const formData: Record<string, any> = {}
      const extras: Record<string, any> = {}
      const movedToExtra: string[] = []
      const movedFromExtra: string[] = []
      
      // First, check if there's an extraFields property
      if (parsed.extraFields && typeof parsed.extraFields === 'object') {
        Object.assign(extras, parsed.extraFields)
      }
      
      // Process all fields
      Object.entries(parsed).forEach(([key, val]) => {
        if (key === 'extraFields') {
          // Skip, already processed
        } else if (entityDef.fields && key in entityDef.fields) {
          formData[key] = val
          // Check if this field was previously in extraFields
          if (extraFields[key] !== undefined) {
            movedFromExtra.push(key)
          }
        } else {
          // Non-schema fields at root level also go to extras
          extras[key] = val
          // Check if this is a new field being moved to extraFields
          if (!extraFields[key] && val !== undefined) {
            movedToExtra.push(key)
          }
        }
      })
      
      // Check for fields that were in extraFields but are now removed
      Object.keys(extraFields).forEach(key => {
        if (!extras[key] && !formData[key]) {
          // Field was removed entirely, not moved
        }
      })
      
      form.setFieldsValue(formData)
      setExtraFields(extras)
      
      // Show toast messages for field movements
      if (movedToExtra.length > 0) {
        message.info(t('vaultEditor.fieldsMovedToExtra', { 
          count: movedToExtra.length,
          fields: movedToExtra.join(', ')
        }))
      }
      if (movedFromExtra.length > 0) {
        message.success(t('vaultEditor.fieldsMovedFromExtra', { 
          count: movedFromExtra.length,
          fields: movedFromExtra.join(', ')
        }))
      }
      
      // Build complete data structure for onChange
      const completeData = { ...formData }
      if (Object.keys(extras).length > 0) {
        completeData.extraFields = extras
      }
      
      setImportedData(completeData)
      
      // Trigger change event
      const hasChanges = JSON.stringify(completeData) !== JSON.stringify(initialData)
      onChange?.(completeData, hasChanges)
      
      // Validate
      form.validateFields()
        .then(() => onValidate?.(true))
        .catch((errorInfo) => {
          const errors = errorInfo.errorFields?.map((field: any) => 
            `${field.name.join('.')}: ${field.errors.join(', ')}`
          )
          onValidate?.(false, errors)
        })
    } catch (error) {
      setRawJsonError(t('vaultEditor.invalidJsonFormat'))
    }
  }

  const handleImport = (file: UploadFile) => {
    const reader = new FileReader()
    reader.onload = (e) => {
      try {
        const data = JSON.parse(e.target?.result as string)
        
        // Extract extra fields from imported data
        const extras: Record<string, any> = {}
        const schemaFields = Object.keys(entityDef.fields || {})
        
        // Check for extraFields structure
        if (data.extraFields && typeof data.extraFields === 'object') {
          Object.assign(extras, data.extraFields)
        }
        
        // Check for non-schema fields at root
        Object.entries(data).forEach(([key, value]) => {
          if (key !== 'extraFields' && !schemaFields.includes(key)) {
            extras[key] = value
          }
        })
        
        setExtraFields(extras)
        setImportedData(data)
        
        // Set form values for known fields
        const formData: Record<string, any> = {}
        Object.entries(entityDef.fields || {}).forEach(([key]) => {
          if (data[key] !== undefined) {
            formData[key] = data[key]
          }
        })
        form.setFieldsValue(formData)
        
        // Manually trigger change after import
        setTimeout(() => {
          handleFormChange()
        }, 0)
      } catch (error) {
        console.error(t('vaultEditor.failedToParseJson'), error)
      }
    }
    reader.readAsText(file as any)
    return false
  }

  const handleExport = () => {
    const formData = form.getFieldsValue()
    
    // Build export data with extraFields structure
    const exportData = { ...formData }
    if (Object.keys(extraFields).length > 0) {
      exportData.extraFields = extraFields
    }
    
    // Remove undefined values
    Object.keys(exportData).forEach(key => {
      if (exportData[key] === undefined) {
        delete exportData[key]
      }
    })

    const dataStr = JSON.stringify(exportData, null, 2)
    const dataBlob = new Blob([dataStr], { type: 'application/json' })
    const url = URL.createObjectURL(dataBlob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${entityType.toLowerCase()}_vault_${Date.now()}.json`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  const renderField = (fieldName: string, fieldDef: FieldDefinition, required: boolean) => {
    // Merge with common types if applicable
    const field = getFieldDefinition(fieldDef)
    
    // Get translated field label and description
    const fieldLabel = t(`vaultEditor.fields.${entityType}.${fieldName}.label`, { defaultValue: fieldName })
    const fieldDescription = t(`vaultEditor.fields.${entityType}.${fieldName}.description`)
    
    const rules: any[] = []
    
    if (required) {
      rules.push({ required: true, message: t('vaultEditor.isRequired', { field: fieldLabel }) })
    }
    
    if (field.pattern) {
      rules.push({
        pattern: new RegExp(field.pattern),
        message: t('vaultEditor.invalidFormat', { description: fieldDescription || '' }),
      })
    }
    
    if (field.minLength !== undefined) {
      rules.push({ min: field.minLength, message: t('vaultEditor.minLength', { length: field.minLength }) })
    }
    
    if (field.maxLength !== undefined) {
      rules.push({ max: field.maxLength, message: t('vaultEditor.maxLength', { length: field.maxLength }) })
    }
    
    if (field.minimum !== undefined) {
      rules.push({ 
        type: 'number', 
        min: field.minimum, 
        message: t('vaultEditor.minValue', { value: field.minimum }) 
      })
    }
    
    if (field.maximum !== undefined) {
      rules.push({ 
        type: 'number', 
        max: field.maximum, 
        message: t('vaultEditor.maxValue', { value: field.maximum }) 
      })
    }

    const commonProps = {
      placeholder: field.example,
      style: { width: '100%' },
    }

    // Render based on type
    if (field.type === 'boolean') {
      return (
        <Form.Item
          name={fieldName}
          label={
            <Space>
              {fieldLabel}
              {fieldDescription && (
                <Tooltip title={fieldDescription}>
                  <InfoCircleOutlined style={{ fontSize: 12 }} />
                </Tooltip>
              )}
            </Space>
          }
          valuePropName="checked"
          initialValue={field.default}
        >
          <Switch />
        </Form.Item>
      )
    }

    if (field.enum) {
      return (
        <Form.Item
          name={fieldName}
          label={
            <Space>
              {fieldLabel}
              {fieldDescription && (
                <Tooltip title={fieldDescription}>
                  <InfoCircleOutlined style={{ fontSize: 12 }} />
                </Tooltip>
              )}
            </Space>
          }
          rules={rules}
          initialValue={field.default}
        >
          <Select {...commonProps}>
            {field.enum.map((option) => (
              <Select.Option key={option} value={option}>
                {option}
              </Select.Option>
            ))}
          </Select>
        </Form.Item>
      )
    }

    if (field.type === 'number') {
      return (
        <Form.Item
          name={fieldName}
          label={
            <Space>
              {fieldLabel}
              {fieldDescription && (
                <Tooltip title={fieldDescription}>
                  <InfoCircleOutlined style={{ fontSize: 12 }} />
                </Tooltip>
              )}
            </Space>
          }
          rules={rules}
          initialValue={field.default}
        >
          <InputNumber
            {...commonProps}
            min={field.minimum}
            max={field.maximum}
          />
        </Form.Item>
      )
    }

    if (field.type === 'object') {
      // For complex objects, use a text area with JSON
      return (
        <Form.Item
          name={fieldName}
          label={
            <Space>
              {fieldLabel}
              {fieldDescription && (
                <Tooltip title={fieldDescription}>
                  <InfoCircleOutlined style={{ fontSize: 12 }} />
                </Tooltip>
              )}
            </Space>
          }
          rules={[
            ...rules,
            {
              validator: (_, value) => {
                if (!value) return Promise.resolve()
                try {
                  if (typeof value === 'string') {
                    JSON.parse(value)
                  }
                  return Promise.resolve()
                } catch {
                  return Promise.reject(t('vaultEditor.mustBeValidJson'))
                }
              },
            },
          ]}
          getValueFromEvent={(e) => {
            const value = e.target.value
            try {
              return value ? JSON.parse(value) : undefined
            } catch {
              return value
            }
          }}
          getValueProps={(value) => ({
            value: typeof value === 'object' ? JSON.stringify(value, null, 2) : value,
          })}
        >
          <Input.TextArea
            {...commonProps}
            rows={4}
            placeholder={field.example ? `${t('vaultEditor.example')} ${JSON.stringify(field.example, null, 2)}` : t('vaultEditor.enterJsonObject')}
          />
        </Form.Item>
      )
    }

    if (field.type === 'array') {
      // For arrays, use a text area with JSON
      return (
        <Form.Item
          name={fieldName}
          label={
            <Space>
              {fieldLabel}
              {fieldDescription && (
                <Tooltip title={fieldDescription}>
                  <InfoCircleOutlined style={{ fontSize: 12 }} />
                </Tooltip>
              )}
            </Space>
          }
          rules={[
            ...rules,
            {
              validator: (_, value) => {
                if (!value) return Promise.resolve()
                try {
                  const parsed = typeof value === 'string' ? JSON.parse(value) : value
                  if (!Array.isArray(parsed)) {
                    return Promise.reject(t('vaultEditor.mustBeArray'))
                  }
                  return Promise.resolve()
                } catch {
                  return Promise.reject(t('vaultEditor.mustBeValidJsonArray'))
                }
              },
            },
          ]}
          getValueFromEvent={(e) => {
            const value = e.target.value
            try {
              return value ? JSON.parse(value) : undefined
            } catch {
              return value
            }
          }}
          getValueProps={(value) => ({
            value: Array.isArray(value) ? JSON.stringify(value, null, 2) : value,
          })}
        >
          <Input.TextArea
            {...commonProps}
            rows={4}
            placeholder={field.example ? `${t('vaultEditor.example')} ${JSON.stringify(field.example, null, 2)}` : t('vaultEditor.enterJsonArray')}
          />
        </Form.Item>
      )
    }

    // Special handling for port type
    if (fieldName === 'port' || field.format === 'port') {
      return (
        <Form.Item
          name={fieldName}
          label={
            <Space>
              {fieldLabel}
              {fieldDescription && (
                <Tooltip title={fieldDescription}>
                  <InfoCircleOutlined style={{ fontSize: 12 }} />
                </Tooltip>
              )}
            </Space>
          }
          rules={rules}
          initialValue={field.default}
        >
          <InputNumber
            {...commonProps}
            min={1}
            max={65535}
            placeholder={t('vaultEditor.portPlaceholder')}
          />
        </Form.Item>
      )
    }

    // Default to text input
    return (
      <Form.Item
        name={fieldName}
        label={
          <Space>
            {fieldLabel}
            {fieldDescription && (
              <Tooltip title={fieldDescription}>
                <InfoCircleOutlined />
              </Tooltip>
            )}
          </Space>
        }
        rules={rules}
        initialValue={field.default}
      >
        <Input
          {...commonProps}
          type={field.sensitive ? 'password' : 'text'}
        />
      </Form.Item>
    )
  }

  const requiredFields = entityDef.required || []
  const optionalFields = entityDef.optional || []
  const fields = entityDef.fields || {}

  return (
    <div>
      <Alert
        message={t(entityDef.descriptionKey)}
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
      />

      <Form
        form={form}
        layout="horizontal"
        labelCol={{ span: 8 }}
        wrapperCol={{ span: 16 }}
        labelAlign="left"
        colon={true}
        onValuesChange={handleFormChange}
        autoComplete="off"
      >
        <Collapse 
          defaultActiveKey={[
            requiredFields.length > 0 ? 'required' : '',
            optionalFields.length > 0 ? 'optional' : '',
          ].filter(Boolean)}
        >
          {requiredFields.length > 0 && (
            <Collapse.Panel
              header={
                <Space>
                  <strong>{t('vaultEditor.requiredFields')}</strong>
                  <Tag color="red">{requiredFields.length}</Tag>
                </Space>
              }
              key="required"
            >
              {requiredFields.map((fieldName) => {
                const field = fields[fieldName as keyof typeof fields]
                if (!field) return null
                return renderField(fieldName, field as FieldDefinition, true)
              })}
            </Collapse.Panel>
          )}

          {optionalFields.length > 0 && (
            <Collapse.Panel
              header={
                <Space>
                  <strong>{t('vaultEditor.optionalFields')}</strong>
                  <Tag>{optionalFields.length}</Tag>
                </Space>
              }
              key="optional"
            >
              {optionalFields.map((fieldName) => {
                const field = fields[fieldName as keyof typeof fields]
                if (!field) return null
                return renderField(fieldName, field as FieldDefinition, false)
              })}
            </Collapse.Panel>
          )}

          {Object.keys(extraFields).length > 0 && (
            <Collapse.Panel
              header={
                <Space>
                  <strong>{t('vaultEditor.extraFields')}</strong>
                  <Tag color="warning">{Object.keys(extraFields).length}</Tag>
                  <Tooltip title={t('vaultEditor.extraFieldsTooltip')}>
                    <WarningOutlined style={{ color: '#faad14' }} />
                  </Tooltip>
                </Space>
              }
              key="extra"
            >
              <Alert
                message={t('vaultEditor.extraFieldsWarning')}
                description={t('vaultEditor.extraFieldsWarningDescription')}
                type="warning"
                showIcon
                style={{ marginBottom: 16 }}
              />
              <Card size="small">
                <pre style={{ margin: 0, overflow: 'auto' }}>
                  {JSON.stringify(extraFields, null, 2)}
                </pre>
              </Card>
            </Collapse.Panel>
          )}

          {uiMode === 'expert' && (
            <Collapse.Panel
              header={
                <Space>
                  <CodeOutlined />
                  <strong>{t('vaultEditor.rawJsonEditor')}</strong>
                  <Tag color="red">{t('vaultEditor.advanced')}</Tag>
                  <Tooltip title={t('vaultEditor.rawJsonTooltip')}>
                    <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />
                  </Tooltip>
                </Space>
              }
              key="rawjson"
            >
              <Alert
                message={t('vaultEditor.expertModeOnly')}
                description={t('vaultEditor.expertModeDescription')}
                type="error"
                showIcon
                icon={<ExclamationCircleOutlined />}
                style={{ marginBottom: 16 }}
              />
              
              {rawJsonError && (
                <Alert
                  message={t('vaultEditor.jsonError')}
                  description={rawJsonError}
                  type="error"
                  showIcon
                  style={{ marginBottom: 16 }}
                />
              )}
              
              <div style={{ border: '1px solid #d9d9d9', borderRadius: 4 }}>
                <Editor
                  height="400px"
                  defaultLanguage="json"
                  value={rawJsonValue}
                  onChange={handleRawJsonChange}
                  theme="vs-light"
                  options={{
                    minimap: { enabled: false },
                    fontSize: 14,
                    formatOnPaste: true,
                    formatOnType: true,
                    automaticLayout: true,
                  }}
                />
              </div>
            </Collapse.Panel>
          )}
        </Collapse>
      </Form>
    </div>
  )
}

export default VaultEditor