import React, { useEffect } from 'react';
import {
  Badge,
  Button,
  Card,
  Col,
  Collapse,
  Descriptions,
  Divider,
  Empty,
  Modal,
  Progress,
  Row,
  Space,
  Statistic,
  Steps,
  Tabs,
  Tooltip,
} from 'antd';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import {
  useCancelQueueItem,
  useQueueItemTrace,
  useRetryFailedQueueItem,
} from '@/api/queries/queue';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { SimpleJsonEditor } from '@/components/common/VaultEditor/components/SimpleJsonEditor';
import { RediaccAlert, RediaccCard, RediaccStack, RediaccTag, RediaccText } from '@/components/ui';
import { useTheme } from '@/context/ThemeContext';
import { useComponentStyles } from '@/hooks/useComponentStyles';
import {
  formatDuration,
  formatDurationFull,
  formatTimestampAsIs,
  normalizeToBoolean,
  normalizeToNumber,
  normalizeToString,
} from '@/platform';
import { ModalSize } from '@/types/modal';
import { showMessage } from '@/utils/messages';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  CodeOutlined,
  DashboardOutlined,
  ExclamationCircleOutlined,
  FileTextOutlined,
  HistoryOutlined,
  HourglassOutlined,
  RetweetOutlined,
  RightOutlined,
  SyncOutlined,
  TeamOutlined,
  UserOutlined,
  WarningOutlined,
} from '@/utils/optimizedIcons';
import { spacing } from '@/utils/styleConstants';
import type { QueuePositionEntry } from '@rediacc/shared/types';
import { ActionButtons } from './components/ActionButtons';
import { ConsoleOutput } from './components/ConsoleOutput';
import { StatsPanel } from './components/StatsPanel';
import { TimelineView } from './components/TimelineView';
import { useTraceState } from './hooks/useTraceState';
import {
  CenteredFooter,
  CenteredMessage,
  CenteredRow,
  ItalicCaption,
  KeyInfoCard,
  KeyInfoValue,
  LastFetchedText,
  ModalTitleContainer,
  ModalTitleLeft,
  ModalTitleRight,
  ModeSegmented,
  NoMarginTitle,
  NoteWrapper,
  ScrollContainer,
  ScrollItem,
  SectionMargin,
} from './styles';
import {
  getCurrentStep,
  getPriorityInfo,
  getSimplifiedStatus,
  getTaskStaleness,
  getTimelineTimestamp,
  isStalePending,
  isTaskStale,
} from './utils';
import type { QueueItemTraceModalProps } from './types';
import type { CollapseProps } from 'antd';

dayjs.extend(relativeTime);

const QueueItemTraceModal: React.FC<QueueItemTraceModalProps> = ({
  taskId,
  open,
  onCancel,
  onTaskStatusChange,
}) => {
  const styles = useComponentStyles();
  const {
    data: traceData,
    isLoading: isTraceLoading,
    refetch: refetchTrace,
  } = useQueueItemTrace(taskId, open);
  const { mutate: retryFailedItem, isPending: isRetrying } = useRetryFailedQueueItem();
  const { mutate: cancelQueueItem, isPending: isCancelling } = useCancelQueueItem();
  const { theme } = useTheme();

  const {
    lastTraceFetchTime,
    isMonitoring,
    activeKeys,
    simpleMode,
    accumulatedOutput,
    consoleProgress,
    progressMessage,
    isSimpleConsoleExpanded,
    isDetailedConsoleExpanded,
    consoleOutputRef,
    setActiveKeys,
    setSimpleMode,
    setIsSimpleConsoleExpanded,
    setIsDetailedConsoleExpanded,
  } = useTraceState({ taskId, open, traceData });

  const totalDurationSeconds = traceData?.queueDetails?.totalDurationSeconds ?? 0;
  const processingDurationSeconds = traceData?.queueDetails?.processingDurationSeconds ?? 0;

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

  const taskStaleness = traceData?.queueDetails ? getTaskStaleness(traceData.queueDetails) : 'none';
  const simplifiedStatus = traceData?.queueDetails
    ? getSimplifiedStatus(traceData.queueDetails)
    : { status: 'unknown', color: 'default' as const, icon: null };

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
      destroyOnClose
      footer={
        <ActionButtons
          queueDetails={traceData?.queueDetails}
          taskId={taskId}
          isCancelling={isCancelling}
          isRetrying={isRetrying}
          isTraceLoading={isTraceLoading}
          taskStaleness={taskStaleness}
          onCancel={handleCancelQueueItem}
          onRetry={handleRetryFailedItem}
          onRefresh={handleRefreshTrace}
          onClose={handleClose}
          styles={styles}
        />
      }
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
          {taskStaleness === 'early' && (
            <RediaccAlert
              data-testid="queue-trace-alert-early"
              message="Task May Be Inactive"
              description="Task hasn't provided updates for over 1 minute. This may be normal for long-running operations."
              variant="info"
              showIcon
              icon={<ClockCircleOutlined />}
              spacing="default"
            />
          )}

          {taskStaleness === 'stale' && (
            <RediaccAlert
              data-testid="queue-trace-alert-stale"
              message="Task May Be Stale"
              description="Task appears inactive for over 1.5 minutes. Consider canceling if no progress is expected."
              variant="warning"
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
              spacing="default"
            />
          )}

          {taskStaleness === 'critical' && (
            <RediaccAlert
              data-testid="queue-trace-alert-critical"
              message="Task Likely Stuck - Cancellation Recommended"
              description="Task has been inactive for over 2 minutes. The queue processor will automatically timeout this task at 3 minutes if no activity is detected."
              variant="error"
              showIcon
              icon={<ExclamationCircleOutlined />}
              action={
                traceData?.queueDetails?.canBeCancelled &&
                (normalizeToString(traceData.queueDetails, 'status', 'Status') === 'PENDING' ||
                  normalizeToString(traceData.queueDetails, 'status', 'Status') === 'ASSIGNED' ||
                  normalizeToString(traceData.queueDetails, 'status', 'Status') ===
                    'PROCESSING') ? (
                  <Button
                    danger
                    type="primary"
                    icon={<CloseCircleOutlined />}
                    onClick={handleCancelQueueItem}
                    loading={isCancelling}
                  >
                    Cancel Stuck Task
                  </Button>
                ) : null
              }
            />
          )}

          {/* Old Pending Warning */}
          {isStalePending(traceData.queueDetails) && (
            <RediaccAlert
              data-testid="queue-trace-alert-old-pending"
              message="Old Pending Task"
              description={`This task has been pending for over 6 hours. It may expire soon if not processed.`}
              variant="warning"
              showIcon
              icon={<WarningOutlined />}
            />
          )}

          {/* Cancelling Status Alert */}
          {traceData.queueDetails &&
            normalizeToString(traceData.queueDetails, 'status', 'Status') === 'CANCELLING' && (
              <RediaccAlert
                data-testid="queue-trace-alert-cancelling"
                message="Task Being Cancelled"
                description="The task is being cancelled. The bridge will stop execution gracefully."
                variant="warning"
                showIcon
                icon={<SyncOutlined spin />}
              />
            )}

          {/* Failure Reason Alert */}
          {traceData.queueDetails &&
            normalizeToString(traceData.queueDetails, 'lastFailureReason', 'LastFailureReason') &&
            normalizeToString(traceData.queueDetails, 'status', 'Status') !== 'CANCELLING' && (
              <RediaccAlert
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
                variant={
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
            <RediaccCard
              spacing="default"
              style={{ marginBottom: '16px' }}
              data-testid="queue-trace-simple-overview"
            >
              <RediaccStack variant="spaced-column" fullWidth>
                {/* Status Summary */}
                <CenteredMessage>
                  <Space size="large">
                    <span
                      className={`queue-trace-status-icon ${simplifiedStatus.status === 'Processing' ? 'processing' : ''}`}
                    >
                      {simplifiedStatus.icon}
                    </span>
                    <NoMarginTitle level={3}>Task {simplifiedStatus.status}</NoMarginTitle>
                  </Space>
                </CenteredMessage>

                {/* Steps */}
                <Steps
                  data-testid="queue-trace-steps"
                  className="queue-trace-steps"
                  current={getCurrentStep(traceData.queueDetails)}
                  status={getCurrentStep(traceData.queueDetails) === -1 ? 'error' : undefined}
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
                        const currentStep = getCurrentStep(traceData.queueDetails);
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
                      <ItalicCaption>{progressMessage}</ItalicCaption>
                    </NoteWrapper>
                  )}

                {/* Progress Bar - Only shown when percentage is found in console output */}
                {consoleProgress !== null && (
                  <Progress
                    data-testid="queue-trace-progress"
                    className="queue-trace-progress"
                    percent={consoleProgress}
                    status={
                      simplifiedStatus.status === 'Failed' ||
                      simplifiedStatus.status === 'Cancelled'
                        ? 'exception'
                        : simplifiedStatus.status === 'Completed'
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
                        <RediaccText variant="caption" color="muted">
                          Duration
                        </RediaccText>
                        <div>
                          <KeyInfoValue>{formatDuration(totalDurationSeconds)}</KeyInfoValue>
                        </div>
                      </KeyInfoCard>
                    </Col>
                    <Col span={8}>
                      <KeyInfoCard
                        data-testid="queue-trace-info-machine"
                        className="queue-trace-key-info"
                      >
                        <RediaccText variant="caption" color="muted">
                          Machine
                        </RediaccText>
                        <div>
                          <RediaccText weight="bold">
                            {traceData.queueDetails.machineName}
                          </RediaccText>
                        </div>
                      </KeyInfoCard>
                    </Col>
                    <Col span={8}>
                      <KeyInfoCard
                        data-testid="queue-trace-info-priority"
                        className="queue-trace-key-info"
                      >
                        <RediaccText variant="caption" color="muted">
                          Priority
                        </RediaccText>
                        <div>
                          <RediaccTag
                            variant={
                              getPriorityInfo(
                                normalizeToNumber(traceData.queueDetails, 0, 'priority', 'Priority')
                              ).color as 'default'
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
                          </RediaccTag>
                        </div>
                      </KeyInfoCard>
                    </Col>
                  </CenteredRow>
                )}
              </RediaccStack>
            </RediaccCard>
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
                        <RediaccText>Response (Console)</RediaccText>
                        {traceData?.queueDetails?.status === 'PROCESSING' && (
                          <RediaccTag icon={<SyncOutlined spin />} variant="primary">
                            Live Output
                          </RediaccTag>
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
                              <RediaccTag
                                variant={
                                  simplifiedStatus.color as
                                    | 'default'
                                    | 'success'
                                    | 'error'
                                    | 'warning'
                                    | 'primary'
                                }
                              >
                                {simplifiedStatus.status}
                              </RediaccTag>
                              {isTaskStale(traceData.queueDetails) && (
                                <RediaccTag variant="warning" icon={<WarningOutlined />}>
                                  Stale
                                </RediaccTag>
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
                                <RediaccStack variant="column" fullWidth gap="md">
                                  <Card
                                    size="small"
                                    title="Task Information"
                                    data-testid="queue-trace-task-info"
                                  >
                                    <Descriptions column={1} size="small">
                                      <Descriptions.Item label="Task ID">
                                        <RediaccText code>
                                          {normalizeToString(
                                            traceData.queueDetails,
                                            'taskId',
                                            'TaskId'
                                          )}
                                        </RediaccText>
                                      </Descriptions.Item>
                                      <Descriptions.Item label="Created By">
                                        <Space>
                                          <UserOutlined />
                                          <RediaccText>
                                            {normalizeToString(
                                              traceData.queueDetails,
                                              'createdBy',
                                              'CreatedBy'
                                            ) || 'System'}
                                          </RediaccText>
                                        </Space>
                                      </Descriptions.Item>
                                      <Descriptions.Item label="Retry Status">
                                        <Space>
                                          <RetweetOutlined />
                                          <RediaccTag
                                            variant={
                                              normalizeToNumber(
                                                traceData.queueDetails,
                                                0,
                                                'retryCount',
                                                'RetryCount'
                                              ) === 0
                                                ? 'success'
                                                : normalizeToNumber(
                                                      traceData.queueDetails,
                                                      0,
                                                      'retryCount',
                                                      'RetryCount'
                                                    ) < 2
                                                  ? 'warning'
                                                  : 'error'
                                            }
                                          >
                                            {normalizeToNumber(
                                              traceData.queueDetails,
                                              0,
                                              'retryCount',
                                              'RetryCount'
                                            )}{' '}
                                            / 2 retries
                                          </RediaccTag>
                                          {normalizeToBoolean(
                                            traceData.queueDetails,
                                            'permanentlyFailed',
                                            'PermanentlyFailed'
                                          ) && (
                                            <RediaccTag variant="error">
                                              Permanently Failed
                                            </RediaccTag>
                                          )}
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
                                          <RediaccTag
                                            variant={
                                              getPriorityInfo(
                                                normalizeToNumber(
                                                  traceData.queueDetails,
                                                  0,
                                                  'priority',
                                                  'Priority'
                                                )
                                              ).color as 'default'
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
                                          </RediaccTag>
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
                                          <RediaccText>
                                            {traceData.queueDetails.machineName}
                                          </RediaccText>
                                        </Space>
                                      </Descriptions.Item>
                                      <Descriptions.Item label="Team">
                                        <RediaccText>{traceData.queueDetails.teamName}</RediaccText>
                                      </Descriptions.Item>
                                      <Descriptions.Item label="Bridge">
                                        <RediaccText>
                                          {traceData.queueDetails.bridgeName}
                                        </RediaccText>
                                      </Descriptions.Item>
                                      <Descriptions.Item label="Region">
                                        <RediaccText>
                                          {traceData.queueDetails.regionName}
                                        </RediaccText>
                                      </Descriptions.Item>
                                    </Descriptions>
                                  </Card>

                                  <StatsPanel
                                    queueDetails={traceData.queueDetails}
                                    totalDurationSeconds={totalDurationSeconds}
                                    processingDurationSeconds={processingDurationSeconds}
                                    isTaskStale={isTaskStale(traceData.queueDetails)}
                                  />
                                </RediaccStack>
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
                                          <RediaccText>Response (Console)</RediaccText>
                                          {traceData.queueDetails?.status === 'PROCESSING' && (
                                            <RediaccTag
                                              icon={<SyncOutlined spin />}
                                              variant="primary"
                                            >
                                              Live Output
                                            </RediaccTag>
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
                              <RediaccText variant="caption" color="muted">
                                (Result Set 1)
                              </RediaccText>
                            </Space>
                          ),
                          children: (
                            <Descriptions column={2} size="small">
                              <Descriptions.Item label="Task ID">
                                <RediaccText code>
                                  {normalizeToString(traceData.queueDetails, 'taskId', 'TaskId')}
                                </RediaccText>
                              </Descriptions.Item>
                              <Descriptions.Item label="Status">
                                <RediaccTag
                                  variant={
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
                                              ? 'primary'
                                              : normalizeToString(
                                                    traceData.queueDetails,
                                                    'status',
                                                    'Status'
                                                  ) === 'ASSIGNED'
                                                ? 'primary'
                                                : 'default'
                                  }
                                >
                                  {normalizeToString(traceData.queueDetails, 'status', 'Status')}
                                </RediaccTag>
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
                                <RediaccTag
                                  variant={
                                    normalizeToNumber(
                                      traceData.queueDetails,
                                      0,
                                      'retryCount',
                                      'RetryCount'
                                    ) === 0
                                      ? 'success'
                                      : normalizeToNumber(
                                            traceData.queueDetails,
                                            0,
                                            'retryCount',
                                            'RetryCount'
                                          ) < 3
                                        ? 'warning'
                                        : 'error'
                                  }
                                >
                                  {normalizeToNumber(
                                    traceData.queueDetails,
                                    0,
                                    'retryCount',
                                    'RetryCount'
                                  )}
                                  /2
                                </RediaccTag>
                              </Descriptions.Item>
                              {normalizeToString(
                                traceData.queueDetails,
                                'lastFailureReason',
                                'LastFailureReason'
                              ) && (
                                <Descriptions.Item label="Last Failure Reason" span={2}>
                                  <RediaccText color="warning">
                                    {normalizeToString(
                                      traceData.queueDetails,
                                      'lastFailureReason',
                                      'LastFailureReason'
                                    )}
                                  </RediaccText>
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
                              <RediaccText variant="caption" color="muted">
                                (Result Set 4 - Audit Log)
                              </RediaccText>
                            </Space>
                          ),
                          children: <TimelineView traceLogs={traceData.traceLogs} />,
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
                              <RediaccText variant="caption" color="muted">
                                (Result Sets 2 & 3)
                              </RediaccText>
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
                                                      icon: <ExclamationCircleOutlined />,
                                                      color: 'var(--color-info)',
                                                    },
                                                  };

                                                  const config =
                                                    statusConfig[
                                                      status as keyof typeof statusConfig
                                                    ] || statusConfig.unknown;

                                                  return (
                                                    <RediaccStack variant="column" fullWidth>
                                                      {/* SSH Test Result Summary */}
                                                      <RediaccCard
                                                        size="sm"
                                                        spacing="default"
                                                        style={{ marginBottom: '16px' }}
                                                        title="SSH Test Result"
                                                      >
                                                        <Descriptions column={2} size="small">
                                                          <Descriptions.Item label="Status">
                                                            <RediaccTag variant="success">
                                                              {result.status}
                                                            </RediaccTag>
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
                                                            <RediaccTag variant="default">
                                                              {result.auth_method}
                                                            </RediaccTag>
                                                          </Descriptions.Item>
                                                          <Descriptions.Item label="SSH Key">
                                                            {result.ssh_key_configured ? (
                                                              <RediaccTag variant="success">
                                                                Configured
                                                              </RediaccTag>
                                                            ) : (
                                                              <RediaccTag variant="warning">
                                                                Not Configured
                                                              </RediaccTag>
                                                            )}
                                                          </Descriptions.Item>
                                                        </Descriptions>
                                                      </RediaccCard>

                                                      {/* System Information */}
                                                      <RediaccCard
                                                        size="sm"
                                                        spacing="default"
                                                        style={{ marginBottom: '16px' }}
                                                        title="System Information"
                                                      >
                                                        <Descriptions column={1} size="small">
                                                          <Descriptions.Item label="Operating System">
                                                            {osInfo.pretty_name || 'Unknown'}
                                                          </Descriptions.Item>
                                                          <Descriptions.Item label="Kernel Version">
                                                            <RediaccText code>
                                                              {compatibility.kernel_version ||
                                                                'Unknown'}
                                                            </RediaccText>
                                                          </Descriptions.Item>
                                                          <Descriptions.Item label="OS ID">
                                                            {osInfo.id || 'Unknown'}
                                                          </Descriptions.Item>
                                                          <Descriptions.Item label="Version">
                                                            {osInfo.version_id || 'Unknown'}
                                                          </Descriptions.Item>
                                                          <Descriptions.Item label="BTRFS Support">
                                                            {compatibility.btrfs_available ? (
                                                              <RediaccTag variant="success">
                                                                Available
                                                              </RediaccTag>
                                                            ) : (
                                                              <RediaccTag variant="warning">
                                                                Not Available
                                                              </RediaccTag>
                                                            )}
                                                          </Descriptions.Item>
                                                          <Descriptions.Item label="Sudo Support">
                                                            {(() => {
                                                              const sudoStatus =
                                                                compatibility.sudo_available ||
                                                                'unknown';
                                                              if (sudoStatus === 'available') {
                                                                return (
                                                                  <RediaccTag variant="success">
                                                                    Available
                                                                  </RediaccTag>
                                                                );
                                                              } else if (
                                                                sudoStatus === 'password_required'
                                                              ) {
                                                                return (
                                                                  <RediaccTag variant="warning">
                                                                    Password Required
                                                                  </RediaccTag>
                                                                );
                                                              } else if (
                                                                sudoStatus === 'not_installed'
                                                              ) {
                                                                return (
                                                                  <RediaccTag variant="error">
                                                                    Not Installed
                                                                  </RediaccTag>
                                                                );
                                                              } else {
                                                                return (
                                                                  <RediaccTag variant="default">
                                                                    Unknown
                                                                  </RediaccTag>
                                                                );
                                                              }
                                                            })()}
                                                          </Descriptions.Item>
                                                        </Descriptions>
                                                      </RediaccCard>

                                                      {/* Compatibility Status */}
                                                      <RediaccAlert
                                                        data-testid="queue-trace-ssh-compatibility-alert"
                                                        variant={config.type}
                                                        icon={config.icon}
                                                        message={
                                                          <Space>
                                                            <RediaccText weight="bold">
                                                              Compatibility Status:
                                                            </RediaccText>
                                                            <RediaccText
                                                              style={{
                                                                color: config.color,
                                                                textTransform: 'capitalize',
                                                              }}
                                                            >
                                                              {status}
                                                            </RediaccText>
                                                          </Space>
                                                        }
                                                        description={
                                                          <>
                                                            {compatibility.compatibility_issues &&
                                                              compatibility.compatibility_issues
                                                                .length > 0 && (
                                                                <SectionMargin $top={spacing('SM')}>
                                                                  <RediaccText weight="bold">
                                                                    Known Issues:
                                                                  </RediaccText>
                                                                  <ul
                                                                    style={{
                                                                      marginTop: spacing('XS'),
                                                                      marginBottom: spacing('SM'),
                                                                    }}
                                                                  >
                                                                    {compatibility.compatibility_issues.map(
                                                                      (
                                                                        issue: string,
                                                                        index: number
                                                                      ) => (
                                                                        <li key={index}>{issue}</li>
                                                                      )
                                                                    )}
                                                                  </ul>
                                                                </SectionMargin>
                                                              )}
                                                            {compatibility.recommendations &&
                                                              compatibility.recommendations.length >
                                                                0 && (
                                                                <SectionMargin>
                                                                  <RediaccText weight="bold">
                                                                    Recommendations:
                                                                  </RediaccText>
                                                                  <ul
                                                                    style={{
                                                                      marginTop: spacing('XS'),
                                                                    }}
                                                                  >
                                                                    {compatibility.recommendations.map(
                                                                      (
                                                                        rec: string,
                                                                        index: number
                                                                      ) => (
                                                                        <li key={index}>{rec}</li>
                                                                      )
                                                                    )}
                                                                  </ul>
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
                                                    </RediaccStack>
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
                              <RediaccText variant="caption" color="muted">
                                (Result Set 5 - Nearby Tasks)
                              </RediaccText>
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
                                              <RediaccText
                                                size="xs"
                                                code
                                                style={{ fontFamily: 'monospace' }}
                                              >
                                                {item.taskId}
                                              </RediaccText>
                                              <RediaccTag
                                                compact
                                                variant={
                                                  item.status === 'PROCESSING'
                                                    ? 'primary'
                                                    : 'neutral'
                                                }
                                              >
                                                {item.status}
                                              </RediaccTag>
                                              <RediaccText variant="caption" color="muted">
                                                {dayjs(item.createdTime).fromNow()}
                                              </RediaccText>
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
                                              <RediaccText
                                                size="xs"
                                                code
                                                style={{ fontFamily: 'monospace' }}
                                              >
                                                {item.taskId}
                                              </RediaccText>
                                              <RediaccTag
                                                compact
                                                variant={
                                                  item.status === 'PROCESSING'
                                                    ? 'primary'
                                                    : 'neutral'
                                                }
                                              >
                                                {item.status}
                                              </RediaccTag>
                                              <RediaccText variant="caption" color="muted">
                                                {dayjs(item.createdTime).fromNow()}
                                              </RediaccText>
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
                                <RediaccText variant="caption" color="muted">
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
                                </RediaccText>
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
                              <RediaccText variant="caption" color="muted">
                                (Result Set 6 - Machine Stats)
                              </RediaccText>
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
                                    <RediaccText color="secondary">
                                      Currently being processed on this machine
                                    </RediaccText>
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
                              <RediaccAlert
                                data-testid="queue-trace-performance-alert"
                                message="Performance Analysis"
                                description={
                                  <Space direction="vertical">
                                    {traceData.machineStats.currentQueueDepth > 50 && (
                                      <RediaccText>
                                        High queue depth detected. Tasks may experience delays.
                                      </RediaccText>
                                    )}
                                    {traceData.machineStats.activeProcessingCount >=
                                      (traceData.machineStats.maxConcurrentTasks || 0) && (
                                      <RediaccText>
                                        Machine at full capacity. New tasks will wait in queue.
                                      </RediaccText>
                                    )}
                                    {traceData.machineStats.currentQueueDepth === 0 &&
                                      traceData.machineStats.activeProcessingCount === 0 && (
                                        <RediaccText>
                                          Machine is idle and ready to process tasks immediately.
                                        </RediaccText>
                                      )}
                                  </Space>
                                }
                                variant={
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
