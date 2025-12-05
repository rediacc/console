import React, { useState, useEffect, useRef } from 'react';
import {
  Modal,
  Button,
  Space,
  Typography,
  Card,
  Descriptions,
  Tag,
  Timeline,
  Empty,
  Row,
  Col,
  Tabs,
  Collapse,
  Steps,
  Progress,
  Statistic,
  Divider,
  Badge,
  Tooltip,
} from 'antd';
import type { CollapseProps } from 'antd';
import {
  ReloadOutlined,
  HistoryOutlined,
  FileTextOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  SyncOutlined,
  RightOutlined,
  UserOutlined,
  RetweetOutlined,
  WarningOutlined,
  RocketOutlined,
  TeamOutlined,
  DashboardOutlined,
  ThunderboltOutlined,
  HourglassOutlined,
  ExclamationCircleOutlined,
  CodeOutlined,
  QuestionCircleOutlined,
} from '@/utils/optimizedIcons';
import {
  useQueueItemTrace,
  useRetryFailedQueueItem,
  useCancelQueueItem,
} from '@/api/queries/queue';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import { SimpleJsonEditor } from '@/components/common/VaultEditor/components/SimpleJsonEditor';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { queueMonitoringService } from '@/services/queueMonitoringService';
import { showMessage } from '@/utils/messages';
import { useTheme } from '@/context/ThemeContext';
import { useTranslation } from 'react-i18next';
import { useSelector } from 'react-redux';
import { RootState } from '@/store/store';
import { formatTimestampAsIs } from '@/core';
import { useComponentStyles } from '@/hooks/useComponentStyles';
import { spacing } from '@/utils/styleConstants';
import { ModalSize } from '@/types/modal';
import {
  ModalTitleContainer,
  ModalTitleLeft,
  ModalTitleRight,
  LastFetchedText,
  ConsoleOutputContainer,
  ModeSegmented,
  SpacedAlert,
  FullWidthSpace,
  CenteredMessage,
  NoMarginTitle,
  NoteWrapper,
  KeyInfoCard,
  KeyInfoValue,
  CaptionText,
  CodeText,
  SmallStatusTag,
  ItalicCaption,
  ScrollContainer,
  ScrollItem,
  SectionMargin,
  CenteredFooter,
  SpacedCard,
  ActionButton,
  InfoList,
  CenteredRow,
  StatusText,
} from './styles';
import {
  normalizeToString,
  normalizeToNumber,
  normalizeToBoolean,
  extractMostRecentProgress,
  extractProgressMessage,
  formatDuration,
  formatDurationFull,
} from '@/core';
import type { QueueTraceLog, QueuePositionEntry } from '@rediacc/shared/types';

dayjs.extend(relativeTime);

const { Text } = Typography;

// Helper function to extract timestamp from trace logs for specific action
const getTimelineTimestamp = (
  traceLogs: QueueTraceLog[],
  action: string,
  fallbackAction?: string
): string | null => {
  if (!traceLogs || traceLogs.length === 0) return null;

  // Try primary action first
  let log = traceLogs.find((log) => normalizeToString(log, 'action', 'Action') === action);

  // If not found and fallback provided, try fallback action
  if (!log && fallbackAction) {
    log = traceLogs.find((log) => normalizeToString(log, 'action', 'Action') === fallbackAction);
  }

  if (log) {
    const timestamp = normalizeToString(log, 'timestamp', 'Timestamp');
    return timestamp ? formatTimestampAsIs(timestamp, 'time') : null;
  }

  return null;
};

export interface QueueItemTraceModalProps {
  taskId: string | null;
  open: boolean;
  onCancel: () => void;
  onTaskStatusChange?: (status: string, taskId: string) => void;
}

// Shared console output component
interface ConsoleOutputProps {
  content: string;
  theme: string;
  consoleOutputRef: React.RefObject<HTMLDivElement | null>;
  isEmpty?: boolean;
}

const ConsoleOutput: React.FC<ConsoleOutputProps> = ({
  content,
  theme,
  consoleOutputRef,
  isEmpty,
}) => {
  if (isEmpty || !content) {
    return <Empty description="No console output available" />;
  }

  return (
    <ConsoleOutputContainer
      ref={consoleOutputRef}
      data-testid="queue-trace-console-output"
      $theme={theme}
    >
      {content}
    </ConsoleOutputContainer>
  );
};

const QueueItemTraceModal: React.FC<QueueItemTraceModalProps> = ({
  taskId,
  open,
  onCancel,
  onTaskStatusChange,
}) => {
  const { t } = useTranslation(['queue', 'common']);
  const uiMode = useSelector((state: RootState) => state.ui.uiMode);
  const styles = useComponentStyles();
  const [lastTraceFetchTime, setLastTraceFetchTime] = useState<dayjs.Dayjs | null>(null);
  const [isMonitoring, setIsMonitoring] = useState(false);
  const [activeKeys, setActiveKeys] = useState<string[]>(['overview']); // Start with overview panel open
  const [simpleMode, setSimpleMode] = useState(true); // Default to simple mode
  const [accumulatedOutput, setAccumulatedOutput] = useState<string>(''); // Store accumulated console output
  const [lastOutputStatus, setLastOutputStatus] = useState<string>(''); // Track the last status to detect completion
  const [consoleProgress, setConsoleProgress] = useState<number | null>(null); // Progress percentage from console output
  const [progressMessage, setProgressMessage] = useState<string | null>(null); // Current progress message text
  const [isSimpleConsoleExpanded, setIsSimpleConsoleExpanded] = useState(false); // Console collapse state for simple mode
  const [isDetailedConsoleExpanded, setIsDetailedConsoleExpanded] = useState(false); // Console collapse state for detailed mode
  const {
    data: traceData,
    isLoading: isTraceLoading,
    refetch: refetchTrace,
  } = useQueueItemTrace(taskId, open);
  const { mutate: retryFailedItem, isPending: isRetrying } = useRetryFailedQueueItem();
  const { mutate: cancelQueueItem, isPending: isCancelling } = useCancelQueueItem();
  const { theme } = useTheme();
  const consoleOutputRef = useRef<HTMLDivElement>(null);
  const totalDurationSeconds = traceData?.queueDetails?.totalDurationSeconds ?? 0;
  const processingDurationSeconds = traceData?.queueDetails?.processingDurationSeconds ?? 0;

  // Sync last fetch time when trace data or visibility changes
  useEffect(() => {
    if (traceData && open) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLastTraceFetchTime(dayjs());
    }
  }, [traceData, open]);

  // Auto-scroll console output to bottom when output updates
  useEffect(() => {
    if (consoleOutputRef.current && accumulatedOutput) {
      consoleOutputRef.current.scrollTop = consoleOutputRef.current.scrollHeight;
    }
  }, [accumulatedOutput]);

  // Handle accumulating console output
  useEffect(() => {
    if (
      traceData?.responseVaultContent?.hasContent &&
      traceData.responseVaultContent.vaultContent
    ) {
      try {
        const vaultContent =
          typeof traceData.responseVaultContent.vaultContent === 'string'
            ? JSON.parse(traceData.responseVaultContent.vaultContent)
            : traceData.responseVaultContent.vaultContent || {};

        if (vaultContent.status === 'completed') {
          // For completed status, replace accumulated output with final result
          let finalOutput = '';
          if (vaultContent.result && typeof vaultContent.result === 'string') {
            try {
              const result = JSON.parse(vaultContent.result);
              // Extract command output from the cleaned response structure
              finalOutput = result.command_output || '';

              // If no command output but we have a message, show it
              if (!finalOutput && result.message) {
                finalOutput = `[${result.status}] ${result.message}`;
                if (result.exit_code !== undefined) {
                  finalOutput += ` (exit code: ${result.exit_code})`;
                }
              }
            } catch {
              finalOutput = vaultContent.result;
            }
          }
          // eslint-disable-next-line react-hooks/set-state-in-effect
          setAccumulatedOutput(finalOutput);
          setLastOutputStatus('completed');
        } else if (vaultContent.status === 'in_progress' && vaultContent.message) {
          // For in-progress updates, check if we should append or replace
          const newMessage = vaultContent.message;
          if (newMessage && lastOutputStatus !== 'completed') {
            setAccumulatedOutput((currentOutput) => {
              // If the new message starts with the current content, only append the difference
              if (newMessage.startsWith(currentOutput)) {
                const newContent = newMessage.substring(currentOutput.length);
                return currentOutput + newContent;
              } else {
                // Otherwise, replace the entire content
                return newMessage;
              }
            });
            setLastOutputStatus('in_progress');
          }
        } else if (!accumulatedOutput) {
          // Handle initial load for already completed tasks or other formats
          let initialOutput = '';
          if (vaultContent.result && typeof vaultContent.result === 'string') {
            try {
              const result = JSON.parse(vaultContent.result);
              // Extract command output from the cleaned response structure
              initialOutput = result.command_output || '';

              // If no command output but we have a message, show it
              if (!initialOutput && result.message) {
                initialOutput = `[${result.status}] ${result.message}`;
                if (result.exit_code !== undefined) {
                  initialOutput += ` (exit code: ${result.exit_code})`;
                }
              }
            } catch {
              initialOutput = vaultContent.result;
            }
          } else if (vaultContent.result && typeof vaultContent.result === 'object') {
            const result = vaultContent.result;
            // Same logic for object format
            initialOutput = result.command_output || '';
            if (!initialOutput && result.message) {
              initialOutput = `[${result.status}] ${result.message}`;
              if (result.exit_code !== undefined) {
                initialOutput += ` (exit code: ${result.exit_code})`;
              }
            }
          }
          if (initialOutput) {
            setAccumulatedOutput(initialOutput);
          }
        }
      } catch {
        // Error processing console output
      }
    }
  }, [traceData?.responseVaultContent, lastOutputStatus, accumulatedOutput]);

  // Extract progress percentage and message from console output

  useEffect(() => {
    const percentage = extractMostRecentProgress(accumulatedOutput);
    const message = extractProgressMessage(accumulatedOutput);

    // eslint-disable-next-line react-hooks/set-state-in-effect
    setConsoleProgress(percentage);
    setProgressMessage(message);
  }, [accumulatedOutput]);

  // Reset states when modal opens with new taskId
  useEffect(() => {
    if (open && taskId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLastTraceFetchTime(null);
      // Check if this task is already being monitored
      setIsMonitoring(queueMonitoringService.isTaskMonitored(taskId));
      // Reset collapsed state and simple mode when opening modal
      setActiveKeys(['overview']);
      setSimpleMode(true); // Default to simple mode
      // Reset accumulated output when opening modal with new task
      setAccumulatedOutput('');
      setLastOutputStatus('');
      // Reset console progress, message, and collapse states
      setConsoleProgress(null);
      setProgressMessage(null);
      setIsSimpleConsoleExpanded(false);
      setIsDetailedConsoleExpanded(false);
    }
  }, [taskId, open, uiMode]);

  // Monitor status changes and notify parent component
  useEffect(() => {
    if (traceData?.queueDetails && taskId && onTaskStatusChange) {
      const status = normalizeToString(traceData.queueDetails, 'status', 'Status');
      if (status === 'FAILED' || status === 'COMPLETED' || status === 'CANCELLED') {
        onTaskStatusChange(status, taskId);
      }
    }
  }, [traceData?.queueDetails, taskId, onTaskStatusChange]);

  const handleRefreshTrace = async () => {
    await refetchTrace();
  };

  const handleRetryFailedItem = () => {
    if (!taskId) return;

    retryFailedItem(taskId, {
      onSuccess: () => {
        // Refetch trace data to show updated status
        refetchTrace();
      },
    });
  };

  const handleCancelQueueItem = () => {
    if (!taskId) return;

    cancelQueueItem(taskId, {
      onSuccess: () => {
        // Refetch trace data to show updated status
        refetchTrace();
      },
    });
  };

  const handleClose = () => {
    // If task is still active and monitoring is enabled, remind user
    if (taskId && isMonitoring && traceData?.queueDetails) {
      const status = normalizeToString(traceData.queueDetails, 'status', 'Status');
      const retryCount = normalizeToNumber(traceData.queueDetails, 0, 'retryCount', 'RetryCount');
      const permanentlyFailed = normalizeToBoolean(
        traceData.queueDetails,
        'permanentlyFailed',
        'PermanentlyFailed'
      );

      const lastFailureReason = normalizeToString(
        traceData.queueDetails,
        'lastFailureReason',
        'LastFailureReason'
      );

      // Check if task is not in a terminal state
      if (
        status !== 'COMPLETED' &&
        status !== 'CANCELLED' &&
        !(status === 'FAILED' && (permanentlyFailed || retryCount >= 2)) &&
        !(status === 'PENDING' && retryCount >= 2 && lastFailureReason)
      ) {
        showMessage('info', `Task ${taskId} will continue to be monitored in the background`);
      }
    }
    onCancel();
  };

  // Helper function to get simplified status
  const getSimplifiedStatus = () => {
    if (!traceData?.queueDetails) return { status: 'unknown', color: 'default', icon: null };
    const status = normalizeToString(traceData.queueDetails, 'status', 'Status');
    const retryCount = normalizeToNumber(traceData.queueDetails, 0, 'retryCount', 'RetryCount');
    const lastFailureReason = normalizeToString(
      traceData.queueDetails,
      'lastFailureReason',
      'LastFailureReason'
    );

    // Check if this is a PENDING status after retry (it was failed and is being retried)
    if (status === 'PENDING' && retryCount > 0 && lastFailureReason) {
      // If we've reached max retries (2), show as failed instead of retrying
      if (retryCount >= 2) {
        return { status: 'Failed (Max Retries)', color: 'error', icon: <CloseCircleOutlined /> };
      }
      return { status: 'Retrying', color: 'warning', icon: <RetweetOutlined spin /> };
    }

    switch (status) {
      case 'COMPLETED':
        return { status: 'Completed', color: 'success', icon: <CheckCircleOutlined /> };
      case 'FAILED':
        return { status: 'Failed', color: 'error', icon: <CloseCircleOutlined /> };
      case 'CANCELLED':
        return { status: 'Cancelled', color: 'error', icon: <CloseCircleOutlined /> };
      case 'CANCELLING':
        return { status: 'Cancelling', color: 'warning', icon: <SyncOutlined spin /> };
      case 'PROCESSING':
        return { status: 'Processing', color: 'processing', icon: <SyncOutlined spin /> };
      case 'ASSIGNED':
        return { status: 'Assigned', color: 'blue', icon: <ClockCircleOutlined /> };
      default:
        return { status: status || 'Pending', color: 'default', icon: <ClockCircleOutlined /> };
    }
  };

  // Helper function to get task staleness level (progressive: none, early, stale, critical)
  const getTaskStaleness = () => {
    if (!traceData?.queueDetails) return 'none';
    const lastAssigned =
      normalizeToString(traceData.queueDetails, 'lastAssigned', 'LastAssigned') ||
      normalizeToString(traceData.queueDetails, 'assignedTime', 'AssignedTime');
    const lastRetryAt = normalizeToString(traceData.queueDetails, 'lastRetryAt', 'LastRetryAt');
    const lastResponseAt = normalizeToString(
      traceData.queueDetails,
      'lastResponseAt',
      'LastResponseAt'
    );
    const status = normalizeToString(traceData.queueDetails, 'status', 'Status');

    // Only check staleness for active processing tasks
    if (
      !lastAssigned ||
      status === 'COMPLETED' ||
      status === 'CANCELLED' ||
      status === 'CANCELLING' ||
      status === 'FAILED' ||
      status === 'PENDING'
    ) {
      return 'none';
    }

    // Find the most recent activity timestamp
    const timestamps = [lastAssigned, lastRetryAt, lastResponseAt].filter(Boolean);
    if (timestamps.length === 0) return 'none';

    // Use the most recent timestamp as the last activity time
    const lastActivityTime = timestamps.reduce((latest, current) => {
      return dayjs(current).isAfter(dayjs(latest)) ? current : latest;
    });

    const secondsSinceLastActivity = dayjs().diff(dayjs(lastActivityTime), 'second');

    // Progressive staleness levels
    if (secondsSinceLastActivity >= 120) return 'critical'; // 2+ minutes - strong cancellation recommendation
    if (secondsSinceLastActivity >= 90) return 'stale'; // 1.5+ minutes - stale with cancel option
    if (secondsSinceLastActivity >= 60) return 'early'; // 1+ minute - early warning
    return 'none';
  };

  // Legacy function for backward compatibility
  const isTaskStale = () => {
    const staleness = getTaskStaleness();
    return staleness === 'stale' || staleness === 'critical';
  };

  // Helper function to check if task is old pending (6+ hours)
  const isStalePending = () => {
    if (!traceData?.queueDetails) return false;
    const status = normalizeToString(traceData.queueDetails, 'status', 'Status');
    const healthStatus = normalizeToString(traceData.queueDetails, 'healthStatus', 'HealthStatus');
    const createdTime = normalizeToString(traceData.queueDetails, 'createdTime', 'CreatedTime');

    if (healthStatus === 'STALE_PENDING') return true;

    if (status !== 'PENDING' || !createdTime) return false;

    const hoursSinceCreated = dayjs().diff(dayjs(createdTime), 'hour');
    return hoursSinceCreated >= 6;
  };

  // Helper function to get priority color and icon
  // Using grayscale system - only visual distinction through icons
  const getPriorityInfo = (priority: number | undefined) => {
    if (!priority) return { color: 'default', icon: null, label: 'Normal' };

    switch (priority) {
      case 1:
        return { color: 'default', icon: <ThunderboltOutlined />, label: 'Highest' };
      case 2:
        return { color: 'default', icon: <RocketOutlined />, label: 'High' };
      case 3:
        return { color: 'default', icon: null, label: 'Normal' };
      case 4:
        return { color: 'default', icon: null, label: 'Low' };
      case 5:
        return { color: 'default', icon: null, label: 'Lowest' };
      default:
        return { color: 'default', icon: null, label: 'Normal' };
    }
  };

  // Get current step for Steps component (3 steps: Assigned, Processing, Completed)
  const getCurrentStep = () => {
    if (!traceData?.queueDetails) return 0;
    const status = normalizeToString(traceData.queueDetails, 'status', 'Status');

    switch (status) {
      case 'COMPLETED':
        return 2;
      case 'FAILED':
      case 'CANCELLED':
        return -1;
      case 'CANCELLING':
        return 1; // Show as processing (with cancelling description)
      case 'PROCESSING':
        return 1;
      case 'ASSIGNED':
        return 0;
      default:
        return 0; // PENDING - will show as waiting for assignment
    }
  };

  return (
    <Modal
      className={ModalSize.Large}
      data-testid="queue-trace-modal"
      title={
        <ModalTitleContainer>
          <ModalTitleLeft>
            <HistoryOutlined />
            <span>{`Queue Item Trace - ${taskId || ''}`}</span>
          </ModalTitleLeft>
          <ModalTitleRight>
            <ModeSegmented
              data-testid="queue-trace-mode-switch"
              value={simpleMode ? 'simple' : 'detailed'}
              onChange={(value) => setSimpleMode(value === 'simple')}
              options={[
                { label: 'Simple', value: 'simple' },
                { label: 'Detailed', value: 'detailed' },
              ]}
            />
            {lastTraceFetchTime && (
              <LastFetchedText>
                Last fetched: {lastTraceFetchTime.format('HH:mm:ss')}
              </LastFetchedText>
            )}
          </ModalTitleRight>
        </ModalTitleContainer>
      }
      open={open}
      onCancel={handleClose}
      destroyOnHidden
      footer={[
        // Show Cancel button for PENDING, ASSIGNED, or PROCESSING tasks that can be cancelled
        // Style and text vary based on staleness level
        traceData?.queueDetails &&
        traceData.queueDetails.canBeCancelled &&
        (normalizeToString(traceData.queueDetails, 'status', 'Status') === 'PENDING' ||
          normalizeToString(traceData.queueDetails, 'status', 'Status') === 'ASSIGNED' ||
          normalizeToString(traceData.queueDetails, 'status', 'Status') === 'PROCESSING') ? (
          <ActionButton
            key="cancel"
            data-testid="queue-trace-cancel-button"
            danger
            type={getTaskStaleness() === 'critical' ? 'primary' : 'default'}
            icon={<CloseCircleOutlined />}
            onClick={handleCancelQueueItem}
            loading={isCancelling}
            style={styles.buttonPrimary}
            $bold={getTaskStaleness() === 'critical'}
            $large={getTaskStaleness() === 'critical'}
          >
            {getTaskStaleness() === 'critical'
              ? 'Cancel Stuck Task'
              : getTaskStaleness() === 'stale'
                ? 'Cancel Task'
                : 'Cancel'}
          </ActionButton>
        ) : null,
        // Show Retry button only for failed tasks that haven't reached max retries
        traceData?.queueDetails &&
        normalizeToString(traceData.queueDetails, 'status', 'Status') === 'FAILED' &&
        normalizeToNumber(traceData.queueDetails, 0, 'retryCount', 'RetryCount') < 2 &&
        !normalizeToBoolean(traceData.queueDetails, 'permanentlyFailed', 'PermanentlyFailed') ? (
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
        </Button>,
      ].filter(Boolean)}
    >
      {isTraceLoading ? (
        <div className="queue-trace-loading">
          <LoadingWrapper loading centered minHeight={160}>
            <div />
          </LoadingWrapper>
        </div>
      ) : traceData ? (
        <div>
          {/* Progressive Stale Task Warnings */}
          {getTaskStaleness() === 'early' && (
            <SpacedAlert
              data-testid="queue-trace-alert-early"
              message="Task May Be Inactive"
              description="Task hasn't provided updates for over 1 minute. This may be normal for long-running operations."
              type="info"
              showIcon
              icon={<ClockCircleOutlined />}
            />
          )}

          {getTaskStaleness() === 'stale' && (
            <SpacedAlert
              data-testid="queue-trace-alert-stale"
              message="Task May Be Stale"
              description="Task appears inactive for over 1.5 minutes. Consider canceling if no progress is expected."
              type="warning"
              showIcon
              icon={<WarningOutlined />}
              action={
                traceData?.queueDetails?.canBeCancelled &&
                (normalizeToString(traceData.queueDetails, 'status', 'Status') === 'PENDING' ||
                  normalizeToString(traceData.queueDetails, 'status', 'Status') === 'ASSIGNED' ||
                  normalizeToString(traceData.queueDetails, 'status', 'Status') ===
                    'PROCESSING') ? (
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
            <SpacedAlert
              data-testid="queue-trace-alert-critical"
              message="Task Likely Stuck - Cancellation Recommended"
              description="Task has been inactive for over 2 minutes. The queue processor will automatically timeout this task at 3 minutes if no activity is detected."
              type="error"
              showIcon
              icon={<ExclamationCircleOutlined />}
              action={
                traceData?.queueDetails?.canBeCancelled &&
                (normalizeToString(traceData.queueDetails, 'status', 'Status') === 'PENDING' ||
                  normalizeToString(traceData.queueDetails, 'status', 'Status') === 'ASSIGNED' ||
                  normalizeToString(traceData.queueDetails, 'status', 'Status') ===
                    'PROCESSING') ? (
                  <ActionButton
                    $bold
                    $large
                    danger
                    type="primary"
                    icon={<CloseCircleOutlined />}
                    onClick={handleCancelQueueItem}
                    loading={isCancelling}
                  >
                    Cancel Stuck Task
                  </ActionButton>
                ) : null
              }
            />
          )}

          {/* Old Pending Warning */}
          {isStalePending() && (
            <SpacedAlert
              data-testid="queue-trace-alert-old-pending"
              message="Old Pending Task"
              description={`This task has been pending for over 6 hours. It may expire soon if not processed.`}
              type="warning"
              showIcon
              icon={<WarningOutlined />}
            />
          )}

          {/* Cancelling Status Alert */}
          {traceData.queueDetails &&
            normalizeToString(traceData.queueDetails, 'status', 'Status') === 'CANCELLING' && (
              <SpacedAlert
                data-testid="queue-trace-alert-cancelling"
                message="Task Being Cancelled"
                description="The task is being cancelled. The bridge will stop execution gracefully."
                type="warning"
                showIcon
                icon={<SyncOutlined spin />}
              />
            )}

          {/* Failure Reason Alert */}
          {traceData.queueDetails &&
            normalizeToString(traceData.queueDetails, 'lastFailureReason', 'LastFailureReason') &&
            normalizeToString(traceData.queueDetails, 'status', 'Status') !== 'CANCELLING' && (
              <SpacedAlert
                data-testid="queue-trace-alert-failure"
                message={
                  normalizeToString(traceData.queueDetails, 'status', 'Status') === 'PENDING' &&
                  normalizeToNumber(traceData.queueDetails, 0, 'retryCount', 'RetryCount') > 0
                    ? normalizeToNumber(traceData.queueDetails, 0, 'retryCount', 'RetryCount') >= 2
                      ? 'Task Failed - Max Retries Reached'
                      : 'Task Failed - Retrying'
                    : 'Task Failed'
                }
                description={normalizeToString(
                  traceData.queueDetails,
                  'lastFailureReason',
                  'LastFailureReason'
                )}
                type={
                  normalizeToString(traceData.queueDetails, 'status', 'Status') === 'PENDING' &&
                  normalizeToNumber(traceData.queueDetails, 0, 'retryCount', 'RetryCount') > 0
                    ? normalizeToNumber(traceData.queueDetails, 0, 'retryCount', 'RetryCount') >= 2
                      ? 'error'
                      : 'warning'
                    : 'error'
                }
                showIcon
                icon={
                  normalizeToString(traceData.queueDetails, 'status', 'Status') === 'PENDING' &&
                  normalizeToNumber(traceData.queueDetails, 0, 'retryCount', 'RetryCount') > 0 ? (
                    normalizeToNumber(traceData.queueDetails, 0, 'retryCount', 'RetryCount') >=
                    2 ? (
                      <CloseCircleOutlined />
                    ) : (
                      <RetweetOutlined />
                    )
                  ) : undefined
                }
              />
            )}

          {/* Simple Progress Overview */}
          {simpleMode && traceData.queueDetails && (
            <SpacedCard data-testid="queue-trace-simple-overview">
              <FullWidthSpace orientation="vertical" size="large">
                {/* Status Summary */}
                <CenteredMessage>
                  <Space size="large">
                    <span
                      className={`queue-trace-status-icon ${getSimplifiedStatus().status === 'Processing' ? 'processing' : ''}`}
                    >
                      {getSimplifiedStatus().icon}
                    </span>
                    <NoMarginTitle level={3}>Task {getSimplifiedStatus().status}</NoMarginTitle>
                  </Space>
                </CenteredMessage>

                {/* Steps */}
                <Steps
                  data-testid="queue-trace-steps"
                  className="queue-trace-steps"
                  current={getCurrentStep()}
                  status={getCurrentStep() === -1 ? 'error' : undefined}
                  size="small"
                  items={[
                    {
                      title: 'Assigned',
                      description: traceData.queueDetails.assignedTime
                        ? formatTimestampAsIs(traceData.queueDetails.assignedTime, 'time')
                        : 'Waiting',
                    },
                    {
                      title: 'Processing',
                      description: (() => {
                        const currentStep = getCurrentStep();
                        const status = normalizeToString(
                          traceData.queueDetails,
                          'status',
                          'Status'
                        );
                        const processingTimestamp = getTimelineTimestamp(
                          traceData.traceLogs,
                          'QUEUE_ITEM_PROCESSING',
                          'QUEUE_ITEM_RESPONSE_UPDATED'
                        );

                        // If currently processing
                        if (status === 'PROCESSING') {
                          return processingTimestamp || 'In Progress';
                        }

                        // If cancelling
                        if (status === 'CANCELLING') {
                          return 'Cancelling...';
                        }

                        // If we've reached or passed processing stage (step 1 or higher)
                        if (currentStep >= 1) {
                          return processingTimestamp || 'Processed';
                        }

                        // Haven't reached processing yet
                        return '';
                      })(),
                    },
                    {
                      title: 'Completed',
                      description:
                        normalizeToString(traceData.queueDetails, 'status', 'Status') ===
                        'COMPLETED'
                          ? `Done${getTimelineTimestamp(traceData.traceLogs, 'QUEUE_ITEM_COMPLETED') ? ' - ' + getTimelineTimestamp(traceData.traceLogs, 'QUEUE_ITEM_COMPLETED') : ''}`
                          : normalizeToString(traceData.queueDetails, 'status', 'Status') ===
                              'FAILED'
                            ? `Failed${getTimelineTimestamp(traceData.traceLogs, 'QUEUE_ITEM_FAILED') ? ' - ' + getTimelineTimestamp(traceData.traceLogs, 'QUEUE_ITEM_FAILED') : ''}`
                            : normalizeToString(traceData.queueDetails, 'status', 'Status') ===
                                'CANCELLED'
                              ? `Cancelled${getTimelineTimestamp(traceData.traceLogs, 'QUEUE_ITEM_CANCELLED') ? ' - ' + getTimelineTimestamp(traceData.traceLogs, 'QUEUE_ITEM_CANCELLED') : ''}`
                              : normalizeToString(traceData.queueDetails, 'status', 'Status') ===
                                  'CANCELLING'
                                ? 'Cancelling'
                                : '',
                    },
                  ]}
                />

                {/* Progress Message - Shows current operation being performed (hidden when completed) */}
                {progressMessage &&
                  normalizeToString(traceData?.queueDetails, 'status', 'Status') !== 'COMPLETED' &&
                  normalizeToString(traceData?.queueDetails, 'status', 'Status') !== 'FAILED' &&
                  normalizeToString(traceData?.queueDetails, 'status', 'Status') !==
                    'CANCELLED' && (
                    <NoteWrapper>
                      <ItalicCaption type="secondary">{progressMessage}</ItalicCaption>
                    </NoteWrapper>
                  )}

                {/* Progress Bar - Only shown when percentage is found in console output */}
                {consoleProgress !== null && (
                  <Progress
                    data-testid="queue-trace-progress"
                    className="queue-trace-progress"
                    percent={consoleProgress}
                    status={
                      getSimplifiedStatus().status === 'Failed' ||
                      getSimplifiedStatus().status === 'Cancelled'
                        ? 'exception'
                        : getSimplifiedStatus().status === 'Completed'
                          ? 'success'
                          : 'active'
                    }
                  />
                )}

                {/* Key Info - Only shown in detailed mode */}
                {!simpleMode && (
                  <CenteredRow gutter={[spacing('MD'), spacing('MD')]}>
                    <Col span={8}>
                      <KeyInfoCard
                        data-testid="queue-trace-info-duration"
                        className="queue-trace-key-info"
                      >
                        <CaptionText type="secondary">Duration</CaptionText>
                        <div>
                          <KeyInfoValue strong>{formatDuration(totalDurationSeconds)}</KeyInfoValue>
                        </div>
                      </KeyInfoCard>
                    </Col>
                    <Col span={8}>
                      <KeyInfoCard
                        data-testid="queue-trace-info-machine"
                        className="queue-trace-key-info"
                      >
                        <CaptionText type="secondary">Machine</CaptionText>
                        <div>
                          <Text strong>{traceData.queueDetails.machineName}</Text>
                        </div>
                      </KeyInfoCard>
                    </Col>
                    <Col span={8}>
                      <KeyInfoCard
                        data-testid="queue-trace-info-priority"
                        className="queue-trace-key-info"
                      >
                        <CaptionText type="secondary">Priority</CaptionText>
                        <div>
                          <Tag
                            color={
                              getPriorityInfo(
                                normalizeToNumber(traceData.queueDetails, 0, 'priority', 'Priority')
                              ).color
                            }
                          >
                            {
                              getPriorityInfo(
                                normalizeToNumber(traceData.queueDetails, 0, 'priority', 'Priority')
                              ).icon
                            }
                            {
                              getPriorityInfo(
                                normalizeToNumber(traceData.queueDetails, 0, 'priority', 'Priority')
                              ).label
                            }
                          </Tag>
                        </div>
                      </KeyInfoCard>
                    </Col>
                  </CenteredRow>
                )}
              </FullWidthSpace>
            </SpacedCard>
          )}

          {/* Console Output for Simple Mode */}
          {simpleMode && (
            <SectionMargin $top={spacing('MD')}>
              <Collapse
                data-testid="queue-trace-simple-console-collapse"
                activeKey={isSimpleConsoleExpanded ? ['console'] : []}
                onChange={(keys) => setIsSimpleConsoleExpanded(keys.includes('console'))}
                expandIcon={({ isActive }) => <RightOutlined rotate={isActive ? 90 : 0} />}
                items={[
                  {
                    key: 'console',
                    label: (
                      <Space>
                        <CodeOutlined />
                        <Text>Response (Console)</Text>
                        {traceData?.queueDetails?.status === 'PROCESSING' && (
                          <Tag icon={<SyncOutlined spin />} color="processing">
                            Live Output
                          </Tag>
                        )}
                      </Space>
                    ),
                    children: (
                      <ConsoleOutput
                        content={accumulatedOutput
                          .replace(/\\r\\n/g, '\n')
                          .replace(/\\n/g, '\n')
                          .replace(/\\r/g, '\r')}
                        theme={theme}
                        consoleOutputRef={consoleOutputRef}
                        isEmpty={!traceData?.responseVaultContent?.hasContent}
                      />
                    ),
                  },
                ]}
              />
            </SectionMargin>
          )}

          {/* Detailed View with All 7 Result Sets */}
          {!simpleMode && (
            <SectionMargin $top={spacing('MD')}>
              <Collapse
                data-testid="queue-trace-collapse"
                className="queue-trace-collapse"
                activeKey={activeKeys}
                onChange={setActiveKeys}
                expandIcon={({ isActive }) => <RightOutlined rotate={isActive ? 90 : 0} />}
                items={
                  [
                    /* Overview Panel - Combines key information from multiple result sets */
                    traceData.queueDetails
                      ? {
                          key: 'overview',
                          label: (
                            <Space>
                              <DashboardOutlined />
                              <span>Task Overview</span>
                              <Tag color={getSimplifiedStatus().color}>
                                {getSimplifiedStatus().status}
                              </Tag>
                              {isTaskStale() && (
                                <Tag color="warning" icon={<WarningOutlined />}>
                                  Stale
                                </Tag>
                              )}
                            </Space>
                          ),
                          extra:
                            traceData.queueDetails.canBeCancelled &&
                            normalizeToString(traceData.queueDetails, 'status', 'Status') !==
                              'COMPLETED' &&
                            normalizeToString(traceData.queueDetails, 'status', 'Status') !==
                              'CANCELLED' &&
                            normalizeToString(traceData.queueDetails, 'status', 'Status') !==
                              'CANCELLING' &&
                            normalizeToString(traceData.queueDetails, 'status', 'Status') !==
                              'FAILED' ? (
                              <Tooltip title="This task can be cancelled">
                                <Badge status="processing" text="Cancellable" />
                              </Tooltip>
                            ) : undefined,
                          children: (
                            <Row gutter={[24, 16]}>
                              {/* Left Column - Task Details */}
                              <Col xs={24} lg={12}>
                                <FullWidthSpace orientation="vertical" size="middle">
                                  <Card
                                    size="small"
                                    title="Task Information"
                                    data-testid="queue-trace-task-info"
                                  >
                                    <Descriptions column={1} size="small">
                                      <Descriptions.Item label="Task ID">
                                        <Text code>
                                          {normalizeToString(
                                            traceData.queueDetails,
                                            'taskId',
                                            'TaskId'
                                          )}
                                        </Text>
                                      </Descriptions.Item>
                                      <Descriptions.Item label="Created By">
                                        <Space>
                                          <UserOutlined />
                                          <Text>
                                            {normalizeToString(
                                              traceData.queueDetails,
                                              'createdBy',
                                              'CreatedBy'
                                            ) || 'System'}
                                          </Text>
                                        </Space>
                                      </Descriptions.Item>
                                      <Descriptions.Item label="Retry Status">
                                        <Space>
                                          <RetweetOutlined />
                                          <Tag
                                            color={
                                              normalizeToNumber(
                                                traceData.queueDetails,
                                                0,
                                                'retryCount',
                                                'RetryCount'
                                              ) === 0
                                                ? 'green'
                                                : normalizeToNumber(
                                                      traceData.queueDetails,
                                                      0,
                                                      'retryCount',
                                                      'RetryCount'
                                                    ) < 2
                                                  ? 'orange'
                                                  : 'red'
                                            }
                                          >
                                            {normalizeToNumber(
                                              traceData.queueDetails,
                                              0,
                                              'retryCount',
                                              'RetryCount'
                                            )}{' '}
                                            / 2 retries
                                          </Tag>
                                          {normalizeToBoolean(
                                            traceData.queueDetails,
                                            'permanentlyFailed',
                                            'PermanentlyFailed'
                                          ) && <Tag color="error">Permanently Failed</Tag>}
                                        </Space>
                                      </Descriptions.Item>
                                      <Descriptions.Item label="Priority">
                                        <Space>
                                          {
                                            getPriorityInfo(
                                              normalizeToNumber(
                                                traceData.queueDetails,
                                                0,
                                                'priority',
                                                'Priority'
                                              )
                                            ).icon
                                          }
                                          <Tag
                                            color={
                                              getPriorityInfo(
                                                normalizeToNumber(
                                                  traceData.queueDetails,
                                                  0,
                                                  'priority',
                                                  'Priority'
                                                )
                                              ).color
                                            }
                                          >
                                            {
                                              getPriorityInfo(
                                                normalizeToNumber(
                                                  traceData.queueDetails,
                                                  0,
                                                  'priority',
                                                  'Priority'
                                                )
                                              ).label
                                            }
                                          </Tag>
                                        </Space>
                                      </Descriptions.Item>
                                    </Descriptions>
                                  </Card>

                                  <Card
                                    size="small"
                                    title="Processing Information"
                                    data-testid="queue-trace-processing-info"
                                  >
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
                                        value={
                                          totalDurationSeconds < 60
                                            ? totalDurationSeconds
                                            : Math.floor(totalDurationSeconds / 60)
                                        }
                                        suffix={totalDurationSeconds < 60 ? 'sec' : 'min'}
                                        prefix={<ClockCircleOutlined />}
                                      />
                                    </Col>
                                    <Col span={8}>
                                      <Statistic
                                        title={t('queue:statistics.processing')}
                                        value={
                                          processingDurationSeconds
                                            ? processingDurationSeconds < 60
                                              ? processingDurationSeconds
                                              : Math.floor(processingDurationSeconds / 60)
                                            : 0
                                        }
                                        suffix={
                                          processingDurationSeconds &&
                                          processingDurationSeconds < 60
                                            ? 'sec'
                                            : 'min'
                                        }
                                        prefix={<SyncOutlined />}
                                      />
                                    </Col>
                                    <Col span={8}>
                                      <Statistic
                                        title={t('queue:statistics.timeSinceAssigned')}
                                        value={
                                          traceData.queueDetails.assignedTime
                                            ? dayjs().diff(
                                                dayjs(traceData.queueDetails.assignedTime),
                                                'minute'
                                              )
                                            : 'N/A'
                                        }
                                        suffix={traceData.queueDetails.assignedTime ? 'min' : ''}
                                        prefix={<HourglassOutlined />}
                                        valueStyle={{
                                          color: isTaskStale() ? 'var(--color-error)' : undefined,
                                        }}
                                      />
                                    </Col>
                                  </Row>
                                </FullWidthSpace>
                              </Col>

                              {/* Right Column - Response Console */}
                              <Col xs={24} lg={12}>
                                <Collapse
                                  data-testid="queue-trace-detailed-console-collapse"
                                  activeKey={isDetailedConsoleExpanded ? ['console'] : []}
                                  onChange={(keys) =>
                                    setIsDetailedConsoleExpanded(keys.includes('console'))
                                  }
                                  expandIcon={({ isActive }) => (
                                    <RightOutlined rotate={isActive ? 90 : 0} />
                                  )}
                                  items={[
                                    {
                                      key: 'console',
                                      label: (
                                        <Space>
                                          <CodeOutlined />
                                          <Text>Response (Console)</Text>
                                          {traceData.queueDetails?.status === 'PROCESSING' && (
                                            <Tag icon={<SyncOutlined spin />} color="processing">
                                              Live Output
                                            </Tag>
                                          )}
                                        </Space>
                                      ),
                                      children: (
                                        <ConsoleOutput
                                          content={accumulatedOutput
                                            .replace(/\\r\\n/g, '\n')
                                            .replace(/\\n/g, '\n')
                                            .replace(/\\r/g, '\r')}
                                          theme={theme}
                                          consoleOutputRef={consoleOutputRef}
                                          isEmpty={!traceData.responseVaultContent?.hasContent}
                                        />
                                      ),
                                    },
                                  ]}
                                />
                              </Col>
                            </Row>
                          ),
                        }
                      : null,

                    /* Result Set 1: Queue Item Details */
                    traceData.queueDetails
                      ? {
                          key: 'details',
                          label: (
                            <Space>
                              <FileTextOutlined />
                              <span>Queue Item Details</span>
                              <CaptionText type="secondary">(Result Set 1)</CaptionText>
                            </Space>
                          ),
                          children: (
                            <Descriptions column={2} size="small">
                              <Descriptions.Item label="Task ID">
                                <Text code>
                                  {normalizeToString(traceData.queueDetails, 'taskId', 'TaskId')}
                                </Text>
                              </Descriptions.Item>
                              <Descriptions.Item label="Status">
                                <Tag
                                  color={
                                    normalizeToString(
                                      traceData.queueDetails,
                                      'status',
                                      'Status'
                                    ) === 'COMPLETED'
                                      ? 'success'
                                      : normalizeToString(
                                            traceData.queueDetails,
                                            'status',
                                            'Status'
                                          ) === 'CANCELLED'
                                        ? 'error'
                                        : normalizeToString(
                                              traceData.queueDetails,
                                              'status',
                                              'Status'
                                            ) === 'CANCELLING'
                                          ? 'warning'
                                          : normalizeToString(
                                                traceData.queueDetails,
                                                'status',
                                                'Status'
                                              ) === 'FAILED'
                                            ? 'error'
                                            : normalizeToString(
                                                  traceData.queueDetails,
                                                  'status',
                                                  'Status'
                                                ) === 'PROCESSING'
                                              ? 'processing'
                                              : normalizeToString(
                                                    traceData.queueDetails,
                                                    'status',
                                                    'Status'
                                                  ) === 'ASSIGNED'
                                                ? 'blue'
                                                : 'default'
                                  }
                                >
                                  {normalizeToString(traceData.queueDetails, 'status', 'Status')}
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
                                {formatTimestampAsIs(
                                  traceData.queueDetails.createdTime,
                                  'datetime'
                                )}
                              </Descriptions.Item>
                              {traceData.queueDetails.assignedTime && (
                                <Descriptions.Item label="Assigned">
                                  {formatTimestampAsIs(
                                    traceData.queueDetails.assignedTime,
                                    'datetime'
                                  )}
                                </Descriptions.Item>
                              )}
                              {traceData.queueDetails.lastRetryAt && (
                                <Descriptions.Item label="Last Retry">
                                  {formatTimestampAsIs(
                                    traceData.queueDetails.lastRetryAt,
                                    'datetime'
                                  )}
                                </Descriptions.Item>
                              )}
                              <Descriptions.Item label="Total Duration">
                                {formatDurationFull(totalDurationSeconds)}
                              </Descriptions.Item>
                              {processingDurationSeconds > 0 && (
                                <Descriptions.Item label="Processing Duration">
                                  {formatDurationFull(processingDurationSeconds)}
                                </Descriptions.Item>
                              )}
                              <Descriptions.Item label="Created By">
                                {normalizeToString(
                                  traceData.queueDetails,
                                  'createdBy',
                                  'CreatedBy'
                                ) || '-'}
                              </Descriptions.Item>
                              <Descriptions.Item label="Retry Count">
                                <Tag
                                  color={
                                    normalizeToNumber(
                                      traceData.queueDetails,
                                      0,
                                      'retryCount',
                                      'RetryCount'
                                    ) === 0
                                      ? 'green'
                                      : normalizeToNumber(
                                            traceData.queueDetails,
                                            0,
                                            'retryCount',
                                            'RetryCount'
                                          ) < 3
                                        ? 'orange'
                                        : 'red'
                                  }
                                >
                                  {normalizeToNumber(
                                    traceData.queueDetails,
                                    0,
                                    'retryCount',
                                    'RetryCount'
                                  )}
                                  /2
                                </Tag>
                              </Descriptions.Item>
                              {normalizeToString(
                                traceData.queueDetails,
                                'lastFailureReason',
                                'LastFailureReason'
                              ) && (
                                <Descriptions.Item label="Last Failure Reason" span={2}>
                                  <Text type="warning">
                                    {normalizeToString(
                                      traceData.queueDetails,
                                      'lastFailureReason',
                                      'LastFailureReason'
                                    )}
                                  </Text>
                                </Descriptions.Item>
                              )}
                            </Descriptions>
                          ),
                        }
                      : null,

                    /* Result Set 4: Processing Timeline (Audit Log) */
                    traceData.traceLogs && traceData.traceLogs.length > 0
                      ? {
                          key: 'timeline',
                          label: (
                            <Space>
                              <HistoryOutlined />
                              <span>Processing Timeline</span>
                              <CaptionText type="secondary">(Result Set 4 - Audit Log)</CaptionText>
                            </Space>
                          ),
                          children: (
                            <Timeline
                              mode="left"
                              className="queue-trace-timeline"
                              data-testid="queue-trace-timeline"
                              items={traceData.traceLogs.map((log: QueueTraceLog) => {
                                const action = normalizeToString(log, 'action', 'Action');
                                const timestamp = normalizeToString(log, 'timestamp', 'Timestamp');
                                const details = normalizeToString(log, 'details', 'Details');
                                const actionByUser = normalizeToString(
                                  log,
                                  'actionByUser',
                                  'ActionByUser'
                                );

                                // Determine timeline item color based on action type
                                // Using grayscale system - only 'red' for actual errors
                                let color = 'gray';
                                if (action === 'QUEUE_ITEM_CANCELLED') color = 'red';
                                else if (action === 'QUEUE_ITEM_FAILED') color = 'red';
                                else if (action.includes('ERROR') || action.includes('FAILED'))
                                  color = 'red';

                                return {
                                  color,
                                  children: (
                                    <Space orientation="vertical" size={0}>
                                      <Text strong>
                                        {action.replace('QUEUE_ITEM_', '').replace(/_/g, ' ')}
                                      </Text>
                                      <Text type="secondary">
                                        {formatTimestampAsIs(timestamp, 'datetime')}
                                      </Text>
                                      {details && <Text>{details}</Text>}
                                      {actionByUser && (
                                        <Text type="secondary">By: {actionByUser}</Text>
                                      )}
                                    </Space>
                                  ),
                                };
                              })}
                            />
                          ),
                        }
                      : null,

                    /* Result Sets 2 & 3: Request and Response Vault Content */
                    traceData.vaultContent || traceData.responseVaultContent
                      ? {
                          key: 'vault',
                          label: (
                            <Space>
                              <FileTextOutlined />
                              <span>Vault Content</span>
                              <CaptionText type="secondary">(Result Sets 2 & 3)</CaptionText>
                            </Space>
                          ),
                          children: (
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
                                  children:
                                    traceData.vaultContent && traceData.vaultContent.hasContent ? (
                                      (() => {
                                        try {
                                          const content =
                                            typeof traceData.vaultContent.vaultContent === 'string'
                                              ? JSON.parse(traceData.vaultContent.vaultContent)
                                              : traceData.vaultContent.vaultContent || {};
                                          return (
                                            <SimpleJsonEditor
                                              value={JSON.stringify(content, null, 2)}
                                              readOnly={true}
                                              height="300px"
                                            />
                                          );
                                        } catch {
                                          // Failed to parse request vault content
                                          return (
                                            <Empty description="Invalid request vault content format" />
                                          );
                                        }
                                      })()
                                    ) : (
                                      <Empty description="No request vault content" />
                                    ),
                                },
                                ...(traceData.responseVaultContent &&
                                traceData.responseVaultContent.hasContent
                                  ? [
                                      {
                                        key: 'response',
                                        label: (
                                          <Space>
                                            <FileTextOutlined />
                                            Response Vault
                                          </Space>
                                        ),
                                        children: (() => {
                                          try {
                                            const content =
                                              typeof traceData.responseVaultContent.vaultContent ===
                                              'string'
                                                ? JSON.parse(
                                                    traceData.responseVaultContent.vaultContent
                                                  )
                                                : traceData.responseVaultContent.vaultContent || {};

                                            // Check if this is an SSH test result with kernel compatibility data
                                            if (
                                              content.result &&
                                              typeof content.result === 'string'
                                            ) {
                                              try {
                                                const result = JSON.parse(content.result);
                                                if (
                                                  result.status === 'success' &&
                                                  result.kernel_compatibility
                                                ) {
                                                  const compatibility = result.kernel_compatibility;
                                                  const osInfo = compatibility.os_info || {};
                                                  const status =
                                                    compatibility.compatibility_status || 'unknown';

                                                  const statusConfig = {
                                                    compatible: {
                                                      type: 'success' as const,
                                                      icon: <CheckCircleOutlined />,
                                                      color: 'var(--color-success)',
                                                    },
                                                    warning: {
                                                      type: 'warning' as const,
                                                      icon: <WarningOutlined />,
                                                      color: 'var(--color-warning)',
                                                    },
                                                    incompatible: {
                                                      type: 'error' as const,
                                                      icon: <ExclamationCircleOutlined />,
                                                      color: 'var(--color-error)',
                                                    },
                                                    unknown: {
                                                      type: 'info' as const,
                                                      icon: <QuestionCircleOutlined />,
                                                      color: 'var(--color-info)',
                                                    },
                                                  };

                                                  const config =
                                                    statusConfig[
                                                      status as keyof typeof statusConfig
                                                    ] || statusConfig.unknown;

                                                  return (
                                                    <FullWidthSpace orientation="vertical">
                                                      {/* SSH Test Result Summary */}
                                                      <SpacedCard
                                                        size="small"
                                                        title="SSH Test Result"
                                                      >
                                                        <Descriptions column={2} size="small">
                                                          <Descriptions.Item label="Status">
                                                            <Tag color="success">
                                                              {result.status}
                                                            </Tag>
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
                                                              <Tag color="warning">
                                                                Not Configured
                                                              </Tag>
                                                            )}
                                                          </Descriptions.Item>
                                                        </Descriptions>
                                                      </SpacedCard>

                                                      {/* System Information */}
                                                      <SpacedCard
                                                        size="small"
                                                        title="System Information"
                                                      >
                                                        <Descriptions column={1} size="small">
                                                          <Descriptions.Item label="Operating System">
                                                            {osInfo.pretty_name || 'Unknown'}
                                                          </Descriptions.Item>
                                                          <Descriptions.Item label="Kernel Version">
                                                            <Text code>
                                                              {compatibility.kernel_version ||
                                                                'Unknown'}
                                                            </Text>
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
                                                              <Tag color="warning">
                                                                Not Available
                                                              </Tag>
                                                            )}
                                                          </Descriptions.Item>
                                                          <Descriptions.Item label="Sudo Support">
                                                            {(() => {
                                                              const sudoStatus =
                                                                compatibility.sudo_available ||
                                                                'unknown';
                                                              if (sudoStatus === 'available') {
                                                                return (
                                                                  <Tag color="success">
                                                                    Available
                                                                  </Tag>
                                                                );
                                                              } else if (
                                                                sudoStatus === 'password_required'
                                                              ) {
                                                                return (
                                                                  <Tag color="warning">
                                                                    Password Required
                                                                  </Tag>
                                                                );
                                                              } else if (
                                                                sudoStatus === 'not_installed'
                                                              ) {
                                                                return (
                                                                  <Tag color="error">
                                                                    Not Installed
                                                                  </Tag>
                                                                );
                                                              } else {
                                                                return (
                                                                  <Tag color="default">Unknown</Tag>
                                                                );
                                                              }
                                                            })()}
                                                          </Descriptions.Item>
                                                        </Descriptions>
                                                      </SpacedCard>

                                                      {/* Compatibility Status */}
                                                      <SpacedAlert
                                                        data-testid="queue-trace-ssh-compatibility-alert"
                                                        type={config.type}
                                                        icon={config.icon}
                                                        message={
                                                          <Space>
                                                            <Text strong>
                                                              Compatibility Status:
                                                            </Text>
                                                            <StatusText $color={config.color}>
                                                              {status}
                                                            </StatusText>
                                                          </Space>
                                                        }
                                                        description={
                                                          <>
                                                            {compatibility.compatibility_issues &&
                                                              compatibility.compatibility_issues
                                                                .length > 0 && (
                                                                <SectionMargin $top={spacing('SM')}>
                                                                  <Text strong>Known Issues:</Text>
                                                                  <InfoList
                                                                    $top={spacing('XS')}
                                                                    $bottom={spacing('SM')}
                                                                  >
                                                                    {compatibility.compatibility_issues.map(
                                                                      (
                                                                        issue: string,
                                                                        index: number
                                                                      ) => (
                                                                        <li key={index}>{issue}</li>
                                                                      )
                                                                    )}
                                                                  </InfoList>
                                                                </SectionMargin>
                                                              )}
                                                            {compatibility.recommendations &&
                                                              compatibility.recommendations.length >
                                                                0 && (
                                                                <SectionMargin>
                                                                  <Text strong>
                                                                    Recommendations:
                                                                  </Text>
                                                                  <InfoList $top={spacing('XS')}>
                                                                    {compatibility.recommendations.map(
                                                                      (
                                                                        rec: string,
                                                                        index: number
                                                                      ) => (
                                                                        <li key={index}>{rec}</li>
                                                                      )
                                                                    )}
                                                                  </InfoList>
                                                                </SectionMargin>
                                                              )}
                                                          </>
                                                        }
                                                        showIcon
                                                      />

                                                      {/* Raw JSON fallback */}
                                                      <SectionMargin $top={spacing('MD')}>
                                                        <Collapse
                                                          items={[
                                                            {
                                                              key: 'raw',
                                                              label: 'Raw Response Data',
                                                              children: (
                                                                <SimpleJsonEditor
                                                                  value={JSON.stringify(
                                                                    result,
                                                                    null,
                                                                    2
                                                                  )}
                                                                  readOnly={true}
                                                                  height="200px"
                                                                />
                                                              ),
                                                            },
                                                          ]}
                                                        />
                                                      </SectionMargin>
                                                    </FullWidthSpace>
                                                  );
                                                }
                                              } catch {
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
                                            );
                                          } catch {
                                            // Failed to parse response vault content
                                            return (
                                              <Empty description="Invalid response vault content format" />
                                            );
                                          }
                                        })(),
                                      },
                                    ]
                                  : []),
                              ]}
                            />
                          ),
                        }
                      : null,

                    /* Result Set 5: Related Queue Items */
                    traceData.queuePosition && traceData.queuePosition.length > 0
                      ? {
                          key: 'related',
                          label: (
                            <Space>
                              <TeamOutlined />
                              <span>Related Queue Items</span>
                              <CaptionText type="secondary">
                                (Result Set 5 - Nearby Tasks)
                              </CaptionText>
                            </Space>
                          ),
                          children: (
                            <>
                              <Row gutter={[16, 16]}>
                                <Col span={12}>
                                  <Card size="small" title="Tasks Before This One">
                                    <ScrollContainer>
                                      {traceData.queuePosition
                                        .filter(
                                          (position: QueuePositionEntry) =>
                                            position.relativePosition === 'Before'
                                        )
                                        .map((item, index) => (
                                          <ScrollItem key={index}>
                                            <Space>
                                              <CodeText code>{item.taskId}</CodeText>
                                              <SmallStatusTag
                                                color={
                                                  item.status === 'PROCESSING'
                                                    ? 'processing'
                                                    : 'default'
                                                }
                                              >
                                                {item.status}
                                              </SmallStatusTag>
                                              <CaptionText type="secondary">
                                                {dayjs(item.createdTime).fromNow()}
                                              </CaptionText>
                                            </Space>
                                          </ScrollItem>
                                        ))}
                                      {traceData.queuePosition.filter(
                                        (position: QueuePositionEntry) =>
                                          position.relativePosition === 'Before'
                                      ).length === 0 && (
                                        <Empty
                                          description="No tasks ahead"
                                          image={Empty.PRESENTED_IMAGE_SIMPLE}
                                        />
                                      )}
                                    </ScrollContainer>
                                  </Card>
                                </Col>
                                <Col span={12}>
                                  <Card size="small" title="Tasks After This One">
                                    <ScrollContainer>
                                      {traceData.queuePosition
                                        .filter(
                                          (position: QueuePositionEntry) =>
                                            position.relativePosition === 'After'
                                        )
                                        .map((item, index) => (
                                          <ScrollItem key={index}>
                                            <Space>
                                              <CodeText code>{item.taskId}</CodeText>
                                              <SmallStatusTag
                                                color={
                                                  item.status === 'PROCESSING'
                                                    ? 'processing'
                                                    : 'default'
                                                }
                                              >
                                                {item.status}
                                              </SmallStatusTag>
                                              <CaptionText type="secondary">
                                                {dayjs(item.createdTime).fromNow()}
                                              </CaptionText>
                                            </Space>
                                          </ScrollItem>
                                        ))}
                                      {traceData.queuePosition.filter(
                                        (position: QueuePositionEntry) =>
                                          position.relativePosition === 'After'
                                      ).length === 0 && (
                                        <Empty
                                          description="No tasks behind"
                                          image={Empty.PRESENTED_IMAGE_SIMPLE}
                                        />
                                      )}
                                    </ScrollContainer>
                                  </Card>
                                </Col>
                              </Row>
                              <CenteredFooter>
                                <CaptionText type="secondary">
                                  Total:{' '}
                                  {
                                    traceData.queuePosition.filter(
                                      (position: QueuePositionEntry) =>
                                        position.relativePosition === 'Before'
                                    ).length
                                  }{' '}
                                  tasks ahead,
                                  {
                                    traceData.queuePosition.filter(
                                      (position: QueuePositionEntry) =>
                                        position.relativePosition === 'After'
                                    ).length
                                  }{' '}
                                  tasks behind
                                </CaptionText>
                              </CenteredFooter>
                            </>
                          ),
                        }
                      : null,

                    /* Result Set 6: Performance Metrics */
                    traceData.machineStats
                      ? {
                          key: 'performance',
                          label: (
                            <Space>
                              <DashboardOutlined />
                              <span>Performance Metrics</span>
                              <CaptionText type="secondary">
                                (Result Set 6 - Machine Stats)
                              </CaptionText>
                            </Space>
                          ),
                          children: (
                            <>
                              <Row gutter={16}>
                                <Col span={8}>
                                  <Card>
                                    <Statistic
                                      title="Current Queue Depth"
                                      value={traceData.machineStats.currentQueueDepth}
                                      prefix={<HourglassOutlined />}
                                      suffix="tasks"
                                      valueStyle={{
                                        color:
                                          traceData.machineStats.currentQueueDepth > 50
                                            ? 'var(--color-error)'
                                            : 'var(--color-text-primary)',
                                      }}
                                    />
                                    <Progress
                                      percent={Math.min(
                                        100,
                                        (traceData.machineStats.currentQueueDepth / 100) * 100
                                      )}
                                      showInfo={false}
                                      status={
                                        traceData.machineStats.currentQueueDepth > 50
                                          ? 'exception'
                                          : 'normal'
                                      }
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
                                    <Text type="secondary">
                                      Currently being processed on this machine
                                    </Text>
                                  </Card>
                                </Col>
                                <Col span={8}>
                                  <Card>
                                    <Statistic
                                      title="Processing Capacity"
                                      value={`${traceData.machineStats.activeProcessingCount}/${traceData.machineStats.maxConcurrentTasks || 'N/A'}`}
                                      prefix={<DashboardOutlined />}
                                      valueStyle={{
                                        color:
                                          traceData.machineStats.activeProcessingCount >=
                                          (traceData.machineStats.maxConcurrentTasks || 0)
                                            ? 'var(--color-error)'
                                            : 'var(--color-text-primary)',
                                      }}
                                    />
                                    <Progress
                                      percent={
                                        traceData.machineStats.maxConcurrentTasks
                                          ? Math.min(
                                              100,
                                              (traceData.machineStats.activeProcessingCount /
                                                traceData.machineStats.maxConcurrentTasks) *
                                                100
                                            )
                                          : 0
                                      }
                                      showInfo={false}
                                      status={
                                        traceData.machineStats.activeProcessingCount >=
                                        (traceData.machineStats.maxConcurrentTasks || 0)
                                          ? 'exception'
                                          : 'normal'
                                      }
                                    />
                                  </Card>
                                </Col>
                              </Row>
                              <Divider />
                              <SpacedAlert
                                data-testid="queue-trace-performance-alert"
                                message="Performance Analysis"
                                description={
                                  <Space orientation="vertical">
                                    {traceData.machineStats.currentQueueDepth > 50 && (
                                      <Text>
                                        ⚠️ High queue depth detected. Tasks may experience delays.
                                      </Text>
                                    )}
                                    {traceData.machineStats.activeProcessingCount >=
                                      (traceData.machineStats.maxConcurrentTasks || 0) && (
                                      <Text>
                                        ⚠️ Machine at full capacity. New tasks will wait in queue.
                                      </Text>
                                    )}
                                    {traceData.machineStats.currentQueueDepth === 0 &&
                                      traceData.machineStats.activeProcessingCount === 0 && (
                                        <Text>
                                          ✅ Machine is idle and ready to process tasks immediately.
                                        </Text>
                                      )}
                                  </Space>
                                }
                                type={
                                  traceData.machineStats.currentQueueDepth > 50 ? 'warning' : 'info'
                                }
                              />
                            </>
                          ),
                        }
                      : null,
                  ].filter(Boolean) as CollapseProps['items']
                }
              />
            </SectionMargin>
          )}
        </div>
      ) : (
        <Empty description="No trace data available" />
      )}
    </Modal>
  );
};

export default QueueItemTraceModal;
