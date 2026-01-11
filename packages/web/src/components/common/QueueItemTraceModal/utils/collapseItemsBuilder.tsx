import React from 'react';
import { Badge, Space, Tag, Tooltip, Typography } from 'antd';
import { normalizeToString } from '@/platform';
import {
  DashboardOutlined,
  FileTextOutlined,
  HistoryOutlined,
  TeamOutlined,
  WarningOutlined,
} from '@/utils/optimizedIcons';
import {
  MachineDetails,
  PerformanceMetrics,
  QueueItemDetails,
  RelatedQueueItems,
  ResponseVaultContent,
  TimelineView,
} from '../components';
import { isTaskStale } from '../utils';
import type { ConsoleViewMode, QueueItemTraceData, SimplifiedStatus } from '../types';
import type { CollapseProps } from 'antd';

// Generic translation function type that accepts any namespace configuration
type TranslateFn = (key: string, options?: Record<string, unknown>) => string;

/** Type for a single collapse panel item - extracted to avoid any-union issues */
interface CollapseItem {
  key: string;
  label: React.ReactNode;
  extra?: React.ReactNode;
  children: React.ReactNode;
}

interface BuildCollapseItemsParams {
  traceData: QueueItemTraceData;
  simplifiedStatus: SimplifiedStatus;
  totalDurationSeconds: number;
  processingDurationSeconds: number;
  isDetailedConsoleExpanded: boolean;
  setIsDetailedConsoleExpanded: (expanded: boolean) => void;
  accumulatedOutput: string;
  consoleOutputRef: React.RefObject<HTMLDivElement | null>;
  consoleViewMode: ConsoleViewMode;
  setConsoleViewMode: (mode: ConsoleViewMode) => void;
  t: TranslateFn;
}

const NON_ACTIVE_STATUSES = ['COMPLETED', 'CANCELLED', 'CANCELLING', 'FAILED'] as const;
type NonActiveStatus = (typeof NON_ACTIVE_STATUSES)[number];

function isCancellable(queueDetails: NonNullable<QueueItemTraceData['queueDetails']>): boolean {
  if (!queueDetails.canBeCancelled) return false;
  const status = normalizeToString(queueDetails, 'status', 'Status');
  return !NON_ACTIVE_STATUSES.includes(status as NonActiveStatus);
}

function buildOverviewItem(params: BuildCollapseItemsParams): CollapseItem | null {
  const {
    traceData,
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
  } = params;

  if (!traceData.queueDetails) return null;

  return {
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
    extra: isCancellable(traceData.queueDetails) ? (
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
  };
}

function buildDetailsItem(
  traceData: QueueItemTraceData,
  totalDurationSeconds: number,
  processingDurationSeconds: number,
  t: TranslateFn
): CollapseItem | null {
  if (!traceData.queueDetails) return null;

  return {
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
  };
}

function buildTimelineItem(traceData: QueueItemTraceData, t: TranslateFn): CollapseItem | null {
  if (traceData.traceLogs.length === 0) return null;

  return {
    key: 'timeline',
    label: (
      <Space>
        <HistoryOutlined />
        <Typography.Text>{t('trace.processingTimeline')}</Typography.Text>
        <Typography.Text>{t('trace.resultSet4')}</Typography.Text>
      </Space>
    ),
    children: <TimelineView traceLogs={traceData.traceLogs} />,
  };
}

function buildVaultItem(traceData: QueueItemTraceData, t: TranslateFn): CollapseItem | null {
  if (!traceData.vaultContent && !traceData.responseVaultContent) return null;

  return {
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
  };
}

function buildRelatedItem(traceData: QueueItemTraceData, t: TranslateFn): CollapseItem | null {
  if (traceData.queuePosition.length === 0) return null;

  return {
    key: 'related',
    label: (
      <Space>
        <TeamOutlined />
        <Typography.Text>{t('trace.relatedQueueItems')}</Typography.Text>
        <Typography.Text>{t('trace.resultSet5')}</Typography.Text>
      </Space>
    ),
    children: <RelatedQueueItems queuePosition={traceData.queuePosition} />,
  };
}

function buildPerformanceItem(traceData: QueueItemTraceData, t: TranslateFn): CollapseItem | null {
  if (!traceData.machineStats) return null;

  return {
    key: 'performance',
    label: (
      <Space>
        <DashboardOutlined />
        <Typography.Text>{t('trace.performanceMetricsTitle')}</Typography.Text>
        <Typography.Text>{t('trace.resultSet6')}</Typography.Text>
      </Space>
    ),
    children: <PerformanceMetrics machineStats={traceData.machineStats} />,
  };
}

export function buildDetailedCollapseItems(
  params: BuildCollapseItemsParams
): CollapseProps['items'] {
  const { traceData, t } = params;

  const items: (CollapseItem | null)[] = [
    buildOverviewItem(params),
    buildDetailsItem(traceData, params.totalDurationSeconds, params.processingDurationSeconds, t),
    buildTimelineItem(traceData, t),
    buildVaultItem(traceData, t),
    buildRelatedItem(traceData, t),
    buildPerformanceItem(traceData, t),
  ];

  return items.filter((item): item is CollapseItem => item !== null);
}
