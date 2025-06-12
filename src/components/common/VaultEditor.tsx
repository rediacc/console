import React, { useState, useEffect, useMemo } from 'react'
import {
  Form,
  Input,
  InputNumber,
  Select,
  Switch,
  Space,
  Alert,
  Card,
  Collapse,
  Tag,
  Tooltip,
  message,
  Divider,
  Typography,
} from 'antd'
import {
  InfoCircleOutlined,
  WarningOutlined,
  CodeOutlined,
  ExclamationCircleOutlined,
  QuestionCircleOutlined,
  BulbOutlined,
} from '@ant-design/icons'
import Editor from '@monaco-editor/react'
import type { UploadFile } from 'antd/es/upload/interface'
import { useTranslation } from 'react-i18next'
import vaultDefinitions from '../../data/vaults.json'
import storageProviders from '../../data/storageProviders.json'
import { useAppSelector } from '@/store/store'
import FieldGenerator from './FieldGenerator'
import { useTheme } from '@/context/ThemeContext'

const { Text } = Typography

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
  const { t } = useTranslation(['common', 'storageProviders'])
  const [form] = Form.useForm()
  const [extraFields, setExtraFields] = useState<Record<string, any>>({})
  const [importedData, setImportedData] = useState<Record<string, any>>(initialData)
  const [rawJsonValue, setRawJsonValue] = useState<string>('')
  const [rawJsonError, setRawJsonError] = useState<string | null>(null)
  const [sshKeyConfigured, setSshKeyConfigured] = useState(false)
  const [selectedProvider, setSelectedProvider] = useState<string | null>(null)
  
  const uiMode = useAppSelector((state) => state.ui.uiMode)
  const { theme } = useTheme()

  // Get entity definition from JSON
  const entityDef = useMemo(() => {
    return vaultDefinitions.entities[entityType as keyof typeof vaultDefinitions.entities]
  }, [entityType])

  // Get provider-specific fields for STORAGE entity
  const providerFields = useMemo(() => {
    if (entityType === 'STORAGE' && selectedProvider && storageProviders.providers[selectedProvider]) {
      return storageProviders.providers[selectedProvider]
    }
    return null
  }, [entityType, selectedProvider])

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
      
      // Initialize ssh_key_configured state for MACHINE and BRIDGE entities
      if ((entityType === 'MACHINE' || entityType === 'BRIDGE') && formData.ssh_key_configured !== undefined) {
        setSshKeyConfigured(formData.ssh_key_configured)
      }
      
      // Initialize provider for STORAGE entity
      if (entityType === 'STORAGE' && formData.provider) {
        setSelectedProvider(formData.provider)
      }
      
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

  const handleFormChange = (changedValues?: any) => {
    const formData = form.getFieldsValue()
    
    // Handle ssh_key_configured changes
    if ((entityType === 'MACHINE' || entityType === 'BRIDGE') && changedValues?.ssh_key_configured !== undefined) {
      setSshKeyConfigured(changedValues.ssh_key_configured)
      
      // If SSH key is configured, clear the password field
      if (changedValues.ssh_key_configured) {
        form.setFieldValue('ssh_password', undefined)
        formData.ssh_password = undefined
      }
    }
    
    // Handle provider changes for STORAGE entity
    if (entityType === 'STORAGE' && changedValues?.provider !== undefined) {
      setSelectedProvider(changedValues.provider)
      
      // Clear provider-specific fields when provider changes
      if (providerFields) {
        const fieldsToKeep = ['name', 'provider', 'description', 'noVersioning', 'parameters']
        const currentValues = form.getFieldsValue()
        const newValues: Record<string, any> = {}
        
        // Keep only base fields
        fieldsToKeep.forEach(field => {
          if (currentValues[field] !== undefined) {
            newValues[field] = currentValues[field]
          }
        })
        
        form.setFieldsValue(newValues)
      }
    }
    
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

  const renderField = (fieldName: string, fieldDef: FieldDefinition, required: boolean, isProviderField: boolean = false) => {
    // Special handling for ssh_password field - hide if SSH key is configured
    if ((entityType === 'MACHINE' || entityType === 'BRIDGE') && fieldName === 'ssh_password' && sshKeyConfigured) {
      return null
    }
    
    // Merge with common types if applicable
    const field = getFieldDefinition(fieldDef)
    
    // Get translated field label and description
    let fieldLabel: string
    let fieldDescription: string | undefined
    let fieldPlaceholder: string | undefined
    let fieldHelpText: string | undefined
    
    if (entityType === 'STORAGE' && isProviderField && selectedProvider) {
      // Use storage provider translations
      fieldLabel = t(`storageProviders:storageProviders.${selectedProvider}.fields.${fieldName}.label`, { defaultValue: fieldName })
      fieldPlaceholder = t(`storageProviders:storageProviders.${selectedProvider}.fields.${fieldName}.placeholder`, { defaultValue: field.example })
      fieldHelpText = t(`storageProviders:storageProviders.${selectedProvider}.fields.${fieldName}.helpText`, { defaultValue: field.description })
      fieldDescription = fieldHelpText
    } else {
      // Use regular vault editor translations
      fieldLabel = t(`vaultEditor.fields.${entityType}.${fieldName}.label`, { defaultValue: fieldName })
      fieldDescription = t(`vaultEditor.fields.${entityType}.${fieldName}.description`)
      fieldPlaceholder = field.example
    }
    
    const rules: any[] = []
    
    // Special validation for ssh_password - required only if SSH key not configured
    if ((entityType === 'MACHINE' || entityType === 'BRIDGE') && fieldName === 'ssh_password') {
      if (!sshKeyConfigured && required) {
        rules.push({ 
          required: true, 
          message: t('vaultEditor.sshPasswordRequiredWhenNoKey', { defaultValue: 'SSH password is required when SSH key is not configured' }) 
        })
      }
    } else if (required) {
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
      placeholder: fieldPlaceholder,
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
          <Switch 
            onChange={(checked) => {
              // Special handling for ssh_key_configured
              if (fieldName === 'ssh_key_configured') {
                handleFormChange({ ssh_key_configured: checked })
              }
            }}
          />
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

    // Check if this field can be generated
    const isGeneratable = 
      (fieldName === 'SSH_PRIVATE_KEY' || fieldName === 'SSH_PUBLIC_KEY') ||
      (fieldName === 'credential' && entityType === 'REPOSITORY')

    const handleFieldGeneration = (values: Record<string, string>) => {
      // For SSH keys, we need to update both private and public keys
      if (fieldName === 'SSH_PRIVATE_KEY' || fieldName === 'SSH_PUBLIC_KEY') {
        const currentValues = form.getFieldsValue()
        form.setFieldsValue({
          ...currentValues,
          SSH_PRIVATE_KEY: values.SSH_PRIVATE_KEY,
          SSH_PUBLIC_KEY: values.SSH_PUBLIC_KEY
        })
      } else {
        // For single field generation
        form.setFieldValue(fieldName, values[fieldName])
      }
      // Trigger validation and change event
      handleFormChange()
      // Force form to re-render
      form.validateFields([fieldName])
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
          addonAfter={isGeneratable ? (
            <FieldGenerator
              fieldName={fieldName}
              fieldType={
                fieldName === 'credential' ? 'repository_credential' : 'ssh_keys'
              }
              onGenerate={handleFieldGeneration}
              entityType={entityType}
            />
          ) : undefined}
        />
      </Form.Item>
    )
  }

  const requiredFields = entityDef.required || []
  const optionalFields = entityDef.optional || []
  const fields = entityDef.fields || {}

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Alert
        message={t(`vaultEditor.${entityDef.descriptionKey}`)}
        type="info"
        showIcon
        style={{ marginBottom: 12, flexShrink: 0 }}
      />

      <Form
        form={form}
        layout="horizontal"
        labelCol={{ span: 6 }}
        wrapperCol={{ span: 18 }}
        labelAlign="right"
        colon={true}
        onValuesChange={(changedValues) => handleFormChange(changedValues)}
        autoComplete="off"
        style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}
      >
        <Collapse 
          defaultActiveKey={[
            requiredFields.length > 0 ? 'required' : '',
            optionalFields.length > 0 ? 'optional' : '',
            (entityType === 'STORAGE' && selectedProvider && providerFields) ? 'provider' : '',
          ].filter(Boolean)}
          style={{ flex: 1 }}
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

          {/* Provider-specific fields for STORAGE entity */}
          {entityType === 'STORAGE' && selectedProvider && providerFields && (
            <Collapse.Panel
              header={
                <Space>
                  <strong>{t('vaultEditor.providerFields', { provider: providerFields.name })}</strong>
                  <Tag color="blue">
                    {(providerFields.required?.length || 0) + (providerFields.optional?.length || 0)}
                  </Tag>
                </Space>
              }
              key="provider"
            >
              {/* Provider help text */}
              <Alert
                message={providerFields.name}
                description={t(`storageProviders:storageProviders.${selectedProvider}.helpText`, { 
                  defaultValue: providerFields.description 
                })}
                type="info"
                showIcon
                icon={<QuestionCircleOutlined />}
                style={{ marginBottom: 16 }}
              />
              
              {/* Required provider fields */}
              {providerFields.required && providerFields.required.length > 0 && (
                <>
                  {providerFields.required.map((fieldName: string) => {
                    const field = providerFields.fields?.[fieldName]
                    if (!field) return null
                    return renderField(fieldName, field as FieldDefinition, true, true)
                  })}
                </>
              )}
              
              {/* Optional provider fields */}
              {providerFields.optional && providerFields.optional.length > 0 && (
                <>
                  {providerFields.required && providerFields.required.length > 0 && <div style={{ marginTop: 24 }} />}
                  {providerFields.optional.map((fieldName: string) => {
                    const field = providerFields.fields?.[fieldName]
                    if (!field) return null
                    return renderField(fieldName, field as FieldDefinition, false, true)
                  })}
                </>
              )}
              
              {/* Provider-specific tips */}
              <Divider orientation="left">
                <Space>
                  <BulbOutlined style={{ color: '#faad14' }} />
                  <Text strong>{t('storageProviders:common.tips', { defaultValue: 'Tips' })}</Text>
                </Space>
              </Divider>
              <Alert
                message={
                  <Space direction="vertical" style={{ width: '100%' }}>
                    {[1, 2, 3, 4].map((index) => {
                      const tip = t(`storageProviders:storageProviders.${selectedProvider}.tips.${index - 1}`, { defaultValue: '' })
                      return tip ? (
                        <div key={index}>
                          <Text>• {tip}</Text>
                        </div>
                      ) : null
                    }).filter(Boolean)}
                  </Space>
                }
                type="info"
                showIcon
                icon={<InfoCircleOutlined />}
                style={{ marginTop: 16 }}
              />
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
              
              <div style={{ 
                border: `1px solid ${theme === 'dark' ? 'var(--color-border-primary)' : '#d9d9d9'}`, 
                borderRadius: 4 
              }}>
                <Editor
                  height="auto"
                  defaultLanguage="json"
                  value={rawJsonValue}
                  onChange={handleRawJsonChange}
                  theme={theme === 'dark' ? 'vs-dark' : 'vs-light'}
                  options={{
                    minimap: { enabled: false },
                    fontSize: 14,
                    formatOnPaste: true,
                    formatOnType: true,
                    automaticLayout: true,
                    scrollBeyondLastLine: false,
                    scrollbar: {
                      vertical: 'hidden',
                      horizontal: 'hidden',
                      handleMouseWheel: false,
                    },
                    wordWrap: 'on',
                    lineNumbers: 'on',
                    glyphMargin: false,
                    folding: false,
                    lineDecorationsWidth: 0,
                    lineNumbersMinChars: 3,
                  }}
                  onMount={(editor) => {
                    // Auto-resize based on content
                    const updateHeight = () => {
                      const contentHeight = Math.min(1000, Math.max(100, editor.getContentHeight()))
                      editor.layout({ width: editor.getLayoutInfo().width, height: contentHeight })
                    }
                    editor.onDidContentSizeChange(updateHeight)
                    updateHeight()
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