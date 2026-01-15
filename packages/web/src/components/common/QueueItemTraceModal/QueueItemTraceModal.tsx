import type { QueueTrace } from '@rediacc/shared/types';
import { Collapse, Empty, Flex, Segmented, Space, Tag, Typography } from 'antd';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import React, { useEffect, useState } from 'react';
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
import { HistoryOutlined, RightOutlined } from '@/utils/optimizedIcons';
import {
  ActionButtons,
  ConsoleOutput,
  FailureReasonAlert,
  OldPendingWarning,
  QueueItemHeader,
  StaleTaskWarning,
} from './components';
import { useTraceState } from './hooks/useTraceState';
import type { ConsoleViewMode, QueueItemTraceModalProps } from './types';
import { getSimplifiedStatus, getTaskStaleness } from './utils';
import { buildDetailedCollapseItems } from './utils/collapseItemsBuilder';
import { isTaskInTerminalState } from './utils/taskStateUtils';

// Generic translation function type that accepts any namespace configuration
type TranslateFn = (key: string, options?: Record<string, unknown>) => string;

dayjs.extend(relativeTime);

interface ModalContentProps {
  isTraceLoading: boolean;
  traceData: QueueTrace | undefined;
  taskStaleness: 'none' | 'early' | 'stale' | 'critical';
  isCancelling: boolean;
  handleCancelQueueItem: () => void;
  simpleMode: boolean;
  progressMessage: string | null;
  consoleProgress: number | null;
  isSimpleConsoleExpanded: boolean;
  setIsSimpleConsoleExpanded: (expanded: boolean) => void;
  consoleViewMode: ConsoleViewMode;
  setConsoleViewMode: (mode: ConsoleViewMode) => void;
  accumulatedOutput: string;
  consoleOutputRef: React.RefObject<HTMLDivElement | null>;
  activeKeys: string[];
  setActiveKeys: (keys: string[]) => void;
  simplifiedStatus: {
    status: string;
    color: 'neutral' | 'success' | 'error' | 'warning' | 'primary' | 'default';
    icon: React.ReactNode;
  };
  totalDurationSeconds: number;
  processingDurationSeconds: number;
  isDetailedConsoleExpanded: boolean;
  setIsDetailedConsoleExpanded: (expanded: boolean) => void;
  t: TranslateFn;
}

const LoadingState: React.FC = () => (
  <Flex className="queue-trace-loading">
    <LoadingWrapper loading centered minHeight={160}>
      <Flex />
    </LoadingWrapper>
  </Flex>
);

const SimpleModeContent: React.FC<{
  traceData: QueueTrace;
  progressMessage: string | null;
  consoleProgress: number | null;
  isSimpleConsoleExpanded: boolean;
  setIsSimpleConsoleExpanded: (expanded: boolean) => void;
  consoleViewMode: ConsoleViewMode;
  setConsoleViewMode: (mode: ConsoleViewMode) => void;
  accumulatedOutput: string;
  consoleOutputRef: React.RefObject<HTMLDivElement | null>;
  t: TranslateFn;
}> = ({
  traceData,
  progressMessage,
  consoleProgress,
  isSimpleConsoleExpanded,
  setIsSimpleConsoleExpanded,
  consoleViewMode,
  setConsoleViewMode,
  accumulatedOutput,
  consoleOutputRef,
  t,
}) => {
  if (!traceData.queueDetails) return null;

  return (
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
  );
};

const DetailedModeContent: React.FC<{
  traceData: QueueTrace;
  activeKeys: string[];
  setActiveKeys: (keys: string[]) => void;
  simplifiedStatus: { status: string; color: string; icon: React.ReactNode };
  totalDurationSeconds: number;
  processingDurationSeconds: number;
  isDetailedConsoleExpanded: boolean;
  setIsDetailedConsoleExpanded: (expanded: boolean) => void;
  accumulatedOutput: string;
  consoleOutputRef: React.RefObject<HTMLDivElement | null>;
  consoleViewMode: ConsoleViewMode;
  setConsoleViewMode: (mode: ConsoleViewMode) => void;
  t: TranslateFn;
}> = ({
  traceData,
  activeKeys,
  setActiveKeys,
  simplifiedStatus,
  totalDurationSeconds,
  processingDurationSeconds,
  isDetailedConsoleExpanded,
  setIsDetailedConsoleExpanded,
  accumulatedOutput,
  consoleOutputRef,
  consoleViewMode,
  setConsoleViewMode,
  t,
}) => (
  <Flex vertical className="mt-4">
    <Collapse
      data-testid="queue-trace-collapse"
      className="queue-trace-collapse"
      activeKey={activeKeys}
      onChange={setActiveKeys}
      expandIcon={({ isActive }) => <RightOutlined rotate={isActive ? 90 : 0} />}
      items={buildDetailedCollapseItems({
        traceData,
        simplifiedStatus: simplifiedStatus as {
          status: string;
          color: 'neutral' | 'success' | 'error' | 'warning' | 'primary';
          icon: React.ReactNode;
        },
        totalDurationSeconds,
        processingDurationSeconds,
        isDetailedConsoleExpanded,
        setIsDetailedConsoleExpanded,
        accumulatedOutput,
        consoleOutputRef,
        consoleViewMode,
        setConsoleViewMode,
        t,
      })}
    />
  </Flex>
);

const ModalContent: React.FC<ModalContentProps> = ({
  isTraceLoading,
  traceData,
  taskStaleness,
  isCancelling,
  handleCancelQueueItem,
  simpleMode,
  progressMessage,
  consoleProgress,
  isSimpleConsoleExpanded,
  setIsSimpleConsoleExpanded,
  consoleViewMode,
  setConsoleViewMode,
  accumulatedOutput,
  consoleOutputRef,
  activeKeys,
  setActiveKeys,
  simplifiedStatus,
  totalDurationSeconds,
  processingDurationSeconds,
  isDetailedConsoleExpanded,
  setIsDetailedConsoleExpanded,
  t,
}) => {
  if (isTraceLoading) return <LoadingState />;

  if (!traceData) return <Empty description={t('trace.noTraceData')} />;

  return (
    <Flex vertical>
      <StaleTaskWarning
        taskStaleness={taskStaleness}
        queueDetails={traceData.queueDetails}
        isCancelling={isCancelling}
        onCancel={handleCancelQueueItem}
      />
      <OldPendingWarning queueDetails={traceData.queueDetails} />
      <FailureReasonAlert queueDetails={traceData.queueDetails} />

      {simpleMode ? (
        <SimpleModeContent
          traceData={traceData}
          progressMessage={progressMessage}
          consoleProgress={consoleProgress}
          isSimpleConsoleExpanded={isSimpleConsoleExpanded}
          setIsSimpleConsoleExpanded={setIsSimpleConsoleExpanded}
          consoleViewMode={consoleViewMode}
          setConsoleViewMode={setConsoleViewMode}
          accumulatedOutput={accumulatedOutput}
          consoleOutputRef={consoleOutputRef}
          t={t}
        />
      ) : (
        <DetailedModeContent
          traceData={traceData}
          activeKeys={activeKeys}
          setActiveKeys={setActiveKeys}
          simplifiedStatus={simplifiedStatus}
          totalDurationSeconds={totalDurationSeconds}
          processingDurationSeconds={processingDurationSeconds}
          isDetailedConsoleExpanded={isDetailedConsoleExpanded}
          setIsDetailedConsoleExpanded={setIsDetailedConsoleExpanded}
          accumulatedOutput={accumulatedOutput}
          consoleOutputRef={consoleOutputRef}
          consoleViewMode={consoleViewMode}
          setConsoleViewMode={setConsoleViewMode}
          t={t}
        />
      )}
    </Flex>
  );
};

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
      <ModalContent
        isTraceLoading={isTraceLoading}
        traceData={traceData}
        taskStaleness={taskStaleness}
        isCancelling={isCancelling}
        handleCancelQueueItem={handleCancelQueueItem}
        simpleMode={simpleMode}
        progressMessage={progressMessage}
        consoleProgress={consoleProgress}
        isSimpleConsoleExpanded={isSimpleConsoleExpanded}
        setIsSimpleConsoleExpanded={setIsSimpleConsoleExpanded}
        consoleViewMode={consoleViewMode}
        setConsoleViewMode={setConsoleViewMode}
        accumulatedOutput={accumulatedOutput}
        consoleOutputRef={consoleOutputRef}
        activeKeys={activeKeys}
        setActiveKeys={setActiveKeys}
        simplifiedStatus={simplifiedStatus}
        totalDurationSeconds={totalDurationSeconds}
        processingDurationSeconds={processingDurationSeconds}
        isDetailedConsoleExpanded={isDetailedConsoleExpanded}
        setIsDetailedConsoleExpanded={setIsDetailedConsoleExpanded}
        t={t}
      />
    </SizedModal>
  );
};

export default QueueItemTraceModal;
