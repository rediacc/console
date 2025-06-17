import React, { useState, useEffect, useRef } from 'react'
import { Modal, Button, Space, Typography, Card, Descriptions, Tag, Timeline, Empty, Spin, Row, Col, Tabs, Switch, Collapse, Steps, Progress, Statistic, Alert, Divider, Badge, Tooltip } from 'antd'
import { ReloadOutlined, HistoryOutlined, FileTextOutlined, BellOutlined, ClockCircleOutlined, CheckCircleOutlined, CloseCircleOutlined, SyncOutlined, RightOutlined, UserOutlined, RetweetOutlined, WarningOutlined, RocketOutlined, TeamOutlined, DashboardOutlined, ThunderboltOutlined, HourglassOutlined, ExclamationCircleOutlined, CrownOutlined, CodeOutlined } from '@ant-design/icons'
import { useQueueItemTrace, useRetryFailedQueueItem, useCancelQueueItem } from '@/api/queries/queue'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import { SimpleJsonEditor } from './SimpleJsonEditor'
import { queueMonitoringService } from '@/services/queueMonitoringService'
import { showMessage } from '@/utils/messages'
import { useTheme } from '@/context/ThemeContext'
import './QueueItemTraceModal.css'

dayjs.extend(relativeTime)

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
  const [activeKeys, setActiveKeys] = useState<string[]>(['overview']) // Start with overview panel open
  const [simpleMode, setSimpleMode] = useState(false) // Start in detailed mode to show all 7 result sets
  const [accumulatedOutput, setAccumulatedOutput] = useState<string>('') // Store accumulated console output
  const [lastOutputStatus, setLastOutputStatus] = useState<string>('') // Track the last status to detect completion
  const { data: traceData, isLoading: isTraceLoading, refetch: refetchTrace } = useQueueItemTrace(taskId, visible)
  const { mutate: retryFailedItem, isPending: isRetrying } = useRetryFailedQueueItem()
  const { mutate: cancelQueueItem, isPending: isCancelling } = useCancelQueueItem()
  const { theme } = useTheme()
  const consoleOutputRef = useRef<HTMLDivElement>(null)

  // Update last fetch time when trace data is loaded
  useEffect(() => {
    if (traceData && visible) {
      setLastTraceFetchTime(dayjs())
    }
  }, [traceData, visible])

  // Auto-scroll console output to bottom when output updates
  useEffect(() => {
    if (consoleOutputRef.current && accumulatedOutput) {
      consoleOutputRef.current.scrollTop = consoleOutputRef.current.scrollHeight
    }
  }, [accumulatedOutput])

  // Handle accumulating console output
  useEffect(() => {
    if (traceData?.responseVaultContent?.hasContent && traceData.responseVaultContent.vaultContent) {
      try {
        const vaultContent = typeof traceData.responseVaultContent.vaultContent === 'string' 
          ? JSON.parse(traceData.responseVaultContent.vaultContent) 
          : traceData.responseVaultContent.vaultContent || {}
        
        if (vaultContent.status === 'completed') {
          // For completed status, replace accumulated output with final result
          let finalOutput = ''
          if (vaultContent.result && typeof vaultContent.result === 'string') {
            try {
              const result = JSON.parse(vaultContent.result)
              // Extract command output from the cleaned response structure
              finalOutput = result.command_output || ''
              
              // If no command output but we have a message, show it
              if (!finalOutput && result.message) {
                finalOutput = `[${result.status}] ${result.message}`
                if (result.exit_code !== undefined) {
                  finalOutput += ` (exit code: ${result.exit_code})`
                }
              }
            } catch (e) {
              finalOutput = vaultContent.result
            }
          }
          setAccumulatedOutput(finalOutput)
          setLastOutputStatus('completed')
        } else if (vaultContent.status === 'in_progress' && vaultContent.message) {
          // For in-progress updates, append new output
          const newLine = vaultContent.message
          if (newLine && lastOutputStatus !== 'completed') {
            setAccumulatedOutput(prev => {
              // Only append if it's actually new content
              if (!prev.endsWith(newLine)) {
                return prev + (prev ? '\n' : '') + newLine
              }
              return prev
            })
            setLastOutputStatus('in_progress')
          }
        } else if (!accumulatedOutput) {
          // Handle initial load for already completed tasks or other formats
          let initialOutput = ''
          if (vaultContent.result && typeof vaultContent.result === 'string') {
            try {
              const result = JSON.parse(vaultContent.result)
              // Extract command output from the cleaned response structure
              initialOutput = result.command_output || ''
              
              // If no command output but we have a message, show it
              if (!initialOutput && result.message) {
                initialOutput = `[${result.status}] ${result.message}`
                if (result.exit_code !== undefined) {
                  initialOutput += ` (exit code: ${result.exit_code})`
                }
              }
            } catch (e) {
              initialOutput = vaultContent.result
            }
          } else if (vaultContent.result && typeof vaultContent.result === 'object') {
            const result = vaultContent.result
            // Same logic for object format
            initialOutput = result.command_output || ''
            if (!initialOutput && result.message) {
              initialOutput = `[${result.status}] ${result.message}`
              if (result.exit_code !== undefined) {
                initialOutput += ` (exit code: ${result.exit_code})`
              }
            }
          }
          if (initialOutput) {
            setAccumulatedOutput(initialOutput)
          }
        }
      } catch (error) {
        console.error('Error processing console output:', error)
      }
    }
  }, [traceData?.responseVaultContent, lastOutputStatus, accumulatedOutput])

  // Reset last fetch time when modal is opened with new taskId
  useEffect(() => {
    if (visible && taskId) {
      setLastTraceFetchTime(null)
      // Check if this task is already being monitored
      setIsMonitoring(queueMonitoringService.isTaskMonitored(taskId))
      // Reset collapsed state and simple mode when opening modal
      setActiveKeys(['overview'])
      setSimpleMode(false)
      // Reset accumulated output when opening modal with new task
      setAccumulatedOutput('')
      setLastOutputStatus('')
    }
  }, [taskId, visible])

  const handleRefreshTrace = async () => {
    await refetchTrace()
  }

  const handleRetryFailedItem = () => {
    if (!taskId) return
    
    retryFailedItem(taskId, {
      onSuccess: () => {
        // Refetch trace data to show updated status
        refetchTrace()
      }
    })
  }

  const handleCancelQueueItem = () => {
    if (!taskId) return
    
    cancelQueueItem(taskId, {
      onSuccess: () => {
        // Refetch trace data to show updated status
        refetchTrace()
      }
    })
  }

  const handleToggleMonitoring = () => {
    if (!taskId || !traceData?.queueDetails) return

    const status = normalizeProperty(traceData.queueDetails, 'status', 'Status')
    const retryCount = normalizeProperty(traceData.queueDetails, 'retryCount', 'RetryCount') || 0
    const permanentlyFailed = normalizeProperty(traceData.queueDetails, 'permanentlyFailed', 'PermanentlyFailed')
    
    const lastFailureReason = normalizeProperty(traceData.queueDetails, 'lastFailureReason', 'LastFailureReason')
    
    // Don't allow monitoring completed, cancelled, cancelling, or permanently failed tasks
    if (status === 'COMPLETED' || status === 'CANCELLED' || status === 'CANCELLING' ||
        (status === 'FAILED' && (permanentlyFailed || retryCount >= 2)) ||
        (status === 'PENDING' && retryCount >= 2 && lastFailureReason)) {
      showMessage('warning', 'Cannot monitor completed, cancelled, or permanently failed tasks')
      return
    }

    if (isMonitoring) {
      queueMonitoringService.removeTask(taskId)
      setIsMonitoring(false)
      showMessage('info', 'Background monitoring disabled for this task')
    } else {
      const teamName = traceData.queueDetails.teamName || ''
      const machineName = traceData.queueDetails.machineName || ''
      queueMonitoringService.addTask(taskId, teamName, machineName, status, retryCount, lastFailureReason)
      setIsMonitoring(true)
      showMessage('success', 'Background monitoring enabled. You will be notified when the task status changes.')
    }
  }

  const handleClose = () => {
    // If task is still active and monitoring is enabled, remind user
    if (taskId && isMonitoring && traceData?.queueDetails) {
      const status = normalizeProperty(traceData.queueDetails, 'status', 'Status')
      const retryCount = normalizeProperty(traceData.queueDetails, 'retryCount', 'RetryCount') || 0
      const permanentlyFailed = normalizeProperty(traceData.queueDetails, 'permanentlyFailed', 'PermanentlyFailed')
      
      const lastFailureReason = normalizeProperty(traceData.queueDetails, 'lastFailureReason', 'LastFailureReason')
      
      // Check if task is not in a terminal state
      if (status !== 'COMPLETED' && status !== 'CANCELLED' && 
          !(status === 'FAILED' && (permanentlyFailed || retryCount >= 2)) &&
          !(status === 'PENDING' && retryCount >= 2 && lastFailureReason)) {
        showMessage('info', `Task ${taskId} will continue to be monitored in the background`)
      }
    }
    onClose()
  }

  // Helper function to get simplified status
  const getSimplifiedStatus = () => {
    if (!traceData?.queueDetails) return { status: 'unknown', color: 'default', icon: null }
    const status = normalizeProperty(traceData.queueDetails, 'status', 'Status')
    const retryCount = normalizeProperty(traceData.queueDetails, 'retryCount', 'RetryCount') || 0
    const lastFailureReason = normalizeProperty(traceData.queueDetails, 'lastFailureReason', 'LastFailureReason')
    
    // Check if this is a PENDING status after retry (it was failed and is being retried)
    if (status === 'PENDING' && retryCount > 0 && lastFailureReason) {
      // If we've reached max retries (2), show as failed instead of retrying
      if (retryCount >= 2) {
        return { status: 'Failed (Max Retries)', color: 'error', icon: <CloseCircleOutlined /> }
      }
      return { status: 'Retrying', color: 'warning', icon: <RetweetOutlined spin /> }
    }
    
    switch (status) {
      case 'COMPLETED':
        return { status: 'Completed', color: 'success', icon: <CheckCircleOutlined /> }
      case 'FAILED':
        return { status: 'Failed', color: 'error', icon: <CloseCircleOutlined /> }
      case 'CANCELLED':
        return { status: 'Cancelled', color: 'error', icon: <CloseCircleOutlined /> }
      case 'CANCELLING':
        return { status: 'Cancelling', color: 'warning', icon: <SyncOutlined spin /> }
      case 'PROCESSING':
        return { status: 'Processing', color: 'processing', icon: <SyncOutlined spin /> }
      case 'ASSIGNED':
        return { status: 'Assigned', color: 'blue', icon: <ClockCircleOutlined /> }
      default:
        return { status: status || 'Pending', color: 'default', icon: <ClockCircleOutlined /> }
    }
  }

  // Helper function to check if task is stale (5+ minute since assigned)
  const isTaskStale = () => {
    if (!traceData?.queueDetails) return false
    const lastAssigned = normalizeProperty(traceData.queueDetails, 'lastAssigned', 'LastAssigned') || normalizeProperty(traceData.queueDetails, 'assignedTime', 'AssignedTime')
    const lastRetryAt = normalizeProperty(traceData.queueDetails, 'lastRetryAt', 'LastRetryAt')
    const status = normalizeProperty(traceData.queueDetails, 'status', 'Status')
    
    if (!lastAssigned || status === 'COMPLETED' || status === 'CANCELLED' || status === 'CANCELLING' || status === 'FAILED' || status === 'PENDING') {
      return false
    }
    
    const minutesSinceAssigned = dayjs().diff(dayjs(lastAssigned), 'minute')
    // If there was a recent retry, check from retry time instead
    if (lastRetryAt) {
      const minutesSinceRetry = dayjs().diff(dayjs(lastRetryAt), 'minute')
      return minutesSinceAssigned >= 5 && minutesSinceRetry >= 5
    }
    return minutesSinceAssigned >= 5
  }

  // Helper function to check if task is old pending (6+ hours)
  const isStalePending = () => {
    if (!traceData?.queueDetails) return false
    const status = normalizeProperty(traceData.queueDetails, 'status', 'Status')
    const healthStatus = normalizeProperty(traceData.queueDetails, 'healthStatus', 'HealthStatus')
    const createdTime = normalizeProperty(traceData.queueDetails, 'createdTime', 'CreatedTime')
    
    if (healthStatus === 'STALE_PENDING') return true
    
    if (status !== 'PENDING' || !createdTime) return false
    
    const hoursSinceCreated = dayjs().diff(dayjs(createdTime), 'hour')
    return hoursSinceCreated >= 6
  }

  // Helper function to get priority color and icon
  const getPriorityInfo = (priority: number | undefined) => {
    if (!priority) return { color: 'default', icon: null, label: 'Normal' }
    
    switch (priority) {
      case 1:
        return { color: 'red', icon: <ThunderboltOutlined />, label: 'Highest' }
      case 2:
        return { color: 'orange', icon: <RocketOutlined />, label: 'High' }
      case 3:
        return { color: 'default', icon: null, label: 'Normal' }
      case 4:
        return { color: 'blue', icon: null, label: 'Low' }
      case 5:
        return { color: 'cyan', icon: null, label: 'Lowest' }
      default:
        return { color: 'default', icon: null, label: 'Normal' }
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
      case 'CANCELLING':
        return 2  // Show as processing (with cancelling description)
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
      width={1200}
      footer={[
        // Monitor switch - always show on the left if there's queue details
        traceData?.queueDetails ? (
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
                  normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'CANCELLING' ||
                  (normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'FAILED' && 
                   ((normalizeProperty(traceData.queueDetails, 'retryCount', 'RetryCount') || 0) >= 2 ||
                    normalizeProperty(traceData.queueDetails, 'permanentlyFailed', 'PermanentlyFailed'))) ||
                  (normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'PENDING' && 
                   (normalizeProperty(traceData.queueDetails, 'retryCount', 'RetryCount') || 0) >= 2 &&
                   normalizeProperty(traceData.queueDetails, 'lastFailureReason', 'LastFailureReason'))
                }
              />
              <Text type="secondary">Background Monitoring</Text>
            </Space>
          </div>
        ) : null,
        // Show Cancel button for PENDING, ASSIGNED, or PROCESSING tasks that can be cancelled
        (traceData?.queueDetails && 
        traceData.queueDetails.canBeCancelled &&
        (normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'PENDING' || 
         normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'ASSIGNED' ||
         normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'PROCESSING')) ? (
          <Button 
            key="cancel"
            danger
            icon={<CloseCircleOutlined />} 
            onClick={handleCancelQueueItem}
            loading={isCancelling}
          >
            Cancel
          </Button>
        ) : null,
        // Show Retry button only for failed tasks that haven't reached max retries
        (traceData?.queueDetails && 
        normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'FAILED' && 
        (normalizeProperty(traceData.queueDetails, 'retryCount', 'RetryCount') || 0) < 2 && 
        !normalizeProperty(traceData.queueDetails, 'permanentlyFailed', 'PermanentlyFailed')) ? (
          <Button 
            key="retry"
            type="primary"
            danger
            icon={<RetweetOutlined />} 
            onClick={handleRetryFailedItem}
            loading={isRetrying}
          >
            Retry Again
          </Button>
        ) : null,
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
      ].filter(Boolean)}
    >
      {isTraceLoading ? (
        <div className="queue-trace-loading">
          <Spin size="large" />
        </div>
      ) : traceData ? (
        <div>
          {/* Stale Task Warning */}
          {isTaskStale() && (
            <Alert
              message="Task May Be Stale"
              description="This task has been processing for over 5 minutes and may be stuck."
              type="warning"
              showIcon
              icon={<WarningOutlined />}
              style={{ marginBottom: 16 }}
            />
          )}
          
          {/* Old Pending Warning */}
          {isStalePending() && (
            <Alert
              message="Old Pending Task"
              description={`This task has been pending for over 6 hours. It may expire soon if not processed.`}
              type="warning"
              showIcon
              icon={<WarningOutlined />}
              style={{ marginBottom: 16 }}
            />
          )}

          {/* Cancelling Status Alert */}
          {traceData.queueDetails && normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'CANCELLING' && (
            <Alert
              message="Task Being Cancelled"
              description="The task is being cancelled. The bridge will stop execution gracefully."
              type="warning"
              showIcon
              icon={<SyncOutlined spin />}
              style={{ marginBottom: 16 }}
            />
          )}

          {/* Failure Reason Alert */}
          {traceData.queueDetails && normalizeProperty(traceData.queueDetails, 'lastFailureReason', 'LastFailureReason') && 
           normalizeProperty(traceData.queueDetails, 'status', 'Status') !== 'CANCELLING' && (
            <Alert
              message={
                normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'PENDING' && 
                normalizeProperty(traceData.queueDetails, 'retryCount', 'RetryCount') > 0 
                  ? normalizeProperty(traceData.queueDetails, 'retryCount', 'RetryCount') >= 2 
                    ? "Task Failed - Max Retries Reached"
                    : "Task Failed - Retrying" 
                  : "Task Failed"
              }
              description={normalizeProperty(traceData.queueDetails, 'lastFailureReason', 'LastFailureReason')}
              type={
                normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'PENDING' && 
                normalizeProperty(traceData.queueDetails, 'retryCount', 'RetryCount') > 0 
                  ? normalizeProperty(traceData.queueDetails, 'retryCount', 'RetryCount') >= 2 
                    ? "error"
                    : "warning" 
                  : "error"
              }
              showIcon
              icon={
                normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'PENDING' && 
                normalizeProperty(traceData.queueDetails, 'retryCount', 'RetryCount') > 0 
                  ? normalizeProperty(traceData.queueDetails, 'retryCount', 'RetryCount') >= 2 
                    ? <CloseCircleOutlined />
                    : <RetweetOutlined /> 
                  : undefined
              }
              style={{ marginBottom: 16 }}
            />
          )}

          {/* Simple Progress Overview */}
          {simpleMode && traceData.queueDetails && (
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
                  <Step title="Processing" description={
                    normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'PROCESSING' ? 'In Progress' : 
                    normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'CANCELLING' ? 'Cancelling...' : ''
                  } />
                  <Step 
                    title="Completed" 
                    description={
                      normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'COMPLETED' ? 'Done' :
                      normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'FAILED' ? 'Failed' :
                      normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'CANCELLED' ? 'Cancelled' :
                      normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'CANCELLING' ? 'Cancelling' : ''
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
                        <Tag color={getPriorityInfo(normalizeProperty(traceData.queueDetails, 'priority', 'Priority')).color}>
                          {getPriorityInfo(normalizeProperty(traceData.queueDetails, 'priority', 'Priority')).icon}
                          {getPriorityInfo(normalizeProperty(traceData.queueDetails, 'priority', 'Priority')).label}
                        </Tag>
                      </div>
                    </div>
                  </Col>
                </Row>
              </Space>
            </Card>
          )}

          {/* Detailed View with All 7 Result Sets */}
          {!simpleMode && (
            <div style={{ marginTop: 16 }}>
              <Collapse 
              className="queue-trace-collapse"
              activeKey={activeKeys}
              onChange={setActiveKeys}
              expandIcon={({ isActive }) => <RightOutlined rotate={isActive ? 90 : 0} />}
            >
            {/* Overview Panel - Combines key information from multiple result sets */}
            {traceData.queueDetails && (
              <Panel 
                header={
                  <Space>
                    <DashboardOutlined />
                    <span>Task Overview</span>
                    <Tag color={getSimplifiedStatus().color}>{getSimplifiedStatus().status}</Tag>
                    {isTaskStale() && <Tag color="warning" icon={<WarningOutlined />}>Stale</Tag>}
                  </Space>
                } 
                key="overview"
                extra={
                  traceData.queueDetails.canBeCancelled && 
                  normalizeProperty(traceData.queueDetails, 'status', 'Status') !== 'COMPLETED' &&
                  normalizeProperty(traceData.queueDetails, 'status', 'Status') !== 'CANCELLED' &&
                  normalizeProperty(traceData.queueDetails, 'status', 'Status') !== 'CANCELLING' &&
                  normalizeProperty(traceData.queueDetails, 'status', 'Status') !== 'FAILED' && (
                    <Tooltip title="This task can be cancelled">
                      <Badge status="processing" text="Cancellable" />
                    </Tooltip>
                  )
                }
              >
                <Row gutter={[24, 16]}>
                  {/* Left Column - Task Details */}
                  <Col xs={24} lg={12}>
                    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                      <Card size="small" title="Task Information">
                        <Descriptions column={1} size="small">
                          <Descriptions.Item label="Task ID">
                            <Text code>{normalizeProperty(traceData.queueDetails, 'taskId', 'TaskId')}</Text>
                          </Descriptions.Item>
                          <Descriptions.Item label="Created By">
                            <Space>
                              <UserOutlined />
                              <Text>{normalizeProperty(traceData.queueDetails, 'createdBy', 'CreatedBy') || 'System'}</Text>
                            </Space>
                          </Descriptions.Item>
                          <Descriptions.Item label="Retry Status">
                            <Space>
                              <RetweetOutlined />
                              <Tag color={
                                normalizeProperty(traceData.queueDetails, 'retryCount', 'RetryCount') === 0 ? 'green' :
                                normalizeProperty(traceData.queueDetails, 'retryCount', 'RetryCount') < 2 ? 'orange' : 'red'
                              }>
                                {normalizeProperty(traceData.queueDetails, 'retryCount', 'RetryCount') || 0} / 2 retries
                              </Tag>
                              {normalizeProperty(traceData.queueDetails, 'permanentlyFailed', 'PermanentlyFailed') && (
                                <Tag color="error">Permanently Failed</Tag>
                              )}
                            </Space>
                          </Descriptions.Item>
                          <Descriptions.Item label="Priority">
                            <Space>
                              {getPriorityInfo(normalizeProperty(traceData.queueDetails, 'priority', 'Priority')).icon}
                              <Tag color={getPriorityInfo(normalizeProperty(traceData.queueDetails, 'priority', 'Priority')).color}>
                                {getPriorityInfo(normalizeProperty(traceData.queueDetails, 'priority', 'Priority')).label}
                              </Tag>
                              {(normalizeProperty(traceData.queueDetails, 'priority', 'Priority') === 1 || 
                                normalizeProperty(traceData.queueDetails, 'priority', 'Priority') === 2) && 
                                traceData.planInfo && 
                                (traceData.planInfo.planName === 'Premium' || traceData.planInfo.planName === 'Elite') && (
                                <Tooltip title="Using high priority slot">
                                  <CrownOutlined style={{ color: '#faad14' }} />
                                </Tooltip>
                              )}
                            </Space>
                          </Descriptions.Item>
                        </Descriptions>
                      </Card>

                      <Card size="small" title="Processing Information">
                        <Descriptions column={1} size="small">
                          <Descriptions.Item label="Machine">
                            <Space>
                              <TeamOutlined />
                              <Text>{traceData.queueDetails.machineName}</Text>
                            </Space>
                          </Descriptions.Item>
                          <Descriptions.Item label="Team">
                            <Text>{traceData.queueDetails.teamName}</Text>
                          </Descriptions.Item>
                          <Descriptions.Item label="Bridge">
                            <Text>{traceData.queueDetails.bridgeName}</Text>
                          </Descriptions.Item>
                          <Descriptions.Item label="Region">
                            <Text>{traceData.queueDetails.regionName}</Text>
                          </Descriptions.Item>
                        </Descriptions>
                      </Card>

                      <Row gutter={[16, 16]}>
                        <Col span={8}>
                          <Statistic
                            title="Total Duration"
                            value={Math.floor(traceData.queueDetails.totalDurationSeconds / 60)}
                            suffix="min"
                            prefix={<ClockCircleOutlined />}
                          />
                        </Col>
                        <Col span={8}>
                          <Statistic
                            title="Processing"
                            value={traceData.queueDetails.processingDurationSeconds ? Math.floor(traceData.queueDetails.processingDurationSeconds / 60) : 0}
                            suffix="min"
                            prefix={<SyncOutlined />}
                          />
                        </Col>
                        <Col span={8}>
                          <Statistic
                            title="Processing"
                            value={traceData.queueDetails.assignedTime ? dayjs().diff(dayjs(traceData.queueDetails.assignedTime), 'minute') : 'N/A'}
                            suffix={traceData.queueDetails.assignedTime ? 'min' : ''}
                            prefix={<HourglassOutlined />}
                            valueStyle={{ color: isTaskStale() ? '#ff4d4f' : undefined }}
                          />
                        </Col>
                      </Row>
                    </Space>
                  </Col>

                  {/* Right Column - Response Console */}
                  <Col xs={24} lg={12}>
                    <Card 
                      title={
                        <Space>
                          <CodeOutlined />
                          <Text>Response (Console)</Text>
                          {traceData.queueDetails?.status === 'PROCESSING' && (
                            <Tag icon={<SyncOutlined spin />} color="processing">
                              Live Output
                            </Tag>
                          )}
                        </Space>
                      }
                      size="small"
                      style={{ height: '100%' }}
                    >
                      {traceData.responseVaultContent && traceData.responseVaultContent.hasContent ? (
                        (() => {
                          try {
                            // Parse the vault content
                            const vaultContent = typeof traceData.responseVaultContent.vaultContent === 'string' 
                              ? JSON.parse(traceData.responseVaultContent.vaultContent) 
                              : traceData.responseVaultContent.vaultContent || {}
                            
                            // Use accumulated output instead of parsing each time
                            // Convert escape sequences to actual newlines
                            const commandOutput = accumulatedOutput
                              .replace(/\\r\\n/g, '\n')  // Replace \r\n with newline
                              .replace(/\\n/g, '\n')     // Replace \n with newline
                              .replace(/\\r/g, '\r')     // Replace \r with carriage return
                            
                            // Display command output in a pre-formatted text area
                            return (
                              <div>
                                {commandOutput ? (
                              <div 
                                ref={consoleOutputRef}
                                style={{ 
                                backgroundColor: theme === 'dark' ? '#1f1f1f' : '#f5f5f5',
                                border: `1px solid ${theme === 'dark' ? '#303030' : '#d9d9d9'}`,
                                borderRadius: '4px',
                                padding: '12px',
                                fontFamily: 'monospace',
                                fontSize: '12px',
                                lineHeight: '1.5',
                                whiteSpace: 'pre-wrap',
                                wordBreak: 'break-word',
                                height: '400px',
                                overflowY: 'scroll'
                              }}>
                                {commandOutput}
                              </div>
                            ) : (
                              <Empty description="No console output available" />
                            )}
                              </div>
                            )
                          } catch (error) {
                            console.error('Failed to parse response console output:', error, traceData.responseVaultContent)
                            // Try to display raw vault content as fallback
                            try {
                              const rawContent = typeof traceData.responseVaultContent.vaultContent === 'string' 
                                ? traceData.responseVaultContent.vaultContent 
                                : JSON.stringify(traceData.responseVaultContent.vaultContent, null, 2)
                              return (
                                <div>
                                  <div 
                                    ref={consoleOutputRef}
                                    style={{ 
                                    backgroundColor: theme === 'dark' ? '#1f1f1f' : '#f5f5f5',
                                    border: `1px solid ${theme === 'dark' ? '#303030' : '#d9d9d9'}`,
                                    borderRadius: '4px',
                                    padding: '12px',
                                    fontFamily: 'monospace',
                                    fontSize: '12px',
                                    lineHeight: '1.5',
                                    whiteSpace: 'pre-wrap',
                                    wordBreak: 'break-word',
                                    height: '400px',
                                    overflowY: 'scroll'
                                  }}>
                                  {rawContent}
                                  </div>
                                </div>
                              )
                            } catch (fallbackError) {
                              return <Empty description="Failed to parse console output" />
                            }
                          }
                        })()
                      ) : (
                        <Empty description="No response available yet" />
                      )}
                    </Card>
                  </Col>
                </Row>
              </Panel>
            )}

            {/* Result Set 1: Queue Item Details */}
            {traceData.queueDetails && (
              <Panel 
                header={
                  <Space>
                    <FileTextOutlined />
                    <span>Queue Item Details</span>
                    <Text type="secondary" style={{ fontSize: '12px' }}>(Result Set 1)</Text>
                  </Space>
                } 
                key="details"
              >
                <Descriptions column={2} size="small">
                <Descriptions.Item label="Task ID">
                  <Text code>{normalizeProperty(traceData.queueDetails, 'taskId', 'TaskId')}</Text>
                </Descriptions.Item>
                <Descriptions.Item label="Status">
                  <Tag color={
                    normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'COMPLETED' ? 'success' :
                    normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'CANCELLED' ? 'error' :
                    normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'CANCELLING' ? 'warning' :
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
                {traceData.queueDetails.lastRetryAt && (
                  <Descriptions.Item label="Last Retry">
                    {dayjs(traceData.queueDetails.lastRetryAt).format('YYYY-MM-DD HH:mm:ss')}
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
                    {normalizeProperty(traceData.queueDetails, 'retryCount', 'RetryCount') || 0}/2
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

            {/* Result Set 4: Processing Timeline (Audit Log) */}
            {traceData.traceLogs && traceData.traceLogs.length > 0 && (
              <Panel 
                header={
                  <Space>
                    <HistoryOutlined />
                    <span>Processing Timeline</span>
                    <Text type="secondary" style={{ fontSize: '12px' }}>(Result Set 4 - Audit Log)</Text>
                  </Space>
                } 
                key="timeline"
              >
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
                  else if (action === 'QUEUE_ITEM_CANCELLING') color = 'warning'
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

            {/* Result Sets 2 & 3: Request and Response Vault Content */}
            {(traceData.vaultContent || traceData.responseVaultContent) && (
              <Panel 
                header={
                  <Space>
                    <FileTextOutlined />
                    <span>Vault Content</span>
                    <Text type="secondary" style={{ fontSize: '12px' }}>(Result Sets 2 & 3)</Text>
                  </Space>
                } 
                key="vault"
              >
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
                ]}
              />
              </Panel>
            )}

            {/* Result Set 5: Related Queue Items */}
            {traceData.queuePosition && traceData.queuePosition.length > 0 && (
              <Panel 
                header={
                  <Space>
                    <TeamOutlined />
                    <span>Related Queue Items</span>
                    <Text type="secondary" style={{ fontSize: '12px' }}>(Result Set 5 - Nearby Tasks)</Text>
                  </Space>
                } 
                key="related"
              >
                <Row gutter={[16, 16]}>
                  <Col span={12}>
                    <Card size="small" title="Tasks Before This One">
                      <div style={{ maxHeight: 200, overflow: 'auto' }}>
                        {traceData.queuePosition
                          .filter((p: any) => p.relativePosition === 'Before')
                          .map((item: any, index: number) => (
                            <div key={index} style={{ marginBottom: 8 }}>
                              <Space>
                                <Text code style={{ fontSize: '11px' }}>{item.taskId}</Text>
                                <Tag color={item.status === 'PROCESSING' ? 'processing' : 'default'} style={{ fontSize: '11px' }}>
                                  {item.status}
                                </Tag>
                                <Text type="secondary" style={{ fontSize: '11px' }}>
                                  {dayjs(item.createdTime).fromNow()}
                                </Text>
                              </Space>
                            </div>
                          ))
                        }
                        {traceData.queuePosition.filter((p: any) => p.relativePosition === 'Before').length === 0 && (
                          <Empty description="No tasks ahead" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                        )}
                      </div>
                    </Card>
                  </Col>
                  <Col span={12}>
                    <Card size="small" title="Tasks After This One">
                      <div style={{ maxHeight: 200, overflow: 'auto' }}>
                        {traceData.queuePosition
                          .filter((p: any) => p.relativePosition === 'After')
                          .map((item: any, index: number) => (
                            <div key={index} style={{ marginBottom: 8 }}>
                              <Space>
                                <Text code style={{ fontSize: '11px' }}>{item.taskId}</Text>
                                <Tag color={item.status === 'PROCESSING' ? 'processing' : 'default'} style={{ fontSize: '11px' }}>
                                  {item.status}
                                </Tag>
                                <Text type="secondary" style={{ fontSize: '11px' }}>
                                  {dayjs(item.createdTime).fromNow()}
                                </Text>
                              </Space>
                            </div>
                          ))
                        }
                        {traceData.queuePosition.filter((p: any) => p.relativePosition === 'After').length === 0 && (
                          <Empty description="No tasks behind" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                        )}
                      </div>
                    </Card>
                  </Col>
                </Row>
                <div style={{ marginTop: 16, textAlign: 'center' }}>
                  <Text type="secondary">
                    Total: {traceData.queuePosition.filter((p: any) => p.relativePosition === 'Before').length} tasks ahead, 
                    {traceData.queuePosition.filter((p: any) => p.relativePosition === 'After').length} tasks behind
                  </Text>
                </div>
              </Panel>
            )}

            {/* Result Set 6: Performance Metrics */}
            {traceData.machineStats && (
              <Panel 
                header={
                  <Space>
                    <DashboardOutlined />
                    <span>Performance Metrics</span>
                    <Text type="secondary" style={{ fontSize: '12px' }}>(Result Set 6 - Machine Stats)</Text>
                  </Space>
                } 
                key="performance"
              >
                <Row gutter={16}>
                  <Col span={8}>
                    <Card>
                      <Statistic
                        title="Current Queue Depth"
                        value={traceData.machineStats.currentQueueDepth}
                        prefix={<HourglassOutlined />}
                        suffix="tasks"
                        valueStyle={{ color: traceData.machineStats.currentQueueDepth > 50 ? '#ff4d4f' : traceData.machineStats.currentQueueDepth > 20 ? '#faad14' : '#52c41a' }}
                      />
                      <Progress 
                        percent={Math.min(100, (traceData.machineStats.currentQueueDepth / 100) * 100)} 
                        showInfo={false}
                        strokeColor={traceData.machineStats.currentQueueDepth > 50 ? '#ff4d4f' : traceData.machineStats.currentQueueDepth > 20 ? '#faad14' : '#52c41a'}
                      />
                    </Card>
                  </Col>
                  <Col span={8}>
                    <Card>
                      <Statistic
                        title="Active Processing Count"
                        value={traceData.machineStats.activeProcessingCount}
                        prefix={<SyncOutlined spin />}
                        suffix="tasks"
                      />
                      <Text type="secondary">Currently being processed on this machine</Text>
                    </Card>
                  </Col>
                  <Col span={8}>
                    <Card>
                      <Statistic
                        title="Processing Capacity"
                        value={`${traceData.machineStats.activeProcessingCount}/${traceData.planInfo?.maxConcurrentTasks || 'N/A'}`}
                        prefix={<DashboardOutlined />}
                        valueStyle={{ color: traceData.machineStats.activeProcessingCount >= (traceData.planInfo?.maxConcurrentTasks || 0) ? '#ff4d4f' : '#52c41a' }}
                      />
                      <Progress 
                        percent={traceData.planInfo ? Math.min(100, (traceData.machineStats.activeProcessingCount / traceData.planInfo.maxConcurrentTasks) * 100) : 0} 
                        showInfo={false}
                        strokeColor={traceData.machineStats.activeProcessingCount >= (traceData.planInfo?.maxConcurrentTasks || 0) ? '#ff4d4f' : '#52c41a'}
                      />
                    </Card>
                  </Col>
                </Row>
                <Divider />
                <Alert
                  message="Performance Analysis"
                  description={
                    <Space direction="vertical">
                      {traceData.machineStats.currentQueueDepth > 50 && (
                        <Text>⚠️ High queue depth detected. Tasks may experience delays.</Text>
                      )}
                      {traceData.machineStats.activeProcessingCount >= (traceData.planInfo?.maxConcurrentTasks || 0) && (
                        <Text>⚠️ Machine at full capacity. New tasks will wait in queue.</Text>
                      )}
                      {traceData.machineStats.currentQueueDepth === 0 && traceData.machineStats.activeProcessingCount === 0 && (
                        <Text>✅ Machine is idle and ready to process tasks immediately.</Text>
                      )}
                    </Space>
                  }
                  type={traceData.machineStats.currentQueueDepth > 50 ? 'warning' : 'info'}
                />
              </Panel>
            )}

            {/* Result Set 7: Subscription Context */}
            {traceData.planInfo && (
              <Panel 
                header={
                  <Space>
                    <CrownOutlined />
                    <span>Subscription Context</span>
                    <Text type="secondary" style={{ fontSize: '12px' }}>(Result Set 7 - Plan Info)</Text>
                  </Space>
                } 
                key="subscription"
              >
                <Card>
                  <Row gutter={[16, 16]}>
                    <Col span={8}>
                      <Card type="inner">
                        <Statistic
                          title="Current Plan"
                          value={traceData.planInfo.planName}
                          prefix={traceData.planInfo.planName === 'Elite' ? <CrownOutlined style={{ color: '#faad14' }} /> : traceData.planInfo.planName === 'Premium' ? <RocketOutlined style={{ color: '#1890ff' }} /> : null}
                        />
                      </Card>
                    </Col>
                    <Col span={8}>
                      <Card type="inner">
                        <Statistic
                          title="Subscription Status"
                          value={traceData.planInfo.subscriptionStatus}
                          valueStyle={{ color: traceData.planInfo.subscriptionStatus === 'Active' ? '#52c41a' : '#ff4d4f' }}
                        />
                      </Card>
                    </Col>
                    <Col span={8}>
                      <Card type="inner">
                        <Statistic
                          title="Max Concurrent Tasks"
                          value={traceData.planInfo.maxConcurrentTasks}
                          suffix="tasks"
                        />
                      </Card>
                    </Col>
                  </Row>
                  
                  {(traceData.planInfo.planName === 'Premium' || traceData.planInfo.planName === 'Elite') && (
                    <>
                      <Divider />
                      <Alert
                        message="Premium Features"
                        description={
                          <Space direction="vertical">
                            <Text>✓ High priority slots available (Priority 1-2)</Text>
                            <Text>✓ Increased concurrent task limit</Text>
                            {traceData.planInfo.planName === 'Elite' && (
                              <Text>✓ Maximum performance and priority access</Text>
                            )}
                          </Space>
                        }
                        type="success"
                        icon={<CrownOutlined />}
                      />
                    </>
                  )}
                </Card>
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