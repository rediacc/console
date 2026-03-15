import type {
  GetTeamQueueItems_ResultSet1,
  QueueFilters,
  QueueStatistics,
} from '@rediacc/shared/types';
import {
  Badge,
  Button,
  Dropdown,
  Flex,
  type MenuProps,
  Modal,
  Space,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import type { Dayjs } from 'dayjs';
import React, { useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useQueueItemsWithFilters } from '@/api/hooks-queue';
import { useDropdownData } from '@/api/queries/useDropdownData';
import { buildQueueColumns } from '@/components/common/columns/builders/queueColumns';
import { MobileCard } from '@/components/common/MobileCard';
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal';
import { ResourceActionsDropdown } from '@/components/common/ResourceActionsDropdown';
import ResourceListView from '@/components/common/ResourceListView';
import FilterTagDisplay, { FilterTagConfig } from '@/features/queue/components/FilterTagDisplay';
import { useFilters, useMultiPagination, useQueueTraceModal } from '@/hooks';
import {
  filterActiveItems,
  filterCancelledItems,
  filterCompletedItems,
  filterFailedItems,
  isValidGuid,
} from '@/platform';
import {
  CloseCircleOutlined,
  DesktopOutlined,
  ExportOutlined,
  HistoryOutlined,
  ReloadOutlined,
  RocketOutlined,
} from '@/utils/optimizedIcons';
import { getQueueStatusColor } from '@/utils/statusColors';
import { QueueFilterPanel } from '../components/QueueFilterPanel';
import { QueueStatisticsBar } from '../components/QueueStatisticsBar';
import { useQueueActions } from '../hooks/useQueueActions';
import { useQueueExport } from '../hooks/useQueueExport';

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

  const {
    data: queueData,
    isLoading,
    refetch,
    isRefetching,
  } = useQueueItemsWithFilters(queryFilters);
  const { data: dropdownData } = useDropdownData();

  // Custom hooks for actions and export
  const { handleCancelQueueItem, cancelLoading } = useQueueActions(modal);
  const handleViewTrace = useCallback(
    (taskId: string) => {
      queueTrace.open(taskId);
    },
    [queueTrace]
  );

  const emptyStatistics: Partial<QueueStatistics> = {};
  const statistics = queueData?.statistics ?? emptyStatistics;
  const totalCount = statistics.totalCount ?? queueData?.items.length ?? 0;
  const activeCount =
    (statistics.pendingCount ?? 0) +
    (statistics.assignedCount ?? 0) +
    (statistics.processingCount ?? 0);
  const failedCount = statistics.failedCount ?? 0;
  const staleCount = statistics.staleCount ?? 0;
  const completedCount = statistics.completedCount ?? 0;
  const cancelledCount = statistics.cancelledCount ?? 0;

  const items: GetTeamQueueItems_ResultSet1[] = queueData?.items ?? [];
  // Normalize healthStatus from nullable to non-nullable for filter functions
  const normalizedItems = items.map((item) => ({ ...item, healthStatus: item.healthStatus ?? '' }));
  const activeItems = filterActiveItems(normalizedItems);
  const completedItems = filterCompletedItems(normalizedItems);
  const cancelledItems = filterCancelledItems(normalizedItems);
  const failedItems = filterFailedItems(normalizedItems);

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
          dropdownData?.teams.find((team) => team.value === filters.teamName)?.label ??
          filters.teamName,
      },
      {
        key: 'machineName',
        value: filters.machineName,
        label: filters.machineName,
      },
      {
        key: 'regionName',
        value: filters.regionName,
        label: filters.regionName,
      },
      {
        key: 'bridgeName',
        value: filters.bridgeName,
        label: filters.bridgeName,
      },
      {
        key: 'dateRange',
        value: filters.dateRange,
        label: filters.dateRange
          ? `${filters.dateRange[0]?.format('MM/DD')}\u2192${filters.dateRange[1]?.format('MM/DD')}`
          : '',
      },
      {
        key: 'statusFilter',
        value: filters.statusFilter,
        label: '', // Array items display themselves
      },
      {
        key: 'taskIdFilter',
        value:
          filters.taskIdFilter && isValidGuid(filters.taskIdFilter) ? filters.taskIdFilter : '',
        label: filters.taskIdFilter ? `${filters.taskIdFilter.substring(0, 8)}...` : '',
      },
      {
        key: 'onlyStale',
        value: filters.onlyStale,
        label: 'Stale',
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
  const queueColumns = buildQueueColumns({
    handleViewTrace,
    handleCancelQueueItem,
    cancelLoading,
    t,
  });

  const mobileRender = useMemo(
    // eslint-disable-next-line react/display-name
    () => (record: GetTeamQueueItems_ResultSet1) => {
      const canCancel = ['PENDING', 'ASSIGNED'].includes(record.status?.toUpperCase() ?? '');
      const menuItems: MenuProps['items'] = [
        ...(record.taskId
          ? [
              {
                key: 'trace',
                label: t('common:actions.trace'),
                icon: <HistoryOutlined />,
                onClick: () => handleViewTrace(record.taskId!),
              },
            ]
          : []),
        ...(canCancel && record.taskId
          ? [
              {
                key: 'cancel',
                label: t('common:actions.cancel'),
                icon: <CloseCircleOutlined />,
                danger: true,
                onClick: () => handleCancelQueueItem(record.taskId!),
              },
            ]
          : []),
      ];
      const truncatedTaskId = record.taskId ? `${record.taskId.substring(0, 8)}...` : '';

      return (
        <MobileCard actions={<ResourceActionsDropdown menuItems={menuItems} />}>
          <Flex align="center" wrap>
            <Space size="small">
              <RocketOutlined />
              <Typography.Text strong className="truncate">
                {truncatedTaskId}
              </Typography.Text>
            </Space>
            <Tag color={getQueueStatusColor(record.status ?? '')}>{record.status}</Tag>
          </Flex>
          {record.machineName && (
            <Space size="small">
              <DesktopOutlined />
              <Typography.Text className="truncate">{record.machineName}</Typography.Text>
            </Space>
          )}
        </MobileCard>
      );
    },
    [t, handleViewTrace, handleCancelQueueItem]
  );

  return (
    <Flex vertical data-testid="queue-page-container">
      {contextHolder}
      <Flex vertical data-testid="queue-filters-card">
        <Flex vertical className="gap-sm w-full">
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
                mobileRender={mobileRender}
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
                mobileRender={mobileRender}
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
                mobileRender={mobileRender}
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
                mobileRender={mobileRender}
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
