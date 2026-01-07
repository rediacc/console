import React, { useEffect, useState } from 'react';
import { Badge, Collapse, Empty, Flex, Segmented, Space, Tag, Tooltip, Typography } from 'antd';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import { useTranslation } from 'react-i18next';
import {
  useCancelQueueItemWithInvalidation,
  useQueueItemTraceWithEnabled,
  useRetryQueueItemWithInvalidation,
} from '@/api/hooks-queue';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { SizedModal } from '@/components/common/SizedModal';
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
import { getSimplifiedStatus, getTaskStaleness, isTaskStale } from './utils';
import { isTaskInTerminalState } from './utils/taskStateUtils';
import type { ConsoleViewMode, QueueItemTraceModalProps } from './types';
import type { CollapseProps } from 'antd';

dayjs.extend(relativeTime);

const QueueItemTraceModal: React.FC<QueueItemTraceModalProps> = ({
  taskId,
  open,
  onCancel,
  onTaskStatusChange,
}) => {
  const { t } = useTranslation(['queue', 'common']);
  const {
    data: traceData,
    isLoading: isTraceLoading,
    refetch: refetchTrace,
  } = useQueueItemTraceWithEnabled(taskId, open);
  const { mutate: retryFailedItem, isPending: isRetrying } = useRetryQueueItemWithInvalidation();
  const { mutate: cancelQueueItem, isPending: isCancelling } = useCancelQueueItemWithInvalidation();

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

  const [consoleViewMode, setConsoleViewMode] = useState<ConsoleViewMode>('structured');

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
    retryFailedItem({ taskId }, { onSuccess: () => refetchTrace() });
  };

  const handleCancelQueueItem = () => {
    if (!taskId) return;
    cancelQueueItem({ taskId }, { onSuccess: () => refetchTrace() });
  };

  const handleClose = () => {
    if (!taskId || !isMonitoring || !traceData?.queueDetails) {
      onCancel();
      return;
    }

    if (!isTaskInTerminalState(traceData.queueDetails)) {
      showMessage('info', t('trace.taskMonitoringContinue', { taskId }));
    }

    onCancel();
  };

  const taskStaleness = traceData?.queueDetails ? getTaskStaleness(traceData.queueDetails) : 'none';
  const simplifiedStatus = traceData?.queueDetails
    ? getSimplifiedStatus(traceData.queueDetails)
    : { status: 'unknown', color: 'default' as const, icon: null };

  return (
    <SizedModal
      size={ModalSize.Large}
      data-testid="queue-trace-modal"
      title={
        <Flex align="center" justify="space-between" wrap>
          <Flex align="center">
            <HistoryOutlined />
            <Typography.Text>{`${t('trace.modalTitle')} - ${taskId ?? ''}`}</Typography.Text>
          </Flex>
          <Flex align="center" wrap>
            <Segmented
              data-testid="queue-trace-mode-switch"
              value={simpleMode ? 'simple' : 'detailed'}
              onChange={(value) => setSimpleMode(value === 'simple')}
              options={[
                { label: t('trace.modeSimple'), value: 'simple' },
                { label: t('trace.modeDetailed'), value: 'detailed' },
              ]}
            />
            {lastTraceFetchTime && (
              <Typography.Text>
                {t('trace.lastFetched', { time: lastTraceFetchTime.format('HH:mm:ss') })}
              </Typography.Text>
            )}
          </Flex>
        </Flex>
      }
      open={open}
      onCancel={handleClose}
      destroyOnHidden
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
        />
      }
    >
      {isTraceLoading ? (
        <Flex className="queue-trace-loading">
          <LoadingWrapper loading centered minHeight={160}>
            <Flex />
          </LoadingWrapper>
        </Flex>
      ) : traceData ? (
        <Flex vertical>
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

              <Flex vertical className="mt-4">
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
                          <Typography.Text>{t('trace.responseConsole')}</Typography.Text>
                          {traceData.queueDetails.status === 'PROCESSING' && (
                            <Tag>{t('trace.liveOutput')}</Tag>
                          )}
                        </Space>
                      ),
                      extra: (
                        <Segmented
                          size="small"
                          value={consoleViewMode}
                          onChange={(value) => setConsoleViewMode(value as ConsoleViewMode)}
                          options={[
                            { label: t('trace.structuredLog.viewStructured'), value: 'structured' },
                            { label: t('trace.structuredLog.viewRaw'), value: 'raw' },
                          ]}
                          onClick={(e) => e.stopPropagation()}
                          data-testid="console-output-view-toggle"
                        />
                      ),
                      children: (
                        <ConsoleOutput
                          content={accumulatedOutput}
                          consoleOutputRef={consoleOutputRef}
                          isEmpty={!traceData.responseVaultContent?.hasContent}
                          viewMode={consoleViewMode}
                        />
                      ),
                    },
                  ]}
                />
              </Flex>
            </>
          )}

          {!simpleMode && (
            <Flex vertical className="mt-4">
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
                              <Typography.Text>{t('trace.taskOverview')}</Typography.Text>
                              <Tag>{simplifiedStatus.status}</Tag>
                              {isTaskStale(traceData.queueDetails) && (
                                <Tag icon={<WarningOutlined />}>{t('trace.stale')}</Tag>
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
                              <Tooltip title={t('common:tooltips.taskCancellable')}>
                                <Badge status="processing" text={t('trace.cancellable')} />
                              </Tooltip>
                            ) : undefined,
                          children: (
                            <MachineDetails
                              queueDetails={traceData.queueDetails}
                              totalDurationSeconds={totalDurationSeconds}
                              processingDurationSeconds={processingDurationSeconds}
                              isDetailedConsoleExpanded={isDetailedConsoleExpanded}
                              setIsDetailedConsoleExpanded={setIsDetailedConsoleExpanded}
                              accumulatedOutput={accumulatedOutput}
                              consoleOutputRef={consoleOutputRef}
                              hasContent={!!traceData.responseVaultContent?.hasContent}
                              consoleViewMode={consoleViewMode}
                              setConsoleViewMode={setConsoleViewMode}
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
                              <Typography.Text>{t('trace.queueItemDetails')}</Typography.Text>
                              <Typography.Text>{t('trace.resultSet1')}</Typography.Text>
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

                    traceData.traceLogs.length > 0
                      ? {
                          key: 'timeline',
                          label: (
                            <Space>
                              <HistoryOutlined />
                              <Typography.Text>{t('trace.processingTimeline')}</Typography.Text>
                              <Typography.Text>{t('trace.resultSet4')}</Typography.Text>
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
                              <Typography.Text>{t('trace.vaultContent')}</Typography.Text>
                              <Typography.Text>{t('trace.resultSets2And3')}</Typography.Text>
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

                    traceData.queuePosition.length > 0
                      ? {
                          key: 'related',
                          label: (
                            <Space>
                              <TeamOutlined />
                              <Typography.Text>{t('trace.relatedQueueItems')}</Typography.Text>
                              <Typography.Text>{t('trace.resultSet5')}</Typography.Text>
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
                              <Typography.Text>
                                {t('trace.performanceMetricsTitle')}
                              </Typography.Text>
                              <Typography.Text>{t('trace.resultSet6')}</Typography.Text>
                            </Space>
                          ),
                          children: <PerformanceMetrics machineStats={traceData.machineStats} />,
                        }
                      : null,
                  ].filter(Boolean) as CollapseProps['items']
                }
              />
            </Flex>
          )}
        </Flex>
      ) : (
        <Empty description={t('trace.noTraceData')} />
      )}
    </SizedModal>
  );
};

export default QueueItemTraceModal;
