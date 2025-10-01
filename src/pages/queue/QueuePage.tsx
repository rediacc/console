import React, { useState, useMemo, useRef } from 'react'
import { Typography, Button, Space, Modal, Select, Card, Tag, Badge, Tabs, Row, Col, Statistic, Tooltip, DatePicker, Checkbox, Dropdown, Input, Alert } from 'antd'
import { ThunderboltOutlined, DesktopOutlined, ApiOutlined, PlayCircleOutlined, CheckCircleOutlined, CloseCircleOutlined, ExclamationCircleOutlined, WarningOutlined, GlobalOutlined, ClockCircleOutlined, ReloadOutlined, ExportOutlined, DownOutlined, HistoryOutlined, SearchOutlined, InfoCircleOutlined } from '@/utils/optimizedIcons'
import { useQueueItems, useCancelQueueItem, QueueFilters } from '@/api/queries/queue'
import { useDropdownData } from '@/api/queries/useDropdownData'
import ResourceListView from '@/components/common/ResourceListView'
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal'
import { showMessage } from '@/utils/messages'
import dayjs from 'dayjs'
import { useDynamicPageSize } from '@/hooks/useDynamicPageSize'
import { useTranslation } from 'react-i18next'
import { formatTimestampAsIs } from '@/utils/timeUtils'
import { useComponentStyles } from '@/hooks/useComponentStyles'

const { Title, Text } = Typography
const { RangePicker } = DatePicker

const QueuePage: React.FC = () => {
  const { t } = useTranslation(['queue'])
  const styles = useComponentStyles()
  const [viewTeam, setViewTeam] = useState<string>('') // Team for viewing queue items
  const [activeTab, setActiveTab] = useState<string>('active') // Track which tab is active
  const [filters, setFilters] = useState<QueueFilters>({
    teamName: '',
    includeCompleted: true,
    includeCancelled: false,  // Don't show cancelled tasks by default
    staleThresholdMinutes: 10,
    maxRecords: 1000
  })
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs | null, dayjs.Dayjs | null] | null>(null)
  const [statusFilter, setStatusFilter] = useState<string[]>([])
  const [taskIdFilter, setTaskIdFilter] = useState<string>('')
  const [traceModalVisible, setTraceModalVisible] = useState(false)
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  
  // GUID validation regex
  const isValidGuid = (value: string) => {
    const guidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
    return guidRegex.test(value)
  }
  
  // Refs for table containers
  const activeTableRef = useRef<HTMLDivElement>(null)
  const completedTableRef = useRef<HTMLDivElement>(null)
  const cancelledTableRef = useRef<HTMLDivElement>(null)
  const failedTableRef = useRef<HTMLDivElement>(null)
  
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
  
  // Dynamic page sizes for resultSets with minimum size for small screens
  const activePageSize = useDynamicPageSize(activeTableRef, {
    containerOffset: 300, // Account for filters, stats cards, tabs
    minRows: 8, // Minimum for small screens
    maxRows: 50
  })
  
  const completedPageSize = useDynamicPageSize(completedTableRef, {
    containerOffset: 300,
    minRows: 8,
    maxRows: 50
  })
  
  const cancelledPageSize = useDynamicPageSize(cancelledTableRef, {
    containerOffset: 300,
    minRows: 8,
    maxRows: 50
  })
  
  const failedPageSize = useDynamicPageSize(failedTableRef, {
    containerOffset: 300,
    minRows: 8,
    maxRows: 50
  })
  
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
          1: { color: 'red', icon: <ExclamationCircleOutlined /> },
          2: { color: 'orange', icon: undefined },
          3: { color: 'gold', icon: undefined },
          4: { color: 'blue', icon: undefined },
          5: { color: 'green', icon: undefined }
        }
        
        const config = priorityConfig[record.priority as keyof typeof priorityConfig] || priorityConfig[3]
        
        return (
          <Tag color={config.color} icon={config.icon}>
            {priorityLabel}
          </Tag>
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


  // Calculate container style for full height layout using design system
  const containerStyle: React.CSSProperties = {
    ...styles.container,
    height: 'calc(100vh - 64px - 48px)', // viewport - header - content margin
    ...styles.flexColumn,
    overflow: 'hidden'
  }

  return (
    <div style={containerStyle} data-testid="queue-page-container">
      <Row gutter={[16, 16]} align="middle" style={{ marginBottom: 16 }}>
        <Col>
          <Title level={2} style={styles.heading2}>Queue Management</Title>
        </Col>
      </Row>

      <Card style={{ ...styles.card, ...styles.marginBottom.md }} data-testid="queue-filters-card">
        <Row gutter={[16, 16]} align="middle">
          <Col xs={24} sm={12} md={6}>
            <label htmlFor="queue-filter-team" style={{ display: 'block', marginBottom: 8 }}>
              <Text type="secondary">Team</Text>
            </label>
            <Select
              id="queue-filter-team"
              style={{ width: '100%' }}
              placeholder="Select a team to view queue items"
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
              aria-label="Select team to filter queue items"
            />
          </Col>

          {viewTeam && (
            <Col xs={24} sm={12} md={6}>
              <label htmlFor="queue-filter-machine" style={{ display: 'block', marginBottom: 8 }}>
                <Text type="secondary">Machine</Text>
              </label>
              <Select
                id="queue-filter-machine"
                style={{ width: '100%' }}
                placeholder="All machines"
                value={filters.machineName || undefined}
                onChange={(value) => setFilters({ ...filters, machineName: value || '' })}
                allowClear
                showSearch
                filterOption={(input, option) =>
                  (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
                }
                options={dropdownData?.machinesByTeam?.find(t => t.teamName === viewTeam)?.machines || []}
                data-testid="queue-filter-machine"
                aria-label="Select machine to filter queue items"
              />
            </Col>
          )}

          <Col xs={24} sm={12} md={6}>
            <label htmlFor="queue-filter-status" style={{ display: 'block', marginBottom: 8 }}>
              <Text type="secondary">Status</Text>
            </label>
            <Select
              id="queue-filter-status"
              mode="multiple"
              style={{ width: '100%' }}
              placeholder="All statuses"
              value={statusFilter}
              onChange={setStatusFilter}
              allowClear
              data-testid="queue-filter-status"
              aria-label="Select statuses to filter queue items"
            >
              <Select.Option value="PENDING" data-testid="queue-filter-status-option-pending">Pending</Select.Option>
              <Select.Option value="ACTIVE" data-testid="queue-filter-status-option-active">Active</Select.Option>
              <Select.Option value="STALE" data-testid="queue-filter-status-option-stale">Stale</Select.Option>
              <Select.Option value="CANCELLING" data-testid="queue-filter-status-option-cancelling">Cancelling</Select.Option>
              <Select.Option value="COMPLETED" data-testid="queue-filter-status-option-completed">Completed</Select.Option>
              <Select.Option value="FAILED" data-testid="queue-filter-status-option-failed">Failed</Select.Option>
              <Select.Option value="CANCELLED" data-testid="queue-filter-status-option-cancelled">Cancelled</Select.Option>
            </Select>
          </Col>

          <Col xs={24} sm={12} md={6}>
            <label htmlFor="queue-filter-date" style={{ display: 'block', marginBottom: 8 }}>
              <Text type="secondary">Date Range</Text>
            </label>
            <RangePicker
              id="queue-filter-date"
              style={{ width: '100%' }}
              showTime
              format="YYYY-MM-DD HH:mm:ss"
              value={dateRange}
              onChange={(dates) => setDateRange(dates)}
              presets={[
                { label: 'Today', value: [dayjs().startOf('day'), dayjs().endOf('day')] },
                { label: 'Yesterday', value: [dayjs().subtract(1, 'day').startOf('day'), dayjs().subtract(1, 'day').endOf('day')] },
                { label: 'Last 7 Days', value: [dayjs().subtract(7, 'day').startOf('day'), dayjs()] },
                { label: 'Last 30 Days', value: [dayjs().subtract(30, 'day').startOf('day'), dayjs()] },
                { label: 'This Month', value: [dayjs().startOf('month'), dayjs().endOf('month')] },
                { label: 'Last Month', value: [dayjs().subtract(1, 'month').startOf('month'), dayjs().subtract(1, 'month').endOf('month')] },
              ]}
              data-testid="queue-filter-date"
              aria-label="Select date range to filter queue items"
            />
          </Col>
        </Row>

        <Row gutter={[16, 16]} style={{ marginTop: 16 }} align="middle">
          <Col xs={24} sm={12} md={6}>
            <label htmlFor="queue-filter-taskid" style={{ display: 'block', marginBottom: 8 }}>
              <Text type="secondary">Task ID</Text>
            </label>
            <Input
              id="queue-filter-taskid"
              placeholder="Filter by Task ID (GUID format)"
              value={taskIdFilter}
              onChange={(e) => setTaskIdFilter(e.target.value)}
              prefix={<SearchOutlined />}
              allowClear
              status={taskIdFilter && !isValidGuid(taskIdFilter) ? 'error' : undefined}
              autoComplete="off"
              data-testid="queue-filter-taskid"
              aria-label="Filter queue items by Task ID"
              aria-describedby={taskIdFilter && !isValidGuid(taskIdFilter) ? 'taskid-error' : undefined}
            />
            {taskIdFilter && !isValidGuid(taskIdFilter) && (
              <Text id="taskid-error" type="danger" style={{ fontSize: '12px' }}>
                Invalid GUID format
              </Text>
            )}
          </Col>

          <Col xs={24} sm={12} md={6}>
            <div style={{ marginBottom: 8 }}>
              <Text type="secondary">Options</Text>
            </div>
            <Space direction="vertical">
              <Tooltip title={activeTab === 'completed' ? 'Automatically enabled when viewing Completed tab' : ''}>
                <Checkbox
                  checked={activeTab === 'completed' ? true : filters.includeCompleted}
                  disabled={activeTab === 'completed'}
                  onChange={(e) => setFilters({ ...filters, includeCompleted: e.target.checked })}
                  data-testid="queue-checkbox-include-completed"
                >
                  Include Completed
                </Checkbox>
              </Tooltip>
              <Tooltip title={activeTab === 'cancelled' ? 'Automatically enabled when viewing Cancelled tab' : ''}>
                <Checkbox
                  checked={activeTab === 'cancelled' ? true : filters.includeCancelled}
                  disabled={activeTab === 'cancelled'}
                  onChange={(e) => setFilters({ ...filters, includeCancelled: e.target.checked })}
                  data-testid="queue-checkbox-include-cancelled"
                >
                  Include Cancelled
                </Checkbox>
              </Tooltip>
              <Checkbox
                checked={filters.onlyStale}
                onChange={(e) => setFilters({ ...filters, onlyStale: e.target.checked })}
                data-testid="queue-checkbox-only-stale"
              >
                Only Stale Items
              </Checkbox>
            </Space>
          </Col>

          <Col style={{ marginLeft: 'auto' }}>
            <Space>
              <Button 
                icon={<ReloadOutlined />} 
                style={styles.touchTarget}
                onClick={() => refetch()} 
                loading={isFetching} 
                data-testid="queue-refresh-button"
              >
                Refresh
              </Button>
              <Dropdown
                menu={{
                  items: [
                    {
                      key: 'csv',
                      label: 'Export as CSV',
                      onClick: () => handleExport('csv')
                    },
                    {
                      key: 'json',
                      label: 'Export as JSON',
                      onClick: () => handleExport('json')
                    }
                  ]
                }}
              >
                <Button 
                  icon={<ExportOutlined />} 
                  style={styles.touchTarget}
                  data-testid="queue-export-dropdown"
                >
                  Export <DownOutlined />
                </Button>
              </Dropdown>
            </Space>
          </Col>
        </Row>
      </Card>

      {/* Queue Statistics */}
      <Row gutter={16} style={styles.marginBottom.md} data-testid="queue-statistics-row">
            <Col xs={24} sm={12} md={8} lg={4} xl={3}>
              <Card style={styles.card}>
                <Statistic
                  title="Total"
                  value={(queueData?.statistics as any)?.totalCount || 0}
                  prefix={<ThunderboltOutlined />}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} md={8} lg={4} xl={3}>
              <Card style={styles.card}>
                <Statistic
                  title="Pending"
                  value={(queueData?.statistics as any)?.pendingCount || 0}
                  valueStyle={{ color: '#8c8c8c' }}
                  prefix={<ClockCircleOutlined />}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} md={8} lg={4} xl={3}>
              <Card style={styles.card}>
                <Statistic
                  title="Assigned"
                  value={(queueData?.statistics as any)?.assignedCount || 0}
                  valueStyle={{ color: '#1890ff' }}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} md={8} lg={4} xl={3}>
              <Card style={styles.card}>
                <Statistic
                  title="Processing"
                  value={(queueData?.statistics as any)?.processingCount || 0}
                  valueStyle={{ color: '#1890ff' }}
                  prefix={<PlayCircleOutlined />}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} md={8} lg={4} xl={3}>
              <Card style={styles.card}>
                <Statistic
                  title="Completed"
                  value={(queueData?.statistics as any)?.completedCount || 0}
                  valueStyle={{ color: '#52c41a' }}
                  prefix={<CheckCircleOutlined />}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} md={8} lg={4} xl={3}>
              <Card style={styles.card}>
                <Statistic
                  title="Failed"
                  value={(queueData?.statistics as any)?.failedCount || 0}
                  valueStyle={{ color: '#ff4d4f' }}
                  prefix={<ExclamationCircleOutlined />}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} md={8} lg={4} xl={3}>
              <Card style={styles.card}>
                <Statistic
                  title="Cancelling"
                  value={(queueData?.statistics as any)?.cancellingCount || 0}
                  valueStyle={{ color: '#faad14' }}
                  prefix={<PlayCircleOutlined spin />}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} md={8} lg={4} xl={3}>
              <Card style={styles.card}>
                <Statistic
                  title="Cancelled"
                  value={(queueData?.statistics as any)?.cancelledCount || 0}
                  valueStyle={{ color: '#ff4d4f' }}
                  prefix={<CloseCircleOutlined />}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} md={8} lg={4} xl={3}>
              <Card style={styles.card}>
                <Statistic
                  title="Stale"
                  value={(queueData?.statistics as any)?.staleCount || 0}
                  valueStyle={{ color: '#faad14' }}
                  prefix={<WarningOutlined />}
                />
              </Card>
            </Col>
          </Row>

          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              minHeight: 0,
              overflow: 'hidden'
            }}
            className="full-height-tabs"
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
              <div ref={activeTableRef} style={{ height: '100%', display: 'flex', flexDirection: 'column' }} data-testid="queue-table-active-container">
                <Alert
                  message={t('queue:tabs.active.description')}
                  type="info"
                  showIcon
                  icon={<InfoCircleOutlined />}
                  style={{ marginBottom: 16 }}
                  closable
                  data-testid="queue-alert-active"
                />
                <ResourceListView
                  loading={isLoading || isRefetching}
                  data={queueData?.items?.filter((item: any) => !['COMPLETED', 'CANCELLED', 'FAILED'].includes(item.healthStatus)) || []}
                  columns={queueColumns}
                  rowKey="taskId"
                  searchPlaceholder="Search queue items..."
                  enableDynamicPageSize={true}
                  containerStyle={{
                    height: '100%',
                    display: 'flex',
                    flexDirection: 'column',
                  }}
                  tableStyle={{ 
                    height: 'calc(100vh - 520px)', // Adjusted for Alert component
                    minHeight: '400px' // Minimum height for small screens
                  }}
                  pagination={{
                    pageSize: activePageSize,
                    showSizeChanger: false,
                    showTotal: (total, range) => `Showing records ${range[0]}-${range[1]} of ${total}`,
                    position: ['bottomRight'],
                  }}
                />
              </div>
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
              <div ref={completedTableRef} style={{ height: '100%', display: 'flex', flexDirection: 'column' }} data-testid="queue-table-completed-container">
                <Alert
                  message={t('queue:tabs.completed.description')}
                  type="success"
                  showIcon
                  icon={<CheckCircleOutlined />}
                  style={{ marginBottom: 16 }}
                  closable
                  data-testid="queue-alert-completed"
                />
                <ResourceListView
                  loading={isLoading || isRefetching}
                  data={queueData?.items?.filter((item: any) => item.healthStatus === 'COMPLETED') || []}
                  columns={queueColumns}
                  rowKey="taskId"
                  searchPlaceholder="Search completed items..."
                  enableDynamicPageSize={true}
                  containerStyle={{
                    height: '100%',
                    display: 'flex',
                    flexDirection: 'column',
                  }}
                  tableStyle={{ 
                    height: 'calc(100vh - 520px)',
                    minHeight: '400px'
                  }}
                  pagination={{
                    pageSize: completedPageSize,
                    showSizeChanger: false,
                    showTotal: (total, range) => `Showing records ${range[0]}-${range[1]} of ${total}`,
                    position: ['bottomRight'],
                  }}
                />
              </div>
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
              <div ref={cancelledTableRef} style={{ height: '100%', display: 'flex', flexDirection: 'column' }} data-testid="queue-table-cancelled-container">
                <Alert
                  message={t('queue:tabs.cancelled.description')}
                  type="warning"
                  showIcon
                  icon={<CloseCircleOutlined />}
                  style={{ marginBottom: 16 }}
                  closable
                  data-testid="queue-alert-cancelled"
                />
                <ResourceListView
                  loading={isLoading || isRefetching}
                  data={queueData?.items?.filter((item: any) => item.healthStatus === 'CANCELLED') || []}
                  columns={queueColumns}
                  rowKey="taskId"
                  searchPlaceholder="Search cancelled items..."
                  enableDynamicPageSize={true}
                  containerStyle={{
                    height: '100%',
                    display: 'flex',
                    flexDirection: 'column',
                  }}
                  tableStyle={{ 
                    height: 'calc(100vh - 520px)',
                    minHeight: '400px'
                  }}
                  pagination={{
                    pageSize: cancelledPageSize,
                    showSizeChanger: false,
                    showTotal: (total, range) => `Showing records ${range[0]}-${range[1]} of ${total}`,
                    position: ['bottomRight'],
                  }}
                />
              </div>
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
              <div ref={failedTableRef} style={{ height: '100%', display: 'flex', flexDirection: 'column' }} data-testid="queue-table-failed-container">
                <Alert
                  message={t('queue:tabs.failed.description')}
                  type="error"
                  showIcon
                  icon={<ExclamationCircleOutlined />}
                  style={{ marginBottom: 16 }}
                  closable
                  data-testid="queue-alert-failed"
                />
                <ResourceListView
                  loading={isLoading || isRefetching}
                  data={queueData?.items?.filter((item: any) => item.healthStatus === 'FAILED') || []}
                  columns={queueColumns}
                  rowKey="taskId"
                  searchPlaceholder="Search failed items..."
                  enableDynamicPageSize={true}
                  containerStyle={{
                    height: '100%',
                    display: 'flex',
                    flexDirection: 'column',
                  }}
                  tableStyle={{ 
                    height: 'calc(100vh - 520px)',
                    minHeight: '400px'
                  }}
                  pagination={{
                    pageSize: failedPageSize,
                    showSizeChanger: false,
                    showTotal: (total, range) => `Showing records ${range[0]}-${range[1]} of ${total}`,
                    position: ['bottomRight'],
                  }}
                />
              </div>
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