import React, { useState, useMemo, useRef, useEffect, useCallback, startTransition } from 'react'
import { Modal, Row, Col, Input, Space, Form, Slider, Empty, Typography, Button, Select, Tooltip, Checkbox, Popover, message } from 'antd'
import { ExclamationCircleOutlined, WarningOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import type { QueueFunction } from '@/api/queries/queue'
import { useLocalizedFunctions } from '@/services/functionsService'
import { useRepos } from '@/api/queries/repos'
import { useMachines } from '@/api/queries/machines'
import { useStorage } from '@/api/queries/storage'
import { ModalSize } from '@/types/modal'
import TemplateSelector from '@/components/common/TemplateSelector'
import TemplatePreviewModal from '@/components/common/TemplatePreviewModal'
import { templateService } from '@/services/templateService'
import {
  StyledModal,
  FunctionListCard,
  ConfigCard,
  SearchInput,
  FunctionList,
  CategorySection,
  CategoryTitle,
  FunctionOption,
  FunctionItemHeader,
  FunctionDescriptionText,
  QuickTaskTag,
  ContentStack,
  PushAlertsRow,
  PushAlertCard,
  AlertBodyText,
  AlertLinkWrapper,
  AlertLink,
  LineageTag,
  LineageSeparator,
  HelpTooltipIcon,
  PriorityHelpIcon,
  SizeInputGroup,
  SizeValueInput,
  SizeUnitSelect,
  CheckboxGroupStack,
  AdditionalOptionsInput,
  PriorityPopoverContent,
  PriorityPopoverHeader,
  PriorityLegendRow,
  PriorityLegendTag,
  PriorityLegendText,
  PriorityTagWrapper,
  PriorityStatusTag,
  PriorityAlert,
  PriorityAlertNote,
  PriorityAlertDetail,
  PrimarySubmitButton,
} from './styles'
import { ModalHeader, ModalTitle, ModalSubtitle } from '@/styles/primitives'

type FunctionParamValue = string | number | string[] | undefined
type FunctionParams = Record<string, FunctionParamValue>

const toFunctionParamValue = (value: unknown): FunctionParamValue | undefined => {
  if (typeof value === 'string' || typeof value === 'number') {
    return value
  }
  if (Array.isArray(value) && value.every((item) => typeof item === 'string')) {
    return value as string[]
  }
  return undefined
}

const { Text, Paragraph } = Typography
const QUICK_TASK_NAMES = ['ping', 'hello', 'ssh_test', 'health_check']

interface FunctionSelectionModalProps {
  open: boolean
  onCancel: () => void
  onSubmit: (functionData: {
    function: QueueFunction
    params: FunctionParams
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
  defaultParams?: FunctionParams // Default values for hidden parameters
  preselectedFunction?: string // Preselected function name
  initialParams?: FunctionParams // Initial values for visible parameters
  currentMachineName?: string // Current machine name for context
  additionalContext?: {
    sourceRepo?: string
    parentRepo?: string | null
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

  const [selectedFunction, setSelectedFunction] = useState<QueueFunction | null>(null)
  const [functionParams, setFunctionParams] = useState<FunctionParams>({})
  const [functionPriority, setFunctionPriority] = useState(4) // Fixed to normal priority
  const [functionDescription, setFunctionDescription] = useState('')
  const [functionSearchTerm, setFunctionSearchTerm] = useState('')
  const [selectedMachine, setSelectedMachine] = useState<string>('')
  const [selectedTemplates, setSelectedTemplates] = useState<string[]>([])
  const [showTemplateDetails, setShowTemplateDetails] = useState(false)
  const [templateToView, setTemplateToView] = useState<string | null>(null)

  const getStringParam = (key: string): string => (functionParams[key] as string | undefined) || ''
  const getArrayParam = (key: string): string[] =>
    Array.isArray(functionParams[key]) ? (functionParams[key] as string[]) : []
  const getSelectValue = (key: string): string | number | undefined =>
    functionParams[key] as string | number | undefined

  // Fetch repos for the current team
  const { data: repos } = useRepos(teamName)

  // Fetch machines and storage for destination dropdown
  const { data: machinesData } = useMachines(teamName)
  const { data: storageData } = useStorage(teamName)

  // Function to initialize parameters for a given function
  const initializeParams = useCallback((func: QueueFunction) => {
    const defaultInitialParams: FunctionParams = {}

    Object.entries(func.params).forEach(([paramName, paramInfo]) => {
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
        if (typeof paramInfo.default === 'string') {
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
        const defaultValue = toFunctionParamValue(paramInfo.default) ?? paramInfo.options[0]
        defaultInitialParams[paramName] = defaultValue
      } else {
        // Initialize other parameters with default value
        const defaultValue = toFunctionParamValue(paramInfo.default)
        if (typeof defaultValue !== 'undefined') {
          defaultInitialParams[paramName] = defaultValue
        }
      }

      // Special handling for destination-dropdown: set current machine as default
      if (paramInfo.ui === 'destination-dropdown' && currentMachineName) {
        // Check if there's a destinationType parameter with value 'machine'
        const destinationTypeParam = func.params['destinationType']
        const destinationDefault =
          typeof destinationTypeParam?.default === 'string' ? destinationTypeParam.default : undefined
        if (
          destinationTypeParam &&
          (defaultInitialParams['destinationType'] === 'machine' || destinationDefault === 'machine')
        ) {
          defaultInitialParams[paramName] = currentMachineName
        }
      }
    })

    return defaultInitialParams
  }, [initialParams, hiddenParams, currentMachineName])

  // Handler for selecting a function
  const handleSelectFunction = (func: QueueFunction) => {
    setSelectedFunction(func)
    setFunctionParams(initializeParams(func))

    // Auto-select P1 for quick tasks (functions that typically complete in under 33 seconds)
    const quickTasks = ['ping', 'hello', 'ssh_test', 'health_check']
    if (quickTasks.includes(func.name) || func.name.includes('test') || func.name.includes('check')) {
      setFunctionPriority(1)
    } else {
      // Reset to default priority for other functions
      setFunctionPriority(4)
    }
  }

  // Handle preselected function - only when modal opens
  // WARNING: Must initialize to false, NOT to `open` prop value!
  // If initialized to `open`, when modal opens with open=true, the ref is already
  // true, causing the preselection logic to never run (wasPreviouslyOpen check fails).
  const previousOpenRef = useRef(false)

  useEffect(() => {
    const wasPreviouslyOpen = previousOpenRef.current

    if (open && !wasPreviouslyOpen) {
      const preselected = preselectedFunction ? localizedFunctions[preselectedFunction] : undefined

      if (preselected) {
        const func = preselected as QueueFunction
        startTransition(() => {
          setSelectedFunction(func)
          setFunctionParams(initializeParams(func))
        })
      }
    }

    previousOpenRef.current = open
  }, [open, preselectedFunction, localizedFunctions, initializeParams])

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

  const priorityLegendItems = useMemo(
    () => [
      { level: 1, label: t('functions:priorityHighest'), description: t('functions:priorityPopoverP1') },
      { level: 2, label: t('functions:priorityHigh'), description: t('functions:priorityPopoverP2') },
      { level: 3, label: t('functions:priorityNormal'), description: t('functions:priorityPopoverP3') },
      { level: 4, label: t('functions:priorityBelowNormal'), description: t('functions:priorityPopoverP4') },
      { level: 5, label: t('functions:priorityLow'), description: t('functions:priorityPopoverP5') },
    ],
    [t]
  )

  // Check if all required parameters are filled
  const areRequiredParamsFilled = useMemo(() => {
    if (!selectedFunction) return false

    return Object.entries(selectedFunction.params)
      .filter(([paramName]) => !hiddenParams.includes(paramName))
      .every(([paramName, paramInfo]) => {
        if (!paramInfo.required) return true

        // For template-selector, check selectedTemplates state
        if (paramInfo.ui === 'template-selector') {
          return selectedTemplates.length > 0
        }

        const paramValue = functionParams[paramName]

        // For size parameters, check the value part
        if (paramInfo.format === 'size' && paramInfo.units) {
          const valueParam = functionParams[`${paramName}_value`]
          return typeof valueParam === 'number' && valueParam > 0
        }

        // For other parameters, check the main value
        return paramValue !== undefined && paramValue !== null && paramValue !== ''
      })
  }, [selectedFunction, functionParams, hiddenParams, selectedTemplates])

  const handleSubmit = async () => {
    if (!selectedFunction) return
    if (showMachineSelection && !selectedMachine) return

    // Validate required parameters
    const missingParams: string[] = []
    Object.entries(selectedFunction.params)
      .filter(([paramName]) => !hiddenParams.includes(paramName))
      .forEach(([paramName, paramInfo]) => {
        if (paramInfo.required) {
          // Special handling for template-selector - check selectedTemplates state
          if (paramInfo.ui === 'template-selector') {
            if (selectedTemplates.length === 0) {
              missingParams.push(paramInfo.label || paramName)
            }
          } else {
            const paramValue = functionParams[paramName]

            // Check if parameter has a value
            if (paramValue === undefined || paramValue === null || paramValue === '') {
              missingParams.push(paramInfo.label || paramName)
            }

            // For size parameters, also check if the value part is filled
            if (paramInfo.format === 'size' && paramInfo.units) {
              const valueParam = functionParams[`${paramName}_value`]
              if (typeof valueParam !== 'number' || valueParam <= 0) {
                if (!missingParams.includes(paramInfo.label || paramName)) {
                  missingParams.push(paramInfo.label || paramName)
                }
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
    }, {} as FunctionParams)

    // Merge visible params with default params
    const allParams: FunctionParams = { ...(defaultParams || {}), ...cleanedParams }

    // Handle template encoding for template-selector parameters
    if (selectedTemplates.length > 0) {
      for (const [paramName, paramInfo] of Object.entries(selectedFunction.params)) {
        if (paramInfo.ui === 'template-selector') {
          try {
            if (selectedTemplates.length === 1) {
              // Single template: use the existing service method
              const encodedTemplate = await templateService.getEncodedTemplateDataById(selectedTemplates[0])
              allParams[paramName] = encodedTemplate
            } else {
              // Multiple templates: fetch and merge them
              const templateDataList = await Promise.all(
                selectedTemplates.map(templateId => templateService.fetchTemplateData({ name: templateId }))
              )

              // Merge all templates into one structure
              const mergedTemplate = {
                name: selectedTemplates.join('+'),
                files: templateDataList.flatMap(template => template.files || [])
              }

              // Encode the merged template using the same method as templateService
              const encoder = new TextEncoder()
              const uint8Array = encoder.encode(JSON.stringify(mergedTemplate))
              let binaryString = ''
              for (let i = 0; i < uint8Array.length; i++) {
                binaryString += String.fromCharCode(uint8Array[i])
              }
              const encodedTemplate = btoa(binaryString)

              allParams[paramName] = encodedTemplate
            }
          } catch (error) {
            console.error('Failed to encode templates:', error)
            message.error(t('resources:templates.failedToLoadTemplate'))
            return
          }
        }
      }
    }


    onSubmit({
      function: selectedFunction,
      params: allParams,
      priority: functionPriority,
      description: functionDescription || selectedFunction.description,
      selectedMachine: selectedMachine || undefined
    })

    // Reset form
    setSelectedFunction(null)
    setFunctionParams({} as FunctionParams)
    setFunctionPriority(4)
    setFunctionDescription('')
    setFunctionSearchTerm('')
    setSelectedMachine('')
    setSelectedTemplates([])
  }

  const handleCancel = () => {
    // Reset form
    setSelectedFunction(null)
    setFunctionParams({} as FunctionParams)
    setFunctionPriority(4)
    setFunctionDescription('')
    setFunctionSearchTerm('')
    setSelectedMachine('')
    setSelectedTemplates([])
    onCancel()
  }

  return (
    <>
      <StyledModal
        title={
          <ModalHeader>
            <ModalTitle>
              <span>{title || t('functions:selectFunction')}</span>
              {subtitle && <ModalSubtitle as="div">{subtitle}</ModalSubtitle>}
            </ModalTitle>
          </ModalHeader>
        }
        open={open}
        onCancel={handleCancel}
        className={ModalSize.ExtraLarge}
        footer={[
          <Button key="cancel" onClick={handleCancel} data-testid="function-modal-cancel">
            {t('common:actions.cancel')}
          </Button>,
          <PrimarySubmitButton
            key="submit"
            type="primary"
            onClick={handleSubmit}
            disabled={!selectedFunction || (showMachineSelection && !selectedMachine) || !areRequiredParamsFilled}
            loading={loading}
            data-testid="function-modal-submit"
          >
            {t('common:actions.addToQueue')}
          </PrimarySubmitButton>
        ]}
      data-testid="function-modal"
    >
      <Row gutter={24}>
        {/* WARNING: Do not add isSimpleMode check here!
            The function list must be visible when clicking "Advanced" regardless of UI mode.
            Specific functions (setup, hello, etc.) are queued directly without modal,
            so this modal is ONLY shown for "Advanced" which always needs the function list. */}
        {!preselectedFunction && (
          <Col span={10}>
            <FunctionListCard title={t('functions:availableFunctions')} size="small">
              <SearchInput
                placeholder={t('functions:searchFunctions')}
                value={functionSearchTerm}
                onChange={(e) => setFunctionSearchTerm(e.target.value)}
                autoComplete="off"
                data-testid="function-modal-search"
              />
              <FunctionList>
                {Object.entries(functionsByCategory).map(([category, funcs]) => (
                  <CategorySection key={category} data-testid={`function-modal-category-${category}`}>
                    <CategoryTitle strong>{categories[category]?.name || category}</CategoryTitle>
                    {funcs.map(func => {
                      const isQuickTask =
                        QUICK_TASK_NAMES.includes(func.name) ||
                        func.name.includes('test') ||
                        func.name.includes('check')

                      return (
                        <FunctionOption
                          key={func.name}
                          onClick={() => handleSelectFunction(func)}
                          $selected={selectedFunction?.name === func.name}
                          data-testid={`function-modal-item-${func.name}`}
                        >
                          <FunctionItemHeader>
                            <Text strong>{func.name}</Text>
                            {isQuickTask && (
                              <QuickTaskTag>âš¡ {t('functions:quickTaskBadge')}</QuickTaskTag>
                            )}
                          </FunctionItemHeader>
                          <FunctionDescriptionText type="secondary">
                            {func.description}
                          </FunctionDescriptionText>
                        </FunctionOption>
                      )
                    })}
                  </CategorySection>
                ))}
              </FunctionList>
            </FunctionListCard>
          </Col>
        )}
        
        <Col span={preselectedFunction ? 24 : 14}>
          {selectedFunction ? (
            <ContentStack>
              <ConfigCard title={`${t('functions:configure')}: ${selectedFunction.name}`} size="small">
                <Paragraph>
                  {selectedFunction.description}
                </Paragraph>
                
                <Form layout="horizontal" labelCol={{ span: 8 }} wrapperCol={{ span: 16 }}>
                  {/* Show additional info for push function */}
                  {selectedFunction.name === 'push' && functionParams.dest && (
                    <PushAlertsRow $hasWarning={functionParams.state === 'online'}>
                      <PushAlertCard
                        type="info"
                        showIcon
                        message="Push Operation Details"
                        description={
                          <Space direction="vertical" size="small">
                            <div>
                              <Text strong>Destination Filename: </Text>
                              <Text code>{functionParams.dest}</Text>
                            </div>
                            {additionalContext?.parentRepo && (
                              <div>
                                <Text strong>Repo Lineage: </Text>
                                <Space>
                                  <LineageTag $variant="parent">{additionalContext.parentRepo}</LineageTag>
                                  <LineageSeparator>â†’</LineageSeparator>
                                  <LineageTag $variant="source">{additionalContext.sourceRepo}</LineageTag>
                                  <LineageSeparator>â†’</LineageSeparator>
                                  <LineageTag $variant="destination">{functionParams.dest}</LineageTag>
                                </Space>
                              </div>
                            )}
                            {!additionalContext?.parentRepo && additionalContext?.sourceRepo && (
                              <div>
                                <Text strong>Source Repo: </Text>
                                <LineageTag $variant="source">{additionalContext.sourceRepo}</LineageTag>
                                <AlertBodyText as="span"> (Original)</AlertBodyText>
                              </div>
                            )}
                            <div>
                              <AlertBodyText>
                                {functionParams.state === 'online'
                                  ? 'The repo will be pushed in online state (mounted).'
                                  : 'The repo will be pushed in offline state (unmounted).'}
                              </AlertBodyText>
                            </div>
                          </Space>
                        }
                      />
                      {functionParams.state === 'online' && (
                        <PushAlertCard
                          type="warning"
                          showIcon
                          message={t('functions:onlinePushWarningTitle')}
                          description={
                            <Space direction="vertical" size="small">
                              <AlertBodyText>
                                {t('functions:onlinePushWarningMessage')}
                              </AlertBodyText>
                              <AlertLinkWrapper>
                                <AlertLink
                                  href="https://docs.rediacc.com/concepts/repo-push-operations"
                                  target="_blank"
                                  rel="noopener noreferrer"
                                >
                                  {t('functions:onlinePushLearnMore')}
                                </AlertLink>
                              </AlertLinkWrapper>
                            </Space>
                          }
                        />
                      )}
                    </PushAlertsRow>
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
                            paramInfo.help ? (
                              <Space size={4}>
                                <span>{paramInfo.label || paramName}</span>
                                <Tooltip title={paramInfo.help}>
                                  <HelpTooltipIcon />
                                </Tooltip>
                              </Space>
                            ) : (
                              <span>{paramInfo.label || paramName}</span>
                            )
                          }
                          required={paramInfo.required}
                          {...(paramInfo.ui === 'template-selector' ? { wrapperCol: { span: 24 }, labelCol: { span: 0 } } : {})}
                        >
                          {isSizeParam ? (
                            <SizeInputGroup>
                              <SizeValueInput
                                value={
                                  typeof functionParams[`${paramName}_value`] === 'number'
                                    ? (functionParams[`${paramName}_value`] as number)
                                    : undefined
                                }
                                onChange={(value) => {
                                  if (value === null || value === undefined) {
                                    setFunctionParams((prev) => ({
                                      ...prev,
                                      [`${paramName}_value`]: undefined,
                                      [paramName]: ''
                                    }))
                                  } else {
                                    const numValue = typeof value === 'string' ? parseInt(value, 10) : value
                                    if (!Number.isNaN(numValue) && numValue > 0 && paramInfo.units) {
                                      setFunctionParams((prev) => {
                                        const unit =
                                          (prev[`${paramName}_unit`] as string | undefined) ||
                                          (paramInfo.units![0] === 'percentage' ? '%' : paramInfo.units![0])

                                        return {
                                          ...prev,
                                          [`${paramName}_value`]: numValue,
                                          [paramName]: `${numValue}${unit}`
                                        }
                                      })
                                    }
                                  }
                                }}
                                parser={(value) => {
                                  const parsed = value?.replace(/[^\d]/g, '')
                                  return parsed ? parseInt(parsed, 10) : 0
                                }}
                                formatter={(v) => (v ? `${v}` : '')}
                                placeholder={paramInfo.units?.includes('percentage') ? '95' : '100'}
                                min={1}
                                max={paramInfo.units?.includes('percentage') ? 100 : undefined}
                                keyboard
                                step={1}
                                precision={0}
                                data-testid={`function-modal-param-${paramName}-value`}
                              />
                              <SizeUnitSelect
                                value={
                                  (functionParams[`${paramName}_unit`] as string | undefined) ||
                                  (paramInfo.units?.[0] === 'percentage' ? '%' : paramInfo.units?.[0] || '')
                                }
                                onChange={(unitValue) => {
                                  const unit = String(unitValue ?? '')
                                  setFunctionParams((prev) => {
                                    const currentValue = prev[`${paramName}_value`]
                                    return {
                                      ...prev,
                                      [`${paramName}_unit`]: unit,
                                      [paramName]:
                                        typeof currentValue === 'number' ? `${currentValue}${unit}` : ''
                                    }
                                  })
                                }}
                                options={paramInfo.units?.map(unit => ({
                                  value: unit === 'percentage' ? '%' : unit,
                                  label: unit === 'percentage' ? '%' : unit === 'G' ? 'GB' : 'TB'
                                }))}
                                data-testid={`function-modal-param-${paramName}-unit`}
                              />
                            </SizeInputGroup>
                          ) : paramInfo.options && paramInfo.options.length > 0 ? (
                            <Select<string>
                              value={(getSelectValue(paramName) as string) ?? paramInfo.default ?? ''}
                              onChange={(value: string) => {
                                setFunctionParams((prev) => {
                                  const previousValue = prev[paramName]
                                  const updatedParams: FunctionParams = {
                                    ...prev,
                                    [paramName]: value,
                                  }
                                  if (paramName === 'destinationType' && value !== previousValue) {
                                    updatedParams['to'] = ''
                                  }
                                  return updatedParams
                                })
                              }}
                              placeholder={paramInfo.help || ''}
                              options={paramInfo.options.map(option => ({
                                value: option,
                                label: option
                              }))}
                              data-testid={`function-modal-param-${paramName}`}
                            />
                          ) : paramInfo.ui === 'repo-dropdown' ? (
                            <Select
                              value={getStringParam(paramName)}
                              onChange={(value) => {
                                setFunctionParams((prev) => ({
                                  ...prev,
                                  [paramName]: value
                                }))
                              }}
                              placeholder={t('resources:repos.selectRepo')}
                              options={repos?.map(repo => ({
                                value: repo.repoGuid,
                                label: repo.repoName
                              })) || []}
                              notFoundContent={t('resources:repos.noReposFound')}
                              showSearch
                              filterOption={(input, option) =>
                                (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                              }
                              data-testid={`function-modal-param-${paramName}`}
                            />
                          ) : paramInfo.ui === 'destination-dropdown' ? (
                            <Select
                              value={getStringParam(paramName)}
                              onChange={(value) => {
                                setFunctionParams((prev) => ({
                                  ...prev,
                                  [paramName]: value
                                }))
                              }}
                              placeholder={
                                getStringParam('destinationType') === 'machine' 
                                  ? t('machines:selectMachine')
                                  : t('resources:storage.selectStorage')
                              }
                              options={
                                getStringParam('destinationType') === 'machine'
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
                                getStringParam('destinationType') === 'machine'
                                  ? t('machines:noMachinesFound')
                                  : t('resources:storage.noStorageFound')
                              }
                              showSearch
                              filterOption={(input, option) =>
                                (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                              }
                              disabled={!getStringParam('destinationType')}
                              data-testid={`function-modal-param-${paramName}`}
                            />
                          ) : paramInfo.ui === 'source-dropdown' ? (
                            <Select
                              value={getStringParam(paramName)}
                              onChange={(value) => {
                                setFunctionParams((prev) => ({
                                  ...prev,
                                  [paramName]: value
                                }))
                              }}
                              placeholder={
                                getStringParam('sourceType') === 'machine' 
                                  ? t('machines:selectMachine')
                                  : t('resources:storage.selectStorage')
                              }
                              options={
                                getStringParam('sourceType') === 'machine'
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
                                getStringParam('sourceType') === 'machine'
                                  ? t('machines:noMachinesFound')
                                  : t('resources:storage.noStorageFound')
                              }
                              showSearch
                              filterOption={(input, option) =>
                                (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                              }
                              disabled={!getStringParam('sourceType')}
                              data-testid={`function-modal-param-${paramName}`}
                            />
                          ) : paramInfo.ui === 'machine-multiselect' ? (
                            <Select
                              mode="multiple"
                              value={getArrayParam(paramName)}
                              onChange={(value) => {
                                setFunctionParams((prev) => ({
                                  ...prev,
                                  [paramName]: value
                                }))
                              }}
                              placeholder={t('machines:selectMachines')}
                              options={
                                machinesData?.map(machine => ({
                                  value: machine.machineName,
                                  label: machine.machineName === currentMachineName
                                    ? `${machine.machineName} (${t('machines:currentMachine')})`
                                    : machine.machineName
                                })) || []
                              }
                              notFoundContent={t('machines:noMachinesFound')}
                              showSearch
                              filterOption={(input, option) =>
                                (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                              }
                              data-testid={`function-modal-param-${paramName}`}
                            />
                          ) : paramInfo.ui === 'storage-multiselect' ? (
                            <Select
                              mode="multiple"
                              value={getArrayParam(paramName)}
                              onChange={(value) => {
                                setFunctionParams((prev) => ({
                                  ...prev,
                                  [paramName]: value
                                }))
                              }}
                              placeholder={t('resources:storage.selectStorageSystems')}
                              options={
                                storageData?.map(storage => ({
                                  value: storage.storageName,
                                  label: storage.storageName
                                })) || []
                              }
                              notFoundContent={t('resources:storage.noStorageFound')}
                              showSearch
                              filterOption={(input, option) =>
                                (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                              }
                              data-testid={`function-modal-param-${paramName}`}
                            />
                          ) : paramInfo.ui === 'template-selector' ? (
                            <TemplateSelector
                              value={selectedTemplates}
                              onChange={(templateIds) => {
                                setSelectedTemplates(Array.isArray(templateIds) ? templateIds : [])
                                // We don't set the functionParams here yet - we'll encode it on submit
                              }}
                              onViewDetails={(templateName) => {
                                setTemplateToView(templateName)
                                setShowTemplateDetails(true)
                              }}
                              multiple={true}
                            />
                          ) : paramInfo.ui === 'checkbox' && paramInfo.checkboxOptions ? (
                            <CheckboxGroupStack>
                              {paramInfo.checkboxOptions.map((option: { value: string; label: string }) => {
                                const selectedValues = getStringParam(paramName).split(' ').filter(Boolean)
                                const isChecked = selectedValues.includes(option.value)

                                return (
                                  <Checkbox
                                    key={option.value}
                                    checked={isChecked}
                                    onChange={(e) => {
                                      const updatedValues = e.target.checked
                                        ? Array.from(new Set([...selectedValues, option.value]))
                                        : selectedValues.filter(value => value !== option.value)

                                      setFunctionParams((prev) => ({
                                        ...prev,
                                        [paramName]: updatedValues.join(' ')
                                      }))
                                    }}
                                    data-testid={`function-modal-param-${paramName}-${option.value}`}
                                  >
                                    {t(`functions:checkboxOptions.${option.label}`)}
                                  </Checkbox>
                                )
                              })}
                              <AdditionalOptionsInput
                                value={getStringParam(paramName)}
                                onChange={(e) =>
                                  setFunctionParams((prev) => ({
                                    ...prev,
                                    [paramName]: e.target.value
                                  }))
                                }
                                placeholder={t('functions:additionalOptions')}
                                autoComplete="off"
                                data-testid={`function-modal-param-${paramName}-additional`}
                              />
                            </CheckboxGroupStack>
                          ) : (
                            <Input
                              value={getStringParam(paramName)}
                              onChange={(e) =>
                                setFunctionParams((prev) => ({
                                  ...prev,
                                  [paramName]: e.target.value
                                }))
                              }
                              placeholder={paramInfo.help || ''}
                              autoComplete="off"
                              data-testid={`function-modal-param-${paramName}`}
                            />
                          )}
                        </Form.Item>
                      )
                    })}
                  
                  {/* Priority - Hidden when function is preselected */}
                  {!preselectedFunction && (
                    <Form.Item
                      label={
                        <Space size={4}>
                          {t('functions:priority')}
                          <Popover
                            content={
                              <PriorityPopoverContent>
                                <PriorityPopoverHeader>
                                  {t('functions:priorityPopoverLevels')}
                                </PriorityPopoverHeader>
                                {priorityLegendItems.map((item) => (
                                  <PriorityLegendRow key={item.level}>
                                    <PriorityLegendTag $level={item.level}>
                                      P{item.level} ({item.label})
                                    </PriorityLegendTag>
                                    <PriorityLegendText>{item.description}</PriorityLegendText>
                                  </PriorityLegendRow>
                                ))}
                              </PriorityPopoverContent>
                            }
                            title={t('functions:priorityPopoverTitle')}
                            trigger="click"
                          >
                            <PriorityHelpIcon />
                          </Popover>
                        </Space>
                      }
                      help={t('functions:priorityHelp')}
                    >
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
                      <PriorityTagWrapper>
                        <PriorityStatusTag
                          $priority={functionPriority}
                          icon={functionPriority === 1 ? <ExclamationCircleOutlined /> : undefined}
                        >
                          {t('functions:currentPriority')}: {
                            functionPriority === 1 ? t('functions:priorityHighest') :
                            functionPriority === 2 ? t('functions:priorityHigh') :
                            functionPriority === 3 ? t('functions:priorityNormal') :
                            functionPriority === 4 ? t('functions:priorityBelowNormal') :
                            t('functions:priorityLow')
                          } ({functionPriority})
                        </PriorityStatusTag>
                      </PriorityTagWrapper>
                      {functionPriority && (
                        <PriorityAlert
                          message={
                            functionPriority === 1 ? t('functions:priorityHighestTimeout') :
                            functionPriority === 2 ? t('functions:priorityHighWarning') :
                            functionPriority === 3 ? t('functions:priorityNormalWarning') :
                            functionPriority === 4 ? t('functions:priorityLowWarning') :
                            t('functions:priorityLowestWarning')
                          }
                          description={
                            functionPriority === 1 ? (
                              <>
                                <PriorityAlertNote>{t('functions:priorityHighestTimeoutWarning')}</PriorityAlertNote>
                                <PriorityAlertDetail>{t('functions:priorityHighestDescription')}</PriorityAlertDetail>
                              </>
                            ) :
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
                        />
                        )}
                    </Form.Item>
                  )}
                </Form>
              </ConfigCard>
            </ContentStack>
          ) : (
            <ConfigCard>
              <Empty description={t('functions:selectFunctionToConfigure')} />
            </ConfigCard>
          )}
        </Col>
      </Row>
    </StyledModal>

    {/* Template Preview Modal */}
    <TemplatePreviewModal
      visible={showTemplateDetails}
      template={null}
      templateName={templateToView}
      onClose={() => {
        setShowTemplateDetails(false)
        setTemplateToView(null)
      }}
      onUseTemplate={(templateName) => {
        const templateId = typeof templateName === 'string' ? templateName : templateName.name
        // Add to selection if not already selected
        if (!selectedTemplates.includes(templateId)) {
          setSelectedTemplates([...selectedTemplates, templateId])
        }
        setShowTemplateDetails(false)
        setTemplateToView(null)
      }}
      context="repo-creation"
    />
    </>
  )
}

export default FunctionSelectionModal


