import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react'
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
  Button,
  Segmented,
} from 'antd'
import {
  InfoCircleOutlined,
  WarningOutlined,
  CodeOutlined,
  ExclamationCircleOutlined,
  QuestionCircleOutlined,
  BulbOutlined,
  CheckCircleOutlined,
  WifiOutlined,
} from '@/utils/optimizedIcons'
import { SimpleJsonEditor } from './SimpleJsonEditor'
import { NestedObjectEditor } from './NestedObjectEditor'
import type { UploadFile } from 'antd/es/upload/interface'
import { useTranslation } from 'react-i18next'
import vaultDefinitions from '../../data/vaults.json'
import storageProviders from '../../data/storageProviders.json'
import FieldGenerator from './FieldGenerator'
import { useCreateQueueItem, useQueueItemTrace } from '@/api/queries/queue'
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder'
import { useTeams } from '@/api/queries/teams'
import { useComponentStyles } from '@/hooks/useComponentStyles'
import { DESIGN_TOKENS, spacing, borderRadius, fontSize } from '@/utils/styleConstants'
import { featureFlags } from '@/config/featureFlags'

const { Text } = Typography

interface VaultEditorProps {
  entityType: string
  initialData?: Record<string, any>
  onChange?: (data: Record<string, any>, hasChanges: boolean) => void
  onValidate?: (isValid: boolean, errors?: string[]) => void
  onImportExport?: (handlers: { handleImport: (file: any) => boolean; handleExport: () => void }) => void
  onFieldMovement?: (movedToExtra: string[], movedFromExtra: string[]) => void
  teamName?: string // For SSH test connection
  bridgeName?: string // For SSH test connection
  onTestConnectionStateChange?: (success: boolean) => void // Callback for test connection state
  onOsSetupStatusChange?: (completed: boolean | null) => void // Callback for OS setup status
  isModalOpen?: boolean // Modal open state to handle resets
  isEditMode?: boolean // Whether we're in edit mode
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
  additionalProperties?: any
}

// Helper components for reduced repetition
const FieldLabel: React.FC<{ label: string; description?: string }> = ({ label, description }) => (
  <Space>
    {label}
    {description && (
      <Tooltip title={description}>
        <InfoCircleOutlined style={{ fontSize: 12 }} />
      </Tooltip>
    )}
  </Space>
)

const FieldFormItem: React.FC<{
  name: string;
  label: string;
  description?: string;
  rules?: any[];
  initialValue?: any;
  valuePropName?: string;
  children: React.ReactNode;
}> = ({ name, label, description, rules, initialValue, valuePropName, children }) => (
  <Form.Item
    name={name}
    label={<FieldLabel label={label} description={description} />}
    rules={rules}
    initialValue={initialValue}
    valuePropName={valuePropName}
  >
    {children}
  </Form.Item>
)

const VaultEditor: React.FC<VaultEditorProps> = ({
  entityType,
  initialData = {},
  onChange,
  onValidate,
  onImportExport,
  onFieldMovement,
  teamName = 'Default Team',
  bridgeName = 'Default Bridge',
  onTestConnectionStateChange,
  onOsSetupStatusChange,
  isModalOpen,
  isEditMode = false,
}) => {
  const { t } = useTranslation(['common', 'storageProviders'])
  const [form] = Form.useForm()
  const [extraFields, setExtraFields] = useState<Record<string, any>>({})
  const [importedData, setImportedData] = useState<Record<string, any>>(initialData)
  const [rawJsonValue, setRawJsonValue] = useState<string>(() => {
    return Object.keys(initialData).length > 0 ? JSON.stringify(initialData, null, 2) : '{}'
  })
  const [rawJsonError, setRawJsonError] = useState<string | null>(null)
  const [sshKeyConfigured, setSshKeyConfigured] = useState(false)
  const [selectedProvider, setSelectedProvider] = useState<string | null>(null)
  const [lastInitializedData, setLastInitializedData] = useState<string>('')
  const [testTaskId, setTestTaskId] = useState<string | null>(null)
  const [isTestingConnection, setIsTestingConnection] = useState(false)
  const [testConnectionSuccess, setTestConnectionSuccess] = useState(false)
  const [osSetupCompleted, setOsSetupCompleted] = useState<boolean | null>(null)
  const formatJsonRef = useRef<(() => void) | null>(null)

  const styles = useComponentStyles()
  
  // Queue vault builder
  const { buildQueueVault } = useQueueVaultBuilder()
  
  // Create queue item mutation for SSH test
  const { mutate: createQueueItem, isPending: isCreatingQueueItem } = useCreateQueueItem()
  
  // Poll for SSH test results
  const { data: testTraceData } = useQueueItemTrace(testTaskId, isTestingConnection)
  
  // Get teams data for SSH keys
  const { data: teams } = useTeams()
  
  // Direct onChange callback - no debouncing to avoid race conditions
  const directOnChange = useCallback((data: Record<string, any>, hasChanges: boolean) => {
    onChange?.(data, hasChanges)
  }, [onChange])

  // Track previous modal open state
  const prevModalOpenRef = useRef(isModalOpen)
  
  // Reset when modal opens (transitions from closed to open)
  useEffect(() => {
    if (isModalOpen && !prevModalOpenRef.current) {
      // Modal just opened - reset everything
      setLastInitializedData('')
      form.resetFields()
      setExtraFields({})
      setImportedData({})
      setRawJsonValue('{}')
      setRawJsonError(null)
      setSshKeyConfigured(false)
      setSelectedProvider(null)
      setTestConnectionSuccess(false)
    }
    prevModalOpenRef.current = isModalOpen
  }, [isModalOpen, form])

  // Get entity definition from JSON
  const entityDef = useMemo(() => {
    return vaultDefinitions.entities[entityType as keyof typeof vaultDefinitions.entities]
  }, [entityType])

  // Get provider-specific fields for STORAGE entity
  const providerFields = useMemo(() => {
    if (entityType === 'STORAGE' && selectedProvider && selectedProvider in storageProviders.providers) {
      return storageProviders.providers[selectedProvider as keyof typeof storageProviders.providers]
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
  
  // Helper to process extra fields
  const processExtraFields = (data: Record<string, any>, schemaFields: string[]) => {
    const extras: Record<string, any> = {}
    const movedToExtra: string[] = []
    const movedFromExtra: string[] = []
    
    // Check if data has extraFields structure
    if (data.extraFields && typeof data.extraFields === 'object') {
      Object.assign(extras, data.extraFields)
    }
    
    // Check for non-schema fields at root level
    Object.entries(data).forEach(([key, value]) => {
      if (key !== 'extraFields' && !schemaFields.includes(key)) {
        extras[key] = value
        if (!extraFields[key] && value !== undefined) {
          movedToExtra.push(key)
        }
      }
    })
    
    // Check if any fields were moved from extraFields back to regular fields
    Object.keys(extraFields).forEach(key => {
      if (!extras[key] && schemaFields.includes(key) && data[key] !== undefined) {
        movedFromExtra.push(key)
      }
    })
    
    return { extras, movedToExtra, movedFromExtra }
  }
  
  // Helper to show field movement toast messages
  const showFieldMovementToasts = (movedToExtra: string[], movedFromExtra: string[]) => {
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
  }
  
  // Helper to build validation rules
  const buildValidationRules = (field: FieldDefinition, required: boolean, fieldLabel: string) => {
    const rules: any[] = []
    
    if (required) {
      rules.push({ required: true, message: t('vaultEditor.isRequired', { field: fieldLabel }) })
    }
    
    const ruleBuilders = {
      pattern: (value: string) => ({
        pattern: new RegExp(value),
        message: t('vaultEditor.invalidFormat', { description: field.description || '' })
      }),
      minLength: (value: number) => ({ min: value, message: t('vaultEditor.minLength', { length: value }) }),
      maxLength: (value: number) => ({ max: value, message: t('vaultEditor.maxLength', { length: value }) }),
      minimum: (value: number) => ({ type: 'number' as const, min: value, message: t('vaultEditor.minValue', { value }) }),
      maximum: (value: number) => ({ type: 'number' as const, max: value, message: t('vaultEditor.maxValue', { value }) })
    }
    
    Object.entries(ruleBuilders).forEach(([key, ruleFn]) => {
      const fieldKey = key as keyof typeof ruleBuilders
      if (fieldKey in field && field[fieldKey as keyof FieldDefinition] !== undefined) {
        rules.push(ruleFn(field[fieldKey as keyof FieldDefinition] as never))
      }
    })
    
    return rules
  }
  
  // Helper for JSON field validation and handling
  const getJsonFieldProps = (isArray = false) => {
    const validator = (_: any, value: any) => {
      if (!value) return Promise.resolve()
      try {
        const parsed = typeof value === 'string' ? JSON.parse(value) : value
        if (isArray && !Array.isArray(parsed)) {
          return Promise.reject(t('vaultEditor.mustBeArray'))
        }
        return Promise.resolve()
      } catch {
        return Promise.reject(t(isArray ? 'vaultEditor.mustBeValidJsonArray' : 'vaultEditor.mustBeValidJson'))
      }
    }
    
    const getValueFromEvent = (e: any) => {
      const value = e.target.value
      try {
        return value ? JSON.parse(value) : undefined
      } catch {
        return value
      }
    }
    
    const getValueProps = (value: any) => ({
      value: (isArray ? Array.isArray(value) : typeof value === 'object') 
        ? JSON.stringify(value, null, 2) 
        : value
    })
    
    return { validator, getValueFromEvent, getValueProps }
  }

  // Update importedData when initialData prop changes
  useEffect(() => {
    setImportedData(initialData)
  }, [initialData])

  // Monitor SSH test results
  useEffect(() => {
    if (testTraceData?.queueDetails && testTraceData?.responseVaultContent?.vaultContent) {
      const status = testTraceData.queueDetails.status || testTraceData.queueDetails.Status
      
      if (status === 'COMPLETED') {
        try {
          // Parse the response vault content
          const responseVault = typeof testTraceData.responseVaultContent.vaultContent === 'string' 
            ? JSON.parse(testTraceData.responseVaultContent.vaultContent)
            : testTraceData.responseVaultContent.vaultContent
          
          // Extract the result
          const result = responseVault.result ? JSON.parse(responseVault.result) : null
          
          if (result) {
            if (result.status === 'success') {
              message.success(t('vaultEditor.testConnection.success'))
              
              // Update form fields with test results
              if (result.ssh_key_configured !== undefined) {
                form.setFieldValue('ssh_key_configured', result.ssh_key_configured)
                setSshKeyConfigured(result.ssh_key_configured)
              }
              
              if (result.host_entry) {
                form.setFieldValue('host_entry', result.host_entry)
              }
              
              // Store kernel compatibility data if available
              if (result.kernel_compatibility) {
                form.setFieldValue('kernel_compatibility', result.kernel_compatibility)
              }

              // Store OS setup status if available (now part of kernel compatibility data)
              if (result.kernel_compatibility && result.kernel_compatibility.os_setup_completed !== undefined) {
                setOsSetupCompleted(result.kernel_compatibility.os_setup_completed)
                if (onOsSetupStatusChange) {
                  onOsSetupStatusChange(result.kernel_compatibility.os_setup_completed)
                }
              }

              // Clear SSH password after successful test
              form.setFieldValue('ssh_password', '')

              // Mark test connection as successful
              setTestConnectionSuccess(true)
              
              // Notify parent component
              if (onTestConnectionStateChange) {
                onTestConnectionStateChange(true)
              }
              
              // Trigger form change to update the vault data
              handleFormChange({ 
                ssh_key_configured: result.ssh_key_configured,
                host_entry: result.host_entry,
                ssh_password: '' // Clear password in vault data too
              })
            } else {
              message.error(result.message || t('vaultEditor.testConnection.failed'))
              setTestConnectionSuccess(false)
              if (onTestConnectionStateChange) {
                onTestConnectionStateChange(false)
              }
            }
          }
        } catch (error) {
          message.error(t('vaultEditor.testConnection.failed'))
          setTestConnectionSuccess(false)
          if (onTestConnectionStateChange) {
            onTestConnectionStateChange(false)
          }
        } finally {
          // Reset testing state
          setIsTestingConnection(false)
          setTestTaskId(null)
        }
      } else if (status === 'FAILED' || status === 'CANCELLED') {
        message.error(t('vaultEditor.testConnection.failed'))
        setIsTestingConnection(false)
        setTestTaskId(null)
        setTestConnectionSuccess(false)
        if (onTestConnectionStateChange) {
          onTestConnectionStateChange(false)
        }
      }
    }
  }, [testTraceData, form, t])

  // Calculate extra fields not in schema
  useEffect(() => {
    if (!entityDef) return

    let schemaFields = Object.keys(entityDef.fields || {})
    
    // For STORAGE entities, also include provider-specific fields
    if (entityType === 'STORAGE' && importedData.provider) {
      const provider = storageProviders.providers[importedData.provider as keyof typeof storageProviders.providers]
      if (provider && provider.fields) {
        schemaFields = [...schemaFields, ...Object.keys(provider.fields)]
      }
    }
    
    const { extras, movedToExtra, movedFromExtra } = processExtraFields(importedData, schemaFields)
    
    setExtraFields(extras)

    // Notify about field movements
    if ((movedToExtra.length > 0 || movedFromExtra.length > 0) && onFieldMovement) {
      onFieldMovement(movedToExtra, movedFromExtra)
    }

    // Show toast messages for field movements
    showFieldMovementToasts(movedToExtra, movedFromExtra)
  }, [importedData, entityDef, entityType])

  // Initialize form with data
  useEffect(() => {
    if (entityDef) {
      // Always re-initialize when initialData changes from non-empty to empty (indicating a reset)
      const currentDataString = JSON.stringify(initialData)
      const wasNonEmpty = lastInitializedData && lastInitializedData !== '{}'
      const isNowEmpty = currentDataString === '{}'
      
      // Skip re-initialization only if data hasn't changed AND we're not resetting
      if (currentDataString === lastInitializedData && !(wasNonEmpty && isNowEmpty)) {
        return
      }
      
      const formData: Record<string, any> = {}
      Object.entries(entityDef.fields || {}).forEach(([key, field]) => {
        const typedField = field as FieldDefinition
        if (initialData[key] !== undefined) {
          formData[key] = initialData[key]
        } else if (typedField.default !== undefined) {
          formData[key] = typedField.default
        }
      })
      
      // For STORAGE entities, also populate provider-specific fields
      if (entityType === 'STORAGE' && initialData.provider) {
        const provider = storageProviders.providers[initialData.provider as keyof typeof storageProviders.providers]
        if (provider && provider.fields) {
          Object.entries(provider.fields).forEach(([key, field]) => {
            if (initialData[key] !== undefined) {
              formData[key] = initialData[key]
            } else if ((field as any).default !== undefined) {
              formData[key] = (field as any).default
            }
          })
        }
      }
      
      // Reset form first to clear any previous values
      form.resetFields()
      form.setFieldsValue(formData)
      
      // Reset state variables
      setSshKeyConfigured(false)
      setSelectedProvider(null)
      setRawJsonError(null)
      
      // Initialize ssh_key_configured state for MACHINE and BRIDGE entities
      if ((entityType === 'MACHINE' || entityType === 'BRIDGE') && formData.ssh_key_configured !== undefined) {
        setSshKeyConfigured(formData.ssh_key_configured)
      }
      
      // Initialize provider for STORAGE entity
      if (entityType === 'STORAGE' && formData.provider) {
        setSelectedProvider(formData.provider)
      }
      
      // Calculate extra fields for this data
      let schemaFields = Object.keys(entityDef.fields || {})
      
      // For STORAGE entities, also include provider-specific fields
      if (entityType === 'STORAGE' && initialData.provider) {
        const provider = storageProviders.providers[initialData.provider as keyof typeof storageProviders.providers]
        if (provider && provider.fields) {
          schemaFields = [...schemaFields, ...Object.keys(provider.fields)]
        }
      }
      
      const extras: Record<string, any> = {}
      
      // Check if initialData has extraFields structure
      if (initialData.extraFields && typeof initialData.extraFields === 'object') {
        Object.assign(extras, initialData.extraFields)
      }
      
      // Also check for non-schema fields at root level
      Object.entries(initialData).forEach(([key, value]) => {
        if (key !== 'extraFields' && !schemaFields.includes(key)) {
          extras[key] = value
        }
      })
      
      // Build complete data structure for raw JSON
      const completeData = { ...formData }
      if (Object.keys(extras).length > 0) {
        completeData.extraFields = extras
      }
      
      // Initialize raw JSON with proper structure
      updateRawJson(completeData)
      
      // Remember what data we initialized with
      setLastInitializedData(currentDataString)
      
      // Validate initial data - but skip validation for repositories in edit mode
      // to avoid race condition with credential field requirements
      if (!(isEditMode && entityType === 'REPOSITORY')) {
        // Use immediate validation for non-repository entities or create mode
        form.validateFields()
          .then(() => {
            onValidate?.(true)
          })
          .catch((errorInfo) => {
            const errors = errorInfo.errorFields?.map((field: any) => 
              `${field.name.join('.')}: ${field.errors.join(', ')}`
            )
            onValidate?.(false, errors)
          })
      } else {
        // For repositories in edit mode, mark as valid immediately
        // since credential field is optional in edit mode
        onValidate?.(true)
      }
    }
  }, [form, entityDef, entityType, initialData])

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
      const jsonString = JSON.stringify(data, null, 2)
      setRawJsonValue(jsonString)
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
      
      // No need for setTimeout - the shouldUpdate prop in renderField handles re-validation automatically
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
    
    // Use direct onChange for immediate updates (no debouncing)
    directOnChange(completeData, hasChanges)

    // Then validate
    // If ssh_key_configured just changed, exclude ssh_password from validation
    // to allow shouldUpdate to re-render the field with updated rules first
    const fieldsToValidate = changedValues?.ssh_key_configured !== undefined && (entityType === 'MACHINE' || entityType === 'BRIDGE')
      ? Object.keys(formData).filter(key => key !== 'ssh_password')
      : undefined // undefined means validate all fields
    
    form
      .validateFields(fieldsToValidate)
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
      directOnChange(completeData, hasChanges)
      
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
        
        // Manually trigger change after import (no delay)
        handleFormChange()
      } catch (error) {
        // Failed to parse JSON file
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
    // Note: We no longer hide ssh_password field based on state alone
    // It will be conditionally rendered using Form.Item dependencies
    
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
    
    // Build validation rules (ssh_password field handles its own dynamic rules)
    const rules = buildValidationRules(field, required, fieldLabel)

    const commonProps = {
      placeholder: fieldPlaceholder,
      style: { 
        // Don't apply input styles to Select - different DOM structure
        width: '100%' 
      },
    }

    // Render based on type using helper components
    if (field.type === 'boolean') {
      // Special rendering for ssh_key_configured field with vertical segmented control
      if (fieldName === 'ssh_key_configured') {
        return (
          <Form.Item
            noStyle
            shouldUpdate
          >
            {({ getFieldValue, setFieldValue }) => {
              const currentValue = getFieldValue(fieldName)
              
              return (
                <Form.Item
                  name={fieldName}
                  label={<FieldLabel label={fieldLabel} description={fieldDescription} />}
                  initialValue={field.default === true}
                  normalize={(value) => value === true || value === 'true'}
                >
                  <Segmented
                    block
                    data-testid={`vault-editor-field-${fieldName}`}
                    value={currentValue === true}
                    onChange={(value) => {
                      // Update the form field value
                      setFieldValue(fieldName, value === true)
                      // Trigger form change to update dependent fields
                      handleFormChange({ [fieldName]: value === true })
                    }}
                    options={[
                      { 
                        label: (
                          <Space direction="vertical" align="center" size={spacing('XS')}>
                            <CheckCircleOutlined style={{ fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_MD }} />
                            <span style={{ fontSize: fontSize('SM') }}>Configured</span>
                          </Space>
                        ), 
                        value: true 
                      },
                      { 
                        label: (
                          <Space direction="vertical" align="center" size={spacing('XS')}>
                            <ExclamationCircleOutlined style={{ fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_MD }} />
                            <span style={{ fontSize: fontSize('SM') }}>Not Configured</span>
                          </Space>
                        ), 
                        value: false 
                      }
                    ]}
                    style={{ 
                      // Height managed by Radio.Group default styles
                      borderRadius: borderRadius('LG')
                    }}
                  />
                </Form.Item>
              )
            }}
          </Form.Item>
        )
      }
      
      // Default Switch for other boolean fields
      return (
        <FieldFormItem
          name={fieldName}
          label={fieldLabel}
          description={fieldDescription}
          initialValue={field.default}
          valuePropName="checked"
        >
          <Switch data-testid={`vault-editor-field-${fieldName}`} />
        </FieldFormItem>
      )
    }

    if (field.enum) {
      return (
        <FieldFormItem
          name={fieldName}
          label={fieldLabel}
          description={fieldDescription}
          rules={rules}
          initialValue={field.default}
        >
          <Select {...commonProps} data-testid={`vault-editor-field-${fieldName}`}>
            {field.enum.map((option) => (
              <Select.Option key={option} value={option}>
                {option}
              </Select.Option>
            ))}
          </Select>
        </FieldFormItem>
      )
    }

    if (field.type === 'number') {
      return (
        <FieldFormItem
          name={fieldName}
          label={fieldLabel}
          description={fieldDescription}
          rules={rules}
          initialValue={field.default}
        >
          <InputNumber
            {...commonProps}
            min={field.minimum}
            max={field.maximum}
            data-testid={`vault-editor-field-${fieldName}`}
          />
        </FieldFormItem>
      )
    }

    if (field.type === 'object') {
      // Check if this object has specific structure definition
      const hasStructure = field.properties || (field.additionalProperties && typeof field.additionalProperties === 'object')
      
      if (hasStructure) {
        // Use NestedObjectEditor for complex objects with defined structure
        return (
          <Form.Item
            name={fieldName}
            label={<FieldLabel label={fieldLabel} description={fieldDescription} />}
            rules={rules}
          >
            <NestedObjectEditor
              fieldDefinition={field}
              title={fieldLabel}
              description={fieldDescription}
              data-testid={`vault-editor-field-${fieldName}`}
            />
          </Form.Item>
        )
      } else {
        // Use JSON editor for generic objects
        const { validator, getValueFromEvent, getValueProps } = getJsonFieldProps(false)
        return (
          <Form.Item
            name={fieldName}
            label={<FieldLabel label={fieldLabel} description={fieldDescription} />}
            rules={[...rules, { validator }]}
            getValueFromEvent={getValueFromEvent}
            getValueProps={getValueProps}
          >
            <Input.TextArea
              {...commonProps}
              rows={4}
              placeholder={field.example ? `${t('vaultEditor.example')} ${JSON.stringify(field.example, null, 2)}` : t('vaultEditor.enterJsonObject')}
              data-testid={`vault-editor-field-${fieldName}`}
            />
          </Form.Item>
        )
      }
    }

    if (field.type === 'array') {
      const { validator, getValueFromEvent, getValueProps } = getJsonFieldProps(true)
      return (
        <Form.Item
          name={fieldName}
          label={<FieldLabel label={fieldLabel} description={fieldDescription} />}
          rules={[...rules, { validator }]}
          getValueFromEvent={getValueFromEvent}
          getValueProps={getValueProps}
        >
          <Input.TextArea
            {...commonProps}
            rows={4}
            placeholder={field.example ? `${t('vaultEditor.example')} ${JSON.stringify(field.example, null, 2)}` : t('vaultEditor.enterJsonArray')}
            data-testid={`vault-editor-field-${fieldName}`}
          />
        </Form.Item>
      )
    }

    // Special handling for port type
    if (fieldName === 'port' || field.format === 'port') {
      return (
        <FieldFormItem
          name={fieldName}
          label={fieldLabel}
          description={fieldDescription}
          rules={rules}
          initialValue={field.default}
        >
          <InputNumber
            {...commonProps}
            min={1}
            max={65535}
            placeholder={t('vaultEditor.portPlaceholder')}
            data-testid={`vault-editor-field-${fieldName}`}
          />
        </FieldFormItem>
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
        // Call handleFormChange immediately (no delay)
        handleFormChange({ SSH_PRIVATE_KEY: values.SSH_PRIVATE_KEY, SSH_PUBLIC_KEY: values.SSH_PUBLIC_KEY })
      } else {
        // For single field generation
        form.setFieldValue(fieldName, values[fieldName])
        // Call handleFormChange immediately (no delay)
        handleFormChange({ [fieldName]: values[fieldName] })
      }
    }

    // Special handling for ssh_password field with dynamic validation
    if ((entityType === 'MACHINE' || entityType === 'BRIDGE') && fieldName === 'ssh_password') {
      return (
        <Form.Item
          noStyle
          shouldUpdate={(prevValues, currentValues) => prevValues.ssh_key_configured !== currentValues.ssh_key_configured}
        >
          {({ getFieldValue }) => {
            const sshKeyConfigured = getFieldValue('ssh_key_configured')
            
            // Hide the field if SSH key is configured
            if (sshKeyConfigured) {
              return null
            }
            
            // Dynamic validation rules based on ssh_key_configured
            const dynamicRules = required && !sshKeyConfigured ? [
              { 
                required: true, 
                message: t('vaultEditor.sshPasswordRequiredWhenNoKey', { defaultValue: 'SSH password is required when SSH key is not configured' }) 
              },
              ...rules.slice(1) // Include any other rules except the first required rule
            ] : rules.filter(rule => !rule.required) // Remove required rule if not needed
            
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
                rules={dynamicRules}
                initialValue={field.default}
              >
                <Input
                  {...commonProps}
                  type="password"
                  autoComplete="new-password"
                  data-testid={`vault-editor-field-${fieldName}`}
                />
              </Form.Item>
            )
          }}
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
                <InfoCircleOutlined style={{ fontSize: 12 }} />
              </Tooltip>
            )}
          </Space>
        }
        rules={rules}
        initialValue={field.default}
        style={{ marginBottom: spacing('MD') }}
      >
        <Input
          {...commonProps}
          type={field.sensitive ? 'password' : 'text'}
          autoComplete={field.sensitive ? 'new-password' : 'off'}
          data-testid={`vault-editor-field-${fieldName}`}
          style={{ 
            // Base styles handled by CSS
            width: '100%', 
            minWidth: 0 
          }}
          addonAfter={isGeneratable ? (
            <FieldGenerator
              fieldType={
                fieldName === 'credential' ? 'repository_credential' : 'ssh_keys'
              }
              onGenerate={handleFieldGeneration}
              entityType={entityType}
              data-testid={`vault-editor-generate-${fieldName}`}
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
        style={{ 
          marginBottom: spacing('SM'), 
          flexShrink: 0,
          borderRadius: borderRadius('LG'),
          fontSize: fontSize('SM')
        }}
      />

      <Form
        form={form}
        layout="horizontal"
        labelCol={{ xs: { span: 24 }, sm: { span: 6 } }}
        wrapperCol={{ xs: { span: 24 }, sm: { span: 18 } }}
        labelAlign="right"
        colon={true}
        onValuesChange={(changedValues, _allValues) => {
          handleFormChange(changedValues)
        }}
        autoComplete="off"
        style={{ 
          flex: 1, 
          minHeight: 0, 
          overflowY: 'auto',
          overflowX: 'hidden'
        }}
        className="vault-editor-form"
        data-testid="vault-editor-form"
      >
        <Collapse 
          defaultActiveKey={[
            requiredFields.length > 0 ? 'required' : '',
            optionalFields.length > 0 ? 'optional' : '',
            (entityType === 'STORAGE' && selectedProvider && providerFields) ? 'provider' : '',
          ].filter(Boolean)}
          style={{ flex: 1 }}
          data-testid="vault-editor-collapse"
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
              data-testid="vault-editor-panel-required"
            >
              {requiredFields
                .map((fieldName) => {
                  const field = fields[fieldName as keyof typeof fields]
                  if (!field) return null
                  // In edit mode for repositories, the credential field should not be required
                  // since it already exists and user may just want to view it
                  const isRequired = !(isEditMode && entityType === 'REPOSITORY' && fieldName === 'credential')
                  return <div key={fieldName}>{renderField(fieldName, field as FieldDefinition, isRequired)}</div>
                })}
              
              {/* Conditionally show ssh_password in required fields when SSH key is not configured */}
              {entityType === 'MACHINE' && !requiredFields.includes('ssh_password' as never) && (
                <Form.Item
                  noStyle
                  shouldUpdate={(prevValues, currentValues) => prevValues.ssh_key_configured !== currentValues.ssh_key_configured}
                >
                  {({ getFieldValue }) => {
                    const sshKeyConfigured = getFieldValue('ssh_key_configured')
                    const sshPasswordField = 'ssh_password' in fields ? fields['ssh_password'] : null
                    if (!sshKeyConfigured && sshPasswordField) {
                      return renderField('ssh_password', sshPasswordField as FieldDefinition, true, false)
                    }
                    return null
                  }}
                </Form.Item>
              )}
              
              {/* Test Connection button for MACHINE entity */}
              {entityType === 'MACHINE' && (
                <Form.Item 
                  wrapperCol={{ offset: 6, span: 18 }}
                  style={{ marginTop: spacing('MD') }}
                >
                  <Space size="middle" wrap style={{ width: '100%' }}>
                    <Tooltip title={t('vaultEditor.testConnection.button')}>
                      <Button
                        type="primary"
                        icon={<WifiOutlined />}
                        loading={isCreatingQueueItem || isTestingConnection}
                        data-testid="vault-editor-test-connection"
                        aria-label={t('vaultEditor.testConnection.button')}
                        style={{ 
                          ...styles.touchTarget,
                          borderRadius: borderRadius('LG'),
                          fontSize: fontSize('SM'),
                          padding: `0 ${spacing('LG')}px`
                        }}
                        onClick={async () => {
                      // Get current form values
                      const values = form.getFieldsValue()
                      const { ip, user, ssh_password, port, datastore } = values
                      
                      // Validate required fields
                      if (!ip || !user || (!ssh_password && !sshKeyConfigured)) {
                        message.error(t('vaultEditor.testConnection.missingFields'))
                        return
                      }
                      
                      try {
                        // Build machine vault with test credentials
                        const testMachineVault = JSON.stringify({
                          ip: ip,
                          user: user,
                          ssh_password: ssh_password || '',
                          port: port || 22,
                          datastore: datastore || ''
                        })
                        
                        // Get team vault data which contains SSH keys
                        const teamData = teams?.find(team => team.teamName === teamName)
                        const teamVaultData = teamData?.vaultContent || '{}'
                        
                        // Build queue vault using the proper service
                        const queueVault = await buildQueueVault({
                          teamName,
                          machineName: '', // Empty string for bridge-only queue item
                          bridgeName,
                          functionName: 'ssh_test',
                          params: {},
                          priority: 1,
                          description: 'SSH connection test',
                          addedVia: 'vault-editor',
                          machineVault: testMachineVault,
                          teamVault: teamVaultData // Pass actual team vault with SSH keys
                        })

                        // Create queue item for SSH connection test
                        createQueueItem({
                          teamName,
                          bridgeName,
                          machineName: '', // Send empty string for bridge-only queue items
                          queueVault,
                          priority: 1 // Highest priority for immediate execution
                        }, {
                          onSuccess: (response) => {
                            // Extract taskId from the response
                            if (response && response.taskId) {
                              // Set the task ID and enable polling
                              setTestTaskId(response.taskId)
                              setIsTestingConnection(true)
                              message.info(t('vaultEditor.testConnection.testing'))
                            } else {
                              message.error(t('vaultEditor.testConnection.failed'))
                            }
                          },
                          onError: (_error) => {
                            message.error(t('vaultEditor.testConnection.failed'))
                          }
                        })
                      } catch (error) {
                        message.error(t('vaultEditor.testConnection.failed'))
                      }
                    }}
                  />
                    </Tooltip>
                    {testConnectionSuccess && (
                      <CheckCircleOutlined 
                        style={{ 
                          color: '#52c41a', 
                          fontSize: 20,
                          marginLeft: 8,
                          display: 'flex',
                          alignItems: 'center'
                        }} 
                      />
                    )}
                  </Space>
                </Form.Item>
              )}
              
              {/* Kernel Compatibility Display */}
              {entityType === 'MACHINE' && form.getFieldValue('kernel_compatibility') && (
                <Form.Item
                  label={t('vaultEditor.systemCompatibility.title')}
                  style={{ marginBottom: 16 }}
                >
                  {(() => {
                    const compatibility = form.getFieldValue('kernel_compatibility')
                    const status = compatibility.compatibility_status || 'unknown'
                    const osInfo = compatibility.os_info || {}

                    const statusConfig: Record<string, { type: 'success' | 'warning' | 'error' | 'info'; icon: JSX.Element; color: string }> = {
                      compatible: { type: 'success' as const, icon: <CheckCircleOutlined />, color: '#52c41a' },
                      warning: { type: 'warning' as const, icon: <WarningOutlined />, color: '#faad14' },
                      incompatible: { type: 'error' as const, icon: <ExclamationCircleOutlined />, color: '#ff4d4f' },
                      unknown: { type: 'info' as const, icon: <QuestionCircleOutlined />, color: '#1890ff' }
                    }

                    const config = statusConfig[status] || statusConfig.unknown
                    
                    return (
                      <Space direction="vertical" style={{ width: '100%' }}>
                        {/* OS Information */}
                        <Card size="small" style={{ marginBottom: 8 }}>
                          <Space direction="vertical" style={{ width: '100%' }}>
                            <Space>
                              <InfoCircleOutlined />
                              <Text strong>{t('vaultEditor.systemCompatibility.systemInfo')}:</Text>
                            </Space>
                            <Text>{t('vaultEditor.systemCompatibility.operatingSystem')}: {osInfo.pretty_name || t('vaultEditor.systemCompatibility.unknown')}</Text>
                            <Text>{t('vaultEditor.systemCompatibility.kernelVersion')}: {compatibility.kernel_version || t('vaultEditor.systemCompatibility.unknown')}</Text>
                            <Space>
                              <Text>{t('vaultEditor.systemCompatibility.btrfsAvailable')}:</Text>
                              {compatibility.btrfs_available ? (
                                <Tag color="success">{t('vaultEditor.systemCompatibility.yes')}</Tag>
                              ) : (
                                <Tag color="warning">{t('vaultEditor.systemCompatibility.no')}</Tag>
                              )}
                            </Space>
                            <Space>
                              <Text>{t('vaultEditor.systemCompatibility.sudoAvailable')}:</Text>
                              {(() => {
                                const sudoStatus = compatibility.sudo_available || 'unknown'
                                const sudoConfig: Record<string, { color: string; text: string }> = {
                                  available: { color: 'success', text: t('vaultEditor.systemCompatibility.available') },
                                  password_required: { color: 'warning', text: t('vaultEditor.systemCompatibility.passwordRequired') },
                                  not_installed: { color: 'error', text: t('vaultEditor.systemCompatibility.notInstalled') }
                                }
                                const config = sudoConfig[sudoStatus] || { color: 'default', text: t('vaultEditor.systemCompatibility.unknown') }
                                return <Tag color={config.color}>{config.text}</Tag>
                              })()}
                            </Space>
                            {osSetupCompleted !== null && (
                              <Space>
                                <Text>{t('vaultEditor.systemCompatibility.osSetup')}:</Text>
                                <Tag color={osSetupCompleted ? 'success' : 'warning'}>
                                  {osSetupCompleted ? t('vaultEditor.systemCompatibility.setupCompleted') : t('vaultEditor.systemCompatibility.setupRequired')}
                                </Tag>
                              </Space>
                            )}
                          </Space>
                        </Card>
                        
                        {/* Compatibility Status */}
                        <Alert
                          type={config.type}
                          icon={config.icon}
                          message={
                            <Space>
                              <Text strong>{t('vaultEditor.systemCompatibility.compatibilityStatus')}:</Text>
                              <Text style={{ color: config.color, textTransform: 'capitalize' }}>
                                {t(`vaultEditor.systemCompatibility.${status}`)}
                              </Text>
                            </Space>
                          }
                          description={
                            <>
                              {compatibility.compatibility_issues && compatibility.compatibility_issues.length > 0 && (
                                <div style={{ marginTop: 8 }}>
                                  <Text strong>{t('vaultEditor.systemCompatibility.knownIssues')}:</Text>
                                  <ul style={{ marginTop: 4, marginBottom: 8 }}>
                                    {compatibility.compatibility_issues.map((issue: string, index: number) => (
                                      <li key={index}>{issue}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                              {compatibility.recommendations && compatibility.recommendations.length > 0 && (
                                <div>
                                  <Text strong>{t('vaultEditor.systemCompatibility.recommendations')}:</Text>
                                  <ul style={{ marginTop: 4, marginBottom: 0 }}>
                                    {compatibility.recommendations.map((rec: string, index: number) => (
                                      <li key={index}>{rec}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                            </>
                          }
                          showIcon
                        />
                      </Space>
                    )
                  })()}
                </Form.Item>
              )}
              
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
              data-testid="vault-editor-panel-optional"
            >
              {optionalFields.map((fieldName) => {
                const field = fields[fieldName as keyof typeof fields]
                if (!field) return null

                // Skip ssh_password for MACHINE entity as it's conditionally shown in required fields
                if (entityType === 'MACHINE' && fieldName === 'ssh_password') {
                  return (
                    <Form.Item
                      key={fieldName}
                      noStyle
                      shouldUpdate={(prevValues, currentValues) => prevValues.ssh_key_configured !== currentValues.ssh_key_configured}
                    >
                      {({ getFieldValue }) => {
                        const sshKeyConfigured = getFieldValue('ssh_key_configured')
                        // Only show in optional fields if SSH key IS configured
                        if (sshKeyConfigured) {
                          return renderField(fieldName, field as FieldDefinition, false)
                        }
                        return null
                      }}
                    </Form.Item>
                  )
                }

                return <div key={fieldName}>{renderField(fieldName, field as FieldDefinition, false)}</div>
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
              data-testid="vault-editor-panel-provider"
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
                    if (!providerFields.fields || !(fieldName in providerFields.fields)) return null
                    const field = providerFields.fields[fieldName as keyof typeof providerFields.fields]
                    if (!field) return null
                    return <div key={fieldName}>{renderField(fieldName, field as FieldDefinition, true, true)}</div>
                  })}
                </>
              )}

              {/* Optional provider fields */}
              {providerFields.optional && providerFields.optional.length > 0 && (
                <>
                  {providerFields.required && providerFields.required.length > 0 && <div style={{ marginTop: 24 }} />}
                  {providerFields.optional.map((fieldName: string) => {
                    if (!providerFields.fields || !(fieldName in providerFields.fields)) return null
                    const field = providerFields.fields[fieldName as keyof typeof providerFields.fields]
                    if (!field) return null
                    return <div key={fieldName}>{renderField(fieldName, field as FieldDefinition, false, true)}</div>
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
              data-testid="vault-editor-panel-extra"
            >
              <Alert
                message={t('vaultEditor.extraFieldsWarning')}
                description={t('vaultEditor.extraFieldsWarningDescription')}
                type="warning"
                showIcon
                style={{ marginBottom: 'var(--space-md)' }}
              />
              <Card size="small">
                <pre style={{ margin: 0, overflow: 'auto' }}>
                  {JSON.stringify(extraFields, null, 2)}
                </pre>
              </Card>
            </Collapse.Panel>
          )}

          {featureFlags.isEnabled('advancedVaultEditor') && (
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
              data-testid="vault-editor-panel-rawjson"
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

              <div style={{ marginBottom: spacing('SM'), display: 'flex', justifyContent: 'flex-end' }}>
                <Button
                  size="small"
                  type="default"
                  onClick={() => formatJsonRef.current?.()}
                  style={{
                    borderRadius: borderRadius('MD'),
                    fontSize: fontSize('SM')
                  }}
                  data-testid="vault-editor-format-json"
                >
                  Format
                </Button>
              </div>

              <SimpleJsonEditor
                value={rawJsonValue}
                onChange={handleRawJsonChange}
                height="400px"
                data-testid="vault-editor-raw-json"
                onFormatReady={(formatFn) => {
                  formatJsonRef.current = formatFn
                }}
              />
            </Collapse.Panel>
          )}
        </Collapse>
      </Form>
    </div>
  )
}

export default VaultEditor