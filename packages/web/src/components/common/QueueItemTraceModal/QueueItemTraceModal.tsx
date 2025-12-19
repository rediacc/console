import React, { useEffect } from 'react';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import { useTranslation } from 'react-i18next';
import type { CollapseProps } from 'antd';
import { Badge, Collapse, Empty, Modal, Space } from 'antd';
import {
  useCancelQueueItem,
  useQueueItemTrace,
  useRetryFailedQueueItem,
} from '@/api/queries/queue';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { RediaccTag, RediaccText, RediaccTooltip } from '@/components/ui';
import { useTheme } from '@/context/ThemeContext';
import { useComponentStyles } from '@/hooks/useComponentStyles';
import { normalizeToString } from '@/platform';
import { ModalSize } from '@/types/modal';
import { showMessage } from '@/utils/messages';
import {
  DashboardOutlined,
  FileTextOutlined,
  HistoryOutlined,
  RightOutlined,
  TeamOutlined,
  WarningOutlined,
} from '@/utils/optimizedIcons';
import { spacing } from '@/utils/styleConstants';
import {
  ActionButtons,
  ConsoleOutput,
  FailureReasonAlert,
  MachineDetails,
  OldPendingWarning,
  PerformanceMetrics,
  QueueItemDetails,
  QueueItemHeader,
  RelatedQueueItems,
  ResponseVaultContent,
  StaleTaskWarning,
  TimelineView,
} from './components';
import { useTraceState } from './hooks/useTraceState';
import {
  LastFetchedText,
  ModalTitleContainer,
  ModalTitleLeft,
  ModalTitleRight,
  ModeSegmented,
  SectionMargin,
} from './styles';
import { getSimplifiedStatus, getTaskStaleness, isTaskStale } from './utils';
import type { QueueItemTraceModalProps } from './types';
import { isTaskInTerminalState } from './utils/taskStateUtils';

dayjs.extend(relativeTime);

const QueueItemTraceModal: React.FC<QueueItemTraceModalProps> = ({
  taskId,
  open,
  onCancel,
  onTaskStatusChange,
}) => {
  const { t } = useTranslation(['queue', 'common']);
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

  useEffect(() => {
    if (!traceData?.queueDetails || !taskId || !onTaskStatusChange) return;

    const status = normalizeToString(traceData.queueDetails, 'status', 'Status');
    if (status === 'FAILED' || status === 'COMPLETED' || status === 'CANCELLED') {
      onTaskStatusChange(status, taskId);
    }
  }, [traceData?.queueDetails, taskId, onTaskStatusChange]);

  const handleRefreshTrace = async () => {
    await refetchTrace();
  };

  const handleRetryFailedItem = () => {
    if (!taskId) return;
    retryFailedItem(taskId, { onSuccess: () => refetchTrace() });
  };

  const handleCancelQueueItem = () => {
    if (!taskId) return;
    cancelQueueItem(taskId, { onSuccess: () => refetchTrace() });
  };

  const handleClose = () => {
    if (!taskId || !isMonitoring || !traceData?.queueDetails) {
      onCancel();
      return;
    }

    if (!isTaskInTerminalState(traceData.queueDetails)) {
      showMessage('info', `Task ${taskId} will continue to be monitored in the background`);
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
          <StaleTaskWarning
            taskStaleness={taskStaleness}
            queueDetails={traceData.queueDetails}
            isCancelling={isCancelling}
            onCancel={handleCancelQueueItem}
          />

          <OldPendingWarning queueDetails={traceData.queueDetails} />

          <FailureReasonAlert queueDetails={traceData.queueDetails} />

          {simpleMode && traceData.queueDetails && (
            <>
              <QueueItemHeader
                queueDetails={traceData.queueDetails}
                traceLogs={traceData.traceLogs}
                progressMessage={progressMessage}
                consoleProgress={consoleProgress}
              />

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
                          <span>Response (Console)</span>
                          {traceData?.queueDetails?.status === 'PROCESSING' && (
                            <RediaccTag variant="primary">Live Output</RediaccTag>
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
            </>
          )}

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
                                    | 'neutral'
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
                              <RediaccTooltip title={t('common:tooltips.taskCancellable')}>
                                <Badge status="processing" text="Cancellable" />
                              </RediaccTooltip>
                            ) : undefined,
                          children: (
                            <MachineDetails
                              queueDetails={traceData.queueDetails}
                              totalDurationSeconds={totalDurationSeconds}
                              processingDurationSeconds={processingDurationSeconds}
                              isTaskStale={isTaskStale(traceData.queueDetails)}
                              isDetailedConsoleExpanded={isDetailedConsoleExpanded}
                              setIsDetailedConsoleExpanded={setIsDetailedConsoleExpanded}
                              accumulatedOutput={accumulatedOutput}
                              theme={theme}
                              consoleOutputRef={consoleOutputRef}
                              hasContent={!!traceData.responseVaultContent?.hasContent}
                            />
                          ),
                        }
                      : null,

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
                            <QueueItemDetails
                              queueDetails={traceData.queueDetails}
                              totalDurationSeconds={totalDurationSeconds}
                              processingDurationSeconds={processingDurationSeconds}
                            />
                          ),
                        }
                      : null,

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
                            <ResponseVaultContent
                              vaultContent={traceData.vaultContent}
                              responseVaultContent={traceData.responseVaultContent}
                            />
                          ),
                        }
                      : null,

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
                          children: <RelatedQueueItems queuePosition={traceData.queuePosition} />,
                        }
                      : null,

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
                          children: <PerformanceMetrics machineStats={traceData.machineStats} />,
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
