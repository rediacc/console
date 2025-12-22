import React, { useCallback, useMemo } from 'react';
import { Badge, Button, Dropdown, Flex, Modal, Space, Tabs, Tooltip, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { QueueFilters, type QueueStatistics, useQueueItems } from '@/api/queries/queue';
import { useDropdownData } from '@/api/queries/useDropdownData';
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal';
import ResourceListView from '@/components/common/ResourceListView';
import { useFilters, useMultiPagination, useQueueTraceModal } from '@/hooks';
import FilterTagDisplay, { FilterTagConfig } from '@/pages/queue/components/FilterTagDisplay';
import {
  filterActiveItems,
  filterCancelledItems,
  filterCompletedItems,
  filterFailedItems,
  isValidGuid,
} from '@/platform';
import { ExportOutlined, ReloadOutlined } from '@/utils/optimizedIcons';
import type { GetTeamQueueItems_ResultSet1 as QueueItem } from '@rediacc/shared/types';
import { QueueFilterPanel } from './components/QueueFilterPanel';
import { QueueStatisticsBar } from './components/QueueStatisticsBar';
import { useQueueActions } from './hooks/useQueueActions';
import { useQueueExport } from './hooks/useQueueExport';
import { getQueueColumns } from './queueTableColumns';
import type { Dayjs } from 'dayjs';

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

const QueuePage: React.FC = () => {
  const { t } = useTranslation(['queue', 'common']);
  const [modal, contextHolder] = Modal.useModal();

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

  const handleDateRangeChange = useCallback(
    (dates: [Dayjs | null, Dayjs | null] | null, _dateStrings?: [string, string]) => {
      setFilter('dateRange', dates);
    },
    [setFilter]
  );

  const handleStatusFilterChange = useCallback(
    (values: string[]) => {
      setFilter('statusFilter', values);
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

  // Custom hooks for actions and export
  const { handleCancelQueueItem, cancelLoading } = useQueueActions(modal);
  const handleViewTrace = (taskId: string) => {
    queueTrace.open(taskId);
  };

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

  // Export hook
  const { handleExport } = useQueueExport(items);

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

  // Get queue columns configuration
  const queueColumns = getQueueColumns({
    handleViewTrace,
    handleCancelQueueItem,
    cancelLoading,
    t,
  });

  return (
    <Flex vertical data-testid="queue-page-container">
      {contextHolder}
      <Flex vertical data-testid="queue-filters-card">
        <Flex vertical gap={8} className="w-full">
          <QueueFilterPanel
            filters={filters}
            dropdownData={dropdownData}
            onFilterChange={setFilter}
            onStatusFilterChange={handleStatusFilterChange}
            onDateRangeChange={handleDateRangeChange}
          />

          {hasActiveFilters && (
            <FilterTagDisplay
              filters={filterTagConfig}
              onClear={handleClearFilter}
              onClearAll={clearAllFilters}
            />
          )}

          <QueueStatisticsBar
            totalCount={totalCount}
            activeCount={activeCount}
            failedCount={failedCount}
            staleCount={staleCount}
          />

          <Space size={4}>
            <Tooltip title={t('common:actions.refresh')}>
              <Button
                type="text"
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
                <Button type="text" icon={<ExportOutlined />} data-testid="queue-export-dropdown" />
              </Tooltip>
            </Dropdown>
          </Space>
        </Flex>
      </Flex>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        data-testid="queue-tabs"
        items={[
          {
            key: 'active',
            label: (
              <Tooltip title={t('queue:tabs.active.tooltip')}>
                <Typography.Text
                  data-testid="queue-tab-active"
                  className="inline-flex items-center gap-2"
                >
                  {t('queue:tabs.active.title')}
                  <Badge count={activeItems.length} />
                </Typography.Text>
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
                <Typography.Text
                  data-testid="queue-tab-completed"
                  className="inline-flex items-center gap-2"
                >
                  {t('queue:tabs.completed.title')}
                  <Badge count={completedCount || completedItems.length} showZero />
                </Typography.Text>
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
                <Typography.Text
                  data-testid="queue-tab-cancelled"
                  className="inline-flex items-center gap-2"
                >
                  {t('queue:tabs.cancelled.title')}
                  <Badge count={cancelledCount || cancelledItems.length} showZero />
                </Typography.Text>
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
                <Typography.Text
                  data-testid="queue-tab-failed"
                  className="inline-flex items-center gap-2"
                >
                  {t('queue:tabs.failed.title')}
                  <Badge count={failedCount || failedItems.length} showZero />
                </Typography.Text>
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
    </Flex>
  );
};

export default QueuePage;
