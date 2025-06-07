import React, { useState } from 'react'
import { Typography, Button, Space, Modal, Input, Select, Form, Slider, Card, Tag, Badge, Tabs, Row, Col, Statistic, Empty, Tooltip } from 'antd'
import { PlusOutlined, ThunderboltOutlined, DesktopOutlined, ApiOutlined, PlayCircleOutlined, PauseCircleOutlined, CheckCircleOutlined, CloseCircleOutlined, ExclamationCircleOutlined } from '@ant-design/icons'
import { useQueueItems, useCreateQueueItem, QUEUE_FUNCTIONS, QueueFunction } from '@/api/queries/queue'
import { useDropdownData } from '@/api/queries/useDropdownData'
import ResourceListView from '@/components/common/ResourceListView'
import toast from 'react-hot-toast'
import { useTranslation } from 'react-i18next'

const { Title, Text, Paragraph } = Typography
const { Search } = Input

const QueuePage: React.FC = () => {
  const { t } = useTranslation('functions')
  const [isAddModalOpen, setIsAddModalOpen] = useState(false)
  const [selectedFunction, setSelectedFunction] = useState<QueueFunction | null>(null)
  const [selectedTeam, setSelectedTeam] = useState<string>('')
  const [selectedMachine, setSelectedMachine] = useState<string>('')
  const [functionParams, setFunctionParams] = useState<Record<string, any>>({})
  const [priority, setPriority] = useState(3)
  const [description, setDescription] = useState('')
  const [searchTerm, setSearchTerm] = useState('')
  const [viewTeam, setViewTeam] = useState<string>('') // Team for viewing queue items
  
  const { data: queueItems, isLoading } = useQueueItems(viewTeam)
  const { data: dropdownData } = useDropdownData()
  const createQueueItemMutation = useCreateQueueItem()

  // Group functions by category
  const functionsByCategory = Object.values(QUEUE_FUNCTIONS).reduce((acc, func) => {
    if (!acc[func.category]) {
      acc[func.category] = []
    }
    acc[func.category].push(func)
    return acc
  }, {} as Record<string, QueueFunction[]>)

  // Filter functions by search
  const filteredFunctions = Object.entries(functionsByCategory).reduce((acc, [category, funcs]) => {
    const filtered = funcs.filter(func => 
      func.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      func.description.toLowerCase().includes(searchTerm.toLowerCase())
    )
    if (filtered.length > 0) {
      acc[category] = filtered
    }
    return acc
  }, {} as Record<string, QueueFunction[]>)

  const handleAddToQueue = async () => {
    if (!selectedFunction || !selectedTeam || !selectedMachine) {
      toast.error('Please select a function, team, and machine')
      return
    }

    // Find the bridge for the selected machine
    const machineData = dropdownData?.machinesByTeam
      ?.find(t => t.teamName === selectedTeam)
      ?.machines.find(m => m.value === selectedMachine)

    if (!machineData?.bridgeName) {
      toast.error('Could not find bridge for selected machine')
      return
    }

    // Build vault data
    const vaultData = {
      type: 'bash_function',
      function: selectedFunction.name,
      params: functionParams,
      description: description || selectedFunction.description,
      priority,
      bridge: machineData.bridgeName
    }

    try {
      await createQueueItemMutation.mutateAsync({
        teamName: selectedTeam,
        machineName: selectedMachine,
        bridgeName: machineData.bridgeName,
        queueVault: JSON.stringify(vaultData),
        priority: priority
      })
      
      setIsAddModalOpen(false)
      resetForm()
    } catch (error) {
      // Error handled by mutation
    }
  }

  const resetForm = () => {
    setSelectedFunction(null)
    setSelectedTeam('')
    setSelectedMachine('')
    setFunctionParams({})
    setPriority(3)
    setDescription('')
  }

  const queueColumns = [
    {
      title: 'Task ID',
      dataIndex: 'taskId',
      key: 'taskId',
      width: 200,
      render: (id: string) => <Text code>{id}</Text>
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: string) => {
        const statusConfig = {
          pending: { color: 'default', icon: <PauseCircleOutlined /> },
          processing: { color: 'processing', icon: <PlayCircleOutlined /> },
          completed: { color: 'success', icon: <CheckCircleOutlined /> },
          failed: { color: 'error', icon: <CloseCircleOutlined /> }
        }
        const config = statusConfig[status as keyof typeof statusConfig] || statusConfig.pending
        return (
          <Tag color={config.color} icon={config.icon}>
            {status.toUpperCase()}
          </Tag>
        )
      }
    },
    {
      title: 'Priority',
      dataIndex: 'priority',
      key: 'priority',
      width: 140,
      render: (priority: number) => {
        // Parse priority from vault data if needed
        const priorityValue = typeof priority === 'number' ? priority : 3
        
        const priorityConfig = {
          1: { color: 'red', label: 'High', icon: <ExclamationCircleOutlined /> },
          2: { color: 'orange', label: 'Above Normal' },
          3: { color: 'gold', label: 'Normal' },
          4: { color: 'blue', label: 'Below Normal' },
          5: { color: 'green', label: 'Low' }
        }
        
        const config = priorityConfig[priorityValue as keyof typeof priorityConfig] || priorityConfig[3]
        
        return (
          <Tooltip title={`Priority ${priorityValue} - ${config.label}`}>
            <Tag color={config.color} icon={config.icon}>
              {config.label} ({priorityValue})
            </Tag>
          </Tooltip>
        )
      },
      sorter: (a: any, b: any) => (a.priority || 3) - (b.priority || 3),
    },
    {
      title: 'Team',
      dataIndex: 'teamName',
      key: 'teamName',
    },
    {
      title: 'Machine',
      dataIndex: 'machineName',
      key: 'machineName',
      render: (name: string) => (
        <Space>
          <DesktopOutlined />
          {name}
        </Space>
      )
    },
    {
      title: 'Bridge',
      dataIndex: 'bridgeName',
      key: 'bridgeName',
      render: (name: string) => (
        <Space>
          <ApiOutlined />
          {name}
        </Space>
      )
    },
    {
      title: 'Created',
      dataIndex: 'createdAt',
      key: 'createdAt',
      render: (date: string) => new Date(date).toLocaleString()
    }
  ]

  // Machine options filtered by selected team
  const machineOptions = selectedTeam
    ? dropdownData?.machinesByTeam?.find(t => t.teamName === selectedTeam)?.machines || []
    : []

  return (
    <Space direction="vertical" size={24} style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={3}>Queue Management</Title>
        <Select
          style={{ width: 300 }}
          placeholder="Select a team to view queue items"
          value={viewTeam}
          onChange={setViewTeam}
          options={dropdownData?.teams || []}
          allowClear
        />
      </div>

      {/* Show message if no team selected */}
      {!viewTeam ? (
        <Card>
          <Empty 
            description="Please select a team to view queue items"
            style={{ padding: '40px 0' }}
          />
        </Card>
      ) : (
        <>
          {/* Queue Statistics */}
          <Row gutter={16}>
            <Col span={4}>
              <Card>
                <Statistic
                  title="Total Queue Items"
                  value={queueItems?.length || 0}
                  prefix={<ThunderboltOutlined />}
                />
              </Card>
            </Col>
            <Col span={4}>
              <Card>
                <Statistic
                  title="High Priority"
                  value={queueItems?.filter((item: any) => item.priority === 1).length || 0}
                  valueStyle={{ color: '#cf1322' }}
                  prefix={<ExclamationCircleOutlined />}
                />
              </Card>
            </Col>
            <Col span={4}>
              <Card>
                <Statistic
                  title="Pending"
                  value={queueItems?.filter((item: any) => item.status === 'pending').length || 0}
                />
              </Card>
            </Col>
            <Col span={4}>
              <Card>
                <Statistic
                  title="Processing"
                  value={queueItems?.filter((item: any) => item.status === 'processing').length || 0}
                  valueStyle={{ color: '#1890ff' }}
                />
              </Card>
            </Col>
            <Col span={4}>
              <Card>
                <Statistic
                  title="Completed"
                  value={queueItems?.filter((item: any) => item.status === 'completed').length || 0}
                  valueStyle={{ color: '#52c41a' }}
                />
              </Card>
            </Col>
            <Col span={4}>
              <Card>
                <Statistic
                  title="Failed"
                  value={queueItems?.filter((item: any) => item.status === 'failed').length || 0}
                  valueStyle={{ color: '#ff4d4f' }}
                />
              </Card>
            </Col>
          </Row>

          <Tabs defaultActiveKey="active">
            <Tabs.TabPane 
              tab={
                <Space>
                  <Badge count={queueItems?.filter((item: any) => item.status !== 'completed').length || 0}>
                    <span>Active Queue</span>
                  </Badge>
                </Space>
              } 
              key="active"
            >
              <ResourceListView
                loading={isLoading}
                data={queueItems?.filter((item: any) => item.status !== 'completed') || []}
                columns={queueColumns}
                rowKey="taskId"
                searchPlaceholder="Search queue items..."
                actions={
                  <Button 
                    type="primary" 
                    icon={<PlusOutlined />}
                    onClick={() => setIsAddModalOpen(true)}
                    style={{ background: '#556b2f', borderColor: '#556b2f' }}
                  >
                    Add Function to Queue
                  </Button>
                }
              />
            </Tabs.TabPane>
            
            <Tabs.TabPane tab="Completed" key="completed">
              <ResourceListView
                loading={isLoading}
                data={queueItems?.filter((item: any) => item.status === 'completed') || []}
                columns={queueColumns}
                rowKey="taskId"
                searchPlaceholder="Search completed items..."
              />
            </Tabs.TabPane>
          </Tabs>
        </>
      )}

      <Modal
        title="Add Function to Queue"
        open={isAddModalOpen}
        onCancel={() => {
          setIsAddModalOpen(false)
          resetForm()
        }}
        width={900}
        footer={[
          <Button key="cancel" onClick={() => {
            setIsAddModalOpen(false)
            resetForm()
          }}>
            Cancel
          </Button>,
          <Button
            key="submit"
            type="primary"
            onClick={handleAddToQueue}
            disabled={!selectedFunction || !selectedTeam || !selectedMachine}
            loading={createQueueItemMutation.isPending}
            style={{ background: '#556b2f', borderColor: '#556b2f' }}
          >
            Add to Queue
          </Button>
        ]}
      >
        <Row gutter={24}>
          <Col span={10}>
            <Card title="Available Functions" size="small">
              <Search
                placeholder="Search functions..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                style={{ marginBottom: 16 }}
              />
              <div style={{ maxHeight: 400, overflow: 'auto' }}>
                {Object.entries(filteredFunctions).map(([category, funcs]) => (
                  <div key={category} style={{ marginBottom: 16 }}>
                    <Title level={5} style={{ marginBottom: 8 }}>{t(`categories.${category}.name`)}</Title>
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
                        <Text type="secondary" style={{ fontSize: 12 }}>{t(`functions.${func.name}.description`)}</Text>
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
                <Card title={`Configure: ${selectedFunction.name}`} size="small">
                  <Paragraph>{t(`functions.${selectedFunction.name}.description`)}</Paragraph>
                  
                  <Form layout="vertical">
                    {/* Function Parameters */}
                    {Object.entries(selectedFunction.params).map(([paramName, paramInfo]) => (
                      <Form.Item
                        key={paramName}
                        label={paramName}
                        required={paramInfo.required}
                        help={t(`functions.${selectedFunction.name}.params.${paramName}.help`)}
                      >
                        <Input
                          value={functionParams[paramName] || ''}
                          onChange={(e) => setFunctionParams({
                            ...functionParams,
                            [paramName]: e.target.value
                          })}
                          placeholder={t(`functions.${selectedFunction.name}.params.${paramName}.help`)}
                        />
                      </Form.Item>
                    ))}
                    
                    {/* Team Selection */}
                    <Form.Item label="Team" required>
                      <Select
                        value={selectedTeam}
                        onChange={setSelectedTeam}
                        placeholder="Select team"
                        options={dropdownData?.teams || []}
                      />
                    </Form.Item>
                    
                    {/* Machine Selection */}
                    <Form.Item label="Machine" required>
                      <Select
                        value={selectedMachine}
                        onChange={setSelectedMachine}
                        placeholder="Select machine"
                        options={machineOptions}
                        disabled={!selectedTeam}
                      />
                    </Form.Item>
                    
                    {/* Priority */}
                    <Form.Item label="Priority" help="1 = Highest priority, 5 = Lowest priority">
                      <div>
                        <Slider
                          min={1}
                          max={5}
                          value={priority}
                          onChange={setPriority}
                          marks={{
                            1: 'High',
                            2: 'Above Normal',
                            3: 'Normal',
                            4: 'Below Normal',
                            5: 'Low'
                          }}
                          tooltip={{
                            formatter: (value?: number) => {
                              const labels = {
                                1: 'High',
                                2: 'Above Normal',
                                3: 'Normal',
                                4: 'Below Normal',
                                5: 'Low'
                              }
                              return value ? `${labels[value as keyof typeof labels]} (${value})` : ''
                            }
                          }}
                        />
                        <div style={{ textAlign: 'center', marginTop: 8 }}>
                          <Tag 
                            color={
                              priority === 1 ? 'red' :
                              priority === 2 ? 'orange' :
                              priority === 3 ? 'gold' :
                              priority === 4 ? 'blue' :
                              'green'
                            }
                            icon={priority === 1 ? <ExclamationCircleOutlined /> : undefined}
                          >
                            Current: {
                              priority === 1 ? 'High' :
                              priority === 2 ? 'Above Normal' :
                              priority === 3 ? 'Normal' :
                              priority === 4 ? 'Below Normal' :
                              'Low'
                            } ({priority})
                          </Tag>
                        </div>
                      </div>
                    </Form.Item>
                    
                    {/* Description */}
                    <Form.Item label="Description (optional)">
                      <Input.TextArea
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                        placeholder="Add a custom description for this queue item"
                        rows={2}
                      />
                    </Form.Item>
                  </Form>
                </Card>
              </Space>
            ) : (
              <Card>
                <Empty description="Select a function to configure" />
              </Card>
            )}
          </Col>
        </Row>
      </Modal>
    </Space>
  )
}

export default QueuePage