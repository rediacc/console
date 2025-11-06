import React, { useState, useEffect, useMemo, useCallback, useRef, type JSX } from 'react'
import {
  Form,
  Input,
  InputNumber,
  Select,
  Switch,
  Space,
  Alert,
  Card,
  Tag,
  Tooltip,
  message,
  Divider,
  Typography,
  Button,
  Row,
  Col,
  Descriptions,
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
import { spacing, borderRadius, fontSize } from '@/utils/styleConstants'
import { featureFlags } from '@/config/featureFlags'

const { Text } = Typography

// Base64 utility functions for fields with format: "base64"
const decodeBase64 = (value: string): string => {
  try {
    return atob(value)
  } catch (e) {
    // If decode fails, return original value
    console.warn('Failed to decode base64 value:', e)
    return value
  }
}

const encodeBase64 = (value: string): string => {
  try {
    return btoa(value)
  } catch (e) {
    // If encode fails, return original value
    console.warn('Failed to encode base64 value:', e)
    return value
  }
}

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
  uiMode?: 'simple' | 'expert' // UI mode for conditional rendering
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
  uiMode = 'expert',
}) => {
  const { t } = useTranslation(['common', 'storageProviders'])
  const [form] = Form.useForm()
  const [extraFields, setExtraFields] = useState<Record<string, any>>({})
  const [importedData, setImportedData] = useState<Record<string, any>>(initialData)
  const [rawJsonValue, setRawJsonValue] = useState<string>(() => {
    return Object.keys(initialData).length > 0 ? JSON.stringify(initialData, null, 2) : '{}'
  })
  const [rawJsonError, setRawJsonError] = useState<string | null>(null)
  const [_sshKeyConfigured, setSshKeyConfigured] = useState(false)
  const [selectedProvider, setSelectedProvider] = useState<string | null>(null)
  const [lastInitializedData, setLastInitializedData] = useState<string>('')
  const [testTaskId, setTestTaskId] = useState<string | null>(null)
  const [isTestingConnection, setIsTestingConnection] = useState(false)
  const [testConnectionSuccess, setTestConnectionSuccess] = useState(false)
  const [osSetupCompleted, setOsSetupCompleted] = useState<boolean | null>(null)
  const formatJsonRef = useRef<(() => void) | null>(null)
  
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

  // Update raw JSON when form data changes
  const updateRawJson = useCallback((data: Record<string, any>) => {
    try {
      const jsonString = JSON.stringify(data, null, 2)
      setRawJsonValue(jsonString)
      setRawJsonError(null)
    } catch (error) {
      setRawJsonError(t('vaultEditor.failedToSerialize'))
    }
  }, [t])

  // Track previous modal open state
  const prevModalOpenRef = useRef(isModalOpen)
  
  // Reset when modal opens (transitions from closed to open)
  useEffect(() => {
    if (isModalOpen && !prevModalOpenRef.current) {
      // Modal just opened - reset everything
      setLastInitializedData('')
      form.resetFields()
      form.setFields([]) // Clear all field errors
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
          // Decode base64 fields for display in the form
          if (typedField.format === 'base64' && typeof initialData[key] === 'string') {
            formData[key] = decodeBase64(initialData[key])
          } else {
            formData[key] = initialData[key]
          }
        } else if (typedField.default !== undefined) {
          formData[key] = typedField.default
        }
      })
      
      // For STORAGE entities, also populate provider-specific fields
      if (entityType === 'STORAGE' && initialData.provider) {
        const provider = storageProviders.providers[initialData.provider as keyof typeof storageProviders.providers]
        if (provider && provider.fields) {
          Object.entries(provider.fields).forEach(([key, field]) => {
            const typedField = field as FieldDefinition
            if (initialData[key] !== undefined) {
              // Decode base64 fields for display in the form
              if (typedField.format === 'base64' && typeof initialData[key] === 'string') {
                formData[key] = decodeBase64(initialData[key])
              } else {
                formData[key] = initialData[key]
              }
            } else if (typedField.default !== undefined) {
              formData[key] = typedField.default
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
        // Use immediate validation for non-repository entities or create mode without surfacing errors
        form.validateFields(undefined, { validateOnly: true })
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
  }, [form, entityDef, entityType, initialData, updateRawJson, isEditMode, onValidate])

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

  const handleFormChange = (changedValues?: any) => {
    const formData = form.getFieldsValue()

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

    // Encode base64 fields before saving
    const encodedData = { ...formData }
    Object.entries(entityDef?.fields || {}).forEach(([key, field]) => {
      const typedField = field as FieldDefinition
      if (typedField.format === 'base64' && encodedData[key] !== undefined && typeof encodedData[key] === 'string') {
        encodedData[key] = encodeBase64(encodedData[key])
      }
    })

    // Also encode base64 fields for STORAGE provider-specific fields
    if (entityType === 'STORAGE' && selectedProvider && providerFields?.fields) {
      Object.entries(providerFields.fields).forEach(([key, field]) => {
        const typedField = field as FieldDefinition
        if (typedField.format === 'base64' && encodedData[key] !== undefined && typeof encodedData[key] === 'string') {
          encodedData[key] = encodeBase64(encodedData[key])
        }
      })
    }

    // Build complete data with extraFields structure
    const completeData = { ...encodedData }
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
    const collectErrors = (errorInfo: any) =>
      errorInfo?.errorFields?.map((field: any) => `${field.name.join('.')}: ${field.errors.join(', ')}`) || []

    const validationTargets =
      changedValues?.ssh_key_configured !== undefined && (entityType === 'MACHINE' || entityType === 'BRIDGE')
        ? Object.keys(formData).filter(key => key !== 'ssh_password')
        : Object.keys(changedValues || {})

    const performValidation = async () => {
      const accumulatedErrors: string[] = []

      if (validationTargets.length > 0) {
        try {
          await form.validateFields(validationTargets, { validateOnly: true })
        } catch (errorInfo: any) {
          accumulatedErrors.push(...collectErrors(errorInfo))
        }
      }

      try {
        await form.validateFields(undefined, { validateOnly: true })
        if (accumulatedErrors.length > 0) {
          onValidate?.(false, accumulatedErrors)
        } else {
          onValidate?.(true)
        }
      } catch (errorInfo: any) {
        const overallErrors = collectErrors(errorInfo)
        const combined = overallErrors.length > 0 ? overallErrors : accumulatedErrors
        onValidate?.(false, combined)
      }
    }

    void performValidation()
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
          const field = entityDef.fields[key] as FieldDefinition
          // Decode base64 fields when loading from raw JSON
          if (field.format === 'base64' && typeof val === 'string') {
            formData[key] = decodeBase64(val)
          } else {
            formData[key] = val
          }
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
      
      // Encode base64 fields before saving
      const encodedData = { ...formData }
      Object.entries(entityDef?.fields || {}).forEach(([key, field]) => {
        const typedField = field as FieldDefinition
        if (typedField.format === 'base64' && encodedData[key] !== undefined && typeof encodedData[key] === 'string') {
          encodedData[key] = encodeBase64(encodedData[key])
        }
      })

      // Build complete data structure for onChange
      const completeData = { ...encodedData }
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
        Object.entries(entityDef.fields || {}).forEach(([key, field]) => {
          const typedField = field as FieldDefinition
          if (data[key] !== undefined) {
            // Decode base64 fields when importing
            if (typedField.format === 'base64' && typeof data[key] === 'string') {
              formData[key] = decodeBase64(data[key])
            } else {
              formData[key] = data[key]
            }
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

    // Encode base64 fields before exporting
    const encodedData = { ...formData }
    Object.entries(entityDef?.fields || {}).forEach(([key, field]) => {
      const typedField = field as FieldDefinition
      if (typedField.format === 'base64' && encodedData[key] !== undefined && typeof encodedData[key] === 'string') {
        encodedData[key] = encodeBase64(encodedData[key])
      }
    })

    // Build export data with extraFields structure
    const exportData = { ...encodedData }
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
      // Default Switch for boolean fields
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
        <Form.Item
          name={fieldName}
          label={<FieldLabel label={fieldLabel} description={fieldDescription} />}
          rules={rules}
          initialValue={field.default}
        >
          <InputNumber
            {...commonProps}
            min={field.minimum}
            max={field.maximum}
            data-testid={`vault-editor-field-${fieldName}`}
          />
        </Form.Item>
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

    if (fieldName === 'ssh_password') {
      return (
        <Form.Item
          name={fieldName}
          label={<FieldLabel label={fieldLabel} description={fieldDescription} />}
          rules={rules}
          initialValue={field.default}
        >
          <Input.Password
            {...commonProps}
            autoComplete="new-password"
            data-testid={`vault-editor-field-${fieldName}`}
            placeholder={t('vaultEditor.sshPasswordPlaceholder')}
          />
        </Form.Item>
      )
    }

    if (fieldName === 'host_entry') {
      return (
        <Form.Item
          name={fieldName}
          label={<FieldLabel label={fieldLabel} description={fieldDescription} />}
          rules={rules}
          initialValue={field.default}
          extra={t('vaultEditor.hostEntryHelp')}
        >
          <Input
            {...commonProps}
            data-testid={`vault-editor-field-${fieldName}`}
            placeholder={t('vaultEditor.hostEntryPlaceholder')}
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
  const machineBasicFieldOrder = ['ip', 'user', 'datastore']

  return (
    <div style={{ display: 'flex', flexDirection: 'column', width: '100%' }}>
      {uiMode !== 'simple' && (
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
      )}

      {/* Warning for TEAM vault without SSH keys */}
      {entityType === 'TEAM' && (!initialData.SSH_PRIVATE_KEY || !initialData.SSH_PUBLIC_KEY) && (
        <Alert
          message={t('vaultEditor.missingSshKeysWarning')}
          description={t('vaultEditor.missingSshKeysDescription')}
          type="warning"
          showIcon
          style={{
            marginBottom: spacing('SM'),
            flexShrink: 0,
            borderRadius: borderRadius('LG'),
            fontSize: fontSize('SM')
          }}
        />
      )}

      <Form
        form={form}
        layout="horizontal"
        labelCol={{ xs: { span: 24 }, sm: { span: 8 } }}
        wrapperCol={{ xs: { span: 24 }, sm: { span: 16 } }}
        labelAlign="right"
        colon={true}
        validateTrigger={false}
        preserve={false}
        onValuesChange={(changedValues, _allValues) => {
          handleFormChange(changedValues)
        }}
        autoComplete="off"
        style={{
          width: '100%'
        }}
        className="vault-editor-form"
        data-testid="vault-editor-form"
      >
        <Row gutter={[spacing('SM'), spacing('SM')]} wrap style={{ width: '100%' }} data-testid="vault-editor-cards">
          {/* Main Configuration - Merged Required & Optional Fields */}
          {(requiredFields.length > 0 || optionalFields.length > 0) && (
            <>
              {/* Required Fields */}
              {(entityType === 'MACHINE' ? machineBasicFieldOrder : requiredFields)
                  .map((fieldName) => {
                    const field = fields[fieldName as keyof typeof fields]
                    if (!field) return null
                    const isRequired = !(isEditMode && entityType === 'REPOSITORY' && fieldName === 'credential')
                    // credential field should be full width for REPOSITORY
                    const colSpan = (entityType === 'REPOSITORY' && fieldName === 'credential') ? 24 : 12
                    return (
                      <Col key={fieldName} xs={24} md={colSpan}>
                        {renderField(fieldName, field as FieldDefinition, isRequired)}
                      </Col>
                    )
                  })}

                {/* Optional Fields (including ssh_password, port, host_entry) */}
                {entityType === 'MACHINE' && optionalFields
                  .filter((fieldName) => fieldName !== 'ssh_key_configured')
                  .map((fieldName) => {
                    const field = fields[fieldName as keyof typeof fields]
                    if (!field) return null
                    return (
                      <Col key={fieldName} xs={24} md={12}>
                        {renderField(fieldName, field as FieldDefinition, false)}
                      </Col>
                    )
                  })}

                {/* Test Connection Button */}
                {entityType === 'MACHINE' && (
                  <Col xs={24}>
                    <Form.Item
                      label={
                        <FieldLabel
                          label={t('vaultEditor.testConnection.label')}
                          description={t('vaultEditor.testConnection.description')}
                        />
                      }
                    >
                      <Space direction="vertical" size="small" style={{ width: '100%' }}>
                        {!testConnectionSuccess && (
                          <Alert
                            message={t('vaultEditor.testConnection.required')}
                            type="info"
                            showIcon
                            icon={<InfoCircleOutlined />}
                            style={{ marginBottom: spacing('XS') }}
                          />
                        )}
                        <Button
                          type="primary"
                          icon={<WifiOutlined />}
                          loading={isCreatingQueueItem || isTestingConnection}
                          data-testid="vault-editor-test-connection"
                          onClick={async () => {
                          const values = form.getFieldsValue()
                          const { ip, user, ssh_password, port, datastore } = values

                          if (!ip || !user) {
                            message.error(t('vaultEditor.testConnection.missingFields'))
                            return
                          }

                          try {
                            const testMachineVault = JSON.stringify({
                              ip: ip,
                              user: user,
                              ssh_password: ssh_password || '',
                              port: port || 22,
                              datastore: datastore || ''
                            })

                            const teamData = teams?.find(team => team.teamName === teamName)
                            const teamVaultData = teamData?.vaultContent || '{}'

                            const queueVault = await buildQueueVault({
                              teamName,
                              machineName: '',
                              bridgeName,
                              functionName: 'ssh_test',
                              params: {},
                              priority: 1,
                              description: 'SSH connection test',
                              addedVia: 'vault-editor',
                              machineVault: testMachineVault,
                              teamVault: teamVaultData
                            })

                            createQueueItem({
                              teamName,
                              bridgeName,
                              machineName: '',
                              queueVault,
                              priority: 1
                            }, {
                              onSuccess: (response) => {
                                if (response && response.taskId) {
                                  setTestTaskId(response.taskId)
                                  setIsTestingConnection(true)
                                  message.info(t('vaultEditor.testConnection.testing'))
                                } else {
                                  message.error(t('vaultEditor.testConnection.failed'))
                                }
                              },
                              onError: () => {
                                message.error(t('vaultEditor.testConnection.failed'))
                              }
                            })
                          } catch (error) {
                            message.error(t('vaultEditor.testConnection.failed'))
                          }
                        }}
                          style={{
                            width: '100%',
                            minHeight: '40px'
                          }}
                        >
                          {t('vaultEditor.testConnection.button')}
                        </Button>
                      </Space>
                    </Form.Item>
                  </Col>
                )}

                {entityType === 'MACHINE' && form.getFieldValue('kernel_compatibility') && (
                  <Col xs={24} lg={12}>
                    <Form.Item
                      label={<Text strong>{t('vaultEditor.systemCompatibility.title')}</Text>}
                      colon={false}
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

                        const sudoStatus = compatibility.sudo_available || 'unknown'
                        const sudoConfig: Record<string, { color: string; text: string }> = {
                          available: { color: 'success', text: t('vaultEditor.systemCompatibility.available') },
                          password_required: { color: 'warning', text: t('vaultEditor.systemCompatibility.passwordRequired') },
                          not_installed: { color: 'error', text: t('vaultEditor.systemCompatibility.notInstalled') }
                        }
                        const sudoConfigValue = sudoConfig[sudoStatus] || { color: 'default', text: t('vaultEditor.systemCompatibility.unknown') }

                        return (
                          <Space direction="vertical" style={{ width: '100%' }}>
                            <Descriptions bordered size="small" column={1}>
                              <Descriptions.Item label={t('vaultEditor.systemCompatibility.operatingSystem')}>
                                {osInfo.pretty_name || t('vaultEditor.systemCompatibility.unknown')}
                              </Descriptions.Item>
                              <Descriptions.Item label={t('vaultEditor.systemCompatibility.kernelVersion')}>
                                {compatibility.kernel_version || t('vaultEditor.systemCompatibility.unknown')}
                              </Descriptions.Item>
                              <Descriptions.Item label={t('vaultEditor.systemCompatibility.btrfsAvailable')}>
                                {compatibility.btrfs_available ? (
                                  <Tag color="success">{t('vaultEditor.systemCompatibility.yes')}</Tag>
                                ) : (
                                  <Tag color="warning">{t('vaultEditor.systemCompatibility.no')}</Tag>
                                )}
                              </Descriptions.Item>
                              <Descriptions.Item label={t('vaultEditor.systemCompatibility.sudoAvailable')}>
                                <Tag color={sudoConfigValue.color}>{sudoConfigValue.text}</Tag>
                              </Descriptions.Item>
                              {osSetupCompleted !== null && (
                                <Descriptions.Item label={t('vaultEditor.systemCompatibility.osSetup')}>
                                  <Tag color={osSetupCompleted ? 'success' : 'warning'}>
                                    {osSetupCompleted ? t('vaultEditor.systemCompatibility.setupCompleted') : t('vaultEditor.systemCompatibility.setupRequired')}
                                  </Tag>
                                </Descriptions.Item>
                              )}
                            </Descriptions>

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
                  </Col>
                )}

              {entityType !== 'MACHINE' && (
                  <>
                    {requiredFields.length > 0 && optionalFields.length > 0 && (
                      <Divider style={{ margin: '16px 0' }} />
                    )}
                      {optionalFields.length > 0 && optionalFields.map((fieldName) => {
                        const field = fields[fieldName as keyof typeof fields]
                        if (!field) return null

                        if (entityType === 'MACHINE' && fieldName === 'ssh_password') {
                          return (
                            <Col key={fieldName} xs={24} lg={12}>
                              <Form.Item
                                noStyle
                                shouldUpdate={(prevValues, currentValues) => prevValues.ssh_key_configured !== currentValues.ssh_key_configured}
                              >
                                {({ getFieldValue }) => {
                                  const sshKeyConfiguredValue = getFieldValue('ssh_key_configured')
                                  if (sshKeyConfiguredValue) {
                                    return renderField(fieldName, field as FieldDefinition, false)
                                  }
                                  return null
                                }}
                              </Form.Item>
                            </Col>
                          )
                        }

                        return (
                          <Col key={fieldName} xs={24} lg={12}>
                            {renderField(fieldName, field as FieldDefinition, false)}
                          </Col>
                        )
                      })}
                  </>
                )}
            </>
          )}

          {/* Provider-specific fields Card for STORAGE entity */}
          {entityType === 'STORAGE' && selectedProvider && providerFields && (
            <Col xs={24} sm={24} md={24} lg={24} xl={24}>
              <Card
                title={t('vaultEditor.providerFields', { provider: providerFields.name })}
                variant="borderless"
                size="default"
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
                          <Text>- {tip}</Text>
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
              </Card>
            </Col>
          )}

          {/* Extra Fields Card - Only show in expert mode */}
          {Object.keys(extraFields).length > 0 && uiMode !== 'simple' && (
            <Col xs={24} sm={24} md={24} lg={24} xl={24}>
              <Card
                title={
                  <Space>
                    {t('vaultEditor.extraFields')}
                    <Tooltip title={t('vaultEditor.extraFieldsTooltip')}>
                      <WarningOutlined style={{ color: '#faad14', fontSize: '14px' }} />
                    </Tooltip>
                  </Space>
                }
                variant="borderless"
                size="default"
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
              </Card>
            </Col>
          )}

          {/* Raw JSON Editor Card - Expert mode only */}
          {featureFlags.isEnabled('advancedVaultEditor') && uiMode !== 'simple' && (
            <Col xs={24} sm={24} md={24} lg={24} xl={24}>
              <Card
                title={
                  <Space>
                    <CodeOutlined />
                    {t('vaultEditor.rawJsonEditor')}
                    <Tooltip title={t('vaultEditor.rawJsonTooltip')}>
                      <ExclamationCircleOutlined style={{ color: '#ff4d4f', fontSize: '14px' }} />
                    </Tooltip>
                  </Space>
                }
                variant="borderless"
                size="default"
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
              </Card>
            </Col>
          )}
        </Row>
      </Form>
    </div>
  )
}

export default VaultEditor


