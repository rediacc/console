import React, { useState, useMemo, useEffect } from 'react'
import { Modal, Row, Col, Card, Input, Space, Form, Slider, Empty, Typography, Tag, Button, Select, Tooltip, InputNumber, Alert } from 'antd'
import { ExclamationCircleOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import type { QueueFunction } from '@/api/queries/queue'
import { useLocalizedFunctions } from '@/services/functionsService'

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
  defaultParams = {}
}) => {
  const { t } = useTranslation(['functions', 'common', 'machines'])
  const { functions: localizedFunctions, categories } = useLocalizedFunctions()
  
  const [selectedFunction, setSelectedFunction] = useState<QueueFunction | null>(null)
  const [functionParams, setFunctionParams] = useState<Record<string, any>>({})
  const [functionPriority, setFunctionPriority] = useState(5)
  const [functionDescription, setFunctionDescription] = useState('')
  const [functionSearchTerm, setFunctionSearchTerm] = useState('')
  const [selectedMachine, setSelectedMachine] = useState<string>('')

  // Initialize parameters when function is selected
  useEffect(() => {
    if (selectedFunction) {
      const initialParams: Record<string, any> = {}
      
      Object.entries(selectedFunction.params).forEach(([paramName, paramInfo]) => {
        if (paramInfo.format === 'size' && paramInfo.units) {
          // Initialize with default values for size parameters
          if (paramInfo.default) {
            const match = paramInfo.default.match(/^(\d+)([%GT]?)$/)
            if (match) {
              const [, value, unit] = match
              initialParams[`${paramName}_value`] = parseInt(value)
              initialParams[`${paramName}_unit`] = unit || (paramInfo.units[0] === 'percentage' ? '%' : paramInfo.units[0])
              initialParams[paramName] = paramInfo.default
            }
          } else {
            // Set default unit
            const defaultUnit = paramInfo.units[0] === 'percentage' ? '%' : paramInfo.units[0]
            initialParams[`${paramName}_unit`] = defaultUnit
          }
        } else if (paramInfo.options && paramInfo.options.length > 0) {
          // Initialize dropdown parameters with default value
          initialParams[paramName] = paramInfo.default || paramInfo.options[0]
        } else if (paramInfo.default) {
          // Initialize other parameters with default value
          initialParams[paramName] = paramInfo.default
        }
      })
      
      setFunctionParams(initialParams)
    }
  }, [selectedFunction])

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

  const handleSubmit = () => {
    if (!selectedFunction) return
    if (showMachineSelection && !selectedMachine) return
    
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
    setFunctionPriority(5)
    setFunctionDescription('')
    setFunctionSearchTerm('')
    setSelectedMachine('')
  }

  const handleCancel = () => {
    // Reset form
    setSelectedFunction(null)
    setFunctionParams({})
    setFunctionPriority(5)
    setFunctionDescription('')
    setFunctionSearchTerm('')
    setSelectedMachine('')
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
      width={900}
      footer={[
        <Button key="cancel" onClick={handleCancel}>
          {t('common:actions.cancel')}
        </Button>,
        <Button
          key="submit"
          type="primary"
          onClick={handleSubmit}
          disabled={!selectedFunction || (showMachineSelection && !selectedMachine)}
          loading={loading}
          style={{ background: '#556b2f', borderColor: '#556b2f' }}
        >
          {t('common:actions.addToQueue')}
        </Button>
      ]}
    >
      <Row gutter={24}>
        <Col span={10}>
          <Card title={t('functions:availableFunctions')} size="small">
            <Search
              placeholder={t('functions:searchFunctions')}
              value={functionSearchTerm}
              onChange={(e) => setFunctionSearchTerm(e.target.value)}
              style={{ marginBottom: 16 }}
            />
            <div style={{ maxHeight: 400, overflow: 'auto' }}>
              {Object.entries(functionsByCategory).map(([category, funcs]) => (
                <div key={category} style={{ marginBottom: 16 }}>
                  <Text strong style={{ display: 'block', marginBottom: 8 }}>{categories[category]?.name || category}</Text>
                  {funcs.map(func => (
                    <div
                      key={func.name}
                      onClick={() => setSelectedFunction(func)}
                      style={{
                        padding: '8px 12px',
                        marginBottom: 4,
                        cursor: 'pointer',
                        borderRadius: 4,
                        backgroundColor: selectedFunction?.name === func.name ? '#f0f5ff' : 'transparent',
                        border: selectedFunction?.name === func.name ? '1px solid #1890ff' : '1px solid transparent'
                      }}
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
        
        <Col span={14}>
          {selectedFunction ? (
            <Space direction="vertical" size={16} style={{ width: '100%' }}>
              <Card title={`${t('functions:configure')}: ${selectedFunction.name}`} size="small">
                <Paragraph>
                  {selectedFunction.description}
                </Paragraph>
                
                <Form layout="horizontal" labelCol={{ span: 8 }} wrapperCol={{ span: 16 }}>
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
                                  setFunctionParams({
                                    ...functionParams,
                                    [`${paramName}_value`]: value,
                                    [paramName]: `${value || ''}${functionParams[`${paramName}_unit`] || (paramInfo.units[0] === 'percentage' ? '%' : paramInfo.units[0])}`
                                  })
                                }}
                                placeholder={paramInfo.units.includes('percentage') ? '95' : '100'}
                                min={1}
                                max={paramInfo.units.includes('percentage') ? 100 : undefined}
                              />
                              <Select
                                style={{ width: '35%' }}
                                value={functionParams[`${paramName}_unit`] || (paramInfo.units[0] === 'percentage' ? '%' : paramInfo.units[0])}
                                onChange={(unit) => {
                                  setFunctionParams({
                                    ...functionParams,
                                    [`${paramName}_unit`]: unit,
                                    [paramName]: `${functionParams[`${paramName}_value`] || ''}${unit}`
                                  })
                                }}
                                options={paramInfo.units.map(unit => ({
                                  value: unit === 'percentage' ? '%' : unit,
                                  label: unit === 'percentage' ? '%' : unit === 'G' ? 'GB' : 'TB'
                                }))}
                              />
                            </Space.Compact>
                          ) : paramInfo.options && paramInfo.options.length > 0 ? (
                            <Select
                              value={functionParams[paramName] || paramInfo.default || ''}
                              onChange={(value) => setFunctionParams({
                                ...functionParams,
                                [paramName]: value
                              })}
                              placeholder={paramInfo.help || ''}
                              options={paramInfo.options.map(option => ({
                                value: option,
                                label: option
                              }))}
                            />
                          ) : (
                            <Input
                              value={functionParams[paramName] || ''}
                              onChange={(e) => setFunctionParams({
                                ...functionParams,
                                [paramName]: e.target.value
                              })}
                              placeholder={paramInfo.help || ''}
                            />
                          )}
                        </Form.Item>
                      )
                    })}
                  
                  {/* Priority */}
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
                              1: t('functions:priorityHigh'),
                              2: t('functions:priorityAboveNormal'),
                              3: t('functions:priorityNormal'),
                              4: t('functions:priorityBelowNormal'),
                              5: t('functions:priorityLow')
                            }
                            return value ? `${labels[value as keyof typeof labels]} (${value})` : ''
                          }
                        }}
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
                            functionPriority === 1 ? t('functions:priorityHigh') :
                            functionPriority === 2 ? t('functions:priorityAboveNormal') :
                            functionPriority === 3 ? t('functions:priorityNormal') :
                            functionPriority === 4 ? t('functions:priorityBelowNormal') :
                            t('functions:priorityLow')
                          } ({functionPriority})
                        </Tag>
                      </div>
                      {(functionPriority === 1 || functionPriority === 2) && (
                        <Alert
                          message={t('functions:priorityHighWarning')}
                          description={t('functions:priorityHighWarningDescription')}
                          type="warning"
                          showIcon
                          icon={<ExclamationCircleOutlined />}
                          style={{ marginTop: 16 }}
                        />
                      )}
                    </div>
                  </Form.Item>
                  
                  {/* Description */}
                  <Form.Item label={t('functions:description')}>
                    <Input.TextArea
                      value={functionDescription}
                      onChange={(e) => setFunctionDescription(e.target.value)}
                      placeholder={t('functions:descriptionPlaceholder')}
                      rows={2}
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