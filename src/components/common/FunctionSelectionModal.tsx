import React, { useState, useMemo } from 'react'
import { Modal, Row, Col, Card, Input, Space, Form, Slider, Empty, Typography, Tag, Button, Select } from 'antd'
import { ExclamationCircleOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import type { QueueFunction } from '@/api/queries/queue'
import functionsData from '@/data/functions.json'

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
  
  const [selectedFunction, setSelectedFunction] = useState<QueueFunction | null>(null)
  const [functionParams, setFunctionParams] = useState<Record<string, any>>({})
  const [functionPriority, setFunctionPriority] = useState(5)
  const [functionDescription, setFunctionDescription] = useState('')
  const [functionSearchTerm, setFunctionSearchTerm] = useState('')
  const [selectedMachine, setSelectedMachine] = useState<string>('')

  // Filter functions based on allowed categories and search term
  const filteredFunctions = useMemo(() => {
    let functions = Object.values(functionsData.functions) as QueueFunction[]
    
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
  }, [allowedCategories, functionSearchTerm])

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
    
    // Merge visible params with default params
    const allParams = { ...defaultParams, ...functionParams }
    
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
                  <Text strong style={{ display: 'block', marginBottom: 8 }}>{category}</Text>
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
                        {t(`functions.${func.name}.description`, func.description)}
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
                  {t(`functions.${selectedFunction.name}.description`, selectedFunction.description)}
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
                    .map(([paramName, paramInfo]) => (
                    <Form.Item
                      key={paramName}
                      label={t(`functions.${selectedFunction.name}.params.${paramName}.label`, { defaultValue: paramName })}
                      required={paramInfo.required}
                      help={t(`functions.${selectedFunction.name}.params.${paramName}.help`, { defaultValue: paramInfo.help || '' })}
                    >
                      <Input
                        value={functionParams[paramName] || ''}
                        onChange={(e) => setFunctionParams({
                          ...functionParams,
                          [paramName]: e.target.value
                        })}
                        placeholder={t(`functions.${selectedFunction.name}.params.${paramName}.help`, { defaultValue: paramInfo.help || '' })}
                      />
                    </Form.Item>
                  ))}
                  
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