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
  Row,
  Col,
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
import vaultDefinitions from '../../data/vaultDefinitions.json'
import { useAppSelector } from '@/store/store'

interface VaultEditorProps {
  entityType: string
  initialData?: Record<string, any>
  onChange?: (data: Record<string, any>, hasChanges: boolean) => void
  onValidate?: (isValid: boolean, errors?: string[]) => void
  onImportExport?: (handlers: { handleImport: (file: any) => boolean; handleExport: () => void }) => void
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
}) => {
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

  // Calculate extra fields not in schema
  useEffect(() => {
    if (!entityDef) return

    const schemaFields = Object.keys(entityDef.fields || {})
    const extras: Record<string, any> = {}

    Object.entries(importedData).forEach(([key, value]) => {
      if (!schemaFields.includes(key)) {
        extras[key] = value
      }
    })

    setExtraFields(extras)
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
      
      // Initialize raw JSON
      updateRawJson({ ...formData, ...extraFields })
    }
  }, [form, entityDef, importedData])

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
        message="Unknown Entity Type"
        description={`Entity type "${entityType}" is not defined in the vault definitions.`}
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
      setRawJsonError('Failed to serialize data to JSON')
    }
  }

  const handleFormChange = () => {
    const formData = form.getFieldsValue()
    const completeData = { ...formData, ...extraFields }
    
    // Update raw JSON view
    updateRawJson(completeData)
    
    // Check if there are any changes
    const hasChanges = JSON.stringify(completeData) !== JSON.stringify(initialData)
    
    onChange?.(completeData, hasChanges)

    // Validate
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
    
    try {
      const parsed = JSON.parse(value)
      setRawJsonError(null)
      
      // Update form with known fields
      const formData: Record<string, any> = {}
      const extras: Record<string, any> = {}
      
      Object.entries(parsed).forEach(([key, val]) => {
        if (entityDef.fields && key in entityDef.fields) {
          formData[key] = val
        } else {
          extras[key] = val
        }
      })
      
      form.setFieldsValue(formData)
      setExtraFields(extras)
      setImportedData(parsed)
      
      // Trigger change event
      const hasChanges = JSON.stringify(parsed) !== JSON.stringify(initialData)
      onChange?.(parsed, hasChanges)
      
      // Validate
      form.validateFields().catch(() => {})
    } catch (error) {
      setRawJsonError('Invalid JSON format')
    }
  }

  const handleImport = (file: UploadFile) => {
    const reader = new FileReader()
    reader.onload = (e) => {
      try {
        const data = JSON.parse(e.target?.result as string)
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
        console.error('Failed to parse JSON:', error)
      }
    }
    reader.readAsText(file as any)
    return false
  }

  const handleExport = () => {
    const formData = form.getFieldsValue()
    const exportData = { ...formData, ...extraFields }
    
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
    
    const rules: any[] = []
    
    if (required) {
      rules.push({ required: true, message: `${fieldName} is required` })
    }
    
    if (field.pattern) {
      rules.push({
        pattern: new RegExp(field.pattern),
        message: `Invalid format. ${field.description || ''}`,
      })
    }
    
    if (field.minLength !== undefined) {
      rules.push({ min: field.minLength, message: `Minimum length is ${field.minLength}` })
    }
    
    if (field.maxLength !== undefined) {
      rules.push({ max: field.maxLength, message: `Maximum length is ${field.maxLength}` })
    }
    
    if (field.minimum !== undefined) {
      rules.push({ 
        type: 'number', 
        min: field.minimum, 
        message: `Minimum value is ${field.minimum}` 
      })
    }
    
    if (field.maximum !== undefined) {
      rules.push({ 
        type: 'number', 
        max: field.maximum, 
        message: `Maximum value is ${field.maximum}` 
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
              {fieldName}
              {field.description && (
                <Tooltip title={field.description}>
                  <InfoCircleOutlined />
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
              {fieldName}
              {field.description && (
                <Tooltip title={field.description}>
                  <InfoCircleOutlined />
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
              {fieldName}
              {field.description && (
                <Tooltip title={field.description}>
                  <InfoCircleOutlined />
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
              {fieldName}
              {field.description && (
                <Tooltip title={field.description}>
                  <InfoCircleOutlined />
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
                  return Promise.reject('Must be valid JSON')
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
            placeholder={field.example ? `Example: ${JSON.stringify(field.example, null, 2)}` : 'Enter JSON object'}
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
              {fieldName}
              {field.description && (
                <Tooltip title={field.description}>
                  <InfoCircleOutlined />
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
                    return Promise.reject('Must be an array')
                  }
                  return Promise.resolve()
                } catch {
                  return Promise.reject('Must be valid JSON array')
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
            placeholder={field.example ? `Example: ${JSON.stringify(field.example, null, 2)}` : 'Enter JSON array'}
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
              {fieldName}
              {field.description && (
                <Tooltip title={field.description}>
                  <InfoCircleOutlined />
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
            placeholder="Port number (1-65535)"
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
            {fieldName}
            {field.description && (
              <Tooltip title={field.description}>
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
        message={entityDef.description}
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
      />

      <Form
        form={form}
        layout="vertical"
        onValuesChange={handleFormChange}
        autoComplete="off"
      >
        <Collapse 
          defaultActiveKey={[
            requiredFields.length > 0 ? 'required' : '',
            optionalFields.length > 0 ? 'optional' : '',
          ].filter(Boolean)}
        >
          <Collapse.Panel
            header={
              <Space>
                <strong>Required Fields</strong>
                <Tag color="red">{requiredFields.length}</Tag>
              </Space>
            }
            key="required"
          >
            <Row gutter={[16, 0]}>
              {requiredFields.map((fieldName) => {
                const field = fields[fieldName]
                if (!field) return null
                return (
                  <Col span={24} key={fieldName}>
                    {renderField(fieldName, field, true)}
                  </Col>
                )
              })}
            </Row>
          </Collapse.Panel>

          <Collapse.Panel
            header={
              <Space>
                <strong>Optional Fields</strong>
                <Tag>{optionalFields.length}</Tag>
              </Space>
            }
            key="optional"
          >
            <Row gutter={[16, 0]}>
              {optionalFields.map((fieldName) => {
                const field = fields[fieldName]
                if (!field) return null
                return (
                  <Col span={24} key={fieldName}>
                    {renderField(fieldName, field, false)}
                  </Col>
                )
              })}
            </Row>
          </Collapse.Panel>

          {Object.keys(extraFields).length > 0 && (
            <Collapse.Panel
              header={
                <Space>
                  <strong>Extra Fields (Not in Schema)</strong>
                  <Tag color="warning">{Object.keys(extraFields).length}</Tag>
                  <Tooltip title="These fields were imported but are not defined in the schema">
                    <WarningOutlined style={{ color: '#faad14' }} />
                  </Tooltip>
                </Space>
              }
              key="extra"
            >
              <Alert
                message="Warning"
                description="These fields are not defined in the schema and may be ignored by the system."
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
                  <strong>Raw JSON Editor (Expert Mode)</strong>
                  <Tag color="red">Advanced</Tag>
                  <Tooltip title="Direct JSON editing - Use with caution!">
                    <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />
                  </Tooltip>
                </Space>
              }
              key="rawjson"
            >
              <Alert
                message="Expert Mode Only"
                description="Direct JSON editing can break system functionality if not done correctly. Only modify if you understand the vault schema and implications."
                type="error"
                showIcon
                icon={<ExclamationCircleOutlined />}
                style={{ marginBottom: 16 }}
              />
              
              {rawJsonError && (
                <Alert
                  message="JSON Error"
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
              
              <Space style={{ marginTop: 16 }}>
                <Button
                  size="small"
                  onClick={() => {
                    try {
                      const formatted = JSON.stringify(JSON.parse(rawJsonValue), null, 2)
                      setRawJsonValue(formatted)
                      handleRawJsonChange(formatted)
                    } catch {
                      // Already showing error
                    }
                  }}
                >
                  Format JSON
                </Button>
                <Button
                  size="small"
                  danger
                  onClick={() => {
                    const currentData = { ...form.getFieldsValue(), ...extraFields }
                    updateRawJson(currentData)
                  }}
                >
                  Reset to Form Values
                </Button>
              </Space>
            </Collapse.Panel>
          )}
        </Collapse>
      </Form>
    </div>
  )
}

export default VaultEditor