import React, { useCallback, useMemo } from 'react';
import { Dropdown, Modal, Space, Tabs, Tooltip } from 'antd';
import dayjs, { Dayjs } from 'dayjs';
import { useTranslation } from 'react-i18next';
import styled, { useTheme as useStyledTheme } from 'styled-components';
import {
  QueueFilters,
  type QueueStatistics,
  useCancelQueueItem,
  useQueueItems,
} from '@/api/queries/queue';
import { useDropdownData } from '@/api/queries/useDropdownData';
import { renderBoolean, renderTimestamp } from '@/components/common/columns';
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal';
import ResourceListView from '@/components/common/ResourceListView';
import {
  PageWrapper,
  RediaccButton,
  RediaccCard,
  RediaccStack,
  RediaccText,
} from '@/components/ui';
import { RediaccTag } from '@/components/ui/Tag';
import { useFilters, useMultiPagination, useQueueTraceModal } from '@/hooks';
import FilterTagDisplay, { FilterTagConfig } from '@/pages/queue/components/FilterTagDisplay';
import {
  filterActiveItems,
  filterCancelledItems,
  filterCompletedItems,
  filterFailedItems,
  formatAge,
  formatTimestampAsIs,
  getSeverityColor,
  isValidGuid,
  parseFailureReason,
  STALE_TASK_CONSTANTS,
} from '@/platform';
import {
  FilterCheckbox,
  FilterInput,
  FilterRangePicker,
  FilterSelect,
  StatDivider,
  StatIcon,
  StatValue,
  TabCount,
  TabLabel,
} from '@/styles/primitives';
import { confirmAction } from '@/utils/confirmations';
import { showMessage } from '@/utils/messages';
import {
  ApiOutlined,
  CloseCircleOutlined,
  DesktopOutlined,
  ExclamationCircleOutlined,
  ExportOutlined,
  GlobalOutlined,
  HistoryOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SearchOutlined,
  ThunderboltOutlined,
  WarningOutlined,
} from '@/utils/optimizedIcons';
import { renderPriority, renderQueueStatus } from '@/utils/queueRenderers';
import type { ParsedError } from '@rediacc/shared/error-parser';
import type { GetTeamQueueItems_ResultSet1 as QueueItem } from '@rediacc/shared/types';
import type { ColumnsType } from 'antd/es/table';

// Page-level filter state type
type QueuePageFilters = {
  teamName: string;
  machineName: string;
  regionName: string;
  bridgeName: string;
  statusFilter: string[];
  dateRange: [Dayjs | null, Dayjs | null] | null;
  taskIdFilter: string;
  onlyStale: boolean;
  includeCompleted: boolean;
  includeCancelled: boolean;
};

const TooltipContent = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.XS / 2}px;
  min-width: 240px;
`;

const TooltipContentSection = styled.div`
  width: 100%;
`;

/**
 * @deprecated Use <RediaccStack variant="row" gap={4} fullWidth /> with inline style for margin
 */
const TooltipPrimaryRow = styled(RediaccStack).attrs({ direction: 'horizontal', gap: 4 })`
  && {
    width: 100%;
    margin-bottom: ${({ theme }) => theme.spacing.XS / 2}px;
  }
`;

const SeverityPill = styled(RediaccTag)<{ $color?: string }>`
  && {
    margin: 0;
    font-size: ${({ theme }) => theme.fontSize.XS}px;
    line-height: 1.2;
    ${({ $color }) => $color && `background-color: ${$color}; border-color: ${$color}; color: white;`}
  }
`;

const TruncatedErrorText = styled(RediaccText).attrs({ size: 'sm', color: 'muted' })`
  && {
    display: inline-flex;
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
`;

const RetrySummaryTag = styled(RediaccTag)<{ $color?: string }>`
  && {
    margin: 0;
    ${({ $color }) => $color && `background-color: ${$color}; border-color: ${$color}; color: white;`}
  }
`;
const QueuePage: React.FC = () => {
  const { t } = useTranslation(['queue', 'common']);
  const [modal, contextHolder] = Modal.useModal();
  const theme = useStyledTheme();

  // Filter state management with useFilters hook
  const {
    filters,
    setFilter,
    clearAllFilters,
    hasActiveFilters: checkHasActiveFilters,
  } = useFilters<QueuePageFilters>({
    teamName: '',
    machineName: '',
    regionName: '',
    bridgeName: '',
    statusFilter: [],
    dateRange: null,
    taskIdFilter: '',
    onlyStale: false,
    includeCompleted: true,
    includeCancelled: true,
  });

  // Active tab state
  const [activeTab, setActiveTab] = React.useState<string>('active');

  // Pagination state for each tab using multi-pagination hook
  const pagination = useMultiPagination(['active', 'completed', 'cancelled', 'failed']);

  // Queue trace modal
  const queueTrace = useQueueTraceModal();
  const dateRangeValue: [Dayjs | null, Dayjs | null] | undefined = filters.dateRange ?? undefined;

  const handleDateRangeChange = useCallback(
    (dates: [Dayjs | null, Dayjs | null] | null, _dateStrings?: [string, string]) => {
      setFilter('dateRange', dates);
    },
    [setFilter]
  );

  const handleStatusFilterChange = useCallback(
    (values: Array<string | number>, _options: unknown) => {
      const normalized = values.map((value) => String(value));
      setFilter('statusFilter', normalized);
    },
    [setFilter]
  );

  // Combine filter state into API query format
  const queryFilters = useMemo(
    (): QueueFilters => ({
      teamName: filters.teamName,
      machineName: filters.machineName,
      bridgeName: filters.bridgeName,
      onlyStale: filters.onlyStale,
      staleThresholdMinutes: 10,
      maxRecords: 1000,
      // Auto-enable includeCancelled when on cancelled tab
      includeCancelled: activeTab === 'cancelled' ? true : filters.includeCancelled,
      // Auto-enable includeCompleted when on completed tab
      includeCompleted: activeTab === 'completed' ? true : filters.includeCompleted,
      dateFrom: filters.dateRange?.[0]?.startOf('day').format('YYYY-MM-DD HH:mm:ss'),
      dateTo: filters.dateRange?.[1]?.endOf('day').format('YYYY-MM-DD HH:mm:ss'),
      status: filters.statusFilter.join(','),
      ...(filters.taskIdFilter.trim() && isValidGuid(filters.taskIdFilter.trim())
        ? { taskId: filters.taskIdFilter.trim() }
        : {}),
    }),
    [filters, activeTab]
  );

  const { data: queueData, isLoading, refetch, isRefetching } = useQueueItems(queryFilters);
  const { data: dropdownData } = useDropdownData();
  const cancelQueueItemMutation = useCancelQueueItem();

  const statistics = queueData?.statistics ?? ({} as Partial<QueueStatistics>);
  const totalCount = statistics.totalCount ?? queueData?.items?.length ?? 0;
  const activeCount =
    (statistics.pendingCount ?? 0) +
    (statistics.assignedCount ?? 0) +
    (statistics.processingCount ?? 0);
  const failedCount = statistics.failedCount ?? 0;
  const staleCount = statistics.staleCount ?? 0;
  const completedCount = statistics.completedCount ?? 0;
  const cancelledCount = statistics.cancelledCount ?? 0;

  const items: QueueItem[] = queueData?.items ?? [];
  const activeItems = filterActiveItems(items);
  const completedItems = filterCompletedItems(items);
  const cancelledItems = filterCancelledItems(items);
  const failedItems = filterFailedItems(items);

  // Use hook's hasActiveFilters but ignore the includeCompleted/includeCancelled flags
  const hasActiveFilters =
    checkHasActiveFilters(['includeCompleted', 'includeCancelled']) ||
    (filters.taskIdFilter && isValidGuid(filters.taskIdFilter));

  // Build filter tag configuration for FilterTagDisplay
  const filterTagConfig = useMemo(
    (): FilterTagConfig[] => [
      {
        key: 'teamName',
        value: filters.teamName,
        label:
          dropdownData?.teams?.find((team) => team.value === filters.teamName)?.label ||
          filters.teamName,
        color: 'blue',
      },
      {
        key: 'machineName',
        value: filters.machineName,
        label: filters.machineName,
        color: 'blue',
      },
      {
        key: 'regionName',
        value: filters.regionName,
        label: filters.regionName,
        color: 'blue',
      },
      {
        key: 'bridgeName',
        value: filters.bridgeName,
        label: filters.bridgeName,
        color: 'blue',
      },
      {
        key: 'dateRange',
        value: filters.dateRange,
        label: filters.dateRange
          ? `${filters.dateRange[0]?.format('MM/DD')}\u2192${filters.dateRange[1]?.format('MM/DD')}`
          : '',
        color: 'blue',
      },
      {
        key: 'statusFilter',
        value: filters.statusFilter,
        label: '', // Array items display themselves
        color: 'blue',
      },
      {
        key: 'taskIdFilter',
        value:
          filters.taskIdFilter && isValidGuid(filters.taskIdFilter) ? filters.taskIdFilter : '',
        label: filters.taskIdFilter ? `${filters.taskIdFilter.substring(0, 8)}...` : '',
        color: 'blue',
      },
      {
        key: 'onlyStale',
        value: filters.onlyStale,
        label: 'Stale',
        color: 'orange',
      },
    ],
    [filters, dropdownData?.teams]
  );

  // Handle clearing individual filter tags
  const handleClearFilter = useCallback(
    (key: string, arrayValue?: string) => {
      switch (key) {
        case 'teamName':
          setFilter('teamName', '');
          break;
        case 'machineName':
          setFilter('machineName', '');
          break;
        case 'regionName':
          setFilter('regionName', '');
          break;
        case 'bridgeName':
          setFilter('bridgeName', '');
          break;
        case 'dateRange':
          setFilter('dateRange', null);
          break;
        case 'statusFilter':
          if (arrayValue) {
            setFilter(
              'statusFilter',
              filters.statusFilter.filter((s) => s !== arrayValue)
            );
          }
          break;
        case 'taskIdFilter':
          setFilter('taskIdFilter', '');
          break;
        case 'onlyStale':
          setFilter('onlyStale', false);
          break;
      }
    },
    [setFilter, filters.statusFilter]
  );

  const isFetching = isLoading || isRefetching;

  // Handle export functionality
  const handleExport = (format: 'csv' | 'json') => {
    const dataToExport: QueueItem[] = queueData?.items || [];
    const timestamp = dayjs().format('YYYY-MM-DD_HH-mm-ss');
    const filename = `queue_export_${timestamp}.${format}`;

    if (format === 'csv') {
      // CSV Export
      const headers = [
        'Task ID',
        'Status',
        'Priority',
        'Age (minutes)',
        'Team',
        'Machine',
        'Region',
        'Bridge',
        'Has Response',
        'Retry Count',
        'Created By',
        'Created',
      ];
      const csvContent = [
        headers.join(','),
        ...dataToExport.map((item) =>
          [
            item.taskId,
            item.healthStatus,
            item.priorityLabel || '',
            item.ageInMinutes,
            item.teamName,
            item.machineName,
            item.regionName,
            item.bridgeName,
            item.hasResponse ? 'Yes' : 'No',
            item.retryCount || 0,
            item.createdBy || '',
            item.createdTime,
          ]
            .map((val) => `"${val || ''}"`)
            .join(',')
        ),
      ].join('\n');

      const blob = new Blob([csvContent], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
      showMessage('success', `Exported ${dataToExport.length} items to ${filename}`);
    } else {
      // JSON Export
      const blob = new Blob([JSON.stringify(dataToExport, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
      showMessage('success', `Exported ${dataToExport.length} items to ${filename}`);
    }
  };

  // Handle cancel queue item
  const handleCancelQueueItem = async (taskId: string) => {
    confirmAction({
      modal,
      title: t('queue:cancelConfirm.title') as string,
      content: t('queue:cancelConfirm.content') as string,
      okText: t('queue:cancelConfirm.okText') as string,
      okType: 'danger',
      cancelText: t('common:actions.cancel') as string,
      onConfirm: async () => {
        await cancelQueueItemMutation.mutateAsync(taskId);
      },
    });
  };

  // Handle trace view
  const handleViewTrace = (taskId: string) => {
    queueTrace.open(taskId);
  };

  const queueColumns: ColumnsType<QueueItem> = [
    {
      title: 'Task ID',
      dataIndex: 'taskId',
      key: 'taskId',
      width: 200,
      render: (id: string) => (
        <RediaccText code copyable>
          {id}
        </RediaccText>
      ),
    },
    {
      title: 'Status',
      dataIndex: 'healthStatus',
      key: 'healthStatus',
      width: 120,
      render: (healthStatus: string, record: QueueItem) => renderQueueStatus(healthStatus, record),
    },
    {
      title: 'Priority',
      dataIndex: 'priorityLabel',
      key: 'priority',
      width: 140,
      render: (priorityLabel: string | undefined, record: QueueItem) => {
        const tooltipContent = (
          <TooltipContent>
            <RediaccText
              weight="bold"
              style={{ margin: 0, display: 'block', marginBottom: theme.spacing.XS / 2 }}
            >
              {priorityLabel}
            </RediaccText>
            <RediaccText variant="caption" as="div">
              {record.priority === 1
                ? t('queue:priorityTooltipP1')
                : t('queue:priorityTooltipTier')}
            </RediaccText>
          </TooltipContent>
        );
        return (
          renderPriority(priorityLabel, record.priority, tooltipContent) || (
            <RediaccText color="secondary">-</RediaccText>
          )
        );
      },
      sorter: (a, b) => (a.priority ?? 3) - (b.priority ?? 3),
    },
    {
      title: 'Age',
      dataIndex: 'ageInMinutes',
      key: 'ageInMinutes',
      width: 100,
      render: (minutes: number) => formatAge(minutes),
      sorter: (a, b) => (a.ageInMinutes ?? 0) - (b.ageInMinutes ?? 0),
    },
    {
      title: 'Team',
      dataIndex: 'teamName',
      key: 'teamName',
    },
    {
      title: 'Machine',
      dataIndex: 'machineName',
      key: 'machineName',
      render: (name: string) => (
        <Space>
          <DesktopOutlined />
          {name}
        </Space>
      ),
    },
    {
      title: 'Region',
      dataIndex: 'regionName',
      key: 'regionName',
      render: (name: string) => (
        <Space>
          <GlobalOutlined />
          {name}
        </Space>
      ),
    },
    {
      title: 'Bridge',
      dataIndex: 'bridgeName',
      key: 'bridgeName',
      render: (name: string) => (
        <Space>
          <ApiOutlined />
          {name}
        </Space>
      ),
    },
    {
      title: 'Response',
      dataIndex: 'hasResponse',
      key: 'hasResponse',
      width: 80,
      render: (hasResponse: boolean) => renderBoolean(hasResponse),
    },
    {
      title: 'Error / Retries',
      dataIndex: 'retryCount',
      key: 'retryCount',
      width: 280,
      render: (retryCount: number | undefined, record: QueueItem) => {
        if (!retryCount && retryCount !== 0) return <RediaccText color="secondary">-</RediaccText>;

        const maxRetries = STALE_TASK_CONSTANTS.MAX_RETRY_COUNT;
        const retryColor =
          retryCount === 0 ? 'green' : retryCount < maxRetries - 1 ? 'orange' : 'red';
        const icon =
          retryCount >= maxRetries - 1 && record.permanentlyFailed ? (
            <ExclamationCircleOutlined />
          ) : undefined;

        // Parse error messages using consolidated utility function
        const { allErrors, primaryError } = parseFailureReason(record.lastFailureReason);

        return (
          <RediaccStack variant="column" fullWidth gap="xs">
            {/* Error messages with severity badges */}
            {allErrors.length > 0 && (
              <Tooltip
                title={
                  <TooltipContent>
                    {allErrors.map((error: ParsedError, index: number) => (
                      <RediaccText
                        key={`${error.message}-${index}`}
                        size="sm"
                        style={{
                          display: 'block',
                          marginBottom: index === allErrors.length - 1 ? 0 : theme.spacing.XS / 2,
                        }}
                      >
                        {error.severity && <strong>[{error.severity}]</strong>} {error.message}
                      </RediaccText>
                    ))}
                    {record.lastRetryAt && (
                      <RediaccText
                        size="sm"
                        style={{
                          display: 'block',
                          marginTop: theme.spacing.XS,
                          paddingTop: theme.spacing.XS / 2,
                          borderTop: `1px solid ${theme.colors.borderSecondary}`,
                        }}
                      >
                        Last retry: {formatTimestampAsIs(record.lastRetryAt, 'datetime')}
                      </RediaccText>
                    )}
                  </TooltipContent>
                }
              >
                <TooltipContentSection>
                  {/* Show primary (highest severity) error */}
                  <TooltipPrimaryRow>
                    {primaryError?.severity && (
                      <SeverityPill $color={getSeverityColor(primaryError.severity)}>
                        {primaryError.severity}
                      </SeverityPill>
                    )}
                    <TruncatedErrorText as="span">{primaryError?.message}</TruncatedErrorText>
                  </TooltipPrimaryRow>
                  {/* Show count of additional errors if any */}
                  {allErrors.length > 1 && (
                    <RediaccText size="xs" color="muted" style={{ fontStyle: 'italic' }}>
                      +{allErrors.length - 1} more{' '}
                      {allErrors.length - 1 === 1 ? 'message' : 'messages'}
                    </RediaccText>
                  )}
                </TooltipContentSection>
              </Tooltip>
            )}

            {/* Retry count badge */}
            <RetrySummaryTag $color={retryColor} icon={icon}>
              {retryCount}/{maxRetries} retries
            </RetrySummaryTag>
          </RediaccStack>
        );
      },
      sorter: (a, b) => (a.retryCount ?? 0) - (b.retryCount ?? 0),
    },
    {
      title: 'Created By',
      dataIndex: 'createdBy',
      key: 'createdBy',
      width: 150,
      render: (createdBy: string | undefined) =>
        createdBy || <RediaccText color="secondary">-</RediaccText>,
    },
    {
      title: 'Age',
      dataIndex: 'ageInMinutes',
      key: 'age',
      width: 100,
      render: (ageInMinutes: number, record: QueueItem) => {
        const hours = Math.floor(ageInMinutes / 60);
        const minutes = ageInMinutes % 60;

        let ageText = '';
        if (hours > 0) {
          ageText = `${hours}h ${minutes}m`;
        } else {
          ageText = `${minutes}m`;
        }

        // Color coding based on age and status
        let color: string | undefined;
        if (record.status === 'PENDING' && hours >= 12) {
          color = 'red';
        } else if (record.status === 'PENDING' && hours >= 6) {
          color = 'orange';
        }

        return (
          <RediaccText style={{ color: color || theme.colors.textPrimary }}>{ageText}</RediaccText>
        );
      },
      sorter: (a, b) => (a.ageInMinutes ?? 0) - (b.ageInMinutes ?? 0),
    },
    {
      title: 'Created',
      dataIndex: 'createdTime',
      key: 'createdTime',
      width: 180,
      render: (date: string) => renderTimestamp(date),
      sorter: (a, b) =>
        new Date(a.createdTime ?? 0).getTime() - new Date(b.createdTime ?? 0).getTime(),
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 180,
      render: (_: unknown, record: QueueItem) => (
        <Space size="small">
          <Tooltip title="Trace">
            <RediaccButton
              size="sm"
              iconOnly
              icon={<HistoryOutlined />}
              onClick={() => record.taskId && handleViewTrace(record.taskId)}
              data-testid={`queue-trace-button-${record.taskId}`}
              aria-label="Trace"
            />
          </Tooltip>
          {record.canBeCancelled &&
            record.healthStatus !== 'CANCELLED' &&
            record.healthStatus !== 'CANCELLING' && (
              <Tooltip title="Cancel">
                <RediaccButton
                  size="sm"
                  danger
                  iconOnly
                  icon={<CloseCircleOutlined />}
                  onClick={() => record.taskId && handleCancelQueueItem(record.taskId)}
                  loading={cancelQueueItemMutation.isPending}
                  data-testid={`queue-cancel-button-${record.taskId}`}
                  aria-label="Cancel"
                />
              </Tooltip>
            )}
        </Space>
      ),
    },
  ];

  return (
    <PageWrapper data-testid="queue-page-container">
      {contextHolder}
      <RediaccCard
        size="sm"
        spacing="default"
        style={{ padding: '8px 16px', marginBottom: '16px' }}
        data-testid="queue-filters-card"
      >
        <RediaccStack variant="column" fullWidth gap="sm">
          <Space size={8} wrap>
            <FilterSelect
              size="sm"
              $minWidth={150}
              placeholder="Team"
              value={filters.teamName || undefined}
              onChange={(value) => {
                const nextValue = typeof value === 'string' ? value : '';
                setFilter('teamName', nextValue);
                setFilter('machineName', '');
              }}
              allowClear
              options={dropdownData?.teams || []}
              data-testid="queue-filter-team"
            />
            <FilterSelect
              size="sm"
              $minWidth={150}
              placeholder="Machine"
              value={filters.machineName || undefined}
              onChange={(value) => setFilter('machineName', typeof value === 'string' ? value : '')}
              allowClear
              options={(dropdownData?.machines || []).map((machine) => ({
                label: machine,
                value: machine,
              }))}
              data-testid="queue-filter-machine"
            />
            <FilterSelect
              size="sm"
              $minWidth={130}
              placeholder="Region"
              value={filters.regionName || undefined}
              onChange={(value) => setFilter('regionName', typeof value === 'string' ? value : '')}
              allowClear
              options={dropdownData?.regions || []}
              data-testid="queue-filter-region"
            />
            <FilterSelect
              size="sm"
              $minWidth={130}
              placeholder="Bridge"
              value={filters.bridgeName || undefined}
              onChange={(value) => setFilter('bridgeName', typeof value === 'string' ? value : '')}
              allowClear
              options={dropdownData?.bridges || []}
              data-testid="queue-filter-bridge"
            />
            <FilterRangePicker
              value={dateRangeValue}
              onChange={handleDateRangeChange}
              allowClear
              placeholder={[t('queue:filters.dateFrom'), t('queue:filters.dateTo')]}
              data-testid="queue-filter-date"
            />
            <FilterSelect
              size="sm"
              mode="multiple"
              $minWidth={160}
              placeholder="Status"
              value={filters.statusFilter}
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              onChange={handleStatusFilterChange as any}
              options={[
                { label: t('queue:statusPending'), value: 'PENDING' },
                { label: t('queue:statusActive'), value: 'ACTIVE' },
                { label: t('queue:statusStale'), value: 'STALE' },
                { label: t('queue:statusCompleted'), value: 'COMPLETED' },
                { label: t('queue:statusCancelled'), value: 'CANCELLED' },
                { label: t('queue:statusFailed'), value: 'FAILED' },
              ]}
              data-testid="queue-filter-status"
            />
            <FilterInput
              size="sm"
              placeholder="Task ID (GUID)"
              prefix={<SearchOutlined />}
              value={filters.taskIdFilter}
              onChange={(e) => setFilter('taskIdFilter', e.target.value)}
              allowClear
              data-testid="queue-filter-task"
            />
            <FilterCheckbox
              checked={filters.onlyStale}
              onChange={(e) => setFilter('onlyStale', e.target.checked)}
              data-testid="queue-checkbox-only-stale"
            >
              {t('queue:filters.onlyStale')}
            </FilterCheckbox>
          </Space>

          {hasActiveFilters && (
            <FilterTagDisplay
              filters={filterTagConfig}
              onClear={handleClearFilter}
              onClearAll={clearAllFilters}
            />
          )}

          <RediaccStack variant="wrap-grid" align="center" gap="sm">
            <RediaccStack variant="tight-row" align="center" gap="xs">
              <StatIcon>
                <ThunderboltOutlined />
              </StatIcon>
              <RediaccText variant="caption" color="secondary">
                {t('queue:statistics.total')}:
              </RediaccText>
              <StatValue>{totalCount}</StatValue>
            </RediaccStack>
            <StatDivider />
            <RediaccStack variant="tight-row" align="center" gap="xs">
              <StatIcon $color="var(--color-info)">
                <PlayCircleOutlined />
              </StatIcon>
              <RediaccText variant="caption" color="secondary">
                {t('queue:statistics.active')}:
              </RediaccText>
              <StatValue $color="var(--color-info)">{activeCount}</StatValue>
            </RediaccStack>
            <StatDivider />
            <RediaccStack variant="tight-row" align="center" gap="xs">
              <StatIcon $color="var(--color-error)">
                <ExclamationCircleOutlined />
              </StatIcon>
              <RediaccText variant="caption" color="secondary">
                {t('queue:statistics.failed')}:
              </RediaccText>
              <StatValue $color="var(--color-error)">{failedCount}</StatValue>
            </RediaccStack>
            <StatDivider />
            <RediaccStack variant="tight-row" align="center" gap="xs">
              <StatIcon $color="var(--color-warning)">
                <WarningOutlined />
              </StatIcon>
              <RediaccText variant="caption" color="secondary">
                {t('queue:statistics.stale')}:
              </RediaccText>
              <StatValue $color="var(--color-warning)">{staleCount}</StatValue>
            </RediaccStack>
          </RediaccStack>

          <Space size={4}>
            <Tooltip title={t('common:actions.refresh')}>
              <RediaccButton
                size="sm"
                iconOnly
                icon={<ReloadOutlined />}
                onClick={() => refetch()}
                loading={isFetching}
                data-testid="queue-refresh-button"
              />
            </Tooltip>
            <Dropdown
              menu={{
                items: [
                  { key: 'csv', label: t('common:exportCSV'), onClick: () => handleExport('csv') },
                  {
                    key: 'json',
                    label: t('common:exportJSON'),
                    onClick: () => handleExport('json'),
                  },
                ],
              }}
            >
              <Tooltip title={t('common:export')}>
                <RediaccButton
                  size="sm"
                  iconOnly
                  icon={<ExportOutlined />}
                  data-testid="queue-export-dropdown"
                />
              </Tooltip>
            </Dropdown>
          </Space>
        </RediaccStack>
      </RediaccCard>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        data-testid="queue-tabs"
        items={[
          {
            key: 'active',
            label: (
              <Tooltip title={t('queue:tabs.active.tooltip')}>
                <TabLabel data-testid="queue-tab-active">
                  {t('queue:tabs.active.title')}
                  <TabCount count={activeItems.length} $color={theme.colors.secondary} />
                </TabLabel>
              </Tooltip>
            ),
            children: (
              <ResourceListView
                loading={isLoading || isRefetching}
                data={activeItems}
                columns={queueColumns}
                rowKey="taskId"
                searchPlaceholder="Search queue items..."
                pagination={{
                  current: pagination.active.page,
                  pageSize: pagination.active.pageSize,
                  showSizeChanger: true,
                  pageSizeOptions: ['10', '20', '50', '100'],
                  showTotal: (total, range) =>
                    `Showing records ${range[0]}-${range[1]} of ${total}`,
                  onChange: pagination.active.onPageChange,
                  position: ['bottomRight'],
                }}
              />
            ),
          },
          {
            key: 'completed',
            label: (
              <Tooltip title={t('queue:tabs.completed.tooltip')}>
                <TabLabel data-testid="queue-tab-completed">
                  {t('queue:tabs.completed.title')}
                  <TabCount
                    count={completedCount || completedItems.length}
                    showZero
                    $color={theme.colors.success}
                  />
                </TabLabel>
              </Tooltip>
            ),
            children: (
              <ResourceListView
                loading={isLoading || isRefetching}
                data={completedItems}
                columns={queueColumns}
                rowKey="taskId"
                searchPlaceholder="Search completed items..."
                pagination={{
                  current: pagination.completed.page,
                  pageSize: pagination.completed.pageSize,
                  showSizeChanger: true,
                  pageSizeOptions: ['10', '20', '50', '100'],
                  showTotal: (total, range) =>
                    `Showing records ${range[0]}-${range[1]} of ${total}`,
                  onChange: pagination.completed.onPageChange,
                  position: ['bottomRight'],
                }}
              />
            ),
          },
          {
            key: 'cancelled',
            label: (
              <Tooltip title={t('queue:tabs.cancelled.tooltip')}>
                <TabLabel data-testid="queue-tab-cancelled">
                  {t('queue:tabs.cancelled.title')}
                  <TabCount
                    count={cancelledCount || cancelledItems.length}
                    showZero
                    $color={theme.colors.accent}
                  />
                </TabLabel>
              </Tooltip>
            ),
            children: (
              <ResourceListView
                loading={isLoading || isRefetching}
                data={cancelledItems}
                columns={queueColumns}
                rowKey="taskId"
                searchPlaceholder="Search cancelled items..."
                pagination={{
                  current: pagination.cancelled.page,
                  pageSize: pagination.cancelled.pageSize,
                  showSizeChanger: true,
                  pageSizeOptions: ['10', '20', '50', '100'],
                  showTotal: (total, range) =>
                    `Showing records ${range[0]}-${range[1]} of ${total}`,
                  onChange: pagination.cancelled.onPageChange,
                  position: ['bottomRight'],
                }}
              />
            ),
          },
          {
            key: 'failed',
            label: (
              <Tooltip title={t('queue:tabs.failed.tooltip')}>
                <TabLabel data-testid="queue-tab-failed">
                  {t('queue:tabs.failed.title')}
                  <TabCount
                    count={failedCount || failedItems.length}
                    showZero
                    $color={theme.colors.error}
                  />
                </TabLabel>
              </Tooltip>
            ),
            children: (
              <ResourceListView
                loading={isLoading || isRefetching}
                data={failedItems}
                columns={queueColumns}
                rowKey="taskId"
                searchPlaceholder="Search failed items..."
                pagination={{
                  current: pagination.failed.page,
                  pageSize: pagination.failed.pageSize,
                  showSizeChanger: true,
                  pageSizeOptions: ['10', '20', '50', '100'],
                  showTotal: (total, range) =>
                    `Showing records ${range[0]}-${range[1]} of ${total}`,
                  onChange: pagination.failed.onPageChange,
                  position: ['bottomRight'],
                }}
              />
            ),
          },
        ]}
      />

      <QueueItemTraceModal
        taskId={queueTrace.state.taskId}
        open={queueTrace.state.open}
        onCancel={queueTrace.close}
      />
    </PageWrapper>
  );
};

export default QueuePage;
