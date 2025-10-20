import React, { useState, useEffect, useRef } from 'react'
import { Modal, Button, Space, Typography, Card, Descriptions, Tag, Timeline, Empty, Spin, Row, Col, Tabs, Collapse, Steps, Progress, Statistic, Alert, Divider, Badge, Tooltip, Segmented } from 'antd'
import { ReloadOutlined, HistoryOutlined, FileTextOutlined, BellOutlined, ClockCircleOutlined, CheckCircleOutlined, CloseCircleOutlined, SyncOutlined, RightOutlined, UserOutlined, RetweetOutlined, WarningOutlined, RocketOutlined, TeamOutlined, DashboardOutlined, ThunderboltOutlined, HourglassOutlined, ExclamationCircleOutlined, CrownOutlined, CodeOutlined, QuestionCircleOutlined } from '@/utils/optimizedIcons'
import { useQueueItemTrace, useRetryFailedQueueItem, useCancelQueueItem } from '@/api/queries/queue'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import { SimpleJsonEditor } from './SimpleJsonEditor'
import { queueMonitoringService } from '@/services/queueMonitoringService'
import { showMessage } from '@/utils/messages'
import { useTheme } from '@/context/ThemeContext'
import { useTranslation } from 'react-i18next'
import { useSelector } from 'react-redux'
import { RootState } from '@/store/store'
import { formatTimestampAsIs } from '@/utils/timeUtils'
import { useComponentStyles } from '@/hooks/useComponentStyles'
import { DESIGN_TOKENS, spacing, createModalStyle } from '@/utils/styleConstants'
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

// Helper function to format duration in seconds to human readable format
const formatDuration = (seconds: number): string => {
  if (seconds < 60) {
    return `${seconds}s`
  }
  return `${Math.floor(seconds / 60)}m`
}

// Helper function to format duration for display with full text
const formatDurationFull = (seconds: number): string => {
  if (seconds < 60) {
    return `${seconds} seconds`
  }
  const minutes = Math.floor(seconds / 60)
  return `${minutes} minute${minutes !== 1 ? 's' : ''}`
}

// Helper function to extract all percentages from console output and return the maximum
const extractMaxPercentage = (output: string): number | null => {
  if (!output) return null

  // Match all occurrences of "X%" where X is a number
  const percentageMatches = output.match(/(\d+(?:\.\d+)?)%/g)

  if (!percentageMatches || percentageMatches.length === 0) return null

  // Extract numeric values and find the maximum
  const percentages = percentageMatches.map(match => parseFloat(match.replace('%', '')))
  const maxPercentage = Math.max(...percentages)

  // Clamp to valid range (0-100)
  return Math.min(100, Math.max(0, maxPercentage))
}

// Helper function to extract timestamp from trace logs for specific action
const getTimelineTimestamp = (traceLogs: any[], action: string, fallbackAction?: string): string | null => {
  if (!traceLogs || traceLogs.length === 0) return null
  
  // Try primary action first
  let log = traceLogs.find(log => 
    normalizeProperty(log, 'action', 'Action') === action
  )
  
  // If not found and fallback provided, try fallback action
  if (!log && fallbackAction) {
    log = traceLogs.find(log => 
      normalizeProperty(log, 'action', 'Action') === fallbackAction
    )
  }
  
  if (log) {
    const timestamp = normalizeProperty(log, 'timestamp', 'Timestamp')
    return timestamp ? formatTimestampAsIs(timestamp, 'time') : null
  }
  
  return null
}

interface QueueItemTraceModalProps {
  taskId: string | null
  visible: boolean
  onClose: () => void
  onTaskStatusChange?: (status: string, taskId: string) => void
}

// Shared console output component
interface ConsoleOutputProps {
  content: string
  theme: string
  consoleOutputRef: React.RefObject<HTMLDivElement>
  isEmpty?: boolean
}

const ConsoleOutput: React.FC<ConsoleOutputProps> = ({ content, theme, consoleOutputRef, isEmpty }) => {
  if (isEmpty || !content) {
    return <Empty description="No console output available" />
  }

  return (
    <div 
      ref={consoleOutputRef}
      data-testid="queue-trace-console-output"
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
      {content}
    </div>
  )
}

const QueueItemTraceModal: React.FC<QueueItemTraceModalProps> = ({ taskId, visible, onClose, onTaskStatusChange }) => {
  const { t } = useTranslation(['queue', 'common'])
  const uiMode = useSelector((state: RootState) => state.ui.uiMode)
  const styles = useComponentStyles()
  const [lastTraceFetchTime, setLastTraceFetchTime] = useState<dayjs.Dayjs | null>(null)
  const [isMonitoring, setIsMonitoring] = useState(false)
  const [activeKeys, setActiveKeys] = useState<string[]>(['overview']) // Start with overview panel open
  const [simpleMode, setSimpleMode] = useState(true) // Default to simple mode
  const [accumulatedOutput, setAccumulatedOutput] = useState<string>('') // Store accumulated console output
  const [lastOutputStatus, setLastOutputStatus] = useState<string>('') // Track the last status to detect completion
  const [consoleProgress, setConsoleProgress] = useState<number | null>(null) // Progress percentage from console output
  const [isSimpleConsoleExpanded, setIsSimpleConsoleExpanded] = useState(false) // Console collapse state for simple mode
  const [isDetailedConsoleExpanded, setIsDetailedConsoleExpanded] = useState(false) // Console collapse state for detailed mode
  const { data: traceData, isLoading: isTraceLoading, refetch: refetchTrace } = useQueueItemTrace(taskId, visible)
  const { mutate: retryFailedItem, isPending: isRetrying } = useRetryFailedQueueItem()
  const { mutate: cancelQueueItem, isPending: isCancelling } = useCancelQueueItem()
  const { theme } = useTheme()
  const consoleOutputRef = useRef<HTMLDivElement>(null)

  // Sync last fetch time when trace data or visibility changes
  useEffect(() => {
    if (traceData && visible) {
      // eslint-disable-next-line
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
          // eslint-disable-next-line
          setAccumulatedOutput(finalOutput)
          setLastOutputStatus('completed')
        } else if (vaultContent.status === 'in_progress' && vaultContent.message) {
          // For in-progress updates, check if we should append or replace
          const newMessage = vaultContent.message
          if (newMessage && lastOutputStatus !== 'completed') {
            setAccumulatedOutput((currentOutput) => {
              // If the new message starts with the current content, only append the difference
              if (newMessage.startsWith(currentOutput)) {
                const newContent = newMessage.substring(currentOutput.length)
                return currentOutput + newContent
              } else {
                // Otherwise, replace the entire content
                return newMessage
              }
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
        // Error processing console output
      }
    }
  }, [traceData?.responseVaultContent, lastOutputStatus, accumulatedOutput])

  // Extract progress percentage from console output
  useEffect(() => {
    const percentage = extractMaxPercentage(accumulatedOutput)
    setConsoleProgress(percentage)
  }, [accumulatedOutput])

  // Reset states when modal opens with new taskId
  useEffect(() => {
    if (visible && taskId) {
      // eslint-disable-next-line
      setLastTraceFetchTime(null)
      // Check if this task is already being monitored
      setIsMonitoring(queueMonitoringService.isTaskMonitored(taskId))
      // Reset collapsed state and simple mode when opening modal
      setActiveKeys(['overview'])
      setSimpleMode(true) // Default to simple mode
      // Reset accumulated output when opening modal with new task
      setAccumulatedOutput('')
      setLastOutputStatus('')
      // Reset console progress and collapse states
      setConsoleProgress(null)
      setIsSimpleConsoleExpanded(false)
      setIsDetailedConsoleExpanded(false)
    }
  }, [taskId, visible, uiMode])
  
  // Monitor status changes and notify parent component
  useEffect(() => {
    if (traceData?.queueDetails && taskId && onTaskStatusChange) {
      const status = normalizeProperty(traceData.queueDetails, 'status', 'Status')
      if (status === 'FAILED' || status === 'COMPLETED' || status === 'CANCELLED') {
        onTaskStatusChange(status, taskId)
      }
    }
  }, [traceData?.queueDetails, taskId, onTaskStatusChange])

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

  const handleToggleMonitoring = (shouldMonitor?: boolean) => {
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

    const targetState = shouldMonitor !== undefined ? shouldMonitor : !isMonitoring

    if (!targetState) {
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

  // Helper function to get task staleness level (progressive: none, early, stale, critical)
  const getTaskStaleness = () => {
    if (!traceData?.queueDetails) return 'none'
    const lastAssigned = normalizeProperty(traceData.queueDetails, 'lastAssigned', 'LastAssigned') || normalizeProperty(traceData.queueDetails, 'assignedTime', 'AssignedTime')
    const lastRetryAt = normalizeProperty(traceData.queueDetails, 'lastRetryAt', 'LastRetryAt')
    const lastResponseAt = normalizeProperty(traceData.queueDetails, 'lastResponseAt', 'LastResponseAt')
    const status = normalizeProperty(traceData.queueDetails, 'status', 'Status')

    // Only check staleness for active processing tasks
    if (!lastAssigned || status === 'COMPLETED' || status === 'CANCELLED' || status === 'CANCELLING' || status === 'FAILED' || status === 'PENDING') {
      return 'none'
    }

    // Find the most recent activity timestamp
    const timestamps = [lastAssigned, lastRetryAt, lastResponseAt].filter(Boolean)
    if (timestamps.length === 0) return 'none'

    // Use the most recent timestamp as the last activity time
    const lastActivityTime = timestamps.reduce((latest, current) => {
      return dayjs(current).isAfter(dayjs(latest)) ? current : latest
    })

    const secondsSinceLastActivity = dayjs().diff(dayjs(lastActivityTime), 'second')

    // Progressive staleness levels
    if (secondsSinceLastActivity >= 120) return 'critical'  // 2+ minutes - strong cancellation recommendation
    if (secondsSinceLastActivity >= 90) return 'stale'      // 1.5+ minutes - stale with cancel option
    if (secondsSinceLastActivity >= 60) return 'early'      // 1+ minute - early warning
    return 'none'
  }

  // Legacy function for backward compatibility
  const isTaskStale = () => {
    const staleness = getTaskStaleness()
    return staleness === 'stale' || staleness === 'critical'
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
        return 66
      case 'ASSIGNED':
        return 33
      default:
        return 15  // PENDING
    }
  }

  // Get current step for Steps component (3 steps: Assigned, Processing, Completed)
  const getCurrentStep = () => {
    if (!traceData?.queueDetails) return 0
    const status = normalizeProperty(traceData.queueDetails, 'status', 'Status')

    switch (status) {
      case 'COMPLETED':
        return 2
      case 'FAILED':
      case 'CANCELLED':
        return -1
      case 'CANCELLING':
        return 1  // Show as processing (with cancelling description)
      case 'PROCESSING':
        return 1
      case 'ASSIGNED':
        return 0
      default:
        return 0  // PENDING - will show as waiting for assignment
    }
  }

  return (
    <Modal
      data-testid="queue-trace-modal"
      title={
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
          <Space>
            <HistoryOutlined />
            {`Queue Item Trace - ${taskId || ''}`}
          </Space>
          <Space direction="vertical" size={8} align="end">
            <Segmented
              data-testid="queue-trace-mode-switch"
              value={simpleMode ? 'simple' : 'detailed'}
              onChange={(value) => setSimpleMode(value === 'simple')}
              options={[
                { label: 'Simple', value: 'simple' },
                { label: 'Detailed', value: 'detailed' }
              ]}
              style={{ minHeight: 32 }}
            />
            {lastTraceFetchTime && (
              <Text type="secondary" style={{ fontSize: '12px' }}>
                Last fetched: {lastTraceFetchTime.format('HH:mm:ss')}
              </Text>
            )}
          </Space>
        </div>
      }
      open={visible}
      onCancel={handleClose}
      style={createModalStyle(1200)}
      destroyOnHidden
      footer={[
        // Show Cancel button for PENDING, ASSIGNED, or PROCESSING tasks that can be cancelled
        // Style and text vary based on staleness level
        (traceData?.queueDetails &&
        traceData.queueDetails.canBeCancelled &&
        (normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'PENDING' ||
         normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'ASSIGNED' ||
         normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'PROCESSING')) ? (
          <Button
            key="cancel"
            data-testid="queue-trace-cancel-button"
            danger
            type={getTaskStaleness() === 'critical' ? 'primary' : 'default'}
            icon={<CloseCircleOutlined />}
            onClick={handleCancelQueueItem}
            loading={isCancelling}
            style={{
              ...styles.buttonPrimary,
              fontWeight: getTaskStaleness() === 'critical' ? 'bold' : 'normal',
              fontSize: getTaskStaleness() === 'critical' ? '14px' : '13px'
            }}
          >
            {getTaskStaleness() === 'critical' ? 'Cancel Stuck Task' :
             getTaskStaleness() === 'stale' ? 'Cancel Task' :
             'Cancel'}
          </Button>
        ) : null,
        // Show Retry button only for failed tasks that haven't reached max retries
        (traceData?.queueDetails && 
        normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'FAILED' && 
        (normalizeProperty(traceData.queueDetails, 'retryCount', 'RetryCount') || 0) < 2 && 
        !normalizeProperty(traceData.queueDetails, 'permanentlyFailed', 'PermanentlyFailed')) ? (
          <Button 
            key="retry"
            data-testid="queue-trace-retry-button"
            type="primary"
            danger
            icon={<RetweetOutlined />} 
            onClick={handleRetryFailedItem}
            loading={isRetrying}
            style={styles.buttonPrimary}
          >
            Retry Again
          </Button>
        ) : null,
        <Button 
          key="refresh" 
          data-testid="queue-trace-refresh-button"
          icon={<ReloadOutlined />} 
          onClick={handleRefreshTrace}
          loading={isTraceLoading}
          style={styles.buttonSecondary}
        >
          Refresh
        </Button>,
        <Button 
          key="close" 
          data-testid="queue-trace-close-button" 
          onClick={handleClose}
          style={styles.buttonSecondary}
        >
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
          {/* Progressive Stale Task Warnings */}
          {getTaskStaleness() === 'early' && (
            <Alert
              data-testid="queue-trace-alert-early"
              message="Task May Be Inactive"
              description="Task hasn't provided updates for over 1 minute. This may be normal for long-running operations."
              type="info"
              showIcon
              icon={<ClockCircleOutlined />}
              style={{ marginBottom: 16 }}
            />
          )}

          {getTaskStaleness() === 'stale' && (
            <Alert
              data-testid="queue-trace-alert-stale"
              message="Task May Be Stale"
              description="Task appears inactive for over 1.5 minutes. Consider canceling if no progress is expected."
              type="warning"
              showIcon
              icon={<WarningOutlined />}
              style={{ marginBottom: 16 }}
              action={
                traceData?.queueDetails?.canBeCancelled &&
                (normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'PENDING' ||
                 normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'ASSIGNED' ||
                 normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'PROCESSING') ? (
                  <Button
                    danger
                    size="small"
                    icon={<CloseCircleOutlined />}
                    onClick={handleCancelQueueItem}
                    loading={isCancelling}
                  >
                    Cancel Task
                  </Button>
                ) : null
              }
            />
          )}

          {getTaskStaleness() === 'critical' && (
            <Alert
              data-testid="queue-trace-alert-critical"
              message="Task Likely Stuck - Cancellation Recommended"
              description="Task has been inactive for over 2 minutes. The queue processor will automatically timeout this task at 3 minutes if no activity is detected."
              type="error"
              showIcon
              icon={<ExclamationCircleOutlined />}
              style={{ marginBottom: 16 }}
              action={
                traceData?.queueDetails?.canBeCancelled &&
                (normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'PENDING' ||
                 normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'ASSIGNED' ||
                 normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'PROCESSING') ? (
                  <Button
                    danger
                    type="primary"
                    icon={<CloseCircleOutlined />}
                    onClick={handleCancelQueueItem}
                    loading={isCancelling}
                    style={{ fontWeight: 'bold' }}
                  >
                    Cancel Stuck Task
                  </Button>
                ) : null
              }
            />
          )}
          
          {/* Old Pending Warning */}
          {isStalePending() && (
            <Alert
              data-testid="queue-trace-alert-old-pending"
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
              data-testid="queue-trace-alert-cancelling"
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
              data-testid="queue-trace-alert-failure"
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
              data-testid="queue-trace-simple-overview"
              style={{ 
                ...styles.card,
                marginBottom: spacing('MD'), 
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

                {/* Steps */}
                <Steps
                  data-testid="queue-trace-steps"
                  className="queue-trace-steps"
                  current={getCurrentStep()}
                  status={getCurrentStep() === -1 ? 'error' : undefined}
                  size="small"
                >
                  <Step title="Assigned" description={traceData.queueDetails.assignedTime ? formatTimestampAsIs(traceData.queueDetails.assignedTime, 'time') : 'Waiting'} />
                  <Step title="Processing" description={
                    (() => {
                      const currentStep = getCurrentStep()
                      const status = normalizeProperty(traceData.queueDetails, 'status', 'Status')
                      const processingTimestamp = getTimelineTimestamp(traceData.traceLogs, 'QUEUE_ITEM_PROCESSING', 'QUEUE_ITEM_RESPONSE_UPDATED')

                      // If currently processing
                      if (status === 'PROCESSING') {
                        return processingTimestamp || 'In Progress'
                      }

                      // If cancelling
                      if (status === 'CANCELLING') {
                        return 'Cancelling...'
                      }

                      // If we've reached or passed processing stage (step 1 or higher)
                      if (currentStep >= 1) {
                        return processingTimestamp || 'Processed'
                      }

                      // Haven't reached processing yet
                      return ''
                    })()
                  } />
                  <Step
                    title="Completed"
                    description={
                      normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'COMPLETED' ?
                        `Done${getTimelineTimestamp(traceData.traceLogs, 'QUEUE_ITEM_COMPLETED') ? ' - ' + getTimelineTimestamp(traceData.traceLogs, 'QUEUE_ITEM_COMPLETED') : ''}` :
                      normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'FAILED' ?
                        `Failed${getTimelineTimestamp(traceData.traceLogs, 'QUEUE_ITEM_FAILED') ? ' - ' + getTimelineTimestamp(traceData.traceLogs, 'QUEUE_ITEM_FAILED') : ''}` :
                      normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'CANCELLED' ?
                        `Cancelled${getTimelineTimestamp(traceData.traceLogs, 'QUEUE_ITEM_CANCELLED') ? ' - ' + getTimelineTimestamp(traceData.traceLogs, 'QUEUE_ITEM_CANCELLED') : ''}` :
                      normalizeProperty(traceData.queueDetails, 'status', 'Status') === 'CANCELLING' ? 'Cancelling' : ''
                    }
                  />
                </Steps>

                {/* Progress Bar - Only shown when percentage is found in console output */}
                {consoleProgress !== null && (
                  <Progress
                    data-testid="queue-trace-progress"
                    className="queue-trace-progress"
                    percent={consoleProgress}
                    status={
                      getSimplifiedStatus().status === 'Failed' || getSimplifiedStatus().status === 'Cancelled' ? 'exception' :
                      getSimplifiedStatus().status === 'Completed' ? 'success' : 'active'
                    }
                    strokeColor={{
                      '0%': '#108ee9',
                      '100%': getSimplifiedStatus().status === 'Failed' || getSimplifiedStatus().status === 'Cancelled' ? '#ff4d4f' : '#87d068'
                    }}
                  />
                )}

                {/* Key Info */}
                <Row gutter={[spacing('MD'), spacing('MD')]} style={{ textAlign: 'center' }}>
                  <Col span={8}>
                    <div data-testid="queue-trace-info-duration" className="queue-trace-key-info" style={{ padding: spacing('SM'), borderRadius: DESIGN_TOKENS.BORDER_RADIUS.LG, background: theme === 'dark' ? '#262626' : '#fafafa' }}>
                      <Text type="secondary">Duration</Text>
                      <div>
                        <Text strong style={{ fontSize: DESIGN_TOKENS.FONT_SIZE.LG }}>
                          {formatDuration(traceData.queueDetails.totalDurationSeconds)}
                        </Text>
                      </div>
                    </div>
                  </Col>
                  <Col span={8}>
                    <div data-testid="queue-trace-info-machine" className="queue-trace-key-info" style={{ padding: spacing('SM'), borderRadius: DESIGN_TOKENS.BORDER_RADIUS.LG, background: theme === 'dark' ? '#262626' : '#fafafa' }}>
                      <Text type="secondary">Machine</Text>
                      <div>
                        <Text strong>{traceData.queueDetails.machineName}</Text>
                      </div>
                    </div>
                  </Col>
                  <Col span={8}>
                    <div data-testid="queue-trace-info-priority" className="queue-trace-key-info" style={{ padding: spacing('SM'), borderRadius: DESIGN_TOKENS.BORDER_RADIUS.LG, background: theme === 'dark' ? '#262626' : '#fafafa' }}>
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

          {/* Console Output for Simple Mode */}
          {simpleMode && (
            <Collapse
              data-testid="queue-trace-simple-console-collapse"
              activeKey={isSimpleConsoleExpanded ? ['console'] : []}
              onChange={(keys) => setIsSimpleConsoleExpanded(keys.includes('console'))}
              style={{ marginTop: spacing('MD') }}
              expandIcon={({ isActive }) => <RightOutlined rotate={isActive ? 90 : 0} />}
            >
              <Panel
                header={
                  <Space>
                    <CodeOutlined />
                    <Text>Response (Console)</Text>
                    {traceData?.queueDetails?.status === 'PROCESSING' && (
                      <Tag icon={<SyncOutlined spin />} color="processing">
                        Live Output
                      </Tag>
                    )}
                  </Space>
                }
                key="console"
              >
                <ConsoleOutput
                  content={accumulatedOutput
                    .replace(/\\r\\n/g, '\n')
                    .replace(/\\n/g, '\n')
                    .replace(/\\r/g, '\r')}
                  theme={theme}
                  consoleOutputRef={consoleOutputRef}
                  isEmpty={!traceData?.responseVaultContent?.hasContent}
                />
              </Panel>
            </Collapse>
          )}

          {/* Detailed View with All 7 Result Sets */}
          {!simpleMode && (
            <div style={{ marginTop: spacing('MD') }}>
              <Collapse 
              data-testid="queue-trace-collapse"
              className="queue-trace-collapse"
              activeKey={activeKeys}
              onChange={setActiveKeys}
              expandIcon={({ isActive }) => <RightOutlined rotate={isActive ? 90 : 0} />}
            >
            {/* Overview Panel - Combines key information from multiple result sets */}
            {traceData.queueDetails && (
              <Panel 
                data-testid="queue-trace-panel-overview"
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
                      <Card size="small" title="Task Information" data-testid="queue-trace-task-info">
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
                            </Space>
                          </Descriptions.Item>
                        </Descriptions>
                      </Card>

                      <Card size="small" title="Processing Information" data-testid="queue-trace-processing-info">
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
                            title={t('queue:statistics.totalDuration')}
                            value={traceData.queueDetails.totalDurationSeconds < 60 ? traceData.queueDetails.totalDurationSeconds : Math.floor(traceData.queueDetails.totalDurationSeconds / 60)}
                            suffix={traceData.queueDetails.totalDurationSeconds < 60 ? "sec" : "min"}
                            prefix={<ClockCircleOutlined />}
                          />
                        </Col>
                        <Col span={8}>
                          <Statistic
                            title={t('queue:statistics.processing')}
                            value={traceData.queueDetails.processingDurationSeconds ? (traceData.queueDetails.processingDurationSeconds < 60 ? traceData.queueDetails.processingDurationSeconds : Math.floor(traceData.queueDetails.processingDurationSeconds / 60)) : 0}
                            suffix={traceData.queueDetails.processingDurationSeconds && traceData.queueDetails.processingDurationSeconds < 60 ? "sec" : "min"}
                            prefix={<SyncOutlined />}
                          />
                        </Col>
                        <Col span={8}>
                          <Statistic
                            title={t('queue:statistics.timeSinceAssigned')}
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
                    <Collapse
                      data-testid="queue-trace-detailed-console-collapse"
                      activeKey={isDetailedConsoleExpanded ? ['console'] : []}
                      onChange={(keys) => setIsDetailedConsoleExpanded(keys.includes('console'))}
                      expandIcon={({ isActive }) => <RightOutlined rotate={isActive ? 90 : 0} />}
                    >
                      <Panel
                        header={
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
                        key="console"
                      >
                        <ConsoleOutput
                          content={accumulatedOutput
                            .replace(/\\r\\n/g, '\n')
                            .replace(/\\n/g, '\n')
                            .replace(/\\r/g, '\r')}
                          theme={theme}
                          consoleOutputRef={consoleOutputRef}
                          isEmpty={!traceData.responseVaultContent?.hasContent}
                        />
                      </Panel>
                    </Collapse>
                  </Col>
                </Row>
              </Panel>
            )}

            {/* Result Set 1: Queue Item Details */}
            {traceData.queueDetails && (
              <Panel 
                data-testid="queue-trace-panel-details"
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
                  {formatTimestampAsIs(traceData.queueDetails.createdTime, 'datetime')}
                </Descriptions.Item>
                {traceData.queueDetails.assignedTime && (
                  <Descriptions.Item label="Assigned">
                    {formatTimestampAsIs(traceData.queueDetails.assignedTime, 'datetime')}
                  </Descriptions.Item>
                )}
                {traceData.queueDetails.lastRetryAt && (
                  <Descriptions.Item label="Last Retry">
                    {formatTimestampAsIs(traceData.queueDetails.lastRetryAt, 'datetime')}
                  </Descriptions.Item>
                )}
                <Descriptions.Item label="Total Duration">
                  {formatDurationFull(traceData.queueDetails.totalDurationSeconds)}
                </Descriptions.Item>
                {traceData.queueDetails.processingDurationSeconds && (
                  <Descriptions.Item label="Processing Duration">
                    {formatDurationFull(traceData.queueDetails.processingDurationSeconds)}
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
                data-testid="queue-trace-panel-timeline"
                header={
                  <Space>
                    <HistoryOutlined />
                    <span>Processing Timeline</span>
                    <Text type="secondary" style={{ fontSize: '12px' }}>(Result Set 4 - Audit Log)</Text>
                  </Space>
                } 
                key="timeline"
              >
                <Timeline mode="left" className="queue-trace-timeline" data-testid="queue-trace-timeline">
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
                        <Text type="secondary">{formatTimestampAsIs(timestamp, 'datetime')}</Text>
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
                data-testid="queue-trace-panel-vault"
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
                data-testid="queue-trace-vault-tabs"
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
                          // Failed to parse request vault content
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
                          
                          // Check if this is an SSH test result with kernel compatibility data
                          if (content.result && typeof content.result === 'string') {
                            try {
                              const result = JSON.parse(content.result)
                              if (result.status === 'success' && result.kernel_compatibility) {
                                const compatibility = result.kernel_compatibility
                                const osInfo = compatibility.os_info || {}
                                const status = compatibility.compatibility_status || 'unknown'
                                
                                const statusConfig = {
                                  compatible: { type: 'success' as const, icon: <CheckCircleOutlined />, color: '#52c41a' },
                                  warning: { type: 'warning' as const, icon: <WarningOutlined />, color: '#faad14' },
                                  incompatible: { type: 'error' as const, icon: <ExclamationCircleOutlined />, color: '#ff4d4f' },
                                  unknown: { type: 'info' as const, icon: <QuestionCircleOutlined />, color: '#1890ff' }
                                }
                                
                                const config = statusConfig[status as keyof typeof statusConfig] || statusConfig.unknown
                                
                                return (
                                  <Space direction="vertical" style={{ width: '100%' }}>
                                    {/* SSH Test Result Summary */}
                                    <Card size="small" title="SSH Test Result" style={{ marginBottom: 16 }}>
                                      <Descriptions column={2} size="small">
                                        <Descriptions.Item label="Status">
                                          <Tag color="success">{result.status}</Tag>
                                        </Descriptions.Item>
                                        <Descriptions.Item label="Machine">
                                          {result.machine || 'N/A'}
                                        </Descriptions.Item>
                                        <Descriptions.Item label="IP Address">
                                          {result.ip}
                                        </Descriptions.Item>
                                        <Descriptions.Item label="User">
                                          {result.user}
                                        </Descriptions.Item>
                                        <Descriptions.Item label="Auth Method">
                                          <Tag>{result.auth_method}</Tag>
                                        </Descriptions.Item>
                                        <Descriptions.Item label="SSH Key">
                                          {result.ssh_key_configured ? (
                                            <Tag color="success">Configured</Tag>
                                          ) : (
                                            <Tag color="warning">Not Configured</Tag>
                                          )}
                                        </Descriptions.Item>
                                      </Descriptions>
                                    </Card>
                                    
                                    {/* System Information */}
                                    <Card size="small" title="System Information" style={{ marginBottom: 16 }}>
                                      <Descriptions column={1} size="small">
                                        <Descriptions.Item label="Operating System">
                                          {osInfo.pretty_name || 'Unknown'}
                                        </Descriptions.Item>
                                        <Descriptions.Item label="Kernel Version">
                                          <Text code>{compatibility.kernel_version || 'Unknown'}</Text>
                                        </Descriptions.Item>
                                        <Descriptions.Item label="OS ID">
                                          {osInfo.id || 'Unknown'}
                                        </Descriptions.Item>
                                        <Descriptions.Item label="Version">
                                          {osInfo.version_id || 'Unknown'}
                                        </Descriptions.Item>
                                        <Descriptions.Item label="BTRFS Support">
                                          {compatibility.btrfs_available ? (
                                            <Tag color="success">Available</Tag>
                                          ) : (
                                            <Tag color="warning">Not Available</Tag>
                                          )}
                                        </Descriptions.Item>
                                        <Descriptions.Item label="Sudo Support">
                                          {(() => {
                                            const sudoStatus = compatibility.sudo_available || 'unknown'
                                            if (sudoStatus === 'available') {
                                              return <Tag color="success">Available</Tag>
                                            } else if (sudoStatus === 'password_required') {
                                              return <Tag color="warning">Password Required</Tag>
                                            } else if (sudoStatus === 'not_installed') {
                                              return <Tag color="error">Not Installed</Tag>
                                            } else {
                                              return <Tag color="default">Unknown</Tag>
                                            }
                                          })()}
                                        </Descriptions.Item>
                                      </Descriptions>
                                    </Card>
                                    
                                    {/* Compatibility Status */}
                                    <Alert
                                      data-testid="queue-trace-ssh-compatibility-alert"
                                      type={config.type}
                                      icon={config.icon}
                                      message={
                                        <Space>
                                          <Text strong>Compatibility Status:</Text>
                                          <Text style={{ color: config.color, textTransform: 'capitalize' }}>
                                            {status}
                                          </Text>
                                        </Space>
                                      }
                                      description={
                                        <>
                                          {compatibility.compatibility_issues && compatibility.compatibility_issues.length > 0 && (
                                            <div style={{ marginTop: 8 }}>
                                              <Text strong>Known Issues:</Text>
                                              <ul style={{ marginTop: 4, marginBottom: 8 }}>
                                                {compatibility.compatibility_issues.map((issue: string, index: number) => (
                                                  <li key={index}>{issue}</li>
                                                ))}
                                              </ul>
                                            </div>
                                          )}
                                          {compatibility.recommendations && compatibility.recommendations.length > 0 && (
                                            <div>
                                              <Text strong>Recommendations:</Text>
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
                                    
                                    {/* Raw JSON fallback */}
                                    <Collapse style={{ marginTop: 16 }}>
                                      <Collapse.Panel header="Raw Response Data" key="raw">
                                        <SimpleJsonEditor
                                          value={JSON.stringify(result, null, 2)}
                                          readOnly={true}
                                          height="200px"
                                        />
                                      </Collapse.Panel>
                                    </Collapse>
                                  </Space>
                                )
                              }
                            } catch (e) {
                              // Fall through to default JSON display
                            }
                          }
                          
                          // Default JSON display for non-SSH test results
                          return (
                            <SimpleJsonEditor
                              value={JSON.stringify(content, null, 2)}
                              readOnly={true}
                              height="300px"
                            />
                          )
                        } catch (error) {
                          // Failed to parse response vault content
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
                data-testid="queue-trace-panel-related"
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
                data-testid="queue-trace-panel-performance"
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
                        value={`${traceData.machineStats.activeProcessingCount}/${traceData.machineStats.maxConcurrentTasks || 'N/A'}`}
                        prefix={<DashboardOutlined />}
                        valueStyle={{ color: traceData.machineStats.activeProcessingCount >= (traceData.machineStats.maxConcurrentTasks || 0) ? '#ff4d4f' : '#52c41a' }}
                      />
                      <Progress
                        percent={traceData.machineStats.maxConcurrentTasks ? Math.min(100, (traceData.machineStats.activeProcessingCount / traceData.machineStats.maxConcurrentTasks) * 100) : 0}
                        showInfo={false}
                        strokeColor={traceData.machineStats.activeProcessingCount >= (traceData.machineStats.maxConcurrentTasks || 0) ? '#ff4d4f' : '#52c41a'}
                      />
                    </Card>
                  </Col>
                </Row>
                <Divider />
                <Alert
                  data-testid="queue-trace-performance-alert"
                  message="Performance Analysis"
                  description={
                    <Space direction="vertical">
                      {traceData.machineStats.currentQueueDepth > 50 && (
                        <Text>⚠️ High queue depth detected. Tasks may experience delays.</Text>
                      )}
                      {traceData.machineStats.activeProcessingCount >= (traceData.machineStats.maxConcurrentTasks || 0) && (
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