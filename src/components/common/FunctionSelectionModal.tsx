import React, { useState, useMemo, useEffect } from 'react'
import { Modal, Row, Col, Card, Input, Space, Form, Slider, Empty, Typography, Tag, Button, Select, Tooltip, InputNumber, Alert, Checkbox } from 'antd'
import { ExclamationCircleOutlined, WarningOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useSelector } from 'react-redux'
import { RootState } from '@/store/store'
import type { QueueFunction } from '@/api/queries/queue'
import { useLocalizedFunctions } from '@/services/functionsService'
import { useRepositories } from '@/api/queries/repositories'
import { useMachines } from '@/api/queries/machines'
import { useStorage } from '@/api/queries/storage'

const { Search } = Input
const { Text, Paragraph } = Typography

interface FunctionSelectionModalProps {
  open: boolean
  onCancel: () => void
  onSubmit: (functionData: {
    function: QueueFunction
    params: Record<string, any>
    priority: number
    description: string
    selectedMachine?: string
  }) => void
  title?: string
  subtitle?: React.ReactNode
  allowedCategories?: string[]
  loading?: boolean
  showMachineSelection?: boolean
  teamName?: string
  machines?: Array<{ value: string; label: string; bridgeName: string }>
  hiddenParams?: string[] // Parameters to hide from the form
  defaultParams?: Record<string, any> // Default values for hidden parameters
  preselectedFunction?: string // Preselected function name
  initialParams?: Record<string, any> // Initial values for visible parameters
  currentMachineName?: string // Current machine name for context
  additionalContext?: {
    sourceRepository?: string
    grandRepository?: string | null
  } // Additional context information to display
}

const FunctionSelectionModal: React.FC<FunctionSelectionModalProps> = ({
  open,
  onCancel,
  onSubmit,
  title,
  subtitle,
  allowedCategories,
  loading = false,
  showMachineSelection = false,
  teamName,
  machines = [],
  hiddenParams = [],
  defaultParams = {},
  preselectedFunction,
  initialParams = {},
  currentMachineName,
  additionalContext
}) => {
  const { t } = useTranslation(['functions', 'common', 'machines'])
  const { functions: localizedFunctions, categories } = useLocalizedFunctions()
  const uiMode = useSelector((state: RootState) => state.ui.uiMode)
  const isSimpleMode = uiMode === 'simple'
  
  const [selectedFunction, setSelectedFunction] = useState<QueueFunction | null>(null)
  const [functionParams, setFunctionParams] = useState<Record<string, any>>({})
  const [functionPriority, setFunctionPriority] = useState(4) // Fixed to normal priority
  const [functionDescription, setFunctionDescription] = useState('')
  const [functionSearchTerm, setFunctionSearchTerm] = useState('')
  const [selectedMachine, setSelectedMachine] = useState<string>('')
  const [previousFunctionName, setPreviousFunctionName] = useState<string | null>(null)

  // Fetch repositories for the current team
  const { data: repositories } = useRepositories(teamName)
  
  // Fetch machines and storage for destination dropdown
  const { data: machinesData } = useMachines(teamName)
  const { data: storageData } = useStorage(teamName)

  // Initialize parameters when function is selected
  useEffect(() => {
    if (selectedFunction) {
      const functionChanged = previousFunctionName !== selectedFunction.name
      
      // Initialize params if function changed or no params exist
      setFunctionParams(prevParams => {
        // If we already have params and function hasn't changed, don't reinitialize
        if (Object.keys(prevParams).length > 0 && !functionChanged) {
          return prevParams
        }
        
        const defaultInitialParams: Record<string, any> = {}
        
        Object.entries(selectedFunction.params).forEach(([paramName, paramInfo]) => {
          // Check if we have an initial value from props
          if (initialParams[paramName] !== undefined && !hiddenParams.includes(paramName)) {
            defaultInitialParams[paramName] = initialParams[paramName]
            // For size parameters, also set the unit and value fields
            if (paramInfo.format === 'size' && paramInfo.units) {
              const match = String(initialParams[paramName]).match(/^(\d+)([%GT]?)$/)
              if (match) {
                const [, value, unit] = match
                defaultInitialParams[`${paramName}_value`] = parseInt(value)
                defaultInitialParams[`${paramName}_unit`] = unit || (paramInfo.units[0] === 'percentage' ? '%' : paramInfo.units[0])
              }
            }
          } else if (paramInfo.format === 'size' && paramInfo.units) {
            // Initialize with default values for size parameters
            if (paramInfo.default) {
              const match = paramInfo.default.match(/^(\d+)([%GT]?)$/)
              if (match) {
                const [, value, unit] = match
                defaultInitialParams[`${paramName}_value`] = parseInt(value)
                defaultInitialParams[`${paramName}_unit`] = unit || (paramInfo.units[0] === 'percentage' ? '%' : paramInfo.units[0])
                defaultInitialParams[paramName] = paramInfo.default
              }
            } else {
              // Set default unit
              const defaultUnit = paramInfo.units[0] === 'percentage' ? '%' : paramInfo.units[0]
              defaultInitialParams[`${paramName}_unit`] = defaultUnit
            }
          } else if (paramInfo.options && paramInfo.options.length > 0) {
            // Initialize dropdown parameters with default value
            defaultInitialParams[paramName] = paramInfo.default || paramInfo.options[0]
          } else if (paramInfo.default) {
            // Initialize other parameters with default value
            defaultInitialParams[paramName] = paramInfo.default
          }
          
          // Special handling for destination-dropdown: set current machine as default
          if (paramInfo.ui === 'destination-dropdown' && currentMachineName && functionChanged) {
            // Check if there's a destinationType parameter with value 'machine'
            const destinationTypeParam = selectedFunction.params['destinationType']
            if (destinationTypeParam && (defaultInitialParams['destinationType'] === 'machine' || destinationTypeParam.default === 'machine')) {
              defaultInitialParams[paramName] = currentMachineName
            }
          }
        })
        
        return defaultInitialParams
      })
      
      // Update previous function name
      setPreviousFunctionName(selectedFunction.name)
    }
  }, [selectedFunction, initialParams, hiddenParams, previousFunctionName, currentMachineName])

  // Handle preselected function
  useEffect(() => {
    if (preselectedFunction && localizedFunctions[preselectedFunction] && open) {
      setSelectedFunction(localizedFunctions[preselectedFunction] as QueueFunction)
    }
  }, [preselectedFunction, localizedFunctions, open])
  
  // Reset params when modal opens/closes to ensure clean state
  useEffect(() => {
    if (!open) {
      // Reset all state when modal closes
      setFunctionParams({})
      setFunctionDescription('')
      setFunctionSearchTerm('')
      setSelectedMachine('')
      setPreviousFunctionName(null)
      // Don't reset selectedFunction here as it might be preselected
    } else if (open && preselectedFunction) {
      // When modal opens with a preselected function, force reinitialization
      setFunctionParams({})
      setPreviousFunctionName(null)
    }
  }, [open, preselectedFunction])

  // Re-apply initial params when they change and modal is open
  useEffect(() => {
    if (open && selectedFunction && Object.keys(initialParams).length > 0) {
      setFunctionParams(prevParams => {
        const newParams = { ...prevParams }
        
        // Apply each initial param
        Object.entries(initialParams).forEach(([paramName, value]) => {
          if (!hiddenParams.includes(paramName)) {
            newParams[paramName] = value
            
            // For the state parameter in push function, ensure it's set
            if (paramName === 'state' && selectedFunction.name === 'push') {
              newParams[paramName] = value
            }
          }
        })
        
        return newParams
      })
    }
  }, [open, initialParams, selectedFunction, hiddenParams])

  // Filter functions based on allowed categories and search term
  const filteredFunctions = useMemo(() => {
    let functions = Object.values(localizedFunctions) as QueueFunction[]
    
    // Filter by allowed categories if specified
    if (allowedCategories && allowedCategories.length > 0) {
      functions = functions.filter(func => allowedCategories.includes(func.category))
    }
    
    // Filter by search term
    if (functionSearchTerm) {
      const searchLower = functionSearchTerm.toLowerCase()
      functions = functions.filter(
        func =>
          func.name.toLowerCase().includes(searchLower) ||
          func.description.toLowerCase().includes(searchLower)
      )
    }
    
    return functions
  }, [localizedFunctions, allowedCategories, functionSearchTerm])

  // Group functions by category
  const functionsByCategory = useMemo(() => {
    return filteredFunctions.reduce((acc, func) => {
      if (!acc[func.category]) {
        acc[func.category] = []
      }
      acc[func.category].push(func)
      return acc
    }, {} as Record<string, QueueFunction[]>)
  }, [filteredFunctions])

  // Check if all required parameters are filled
  const areRequiredParamsFilled = useMemo(() => {
    if (!selectedFunction) return false
    
    return Object.entries(selectedFunction.params)
      .filter(([paramName]) => !hiddenParams.includes(paramName))
      .every(([paramName, paramInfo]) => {
        if (!paramInfo.required) return true
        
        const paramValue = functionParams[paramName]
        
        // For size parameters, check the value part
        if (paramInfo.format === 'size' && paramInfo.units) {
          const valueParam = functionParams[`${paramName}_value`]
          return valueParam !== undefined && valueParam !== null && valueParam !== ''
        }
        
        // For other parameters, check the main value
        return paramValue !== undefined && paramValue !== null && paramValue !== ''
      })
  }, [selectedFunction, functionParams, hiddenParams])

  const handleSubmit = () => {
    if (!selectedFunction) return
    if (showMachineSelection && !selectedMachine) return
    
    // Validate required parameters
    const missingParams: string[] = []
    Object.entries(selectedFunction.params)
      .filter(([paramName]) => !hiddenParams.includes(paramName))
      .forEach(([paramName, paramInfo]) => {
        if (paramInfo.required) {
          const paramValue = functionParams[paramName]
          
          // Check if parameter has a value
          if (paramValue === undefined || paramValue === null || paramValue === '') {
            missingParams.push(paramInfo.label || paramName)
          }
          
          // For size parameters, also check if the value part is filled
          if (paramInfo.format === 'size' && paramInfo.units) {
            const valueParam = functionParams[`${paramName}_value`]
            if (!valueParam || valueParam === '') {
              if (!missingParams.includes(paramInfo.label || paramName)) {
                missingParams.push(paramInfo.label || paramName)
              }
            }
          }
        }
      })
    
    // If there are missing parameters, show error and return
    if (missingParams.length > 0) {
      Modal.error({
        title: t('functions:validationError'),
        content: t('functions:missingRequiredParams', { params: missingParams.join(', ') })
      })
      return
    }
    
    // Clean up the params - remove the helper _value and _unit fields
    const cleanedParams = Object.entries(functionParams).reduce((acc, [key, value]) => {
      if (!key.endsWith('_value') && !key.endsWith('_unit')) {
        acc[key] = value
      }
      return acc
    }, {} as Record<string, any>)
    
    // Merge visible params with default params
    const allParams = { ...defaultParams, ...cleanedParams }
    
    
    onSubmit({
      function: selectedFunction,
      params: allParams,
      priority: functionPriority,
      description: functionDescription || selectedFunction.description,
      selectedMachine: selectedMachine || undefined
    })
    
    // Reset form
    setSelectedFunction(null)
    setFunctionParams({})
    setFunctionPriority(4)
    setFunctionDescription('')
    setFunctionSearchTerm('')
    setSelectedMachine('')
    setPreviousFunctionName(null)
  }

  const handleCancel = () => {
    // Reset form
    setSelectedFunction(null)
    setFunctionParams({})
    setFunctionPriority(4)
    setFunctionDescription('')
    setFunctionSearchTerm('')
    setSelectedMachine('')
    setPreviousFunctionName(null)
    onCancel()
  }

  return (
    <Modal
      title={
        <Space direction="vertical" size={4}>
          <div>{title || t('functions:selectFunction')}</div>
          {subtitle && <div>{subtitle}</div>}
        </Space>
      }
      open={open}
      onCancel={handleCancel}
      width={1000}
      footer={[
        <Button key="cancel" onClick={handleCancel} data-testid="function-modal-cancel">
          {t('common:actions.cancel')}
        </Button>,
        <Button
          key="submit"
          type="primary"
          onClick={handleSubmit}
          disabled={!selectedFunction || (showMachineSelection && !selectedMachine) || !areRequiredParamsFilled}
          loading={loading}
          style={{ 
            background: 'var(--color-primary)',
            borderColor: 'var(--color-primary)',
            minHeight: '44px'
          }}
          data-testid="function-modal-submit"
        >
          {t('common:actions.addToQueue')}
        </Button>
      ]}
      data-testid="function-modal"
    >
      <Row gutter={24}>
        {!preselectedFunction && !isSimpleMode && (
          <Col span={10}>
            <Card title={t('functions:availableFunctions')} size="small">
            <Search
              placeholder={t('functions:searchFunctions')}
              value={functionSearchTerm}
              onChange={(e) => setFunctionSearchTerm(e.target.value)}
              style={{ 
                marginBottom: 'var(--space-md)',
                minHeight: '44px'
              }}
              autoComplete="off"
              data-testid="function-modal-search"
            />
            <div style={{ 
              maxHeight: 400, 
              overflow: 'auto',
              padding: 'var(--space-xs)',
              backgroundColor: 'var(--color-bg-secondary)',
              borderRadius: '8px',
              border: '1px solid var(--color-border-secondary)'
            }}>
              {Object.entries(functionsByCategory).map(([category, funcs]) => (
                <div key={category} style={{ marginBottom: 'var(--space-md)' }} data-testid={`function-modal-category-${category}`}>
                  <Text strong style={{ 
                    display: 'block', 
                    marginBottom: 'var(--space-sm)',
                    fontSize: '15px',
                    color: 'var(--color-text-primary)'
                  }}>{categories[category]?.name || category}</Text>
                  {funcs.map(func => (
                    <div
                      key={func.name}
                      onClick={() => setSelectedFunction(func)}
                      style={{
                        padding: 'var(--space-sm) var(--space-md)',
                        marginBottom: 'var(--space-xs)',
                        cursor: 'pointer',
                        borderRadius: '6px',
                        backgroundColor: selectedFunction?.name === func.name 
                          ? 'var(--color-primary-bg)' 
                          : 'var(--color-bg-primary)',
                        border: selectedFunction?.name === func.name 
                          ? `2px solid var(--color-primary)` 
                          : `1px solid var(--color-border-secondary)`,
                        minHeight: '44px',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'center',
                        transition: 'all 0.2s ease'
                      }}
                      data-testid={`function-modal-item-${func.name}`}
                    >
                      <Text strong>{func.name}</Text>
                      <br />
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {func.description}
                      </Text>
                    </div>
                  ))}
                </div>
              ))}
            </div>
            </Card>
          </Col>
        )}
        
        <Col span={preselectedFunction || isSimpleMode ? 24 : 14}>
          {selectedFunction ? (
            <Space direction="vertical" size={'md'} style={{ width: '100%' }}>
              <Card title={`${t('functions:configure')}: ${selectedFunction.name}`} size="small">
                <Paragraph>
                  {selectedFunction.description}
                </Paragraph>
                
                <Form layout="horizontal" labelCol={{ span: 8 }} wrapperCol={{ span: 16 }}>
                  {/* Show additional info for push function */}
                  {selectedFunction.name === 'push' && functionParams.dest && (
                    <Alert
                      type="info"
                      showIcon
                      style={{ 
                        marginBottom: 'var(--space-md)',
                        borderRadius: '8px',
                        border: '1px solid var(--color-info)'
                      }}
                      message="Push Operation Details"
                      description={
                        <Space direction="vertical" size="small">
                          <div>
                            <Text strong>Destination Filename: </Text>
                            <Text code>{functionParams.dest}</Text>
                          </div>
                          {additionalContext?.grandRepository && (
                            <div>
                              <Text strong>Repository Lineage: </Text>
                              <Space>
                                <Tag color="blue">{additionalContext.grandRepository}</Tag>
                                <Text type="secondary">→</Text>
                                <Tag color="#8FBC8F">{additionalContext.sourceRepository}</Tag>
                                <Text type="secondary">→</Text>
                                <Tag color="green">{functionParams.dest}</Tag>
                              </Space>
                            </div>
                          )}
                          {!additionalContext?.grandRepository && additionalContext?.sourceRepository && (
                            <div>
                              <Text strong>Source Repository: </Text>
                              <Tag color="#8FBC8F">{additionalContext.sourceRepository}</Tag>
                              <Text type="secondary"> (Original)</Text>
                            </div>
                          )}
                          <div>
                            <Text type="secondary" style={{ fontSize: '12px' }}>
                              {functionParams.state === 'online' 
                                ? 'The repository will be pushed in online state (mounted).' 
                                : 'The repository will be pushed in offline state (unmounted).'}
                            </Text>
                          </div>
                          {functionParams.state === 'online' && (
                            <Alert
                              type="warning"
                              showIcon
                              style={{ 
                                marginTop: 'var(--space-sm)',
                                borderRadius: '8px',
                                border: '1px solid var(--color-warning)'
                              }}
                              message="Online Push Warning"
                              description={
                                <Space direction="vertical" size="small">
                                  <Text type="secondary" style={{ fontSize: '12px' }}>
                                    Pushing a mounted repository while services are running may cause data inconsistencies.
                                  </Text>
                                  <Text type="secondary" style={{ fontSize: '12px' }}>
                                    <strong>Potential issues:</strong>
                                  </Text>
                                  <ul style={{ margin: '4px 0', paddingLeft: '20px' }}>
                                    <li style={{ fontSize: '12px' }}>
                                      <Text type="secondary">Database services may have open transactions that could be interrupted</Text>
                                    </li>
                                    <li style={{ fontSize: '12px' }}>
                                      <Text type="secondary">Applications actively writing files may result in partial or corrupted data</Text>
                                    </li>
                                    <li style={{ fontSize: '12px' }}>
                                      <Text type="secondary">File locks and temporary files may be included in the snapshot</Text>
                                    </li>
                                  </ul>
                                  <Text type="secondary" style={{ fontSize: '12px' }}>
                                    <strong>Recommendation:</strong> Online pushes are convenient for regular backups without service interruption. 
                                    However, periodically perform offline pushes (unmount first) to ensure you have fully consistent backups for critical recovery scenarios.
                                  </Text>
                                </Space>
                              }
                            />
                          )}
                        </Space>
                      }
                    />
                  )}
                  {/* Machine Selection */}
                  {showMachineSelection && (
                    <Form.Item
                      label={t('machines:machine')}
                      required
                    >
                      <Select
                        value={selectedMachine}
                        onChange={setSelectedMachine}
                        placeholder={t('machines:selectMachine')}
                        options={machines}
                        data-testid="function-modal-machine-select"
                      />
                    </Form.Item>
                  )}
                  
                  {/* Function Parameters */}
                  {Object.entries(selectedFunction.params)
                    .filter(([paramName]) => !hiddenParams.includes(paramName))
                    .map(([paramName, paramInfo]) => {
                      // Check if this is a size parameter with units
                      const isSizeParam = paramInfo.format === 'size' && paramInfo.units
                      
                      return (
                        <Form.Item
                          key={paramName}
                          label={
                            <Tooltip title={`Background parameter: ${paramName}`}>
                              <span style={{ cursor: 'help' }}>
                                {paramInfo.label || paramName}
                              </span>
                            </Tooltip>
                          }
                          required={paramInfo.required}
                          help={paramInfo.help || ''}
                        >
                          {isSizeParam ? (
                            <Space.Compact style={{ width: '100%' }}>
                              <InputNumber
                                style={{ width: '65%' }}
                                value={functionParams[`${paramName}_value`] || ''}
                                onChange={(value) => {
                                  // Ensure only numbers are accepted
                                  if (value === null || value === undefined) {
                                    setFunctionParams({
                                      ...functionParams,
                                      [`${paramName}_value`]: '',
                                      [paramName]: ''
                                    })
                                  } else {
                                    const numValue = typeof value === 'string' ? parseInt(value, 10) : value
                                    if (!isNaN(numValue) && numValue > 0) {
                                      const unit = functionParams[`${paramName}_unit`] || (paramInfo.units[0] === 'percentage' ? '%' : paramInfo.units[0])
                                      setFunctionParams({
                                        ...functionParams,
                                        [`${paramName}_value`]: numValue,
                                        [paramName]: `${numValue}${unit}`
                                      })
                                    }
                                  }
                                }}
                                onKeyPress={(e) => {
                                  // Only allow numbers
                                  const charCode = e.which || e.keyCode
                                  if (charCode < 48 || charCode > 57) {
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
                                placeholder={paramInfo.units.includes('percentage') ? '95' : '100'}
                                min={1}
                                max={paramInfo.units.includes('percentage') ? 100 : undefined}
                                keyboard={true}
                                step={1}
                                precision={0}
                                data-testid={`function-modal-param-${paramName}-value`}
                              />
                              <Select
                                style={{ width: '35%' }}
                                value={functionParams[`${paramName}_unit`] || (paramInfo.units[0] === 'percentage' ? '%' : paramInfo.units[0])}
                                onChange={(unit) => {
                                  const currentValue = functionParams[`${paramName}_value`]
                                  setFunctionParams({
                                    ...functionParams,
                                    [`${paramName}_unit`]: unit,
                                    [paramName]: currentValue ? `${currentValue}${unit}` : ''
                                  })
                                }}
                                options={paramInfo.units.map(unit => ({
                                  value: unit === 'percentage' ? '%' : unit,
                                  label: unit === 'percentage' ? '%' : unit === 'G' ? 'GB' : 'TB'
                                }))}
                                data-testid={`function-modal-param-${paramName}-unit`}
                              />
                            </Space.Compact>
                          ) : paramInfo.options && paramInfo.options.length > 0 ? (
                            <Select
                              value={functionParams[paramName] || paramInfo.default || ''}
                              onChange={(value) => {
                                const newParams = {
                                  ...functionParams,
                                  [paramName]: value
                                }
                                // If this is destinationType parameter and it changes, clear the 'to' field
                                if (paramName === 'destinationType' && value !== functionParams[paramName]) {
                                  newParams['to'] = ''
                                }
                                setFunctionParams(newParams)
                              }}
                              placeholder={paramInfo.help || ''}
                              options={paramInfo.options.map(option => ({
                                value: option,
                                label: option
                              }))}
                              data-testid={`function-modal-param-${paramName}`}
                            />
                          ) : paramInfo.ui === 'repository-dropdown' ? (
                            <Select
                              value={functionParams[paramName] || ''}
                              onChange={(value) => {
                                setFunctionParams({
                                  ...functionParams,
                                  [paramName]: value
                                })
                              }}
                              placeholder={t('resources:repositories.selectRepository')}
                              options={repositories?.map(repo => ({
                                value: repo.repositoryGuid,
                                label: repo.repositoryName
                              })) || []}
                              notFoundContent={t('resources:repositories.noRepositoriesFound')}
                              showSearch
                              filterOption={(input, option) =>
                                (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                              }
                              data-testid={`function-modal-param-${paramName}`}
                            />
                          ) : paramInfo.ui === 'destination-dropdown' ? (
                            <Select
                              value={functionParams[paramName] || ''}
                              onChange={(value) => {
                                setFunctionParams({
                                  ...functionParams,
                                  [paramName]: value
                                })
                              }}
                              placeholder={
                                functionParams['destinationType'] === 'machine' 
                                  ? t('machines:selectMachine')
                                  : t('resources:storage.selectStorage')
                              }
                              options={
                                functionParams['destinationType'] === 'machine'
                                  ? machinesData?.map(machine => ({
                                      value: machine.machineName,
                                      label: machine.machineName === currentMachineName 
                                        ? `${machine.machineName} (${t('machines:currentMachine')})`
                                        : machine.machineName
                                    })) || []
                                  : storageData?.map(storage => ({
                                      value: storage.storageName,
                                      label: storage.storageName
                                    })) || []
                              }
                              notFoundContent={
                                functionParams['destinationType'] === 'machine'
                                  ? t('machines:noMachinesFound')
                                  : t('resources:storage.noStorageFound')
                              }
                              showSearch
                              filterOption={(input, option) =>
                                (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                              }
                              disabled={!functionParams['destinationType']}
                              data-testid={`function-modal-param-${paramName}`}
                            />
                          ) : paramInfo.ui === 'source-dropdown' ? (
                            <Select
                              value={functionParams[paramName] || ''}
                              onChange={(value) => {
                                setFunctionParams({
                                  ...functionParams,
                                  [paramName]: value
                                })
                              }}
                              placeholder={
                                functionParams['sourceType'] === 'machine' 
                                  ? t('machines:selectMachine')
                                  : t('resources:storage.selectStorage')
                              }
                              options={
                                functionParams['sourceType'] === 'machine'
                                  ? machinesData?.map(machine => ({
                                      value: machine.machineName,
                                      label: machine.machineName === currentMachineName 
                                        ? `${machine.machineName} (${t('machines:currentMachine')})`
                                        : machine.machineName
                                    })) || []
                                  : storageData?.map(storage => ({
                                      value: storage.storageName,
                                      label: storage.storageName
                                    })) || []
                              }
                              notFoundContent={
                                functionParams['sourceType'] === 'machine'
                                  ? t('machines:noMachinesFound')
                                  : t('resources:storage.noStorageFound')
                              }
                              showSearch
                              filterOption={(input, option) =>
                                (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                              }
                              disabled={!functionParams['sourceType']}
                              data-testid={`function-modal-param-${paramName}`}
                            />
                          ) : paramInfo.ui === 'checkbox' && paramInfo.checkboxOptions ? (
                            <Space direction="vertical" style={{ width: '100%' }}>
                              {paramInfo.checkboxOptions.map((option: any) => (
                                <Checkbox
                                  key={option.value}
                                  checked={functionParams[paramName]?.includes(option.value)}
                                  onChange={(e) => {
                                    const currentValue = functionParams[paramName] || ''
                                    const values = currentValue.split(' ').filter(Boolean)
                                    
                                    if (e.target.checked) {
                                      // Add the value if not already present
                                      if (!values.includes(option.value)) {
                                        values.push(option.value)
                                      }
                                    } else {
                                      // Remove the value
                                      const index = values.indexOf(option.value)
                                      if (index > -1) {
                                        values.splice(index, 1)
                                      }
                                    }
                                    
                                    setFunctionParams({
                                      ...functionParams,
                                      [paramName]: values.join(' ')
                                    })
                                  }}
                                  data-testid={`function-modal-param-${paramName}-${option.value}`}
                                >
                                  {t(`functions:checkboxOptions.${option.label}`)}
                                </Checkbox>
                              ))}
                              <Input
                                value={functionParams[paramName] || ''}
                                onChange={(e) => setFunctionParams({
                                  ...functionParams,
                                  [paramName]: e.target.value
                                })}
                                placeholder={t('functions:additionalOptions')}
                                autoComplete="off"
                                style={{ marginTop: 8 }}
                                data-testid={`function-modal-param-${paramName}-additional`}
                              />
                            </Space>
                          ) : (
                            <Input
                              value={functionParams[paramName] || ''}
                              onChange={(e) => setFunctionParams({
                                ...functionParams,
                                [paramName]: e.target.value
                              })}
                              placeholder={paramInfo.help || ''}
                              autoComplete="off"
                              data-testid={`function-modal-param-${paramName}`}
                            />
                          )}
                        </Form.Item>
                      )
                    })}
                  
                  {/* Priority - Hidden when function is preselected or in simple mode */}
                  {!preselectedFunction && !isSimpleMode && (
                    <Form.Item label={t('functions:priority')} help={t('functions:priorityHelp')}>
                      <div>
                      <Slider
                        min={1}
                        max={5}
                        value={functionPriority}
                        onChange={setFunctionPriority}
                        marks={{
                          1: t('functions:priorityHigh'),
                          3: t('functions:priorityNormal'),
                          5: t('functions:priorityLow')
                        }}
                        tooltip={{
                          formatter: (value?: number) => {
                            const labels = {
                              1: t('functions:priorityHighest'),
                              2: t('functions:priorityHigh'),
                              3: t('functions:priorityNormal'),
                              4: t('functions:priorityBelowNormal'),
                              5: t('functions:priorityLow')
                            }
                            return value ? `${labels[value as keyof typeof labels]} (${value})` : ''
                          }
                        }}
                        data-testid="function-modal-priority-slider"
                      />
                      <div style={{ textAlign: 'center', marginTop: 8 }}>
                        <Tag 
                          color={
                            functionPriority === 1 ? 'red' :
                            functionPriority === 2 ? 'orange' :
                            functionPriority === 3 ? 'gold' :
                            functionPriority === 4 ? 'blue' :
                            'green'
                          }
                          icon={functionPriority === 1 ? <ExclamationCircleOutlined /> : undefined}
                        >
                          {t('functions:currentPriority')}: {
                            functionPriority === 1 ? t('functions:priorityHighest') :
                            functionPriority === 2 ? t('functions:priorityHigh') :
                            functionPriority === 3 ? t('functions:priorityNormal') :
                            functionPriority === 4 ? t('functions:priorityBelowNormal') :
                            t('functions:priorityLow')
                          } ({functionPriority})
                        </Tag>
                      </div>
                      {functionPriority && (
                        <Alert
                          message={
                            functionPriority === 1 ? t('functions:priorityHighestWarning') :
                            functionPriority === 2 ? t('functions:priorityHighWarning') :
                            functionPriority === 3 ? t('functions:priorityNormalWarning') :
                            functionPriority === 4 ? t('functions:priorityLowWarning') :
                            t('functions:priorityLowestWarning')
                          }
                          description={
                            functionPriority === 1 ? t('functions:priorityHighestDescription') :
                            functionPriority === 2 ? t('functions:priorityHighDescription') :
                            functionPriority === 3 ? t('functions:priorityNormalDescription') :
                            functionPriority === 4 ? t('functions:priorityLowDescription') :
                            t('functions:priorityLowestDescription')
                          }
                          type={
                            functionPriority === 1 ? 'error' :
                            functionPriority === 2 ? 'warning' :
                            functionPriority === 3 ? 'info' :
                            'success'
                          }
                          showIcon
                          icon={
                            functionPriority === 1 ? <ExclamationCircleOutlined /> :
                            functionPriority === 2 ? <WarningOutlined /> :
                            undefined
                          }
                          style={{ marginTop: 16 }}
                        />
                        )}
                      </div>
                    </Form.Item>
                  )}
                  
                  {/* Description */}
                  <Form.Item label={t('functions:description')}>
                    <Input.TextArea
                      value={functionDescription}
                      onChange={(e) => setFunctionDescription(e.target.value)}
                      placeholder={t('functions:descriptionPlaceholder')}
                      rows={2}
                      autoComplete="off"
                      data-testid="function-modal-description"
                    />
                  </Form.Item>
                </Form>
              </Card>
            </Space>
          ) : (
            <Card>
              <Empty description={t('functions:selectFunctionToConfigure')} />
            </Card>
          )}
        </Col>
      </Row>
    </Modal>
  )
}

export default FunctionSelectionModal