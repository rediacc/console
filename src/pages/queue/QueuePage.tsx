import React, { useState, useMemo } from 'react'
import { Typography, Space, Modal, Tag, Tabs, Tooltip, Dropdown } from 'antd'
import { ThunderboltOutlined, DesktopOutlined, ApiOutlined, PlayCircleOutlined, CheckCircleOutlined, CloseCircleOutlined, ExclamationCircleOutlined, WarningOutlined, GlobalOutlined, ClockCircleOutlined, ReloadOutlined, ExportOutlined, HistoryOutlined, SearchOutlined } from '@/utils/optimizedIcons'
import { useQueueItems, useCancelQueueItem, QueueFilters, type QueueStatistics } from '@/api/queries/queue'
import { useDropdownData } from '@/api/queries/useDropdownData'
import ResourceListView from '@/components/common/ResourceListView'
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal'
import { showMessage } from '@/utils/messages'
import dayjs from 'dayjs'
import { useTranslation } from 'react-i18next'
import { formatTimestampAsIs } from '@/utils/timeUtils'
import { createSorter, createDateSorter } from '@/utils/tableSorters'
import {
  PageWrapper,
  FiltersCard,
  FiltersGrid,
  FilterSelect,
  FilterRangePicker,
  FilterInput,
  FilterTagBar,
  ClearFiltersButton,
  StatsBar,
  StatItem,
  StatLabel,
  StatValue,
  StatDivider,
  StatIcon,
  IconButton,
  TabLabel,
  TabCount,
  FilterCheckbox,
} from './styles'

const { Text } = Typography
const QueuePage: React.FC = () => {
  const { t } = useTranslation(['queue', 'common'])
  const [viewTeam, setViewTeam] = useState<string>('') // Team for viewing queue items
  const [activeTab, setActiveTab] = useState<string>('active') // Track which tab is active
  const [filters, setFilters] = useState<QueueFilters>({
    teamName: '',
    includeCompleted: true,
    includeCancelled: true,  // Always include for proper tab filtering
    staleThresholdMinutes: 10,
    maxRecords: 1000
  })
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs | null, dayjs.Dayjs | null] | null>(null)
  const [statusFilter, setStatusFilter] = useState<string[]>([])
  const [taskIdFilter, setTaskIdFilter] = useState<string>('')
  const [traceModalVisible, setTraceModalVisible] = useState(false)
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)

  // Pagination state for each tab
  const [activePageSize, setActivePageSize] = useState(20)
  const [activePage, setActivePage] = useState(1)
  const [completedPageSize, setCompletedPageSize] = useState(20)
  const [completedPage, setCompletedPage] = useState(1)
  const [cancelledPageSize, setCancelledPageSize] = useState(20)
  const [cancelledPage, setCancelledPage] = useState(1)
  const [failedPageSize, setFailedPageSize] = useState(20)
  const [failedPage, setFailedPage] = useState(1)

  // GUID validation regex
  const isValidGuid = (value: string) => {
    const guidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
    return guidRegex.test(value)
  }

  // Combine team selection with filters
  // Dynamically adjust filters based on active tab
  const queryFilters = useMemo(() => ({
    ...filters,
    teamName: viewTeam,
    // Auto-enable includeCancelled when on cancelled tab
    includeCancelled: activeTab === 'cancelled' ? true : filters.includeCancelled,
    // Auto-enable includeCompleted when on completed tab
    includeCompleted: activeTab === 'completed' ? true : filters.includeCompleted,
    dateFrom: dateRange?.[0]?.startOf('day').format('YYYY-MM-DD HH:mm:ss'),
    dateTo: dateRange?.[1]?.endOf('day').format('YYYY-MM-DD HH:mm:ss'),
    status: statusFilter.join(','),
    ...(taskIdFilter.trim() && isValidGuid(taskIdFilter.trim()) ? { taskId: taskIdFilter.trim() } : {})
  }), [filters, viewTeam, dateRange, statusFilter, taskIdFilter, activeTab])
  
  const { data: queueData, isLoading, refetch, isRefetching } = useQueueItems(queryFilters)
  const { data: dropdownData } = useDropdownData()
  const cancelQueueItemMutation = useCancelQueueItem()

  const statistics = (queueData?.statistics ?? ({} as Partial<QueueStatistics>))
  const totalCount = statistics.totalCount ?? queueData?.items?.length ?? 0
  const activeCount = (statistics.pendingCount ?? 0) + (statistics.assignedCount ?? 0) + (statistics.processingCount ?? 0)
  const failedCount = statistics.failedCount ?? 0
  const staleCount = statistics.staleCount ?? 0
  const completedCount = statistics.completedCount ?? 0
  const cancelledCount = statistics.cancelledCount ?? 0

  const items = queueData?.items || []
  const activeItems = items.filter((item: any) => !['COMPLETED', 'CANCELLED', 'FAILED'].includes(item.healthStatus))
  const completedItems = items.filter((item: any) => item.healthStatus === 'COMPLETED')
  const cancelledItems = items.filter((item: any) => item.healthStatus === 'CANCELLED')
  const failedItems = items.filter((item: any) => item.healthStatus === 'FAILED')

  const hasActiveFilters =
    Boolean(viewTeam) ||
    Boolean(filters.machineName) ||
    Boolean(filters.regionName) ||
    Boolean(filters.bridgeName) ||
    Boolean(filters.onlyStale) ||
    statusFilter.length > 0 ||
    Boolean(dateRange) ||
    (taskIdFilter && isValidGuid(taskIdFilter))

  const isFetching = isLoading || isRefetching

  // Handle export functionality
  const handleExport = (format: 'csv' | 'json') => {
    const dataToExport = queueData?.items || []
    const timestamp = dayjs().format('YYYY-MM-DD_HH-mm-ss')
    const filename = `queue_export_${timestamp}.${format}`
    
    if (format === 'csv') {
      // CSV Export
      const headers = ['Task ID', 'Status', 'Priority', 'Age (minutes)', 'Team', 'Machine', 'Region', 'Bridge', 'Has Response', 'Retry Count', 'Created By', 'Created']
      const csvContent = [
        headers.join(','),
        ...dataToExport.map((item: any) => [
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
          item.createdTime
        ].map(val => `"${val || ''}"`).join(','))
      ].join('\n')
      
      const blob = new Blob([csvContent], { type: 'text/csv' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      link.click()
      URL.revokeObjectURL(url)
      showMessage('success', `Exported ${dataToExport.length} items to ${filename}`)
    } else {
      // JSON Export
      const blob = new Blob([JSON.stringify(dataToExport, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      link.click()
      URL.revokeObjectURL(url)
      showMessage('success', `Exported ${dataToExport.length} items to ${filename}`)
    }
  }
  
  // Handle cancel queue item
  const handleCancelQueueItem = async (taskId: string) => {
    Modal.confirm({
      title: 'Cancel Queue Item',
      content: 'Are you sure you want to cancel this queue item? This action cannot be undone.',
      okText: 'Yes, Cancel',
      okType: 'danger',
      cancelText: 'No',
      onOk: async () => {
        try {
          await cancelQueueItemMutation.mutateAsync(taskId)
        } catch (error) {
          // Error handled by mutation
        }
      }
    })
  }

  // Handle trace view
  const handleViewTrace = (taskId: string) => {
    setSelectedTaskId(taskId)
    setTraceModalVisible(true)
  }


  const queueColumns = [
    {
      title: 'Task ID',
      dataIndex: 'taskId',
      key: 'taskId',
      width: 200,
      render: (id: string) => <Text code copyable>{id}</Text>
    },
    {
      title: 'Status',
      dataIndex: 'healthStatus',
      key: 'healthStatus',
      width: 120,
      render: (healthStatus: string, record: any) => {
        const statusConfig = {
          'PENDING': { color: 'default', icon: <ClockCircleOutlined /> },
          'ACTIVE': { color: 'processing', icon: <PlayCircleOutlined /> },
          'STALE': { color: 'warning', icon: <WarningOutlined /> },
          'STALE_PENDING': { color: 'orange', icon: <WarningOutlined /> },
          'CANCELLING': { color: 'warning', icon: <PlayCircleOutlined spin /> },
          'COMPLETED': { color: 'success', icon: <CheckCircleOutlined /> },
          'FAILED': { color: 'error', icon: <ExclamationCircleOutlined /> },
          'CANCELLED': { color: 'error', icon: <CloseCircleOutlined /> },
          'UNKNOWN': { color: 'default', icon: <ExclamationCircleOutlined /> }
        }
        const config = statusConfig[healthStatus as keyof typeof statusConfig] || statusConfig.UNKNOWN
        
        // Show actual status alongside health status for active items
        const statusText = healthStatus === 'ACTIVE' && record.status ? 
          `${record.status} (${healthStatus})` : healthStatus
        
        let tooltipText = undefined
        if (record.minutesSinceAssigned) {
          tooltipText = `${record.minutesSinceAssigned} minutes since assigned`
        } else if (healthStatus === 'STALE_PENDING') {
          const hoursOld = Math.floor(record.ageInMinutes / 60)
          tooltipText = `Pending for ${hoursOld} hours - may need attention`
        }
        
        return (
          <Tooltip title={tooltipText}>
            <Tag color={config.color} icon={config.icon}>
              {statusText}
            </Tag>
          </Tooltip>
        )
      }
    },
    {
      title: 'Priority',
      dataIndex: 'priorityLabel',
      key: 'priority',
      width: 140,
      render: (priorityLabel: string | undefined, record: any) => {
        if (!priorityLabel || !record.priority) {
          return <Text type="secondary">-</Text>
        }

        const priorityConfig = {
          1: { color: 'red', icon: <ExclamationCircleOutlined />, timeout: '33s' },
          2: { color: 'orange', icon: undefined, timeout: 'Tier timeout' },
          3: { color: 'gold', icon: undefined, timeout: 'Tier timeout' },
          4: { color: 'blue', icon: undefined, timeout: 'Tier timeout' },
          5: { color: 'green', icon: undefined, timeout: 'Tier timeout' }
        }

        const config = priorityConfig[record.priority as keyof typeof priorityConfig] || priorityConfig[3]

        return (
          <Tooltip title={
            <div>
              <div style={{ marginBottom: 4 }}><strong>{priorityLabel}</strong></div>
              <div style={{ fontSize: 12 }}>
                {record.priority === 1
                  ? t('queue:priorityTooltipP1')
                  : t('queue:priorityTooltipTier')}
              </div>
            </div>
          }>
            <Tag color={config.color} icon={config.icon}>
              {priorityLabel}
            </Tag>
          </Tooltip>
        )
      },
      sorter: createSorter('priority'),
    },
    {
      title: 'Age',
      dataIndex: 'ageInMinutes',
      key: 'ageInMinutes',
      width: 100,
      render: (minutes: number) => {
        if (minutes < 60) return `${minutes}m`
        if (minutes < 1440) return `${Math.floor(minutes / 60)}h ${minutes % 60}m`
        return `${Math.floor(minutes / 1440)}d ${Math.floor((minutes % 1440) / 60)}h`
      },
      sorter: createSorter('ageInMinutes'),
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
      )
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
      )
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
      )
    },
    {
      title: 'Response',
      dataIndex: 'hasResponse',
      key: 'hasResponse',
      width: 80,
      render: (hasResponse: boolean) => hasResponse ? 
        <Tag color="success">Yes</Tag> : 
        <Tag>No</Tag>
    },
    {
      title: 'Retries',
      dataIndex: 'retryCount',
      key: 'retryCount',
      width: 80,
      render: (retryCount: number | undefined, record: any) => {
        if (!retryCount && retryCount !== 0) return <Text type="secondary">-</Text>
        
        const color = retryCount === 0 ? 'green' : retryCount < 2 ? 'orange' : 'red'
        const icon = retryCount >= 2 && record.permanentlyFailed ? <ExclamationCircleOutlined /> : undefined
        
        return (
          <Tooltip title={
            <div>
              {record.lastFailureReason || 'No failures'}
              {record.lastRetryAt && (
                <div style={{ marginTop: 4, fontSize: '12px' }}>
                  Last retry: {formatTimestampAsIs(record.lastRetryAt, 'datetime')}
                </div>
              )}
            </div>
          }>
            <Tag color={color} icon={icon}>
              {retryCount}/2
            </Tag>
          </Tooltip>
        )
      },
      sorter: createSorter('retryCount'),
    },
    {
      title: 'Created By',
      dataIndex: 'createdBy',
      key: 'createdBy',
      width: 150,
      render: (createdBy: string | undefined) => createdBy || <Text type="secondary">-</Text>,
    },
    {
      title: 'Age',
      dataIndex: 'ageInMinutes',
      key: 'age',
      width: 100,
      render: (ageInMinutes: number, record: any) => {
        const hours = Math.floor(ageInMinutes / 60)
        const minutes = ageInMinutes % 60
        
        let ageText = ''
        if (hours > 0) {
          ageText = `${hours}h ${minutes}m`
        } else {
          ageText = `${minutes}m`
        }
        
        // Color coding based on age and status
        let color = undefined
        if (record.status === 'PENDING' && hours >= 6) {
          color = 'orange' // Warning for old pending items
        } else if (record.status === 'PENDING' && hours >= 12) {
          color = 'red' // Critical for very old pending items
        }
        
        return <Text style={{ color }}>{ageText}</Text>
      },
      sorter: createSorter('ageInMinutes'),
    },
    {
      title: 'Created',
      dataIndex: 'createdTime',
      key: 'createdTime',
      width: 180,
      render: (date: string) => dayjs(date).format('YYYY-MM-DD HH:mm:ss'),
      sorter: createDateSorter('createdTime'),
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 180,
      render: (_: unknown, record: Record<string, unknown>) => (
        <Space size="small">
          <Tooltip title="Trace">
            <IconButton
              size="small"
              type="primary"
              icon={<HistoryOutlined />}
              onClick={() => handleViewTrace(record.taskId)}
              data-testid={`queue-trace-button-${record.taskId}`}
              aria-label="Trace"
            />
          </Tooltip>
          {record.canBeCancelled && record.healthStatus !== 'CANCELLED' && record.healthStatus !== 'CANCELLING' && (
            <Tooltip title="Cancel">
              <IconButton
                size="small"
                danger
                icon={<CloseCircleOutlined />}
                onClick={() => handleCancelQueueItem(record.taskId)}
                loading={cancelQueueItemMutation.isPending}
                data-testid={`queue-cancel-button-${record.taskId}`}
                aria-label="Cancel"
              />
            </Tooltip>
          )}
        </Space>
      )
    }
  ]


  return (
    <PageWrapper data-testid="queue-page-container">
      <FiltersCard size="small" data-testid="queue-filters-card">
        <FiltersGrid direction="vertical">
          <Space size={8} wrap>
            <FilterSelect
              size="small"
              $minWidth={150}
              placeholder="Team"
              value={viewTeam || undefined}
              onChange={(value) => {
                const nextValue = typeof value === 'string' ? value : ''
                setViewTeam(nextValue)
                setFilters({ ...filters, machineName: '' })
              }}
              allowClear
              options={dropdownData?.teams || []}
              data-testid="queue-filter-team"
            />
            <FilterSelect
              size="small"
              $minWidth={150}
              placeholder="Machine"
              value={filters.machineName || undefined}
              onChange={(value) =>
                setFilters({ ...filters, machineName: (value as string) || '' })
              }
              allowClear
              options={(dropdownData?.machines || []).map((machine: string) => ({ label: machine, value: machine }))}
              data-testid="queue-filter-machine"
            />
            <FilterSelect
              size="small"
              $minWidth={130}
              placeholder="Region"
              value={filters.regionName || undefined}
              onChange={(value) =>
                setFilters({ ...filters, regionName: (value as string) || '' })
              }
              allowClear
              options={dropdownData?.regions || []}
              data-testid="queue-filter-region"
            />
            <FilterSelect
              size="small"
              $minWidth={130}
              placeholder="Bridge"
              value={filters.bridgeName || undefined}
              onChange={(value) =>
                setFilters({ ...filters, bridgeName: (value as string) || '' })
              }
              allowClear
              options={dropdownData?.bridges || []}
              data-testid="queue-filter-bridge"
            />
            <FilterRangePicker
              size="small"
              value={dateRange as any}
              onChange={(dates) => setDateRange(dates as any)}
              allowClear
              placeholder={[t('queue:filters.dateFrom'), t('queue:filters.dateTo')]}
              data-testid="queue-filter-date"
            />
            <FilterSelect
              size="small"
              mode="multiple"
              $minWidth={160}
              placeholder="Status"
              value={statusFilter}
              onChange={(values) => setStatusFilter(values as string[])}
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
              size="small"
              placeholder="Task ID (GUID)"
              prefix={<SearchOutlined />}
              value={taskIdFilter}
              onChange={(e) => setTaskIdFilter(e.target.value)}
              allowClear
              data-testid="queue-filter-task"
            />
            <FilterCheckbox
              checked={filters.onlyStale}
              onChange={(e) => setFilters({ ...filters, onlyStale: e.target.checked })}
              data-testid="queue-checkbox-only-stale"
            >
              {t('queue:filters.onlyStale')}
            </FilterCheckbox>
          </Space>

          {hasActiveFilters && (
            <FilterTagBar>
              {viewTeam && (
                <Tag closable onClose={() => setViewTeam('')} color="blue">
                  {dropdownData?.teams?.find(t => t.value === viewTeam)?.label || viewTeam}
                </Tag>
              )}
              {filters.machineName && (
                <Tag closable onClose={() => setFilters({ ...filters, machineName: '' })} color="blue">
                  {filters.machineName}
                </Tag>
              )}
              {filters.regionName && (
                <Tag closable onClose={() => setFilters({ ...filters, regionName: '' })} color="blue">
                  {filters.regionName}
                </Tag>
              )}
              {filters.bridgeName && (
                <Tag closable onClose={() => setFilters({ ...filters, bridgeName: '' })} color="blue">
                  {filters.bridgeName}
                </Tag>
              )}
              {dateRange && (
                <Tag closable onClose={() => setDateRange(null)} color="blue">
                  {dateRange[0]?.format('MM/DD')}→{dateRange[1]?.format('MM/DD')}
                </Tag>
              )}
              {statusFilter.map(status => (
                <Tag key={status} closable onClose={() => setStatusFilter(statusFilter.filter(s => s !== status))} color="blue">
                  {status}
                </Tag>
              ))}
              {taskIdFilter && isValidGuid(taskIdFilter) && (
                <Tag closable onClose={() => setTaskIdFilter('')} color="blue">
                  {taskIdFilter.substring(0, 8)}...
                </Tag>
              )}
              {filters.onlyStale && (
                <Tag closable onClose={() => setFilters({ ...filters, onlyStale: false })} color="orange">
                  Stale
                </Tag>
              )}
              <ClearFiltersButton
                type="link"
                size="small"
                onClick={() => {
                  setViewTeam('')
                  setDateRange(null)
                  setStatusFilter([])
                  setTaskIdFilter('')
                  setFilters({ ...filters, onlyStale: false, machineName: '', regionName: '', bridgeName: '' })
                }}
              >
                Clear
              </ClearFiltersButton>
            </FilterTagBar>
          )}

          <StatsBar>
            <StatItem>
              <StatIcon>
                <ThunderboltOutlined />
              </StatIcon>
              <StatLabel>{t('queue:statistics.total')}:</StatLabel>
              <StatValue>{totalCount}</StatValue>
            </StatItem>
            <StatDivider />
            <StatItem>
              <StatIcon $color="var(--color-info)">
                <PlayCircleOutlined />
              </StatIcon>
              <StatLabel>{t('queue:statistics.active')}:</StatLabel>
              <StatValue $color="var(--color-info)">{activeCount}</StatValue>
            </StatItem>
            <StatDivider />
            <StatItem>
              <StatIcon $color="var(--color-error)">
                <ExclamationCircleOutlined />
              </StatIcon>
              <StatLabel>{t('queue:statistics.failed')}:</StatLabel>
              <StatValue $color="var(--color-error)">{failedCount}</StatValue>
            </StatItem>
            <StatDivider />
            <StatItem>
              <StatIcon $color="var(--color-warning)">
                <WarningOutlined />
              </StatIcon>
              <StatLabel>{t('queue:statistics.stale')}:</StatLabel>
              <StatValue $color="var(--color-warning)">{staleCount}</StatValue>
            </StatItem>
          </StatsBar>

          <Space size={4}>
            <Tooltip title={t('common:actions.refresh')}>
              <IconButton
                size="small"
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
                  { key: 'json', label: t('common:exportJSON'), onClick: () => handleExport('json') }
                ]
              }}
            >
              <Tooltip title={t('common:export')}>
                <IconButton
                  size="small"
                  icon={<ExportOutlined />}
                  data-testid="queue-export-dropdown"
                />
              </Tooltip>
            </Dropdown>
          </Space>
        </FiltersGrid>
      </FiltersCard>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        data-testid="queue-tabs"
      >
            <Tabs.TabPane 
              tab={
                <Tooltip title={t('queue:tabs.active.tooltip')}>
                  <TabLabel data-testid="queue-tab-active">
                    {t('queue:tabs.active.title')}
                    <TabCount count={activeItems.length} $color="#5a5a5a" />
                  </TabLabel>
                </Tooltip>
              } 
              key="active"
              data-testid="queue-tabpane-active"
            >
              <ResourceListView
                loading={isLoading || isRefetching}
                data={activeItems}
                columns={queueColumns}
                rowKey="taskId"
                searchPlaceholder="Search queue items..."
                pagination={{
                  current: activePage,
                  pageSize: activePageSize,
                  showSizeChanger: true,
                  pageSizeOptions: ['10', '20', '50', '100'],
                  showTotal: (total, range) => `Showing records ${range[0]}-${range[1]} of ${total}`,
                  onChange: (page, size) => {
                    setActivePage(page);
                    if (size !== activePageSize) {
                      setActivePageSize(size);
                      setActivePage(1);
                    }
                  },
                  position: ['bottomRight'],
                }}
              />
            </Tabs.TabPane>
            
            <Tabs.TabPane 
              tab={
                <Tooltip title={t('queue:tabs.completed.tooltip')}>
                  <TabLabel data-testid="queue-tab-completed">
                    {t('queue:tabs.completed.title')}
                    <TabCount count={completedCount || completedItems.length} showZero $color="#4a4a4a" />
                  </TabLabel>
                </Tooltip>
              } 
              key="completed"
              data-testid="queue-tabpane-completed"
            >
              <ResourceListView
                loading={isLoading || isRefetching}
                data={completedItems}
                columns={queueColumns}
                rowKey="taskId"
                searchPlaceholder="Search completed items..."
                pagination={{
                  current: completedPage,
                  pageSize: completedPageSize,
                  showSizeChanger: true,
                  pageSizeOptions: ['10', '20', '50', '100'],
                  showTotal: (total, range) => `Showing records ${range[0]}-${range[1]} of ${total}`,
                  onChange: (page, size) => {
                    setCompletedPage(page);
                    if (size !== completedPageSize) {
                      setCompletedPageSize(size);
                      setCompletedPage(1);
                    }
                  },
                  position: ['bottomRight'],
                }}
              />
            </Tabs.TabPane>
            
            <Tabs.TabPane 
              tab={
                <Tooltip title={t('queue:tabs.cancelled.tooltip')}>
                  <TabLabel data-testid="queue-tab-cancelled">
                    {t('queue:tabs.cancelled.title')}
                    <TabCount count={cancelledCount || cancelledItems.length} showZero $color="#6a6a6a" />
                  </TabLabel>
                </Tooltip>
              } 
              key="cancelled"
              data-testid="queue-tabpane-cancelled"
            >
              <ResourceListView
                loading={isLoading || isRefetching}
                data={cancelledItems}
                columns={queueColumns}
                rowKey="taskId"
                searchPlaceholder="Search cancelled items..."
                pagination={{
                  current: cancelledPage,
                  pageSize: cancelledPageSize,
                  showSizeChanger: true,
                  pageSizeOptions: ['10', '20', '50', '100'],
                  showTotal: (total, range) => `Showing records ${range[0]}-${range[1]} of ${total}`,
                  onChange: (page, size) => {
                    setCancelledPage(page);
                    if (size !== cancelledPageSize) {
                      setCancelledPageSize(size);
                      setCancelledPage(1);
                    }
                  },
                  position: ['bottomRight'],
                }}
              />
            </Tabs.TabPane>
            
            <Tabs.TabPane 
              tab={
                <Tooltip title={t('queue:tabs.failed.tooltip')}>
                  <TabLabel data-testid="queue-tab-failed">
                    {t('queue:tabs.failed.title')}
                    <TabCount count={failedCount || failedItems.length} showZero $color="#ff4d4f" />
                  </TabLabel>
                </Tooltip>
              } 
              key="failed"
              data-testid="queue-tabpane-failed"
            >
              <ResourceListView
                loading={isLoading || isRefetching}
                data={failedItems}
                columns={queueColumns}
                rowKey="taskId"
                searchPlaceholder="Search failed items..."
                pagination={{
                  current: failedPage,
                  pageSize: failedPageSize,
                  showSizeChanger: true,
                  pageSizeOptions: ['10', '20', '50', '100'],
                  showTotal: (total, range) => `Showing records ${range[0]}-${range[1]} of ${total}`,
                  onChange: (page, size) => {
                    setFailedPage(page);
                    if (size !== failedPageSize) {
                      setFailedPageSize(size);
                      setFailedPage(1);
                    }
                  },
                  position: ['bottomRight'],
                }}
              />
            </Tabs.TabPane>
      </Tabs>

      <QueueItemTraceModal
        taskId={selectedTaskId}
        visible={traceModalVisible}
        onClose={() => {
          setTraceModalVisible(false)
          setSelectedTaskId(null)
        }}
      />
    </PageWrapper>
  )
}

export default QueuePage
