import React, { useState, useEffect } from 'react'
import { Modal, Button, Space, Typography, Card, Descriptions, Tag, Timeline, Empty, Spin, Row, Col, Tabs, Switch, Collapse, Steps, Progress } from 'antd'
import { ReloadOutlined, HistoryOutlined, FileTextOutlined, BellOutlined, ClockCircleOutlined, CheckCircleOutlined, CloseCircleOutlined, SyncOutlined, RightOutlined } from '@ant-design/icons'
import { useQueueItemTrace } from '@/api/queries/queue'
import dayjs from 'dayjs'
import { SimpleJsonEditor } from './SimpleJsonEditor'
import { queueMonitoringService } from '@/services/queueMonitoringService'
import { showMessage } from '@/utils/messages'
import { useTheme } from '@/context/ThemeContext'
import './QueueItemTraceModal.css'

const { Text, Title } = Typography
const { Panel } = Collapse
const { Step } = Steps

// Helper function to normalize property names from API responses
const normalizeProperty = <T extends Record<string, any>>(obj: T, ...propertyNames: string[]): any => {
  if (!obj) return null
  for (const prop of propertyNames) {
    if (obj[prop] !== undefined && obj[prop] !== null) {
      return obj[prop]
    }
  }
  return null
}

interface QueueItemTraceModalProps {
  taskId: string | null
  visible: boolean
  onClose: () => void
}

const QueueItemTraceModal: React.FC<QueueItemTraceModalProps> = ({ taskId, visible, onClose }) => {
  const [lastTraceFetchTime, setLastTraceFetchTime] = useState<dayjs.Dayjs | null>(null)
  const [isMonitoring, setIsMonitoring] = useState(false)
  const [activeKeys, setActiveKeys] = useState<string[]>([]) // Start with all panels collapsed
  const [simpleMode, setSimpleMode] = useState(true) // Start in simple mode
  const { data: traceData, isLoading: isTraceLoading, refetch: refetchTrace } = useQueueItemTrace(taskId, visible)
  const { theme } = useTheme()

  // Update last fetch time when trace data is loaded
  useEffect(() => {
    if (traceData && visible) {
      setLastTraceFetchTime(dayjs())
    }
  }, [traceData, visible])

  // Reset last fetch time when modal is opened with new taskId
  useEffect(() => {
    if (visible && taskId) {
      setLastTraceFetchTime(null)
      // Check if this task is already being monitored
      setIsMonitoring(queueMonitoringService.isTaskMonitored(taskId))
      // Reset collapsed state and simple mode when opening modal
      setActiveKeys([])
      setSimpleMode(true)
    }
  }, [taskId, visible])

  const handleRefreshTrace = async () => {
    await refetchTrace()
  }

  const handleToggleMonitoring = () => {
    if (!taskId || !traceData?.queueDetails) return

    const status = normalizeProperty(traceData.queueDetails, 'status', 'Status')
    
    // Don't allow monitoring completed, cancelled, or failed tasks
    if (status === 'COMPLETED' || status === 'CANCELLED' || status === 'FAILED') {
      showMessage('warning', 'Cannot monitor completed, cancelled, or failed tasks')
      return
    }

    if (isMonitoring) {
      queueMonitoringService.removeTask(taskId)
      setIsMonitoring(false)
      showMessage('info', 'Background monitoring disabled for this task')
    } else {
      const teamName = traceData.queueDetails.teamName || ''
      const machineName = traceData.queueDetails.machineName || ''
      queueMonitoringService.addTask(taskId, teamName, machineName, status)
      setIsMonitoring(true)
      showMessage('success', 'Background monitoring enabled. You will be notified when the task status changes.')
    }
  }

  const handleClose = () => {
    // If task is still active and monitoring is enabled, remind user
    if (taskId && isMonitoring && traceData?.queueDetails) {
      const status = normalizeProperty(traceData.queueDetails, 'status', 'Status')
      if (status !== 'COMPLETED' && status !== 'CANCELLED' && status !== 'FAILED') {
        showMessage('info', `Task ${taskId} will continue to be monitored in the background`)
      }
    }
    onClose()
  }

  // Helper function to get simplified status
  const getSimplifiedStatus = () => {
    if (!traceData?.queueDetails) return { status: 'unknown', color: 'default', icon: null }
    const status = normalizeProperty(traceData.queueDetails, 'status', 'Status')
    
    switch (status) {
      case 'COMPLETED':
        return { status: 'Completed', color: 'success', icon: <CheckCircleOutlined /> }
      case 'FAILED':
        return { status: 'Failed', color: 'error', icon: <CloseCircleOutlined /> }
      case 'CANCELLED':
        return { status: 'Cancelled', color: 'error', icon: <CloseCircleOutlined /> }
      case 'PROCESSING':
        return { status: 'Processing', color: 'processing', icon: <SyncOutlined spin /> }
      case 'ASSIGNED':
        return { status: 'Assigned', color: 'blue', icon: <ClockCircleOutlined /> }
      default:
        return { status: status || 'Pending', color: 'default', icon: <ClockCircleOutlined /> }
    }
  }

  // Helper function to calculate progress percentage
  const getProgressPercentage = () => {
    if (!traceData?.queueDetails) return 0
    const status = normalizeProperty(traceData.queueDetails, 'status', 'Status')
    
    switch (status) {
      case 'COMPLETED':
        return 100
      case 'FAILED':
      case 'CANCELLED':
        return 100
      case 'PROCESSING':
        return 60
      case 'ASSIGNED':
        return 30
      default:
        return 10
    }
  }

  // Get current step for Steps component
  const getCurrentStep = () => {
    if (!traceData?.queueDetails) return 0
    const status = normalizeProperty(traceData.queueDetails, 'status', 'Status')
    
    switch (status) {
      case 'COMPLETED':
        return 3
      case 'FAILED':
      case 'CANCELLED':
        return -1
      case 'PROCESSING':
        return 2
      case 'ASSIGNED':
        return 1
      default:
        return 0
    }
  }

  return (
    <Modal
      title={
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
          <Space>
            <HistoryOutlined />
            {`Queue Item Trace - ${taskId || ''}`}
          </Space>
          <Space>
            <Switch
              checked={!simpleMode}
              onChange={(checked) => setSimpleMode(!checked)}
              checkedChildren="Detailed"
              unCheckedChildren="Simple"
              style={{ marginRight: 16 }}
            />
            {lastTraceFetchTime && (
              <Text type="secondary" style={{ fontSize: '14px' }}>
                Last fetched: {lastTraceFetchTime.format('HH:mm:ss')}
              </Text>
            )}
          </Space>
        </div>
      }
      open={visible}
      onCancel={handleClose}
      width={900}
      footer={[
        traceData?.queueDetails && (
          <div key="monitor-switch" style={{ float: 'left', marginRight: 'auto' }}>
            <Space>
              <BellOutlined />
              <Switch
                checked={isMonitoring}
                onChange={handleToggleMonitoring}
                disabled={
                  !traceData?.queueDetails ||
                  normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'COMPLETED' ||
                  normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'CANCELLED' ||
                  normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'FAILED'
                }
              />
              <Text type="secondary">Background Monitoring</Text>
            </Space>
          </div>
        ),
        <Button 
          key="refresh" 
          icon={<ReloadOutlined />} 
          onClick={handleRefreshTrace}
          loading={isTraceLoading}
        >
          Refresh
        </Button>,
        <Button key="close" onClick={handleClose}>
          Close
        </Button>
      ]}
    >
      {isTraceLoading ? (
        <div className="queue-trace-loading">
          <Spin size="large" />
        </div>
      ) : traceData ? (
        <div>
          {/* Simple Progress Overview */}
          {traceData.queueDetails && (
            <Card 
              style={{ 
                marginBottom: 16, 
                background: theme === 'dark' ? '#1f1f1f' : '#f0f2f5',
                border: `1px solid ${theme === 'dark' ? '#303030' : '#e8e8e8'}`
              }}
            >
              <Space direction="vertical" size="large" style={{ width: '100%' }}>
                {/* Status Summary */}
                <div style={{ textAlign: 'center' }}>
                  <Space size="large">
                    <span className={`queue-trace-status-icon ${getSimplifiedStatus().status === 'Processing' ? 'processing' : ''}`}>
                      {getSimplifiedStatus().icon}
                    </span>
                    <Title level={3} style={{ margin: 0 }}>
                      Task {getSimplifiedStatus().status}
                    </Title>
                  </Space>
                </div>

                {/* Progress Bar */}
                <Progress
                  className="queue-trace-progress" 
                  percent={getProgressPercentage()} 
                  status={
                    getSimplifiedStatus().status === 'Failed' || getSimplifiedStatus().status === 'Cancelled' ? 'exception' :
                    getSimplifiedStatus().status === 'Completed' ? 'success' : 'active'
                  }
                  strokeColor={{
                    '0%': '#108ee9',
                    '100%': getSimplifiedStatus().status === 'Failed' || getSimplifiedStatus().status === 'Cancelled' ? '#ff4d4f' : '#87d068'
                  }}
                />

                {/* Steps */}
                <Steps
                  className="queue-trace-steps" 
                  current={getCurrentStep()} 
                  status={getCurrentStep() === -1 ? 'error' : undefined}
                  size="small"
                >
                  <Step title="Created" description={traceData.queueDetails.createdTime ? dayjs(traceData.queueDetails.createdTime).format('HH:mm:ss') : ''} />
                  <Step title="Assigned" description={traceData.queueDetails.assignedTime ? dayjs(traceData.queueDetails.assignedTime).format('HH:mm:ss') : 'Waiting'} />
                  <Step title="Processing" description={normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'PROCESSING' ? 'In Progress' : ''} />
                  <Step 
                    title="Completed" 
                    description={
                      normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'COMPLETED' ? 'Done' :
                      normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'FAILED' ? 'Failed' :
                      normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'CANCELLED' ? 'Cancelled' : ''
                    }
                  />
                </Steps>

                {/* Key Info */}
                <Row gutter={[16, 16]} style={{ textAlign: 'center' }}>
                  <Col span={8}>
                    <div className="queue-trace-key-info" style={{ padding: '12px', borderRadius: '8px', background: theme === 'dark' ? '#262626' : '#fafafa' }}>
                      <Text type="secondary">Duration</Text>
                      <div>
                        <Text strong style={{ fontSize: '18px' }}>
                          {Math.floor(traceData.queueDetails.totalDurationSeconds / 60)}m
                        </Text>
                      </div>
                    </div>
                  </Col>
                  <Col span={8}>
                    <div className="queue-trace-key-info" style={{ padding: '12px', borderRadius: '8px', background: theme === 'dark' ? '#262626' : '#fafafa' }}>
                      <Text type="secondary">Machine</Text>
                      <div>
                        <Text strong>{traceData.queueDetails.machineName}</Text>
                      </div>
                    </div>
                  </Col>
                  <Col span={8}>
                    <div className="queue-trace-key-info" style={{ padding: '12px', borderRadius: '8px', background: theme === 'dark' ? '#262626' : '#fafafa' }}>
                      <Text type="secondary">Priority</Text>
                      <div>
                        <Tag color={traceData.queueDetails.priorityLabel === 'High' ? 'red' : 'default'}>
                          {traceData.queueDetails.priorityLabel || 'Normal'}
                        </Tag>
                      </div>
                    </div>
                  </Col>
                </Row>
              </Space>
            </Card>
          )}

          {/* Collapsible Sections */}
          {!simpleMode && (
            <div style={{ marginTop: 16 }}>
              <Text type="secondary" style={{ fontSize: '12px', display: 'block', marginBottom: 8 }}>
                Click on any section below to view more details
              </Text>
              <Collapse 
              className="queue-trace-collapse"
              activeKey={activeKeys}
              onChange={setActiveKeys}
              expandIcon={({ isActive }) => <RightOutlined rotate={isActive ? 90 : 0} />}
            >
            {/* Queue Details Panel */}
            {traceData.queueDetails && (
              <Panel header="Detailed Information" key="details">
                <Descriptions column={2} size="small">
                <Descriptions.Item label="Task ID">
                  <Text code>{normalizeProperty(traceData.queueDetails, 'taskId', 'TaskId')}</Text>
                </Descriptions.Item>
                <Descriptions.Item label="Status">
                  <Tag color={
                    normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'COMPLETED' ? 'success' :
                    normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'CANCELLED' ? 'error' :
                    normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'FAILED' ? 'error' :
                    normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'PROCESSING' ? 'processing' :
                    normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'ASSIGNED' ? 'blue' :
                    'default'
                  }>
                    {normalizeProperty(traceData.queueDetails, 'status', 'Status')}
                  </Tag>
                </Descriptions.Item>
                <Descriptions.Item label="Priority">
                  {traceData.queueDetails.priorityLabel || '-'}
                </Descriptions.Item>
                <Descriptions.Item label="Machine">
                  {traceData.queueDetails.machineName}
                </Descriptions.Item>
                <Descriptions.Item label="Team">
                  {traceData.queueDetails.teamName}
                </Descriptions.Item>
                <Descriptions.Item label="Bridge">
                  {traceData.queueDetails.bridgeName}
                </Descriptions.Item>
                <Descriptions.Item label="Region">
                  {traceData.queueDetails.regionName}
                </Descriptions.Item>
                <Descriptions.Item label="Created">
                  {dayjs(traceData.queueDetails.createdTime).format('YYYY-MM-DD HH:mm:ss')}
                </Descriptions.Item>
                {traceData.queueDetails.assignedTime && (
                  <Descriptions.Item label="Assigned">
                    {dayjs(traceData.queueDetails.assignedTime).format('YYYY-MM-DD HH:mm:ss')}
                  </Descriptions.Item>
                )}
                {traceData.queueDetails.lastHeartbeat && (
                  <Descriptions.Item label="Last Heartbeat">
                    {dayjs(traceData.queueDetails.lastHeartbeat).format('YYYY-MM-DD HH:mm:ss')}
                  </Descriptions.Item>
                )}
                <Descriptions.Item label="Total Duration">
                  {Math.floor(traceData.queueDetails.totalDurationSeconds / 60)} minutes
                </Descriptions.Item>
                {traceData.queueDetails.processingDurationSeconds && (
                  <Descriptions.Item label="Processing Duration">
                    {Math.floor(traceData.queueDetails.processingDurationSeconds / 60)} minutes
                  </Descriptions.Item>
                )}
                <Descriptions.Item label="Created By">
                  {normalizeProperty(traceData.queueDetails, 'createdBy', 'CreatedBy') || '-'}
                </Descriptions.Item>
                <Descriptions.Item label="Retry Count">
                  <Tag color={
                    normalizeProperty(traceData.queueDetails, 'retryCount', 'RetryCount') === 0 ? 'green' :
                    normalizeProperty(traceData.queueDetails, 'retryCount', 'RetryCount') < 3 ? 'orange' : 'red'
                  }>
                    {normalizeProperty(traceData.queueDetails, 'retryCount', 'RetryCount') || 0}/3
                  </Tag>
                </Descriptions.Item>
                {normalizeProperty(traceData.queueDetails, 'lastFailureReason', 'LastFailureReason') && (
                  <Descriptions.Item label="Last Failure Reason" span={2}>
                    <Text type="warning">{normalizeProperty(traceData.queueDetails, 'lastFailureReason', 'LastFailureReason')}</Text>
                  </Descriptions.Item>
                )}
              </Descriptions>
              </Panel>
            )}

            {/* Trace Logs Panel */}
            {traceData.traceLogs && traceData.traceLogs.length > 0 && (
              <Panel header="Activity Timeline" key="timeline">
                <Timeline mode="left" className="queue-trace-timeline">
                {traceData.traceLogs.map((log: any, index: number) => {
                  const action = normalizeProperty(log, 'action', 'Action')
                  const timestamp = normalizeProperty(log, 'timestamp', 'Timestamp')
                  const details = normalizeProperty(log, 'details', 'Details') || ''
                  const actionByUser = normalizeProperty(log, 'actionByUser', 'ActionByUser') || ''

                  // Determine timeline item color based on action type
                  let color = 'gray'
                  if (action === 'QUEUE_ITEM_CREATED') color = 'green'
                  else if (action === 'QUEUE_ITEM_ASSIGNED') color = 'blue'
                  else if (action === 'QUEUE_ITEM_PROCESSING' || action === 'QUEUE_ITEM_RESPONSE_UPDATED') color = 'orange'
                  else if (action === 'QUEUE_ITEM_COMPLETED') color = 'green'
                  else if (action === 'QUEUE_ITEM_CANCELLED') color = 'red'
                  else if (action === 'QUEUE_ITEM_FAILED') color = 'red'
                  else if (action === 'QUEUE_ITEM_RETRY') color = 'orange'
                  else if (action.includes('ERROR') || action.includes('FAILED')) color = 'red'

                  return (
                    <Timeline.Item key={index} color={color}>
                      <Space direction="vertical" size={0}>
                        <Text strong>{action.replace('QUEUE_ITEM_', '').replace(/_/g, ' ')}</Text>
                        <Text type="secondary">{dayjs(timestamp).format('YYYY-MM-DD HH:mm:ss')}</Text>
                        {details && <Text>{details}</Text>}
                        {actionByUser && <Text type="secondary">By: {actionByUser}</Text>}
                      </Space>
                    </Timeline.Item>
                  )
                })}
              </Timeline>
              </Panel>
            )}

            {/* Vault Content Panel */}
            {(traceData.vaultContent || traceData.responseVaultContent) && (
              <Panel header="Vault Content" key="vault">
                <Tabs
                items={[
                  {
                    key: 'request',
                    label: (
                      <Space>
                        <FileTextOutlined />
                        Request Vault
                      </Space>
                    ),
                    children: traceData.vaultContent && traceData.vaultContent.hasContent ? (
                      (() => {
                        try {
                          const content = typeof traceData.vaultContent.vaultContent === 'string' 
                            ? JSON.parse(traceData.vaultContent.vaultContent) 
                            : traceData.vaultContent.vaultContent || {}
                          return (
                            <SimpleJsonEditor
                              value={JSON.stringify(content, null, 2)}
                              readOnly={true}
                              height="300px"
                            />
                          )
                        } catch (error) {
                          console.error('Failed to parse request vault content:', error)
                          return <Empty description="Invalid request vault content format" />
                        }
                      })()
                    ) : (
                      <Empty description="No request vault content" />
                    ),
                  },
                  ...(traceData.responseVaultContent && traceData.responseVaultContent.hasContent ? [{
                    key: 'response',
                    label: (
                      <Space>
                        <FileTextOutlined />
                        Response Vault
                      </Space>
                    ),
                    children: (
                      (() => {
                        try {
                          const content = typeof traceData.responseVaultContent.vaultContent === 'string' 
                            ? JSON.parse(traceData.responseVaultContent.vaultContent) 
                            : traceData.responseVaultContent.vaultContent || {}
                          return (
                            <SimpleJsonEditor
                              value={JSON.stringify(content, null, 2)}
                              readOnly={true}
                              height="300px"
                            />
                          )
                        } catch (error) {
                          console.error('Failed to parse response vault content:', error)
                          return <Empty description="Invalid response vault content format" />
                        }
                      })()
                    ),
                  }] : []),
                  ...(traceData.responseVaultContent && traceData.responseVaultContent.hasContent ? [{
                    key: 'console',
                    label: (
                      <Space>
                        <FileTextOutlined />
                        Response (Console)
                      </Space>
                    ),
                    children: (
                      (() => {
                        try {
                          // Parse the vault content
                          const vaultContent = typeof traceData.responseVaultContent.vaultContent === 'string' 
                            ? JSON.parse(traceData.responseVaultContent.vaultContent) 
                            : traceData.responseVaultContent.vaultContent || {}
                          
                          // Parse the result field which contains the actual response
                          let result = {}
                          if (vaultContent.result && typeof vaultContent.result === 'string') {
                            result = JSON.parse(vaultContent.result)
                          }
                          
                          // Extract command_output
                          const commandOutput = result.command_output || ''
                          
                          // Display command output in a pre-formatted text area
                          return commandOutput ? (
                            <div style={{ 
                              backgroundColor: theme === 'dark' ? '#1f1f1f' : '#f5f5f5',
                              border: `1px solid ${theme === 'dark' ? '#303030' : '#d9d9d9'}`,
                              borderRadius: '4px',
                              padding: '12px',
                              fontFamily: 'monospace',
                              fontSize: '12px',
                              lineHeight: '1.5',
                              whiteSpace: 'pre-wrap',
                              wordBreak: 'break-word',
                              maxHeight: '400px',
                              overflowY: 'auto'
                            }}>
                              {commandOutput}
                            </div>
                          ) : (
                            <Empty description="No console output available" />
                          )
                        } catch (error) {
                          console.error('Failed to parse response console output:', error)
                          return <Empty description="Failed to parse console output" />
                        }
                      })()
                    ),
                  }] : []),
                ]}
              />
              </Panel>
            )}

            {/* Additional Information Panel */}
            {(traceData.queuePosition || traceData.machineStats || traceData.planInfo) && (
              <Panel header="Additional Information" key="additional">
                <Row gutter={16}>
              {traceData.machineStats && (
                <Col span={8}>
                  <Card title="Machine Statistics" size="small">
                    <Space direction="vertical" size="small" style={{ width: '100%' }}>
                      <div>
                        <Text type="secondary">Current Queue Depth:</Text>{' '}
                        <Text strong>{traceData.machineStats.currentQueueDepth}</Text>
                      </div>
                      <div>
                        <Text type="secondary">Active Processing:</Text>{' '}
                        <Text strong>{traceData.machineStats.activeProcessingCount}</Text>
                      </div>
                    </Space>
                  </Card>
                </Col>
              )}
              {traceData.planInfo && (
                <Col span={8}>
                  <Card title="Plan Information" size="small">
                    <div><Text strong>Plan:</Text> {traceData.planInfo.planName}</div>
                    <div><Text strong>Status:</Text> <Tag color="success">{traceData.planInfo.subscriptionStatus}</Tag></div>
                    <div><Text strong>Max Tasks:</Text> {traceData.planInfo.maxConcurrentTasks}</div>
                  </Card>
                </Col>
              )}
              {traceData.queuePosition && traceData.queuePosition.length > 0 && (
                <Col span={8}>
                  <Card title="Queue Position" size="small">
                    <div style={{ maxHeight: 200, overflow: 'auto' }}>
                      {traceData.queuePosition.filter((p: any) => p.relativePosition === 'Before').length > 0 && (
                        <div><Text type="secondary">{traceData.queuePosition.filter((p: any) => p.relativePosition === 'Before').length} tasks ahead</Text></div>
                      )}
                      {traceData.queuePosition.filter((p: any) => p.relativePosition === 'After').length > 0 && (
                        <div><Text type="secondary">{traceData.queuePosition.filter((p: any) => p.relativePosition === 'After').length} tasks behind</Text></div>
                      )}
                    </div>
                  </Card>
                </Col>
              )}
              </Row>
              </Panel>
            )}
              </Collapse>
            </div>
          )}
        </div>
      ) : (
        <Empty description="No trace data available" />
      )}
    </Modal>
  )
}

export default QueueItemTraceModal