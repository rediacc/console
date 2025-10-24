import React, { useState, useMemo } from 'react'
import { Typography, Button, Space, Modal, Select, Card, Tag, Badge, Tabs, Row, Col, Tooltip, DatePicker, Checkbox, Dropdown, Input } from 'antd'
import { ThunderboltOutlined, DesktopOutlined, ApiOutlined, PlayCircleOutlined, CheckCircleOutlined, CloseCircleOutlined, ExclamationCircleOutlined, WarningOutlined, GlobalOutlined, ClockCircleOutlined, ReloadOutlined, ExportOutlined, HistoryOutlined, SearchOutlined } from '@/utils/optimizedIcons'
import { useQueueItems, useCancelQueueItem, QueueFilters } from '@/api/queries/queue'
import { useDropdownData } from '@/api/queries/useDropdownData'
import ResourceListView from '@/components/common/ResourceListView'
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal'
import { showMessage } from '@/utils/messages'
import dayjs from 'dayjs'
import { useTranslation } from 'react-i18next'
import { formatTimestampAsIs } from '@/utils/timeUtils'
import { useComponentStyles } from '@/hooks/useComponentStyles'

const { Text, Title } = Typography
const { RangePicker } = DatePicker

const QueuePage: React.FC = () => {
  const { t } = useTranslation(['queue'])
  const styles = useComponentStyles()
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
      sorter: (a: any, b: any) => (a.priority || 3) - (b.priority || 3),
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
      sorter: (a: any, b: any) => a.ageInMinutes - b.ageInMinutes,
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
      sorter: (a: any, b: any) => (a.retryCount || 0) - (b.retryCount || 0),
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
      sorter: (a: any, b: any) => a.ageInMinutes - b.ageInMinutes,
    },
    {
      title: 'Created',
      dataIndex: 'createdTime',
      key: 'createdTime',
      width: 180,
      render: (date: string) => dayjs(date).format('YYYY-MM-DD HH:mm:ss'),
      sorter: (a: any, b: any) => new Date(a.createdTime).getTime() - new Date(b.createdTime).getTime(),
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 180,
      render: (_: any, record: any) => (
        <Space size="small">
          <Tooltip title="Trace">
            <Button
              size="small"
              type="primary"
              icon={<HistoryOutlined />}
              style={styles.touchTargetSmall}
              onClick={() => handleViewTrace(record.taskId)}
              data-testid={`queue-trace-button-${record.taskId}`}
              aria-label="Trace"
            />
          </Tooltip>
          {record.canBeCancelled && record.healthStatus !== 'CANCELLED' && record.healthStatus !== 'CANCELLING' && (
            <Tooltip title="Cancel">
              <Button
                size="small"
                danger
                icon={<CloseCircleOutlined />}
                style={styles.touchTargetSmall}
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
    <div style={{ padding: 24 }} data-testid="queue-page-container">
      <Title level={2} style={{ ...styles.heading2, marginBottom: 16 }}>{t('title')}</Title>
      {/* Ultra-Compact Filter & Stats Bar */}
      <Card
        size="small"
        style={{ marginBottom: 16, padding: '8px 12px' }}
        data-testid="queue-filters-card"
      >
        <Row gutter={[8, 8]} align="middle" wrap>
          {/* Filters Section */}
          <Col flex="auto">
            <Space size={8} wrap>
              <Select
                size="small"
                style={{ minWidth: 150 }}
                placeholder="Team"
                value={viewTeam || undefined}
                onChange={(value) => {
                  setViewTeam(value || '')
                  setFilters({ ...filters, machineName: '' })
                }}
                allowClear
                showSearch
                filterOption={(input, option) =>
                  (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
                }
                options={dropdownData?.teams || []}
                data-testid="queue-filter-team"
              />

              <Select
                size="small"
                mode="multiple"
                style={{ minWidth: 150 }}
                placeholder="Status"
                value={statusFilter}
                onChange={setStatusFilter}
                allowClear
                maxTagCount="responsive"
                data-testid="queue-filter-status"
              >
                <Select.Option value="PENDING">Pending</Select.Option>
                <Select.Option value="ACTIVE">Active</Select.Option>
                <Select.Option value="STALE">Stale</Select.Option>
                <Select.Option value="CANCELLING">Cancelling</Select.Option>
                <Select.Option value="COMPLETED">Completed</Select.Option>
                <Select.Option value="FAILED">Failed</Select.Option>
                <Select.Option value="CANCELLED">Cancelled</Select.Option>
              </Select>

              <RangePicker
                size="small"
                format="YYYY-MM-DD"
                value={dateRange}
                onChange={(dates) => setDateRange(dates)}
                placeholder={['Start', 'End']}
                presets={[
                  { label: 'Today', value: [dayjs().startOf('day'), dayjs().endOf('day')] },
                  { label: 'Last 7D', value: [dayjs().subtract(7, 'day').startOf('day'), dayjs()] },
                  { label: 'Last 30D', value: [dayjs().subtract(30, 'day').startOf('day'), dayjs()] },
                ]}
                data-testid="queue-filter-date"
              />

              <Checkbox
                checked={filters.onlyStale}
                onChange={(e) => setFilters({ ...filters, onlyStale: e.target.checked })}
                data-testid="queue-checkbox-only-stale"
              >
                Stale Only
              </Checkbox>

              {viewTeam && (
                <>
                  <Select
                    size="small"
                    style={{ minWidth: 130 }}
                    placeholder="Machine"
                    value={filters.machineName || undefined}
                    onChange={(value) => setFilters({ ...filters, machineName: value || '' })}
                    allowClear
                    showSearch
                    filterOption={(input, option) =>
                      (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
                    }
                    options={dropdownData?.machinesByTeam?.find(t => t.teamName === viewTeam)?.machines || []}
                    data-testid="queue-filter-machine"
                  />

                  <Input
                    size="small"
                    placeholder="Task ID"
                    value={taskIdFilter}
                    onChange={(e) => setTaskIdFilter(e.target.value)}
                    prefix={<SearchOutlined />}
                    allowClear
                    status={taskIdFilter && !isValidGuid(taskIdFilter) ? 'error' : undefined}
                    style={{ width: 200 }}
                    data-testid="queue-filter-taskid"
                  />
                </>
              )}

              {/* Active Filter Pills - Inline */}
              {(viewTeam || dateRange || statusFilter.length > 0 || (taskIdFilter && isValidGuid(taskIdFilter)) || filters.onlyStale) && (
                <>
                  {viewTeam && (
                    <Tag closable onClose={() => setViewTeam('')} color="blue">
                      {dropdownData?.teams?.find(t => t.value === viewTeam)?.label || viewTeam}
                    </Tag>
                  )}
                  {dateRange && (
                    <Tag closable onClose={() => setDateRange(null)} color="blue">
                      {dateRange[0]?.format('MM/DD')}→{dateRange[1]?.format('MM/DD')}
                    </Tag>
                  )}
                  {statusFilter.map(status => (
                    <Tag
                      key={status}
                      closable
                      onClose={() => setStatusFilter(statusFilter.filter(s => s !== status))}
                      color="blue"
                    >
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
                  <Button
                    type="link"
                    size="small"
                    onClick={() => {
                      setViewTeam('')
                      setDateRange(null)
                      setStatusFilter([])
                      setTaskIdFilter('')
                      setFilters({ ...filters, onlyStale: false })
                    }}
                    style={{ padding: '0 4px', height: 'auto' }}
                  >
                    Clear
                  </Button>
                </>
              )}
            </Space>
          </Col>

          {/* Statistics Section - Inline */}
          <Col flex="none">
            <Space size={12} split={<span style={{ color: '#d9d9d9' }}>|</span>}>
              <Space size={4}>
                <ThunderboltOutlined style={{ fontSize: 12 }} />
                <Text type="secondary" style={{ fontSize: 12 }}>Total:</Text>
                <Text strong style={{ fontSize: 12 }}>{(queueData?.statistics as any)?.totalCount || 0}</Text>
              </Space>
              <Space size={4}>
                <PlayCircleOutlined style={{ fontSize: 12, color: '#1890ff' }} />
                <Text type="secondary" style={{ fontSize: 12 }}>Active:</Text>
                <Text strong style={{ fontSize: 12, color: '#1890ff' }}>
                  {((queueData?.statistics as any)?.pendingCount || 0) +
                   ((queueData?.statistics as any)?.assignedCount || 0) +
                   ((queueData?.statistics as any)?.processingCount || 0)}
                </Text>
              </Space>
              <Space size={4}>
                <ExclamationCircleOutlined style={{ fontSize: 12, color: '#ff4d4f' }} />
                <Text type="secondary" style={{ fontSize: 12 }}>Failed:</Text>
                <Text strong style={{ fontSize: 12, color: '#ff4d4f' }}>{(queueData?.statistics as any)?.failedCount || 0}</Text>
              </Space>
              <Space size={4}>
                <WarningOutlined style={{ fontSize: 12, color: '#faad14' }} />
                <Text type="secondary" style={{ fontSize: 12 }}>Stale:</Text>
                <Text strong style={{ fontSize: 12, color: '#faad14' }}>{(queueData?.statistics as any)?.staleCount || 0}</Text>
              </Space>
            </Space>
          </Col>

          {/* Actions Section */}
          <Col flex="none">
            <Space size={4}>
              <Tooltip title="Refresh">
                <Button
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
                    { key: 'csv', label: 'Export as CSV', onClick: () => handleExport('csv') },
                    { key: 'json', label: 'Export as JSON', onClick: () => handleExport('json') }
                  ]
                }}
              >
                <Tooltip title="Export">
                  <Button
                    size="small"
                    icon={<ExportOutlined />}
                    data-testid="queue-export-dropdown"
                  />
                </Tooltip>
              </Dropdown>
            </Space>
          </Col>
        </Row>
      </Card>

      <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            data-testid="queue-tabs"
          >
            <Tabs.TabPane 
              tab={
                <Tooltip title={t('queue:tabs.active.tooltip')}>
                  <Space data-testid="queue-tab-active">
                    <span style={{ marginRight: 8 }}>{t('queue:tabs.active.title')}</span>
                    <Badge count={queueData?.items?.filter((item: any) => !['COMPLETED', 'CANCELLED', 'FAILED'].includes(item.healthStatus)).length || 0} color="gold" />
                  </Space>
                </Tooltip>
              } 
              key="active"
              data-testid="queue-tabpane-active"
            >
              <ResourceListView
                loading={isLoading || isRefetching}
                data={queueData?.items?.filter((item: any) => !['COMPLETED', 'CANCELLED', 'FAILED'].includes(item.healthStatus)) || []}
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
                  <Space data-testid="queue-tab-completed">
                    <span style={{ marginRight: 8 }}>{t('queue:tabs.completed.title')}</span>
                    <Badge count={(queueData?.statistics as any)?.completedCount || 0} showZero color="#52c41a" />
                  </Space>
                </Tooltip>
              } 
              key="completed"
              data-testid="queue-tabpane-completed"
            >
              <ResourceListView
                loading={isLoading || isRefetching}
                data={queueData?.items?.filter((item: any) => item.healthStatus === 'COMPLETED') || []}
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
                  <Space data-testid="queue-tab-cancelled">
                    <span style={{ marginRight: 8 }}>{t('queue:tabs.cancelled.title')}</span>
                    <Badge count={(queueData?.statistics as any)?.cancelledCount || 0} showZero color="#ff4d4f" />
                  </Space>
                </Tooltip>
              } 
              key="cancelled"
              data-testid="queue-tabpane-cancelled"
            >
              <ResourceListView
                loading={isLoading || isRefetching}
                data={queueData?.items?.filter((item: any) => item.healthStatus === 'CANCELLED') || []}
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
                  <Space data-testid="queue-tab-failed">
                    <span style={{ marginRight: 8 }}>{t('queue:tabs.failed.title')}</span>
                    <Badge count={(queueData?.statistics as any)?.failedCount || 0} showZero color="#ff4d4f" />
                  </Space>
                </Tooltip>
              } 
              key="failed"
              data-testid="queue-tabpane-failed"
            >
              <ResourceListView
                loading={isLoading || isRefetching}
                data={queueData?.items?.filter((item: any) => item.healthStatus === 'FAILED') || []}
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

          {/* Trace Modal */}
          <QueueItemTraceModal
            taskId={selectedTaskId}
            visible={traceModalVisible}
            onClose={() => {
              setTraceModalVisible(false)
              setSelectedTaskId(null)
            }}
          />
    </div>
  )
}

export default QueuePage