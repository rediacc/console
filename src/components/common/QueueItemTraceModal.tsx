import React, { useState, useEffect } from 'react'
import { Modal, Button, Space, Typography, Card, Descriptions, Tag, Timeline, Empty, Spin, Row, Col, Tabs, Switch } from 'antd'
import { ReloadOutlined, HistoryOutlined, FileTextOutlined, BellOutlined } from '@ant-design/icons'
import { useQueueItemTrace } from '@/api/queries/queue'
import dayjs from 'dayjs'
import MonacoEditor from '@monaco-editor/react'
import { queueMonitoringService } from '@/services/queueMonitoringService'
import { showMessage } from '@/utils/messages'

const { Text } = Typography

interface QueueItemTraceModalProps {
  taskId: string | null
  visible: boolean
  onClose: () => void
}

const QueueItemTraceModal: React.FC<QueueItemTraceModalProps> = ({ taskId, visible, onClose }) => {
  const [lastTraceFetchTime, setLastTraceFetchTime] = useState<dayjs.Dayjs | null>(null)
  const [isMonitoring, setIsMonitoring] = useState(false)
  const { data: traceData, isLoading: isTraceLoading, refetch: refetchTrace } = useQueueItemTrace(taskId, visible)

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
    }
  }, [taskId, visible])

  const handleRefreshTrace = async () => {
    await refetchTrace()
  }

  const handleToggleMonitoring = () => {
    if (!taskId || !traceData?.queueDetails) return

    const status = traceData.queueDetails.status || traceData.queueDetails.Status
    
    // Don't allow monitoring completed or cancelled tasks
    if (status === 'COMPLETED' || status === 'CANCELLED') {
      showMessage('warning', 'Cannot monitor completed or cancelled tasks')
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
      const status = traceData.queueDetails.status || traceData.queueDetails.Status
      if (status !== 'COMPLETED' && status !== 'CANCELLED') {
        showMessage('info', `Task ${taskId} will continue to be monitored in the background`)
      }
    }
    onClose()
  }

  return (
    <Modal
      title={
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
          <Space>
            <HistoryOutlined />
            {`Queue Item Trace - ${taskId || ''}`}
          </Space>
          {lastTraceFetchTime && (
            <Text type="secondary" style={{ fontSize: '14px', marginRight: '20px' }}>
              Last fetched: {lastTraceFetchTime.format('HH:mm:ss')}
            </Text>
          )}
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
                  traceData.queueDetails.status === 'COMPLETED' ||
                  traceData.queueDetails.status === 'CANCELLED'
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
        <div style={{ textAlign: 'center', padding: '50px 0' }}>
          <Spin size="large" />
        </div>
      ) : traceData ? (
        <div>
          {/* Queue Details */}
          {traceData.queueDetails && (
            <Card title="Queue Item Details" style={{ marginBottom: 16 }}>
              <Descriptions column={2} size="small">
                <Descriptions.Item label="Task ID">
                  <Text code>{traceData.queueDetails.taskId || traceData.queueDetails.TaskId}</Text>
                </Descriptions.Item>
                <Descriptions.Item label="Status">
                  <Tag color={
                    traceData.queueDetails.status === 'COMPLETED' ? 'success' :
                    traceData.queueDetails.status === 'CANCELLED' ? 'error' :
                    traceData.queueDetails.status === 'PROCESSING' ? 'processing' :
                    traceData.queueDetails.status === 'ASSIGNED' ? 'blue' :
                    'default'
                  }>
                    {traceData.queueDetails.status}
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
              </Descriptions>
            </Card>
          )}

          {/* Trace Logs */}
          <Card title="Activity Timeline">
            {traceData.traceLogs && traceData.traceLogs.length > 0 ? (
              <Timeline mode="left">
                {traceData.traceLogs.map((log: any, index: number) => {
                  const action = log.action || log.Action
                  const timestamp = log.timestamp || log.Timestamp
                  const details = log.details || log.Details || ''
                  const actionByUser = log.actionByUser || log.ActionByUser || ''

                  // Determine timeline item color based on action type
                  let color = 'gray'
                  if (action === 'QUEUE_ITEM_CREATED') color = 'green'
                  else if (action === 'QUEUE_ITEM_ASSIGNED') color = 'blue'
                  else if (action === 'QUEUE_ITEM_PROCESSING' || action === 'QUEUE_ITEM_RESPONSE_UPDATED') color = 'orange'
                  else if (action === 'QUEUE_ITEM_COMPLETED') color = 'green'
                  else if (action === 'QUEUE_ITEM_CANCELLED') color = 'red'
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
            ) : (
              <Empty description="No trace logs available" />
            )}
          </Card>

          {/* Vault Content Section */}
          {(traceData.vaultContent || traceData.responseVaultContent) && (
            <Card title="Vault Content" style={{ marginTop: 16 }}>
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
                    children: traceData.vaultContent ? (
                      <MonacoEditor
                        height="300px"
                        language="json"
                        theme="vs-dark"
                        value={JSON.stringify(JSON.parse(traceData.vaultContent.vaultContent || '{}'), null, 2)}
                        options={{
                          readOnly: true,
                          minimap: { enabled: false },
                          scrollBeyondLastLine: false,
                          wordWrap: 'on',
                          fontSize: 12,
                        }}
                      />
                    ) : (
                      <Empty description="No request vault content" />
                    ),
                  },
                  ...(traceData.responseVaultContent ? [{
                    key: 'response',
                    label: (
                      <Space>
                        <FileTextOutlined />
                        Response Vault
                      </Space>
                    ),
                    children: (
                      <MonacoEditor
                        height="300px"
                        language="json"
                        theme="vs-dark"
                        value={JSON.stringify(JSON.parse(traceData.responseVaultContent.vaultContentResponse || '{}'), null, 2)}
                        options={{
                          readOnly: true,
                          minimap: { enabled: false },
                          scrollBeyondLastLine: false,
                          wordWrap: 'on',
                          fontSize: 12,
                        }}
                      />
                    ),
                  }] : []),
                ]}
              />
            </Card>
          )}

          {/* Additional Information */}
          {(traceData.queuePosition || traceData.machineStats || traceData.planInfo) && (
            <Row gutter={16} style={{ marginTop: 16 }}>
              {traceData.machineStats && (
                <Col span={8}>
                  <Card title="Machine Statistics" size="small">
                    <Space direction="vertical" size="small" style={{ width: '100%' }}>
                      <div>
                        <Text type="secondary">Success Rate:</Text>{' '}
                        <Text strong>{traceData.machineStats.machineSuccessRate}%</Text>
                      </div>
                      <div>
                        <Text type="secondary">Queue Depth:</Text>{' '}
                        <Text strong>{traceData.machineStats.currentQueueDepth}</Text>
                      </div>
                      <div>
                        <Text type="secondary">Active Tasks:</Text>{' '}
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
          )}
        </div>
      ) : (
        <Empty description="No trace data available" />
      )}
    </Modal>
  )
}

export default QueueItemTraceModal