import React, { useState, useMemo, useRef } from 'react'
import { Typography, Button, Space, Modal, Select, Card, Tag, Badge, Tabs, Row, Col, Statistic, Tooltip, DatePicker, Checkbox, Dropdown } from 'antd'
import { ThunderboltOutlined, DesktopOutlined, ApiOutlined, PlayCircleOutlined, CheckCircleOutlined, CloseCircleOutlined, ExclamationCircleOutlined, WarningOutlined, GlobalOutlined, ClockCircleOutlined, ReloadOutlined, ExportOutlined, DownOutlined, HistoryOutlined } from '@ant-design/icons'
import { useQueueItems, useCancelQueueItem, QueueFilters } from '@/api/queries/queue'
import { useDropdownData } from '@/api/queries/useDropdownData'
import ResourceListView from '@/components/common/ResourceListView'
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal'
import { showMessage } from '@/utils/messages'
import dayjs from 'dayjs'
import { useDynamicPageSize } from '@/hooks/useDynamicPageSize'

const { Title, Text } = Typography
const { RangePicker } = DatePicker

const QueuePage: React.FC = () => {
  const [viewTeam, setViewTeam] = useState<string>('') // Team for viewing queue items
  const [filters, setFilters] = useState<QueueFilters>({
    teamName: '',
    includeCompleted: true,
    includeCancelled: true,
    staleThresholdMinutes: 10,
    maxRecords: 1000
  })
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs | null, dayjs.Dayjs | null] | null>(null)
  const [statusFilter, setStatusFilter] = useState<string[]>([])
  const [traceModalVisible, setTraceModalVisible] = useState(false)
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  
  // Refs for table containers
  const activeTableRef = useRef<HTMLDivElement>(null)
  const completedTableRef = useRef<HTMLDivElement>(null)
  const cancelledTableRef = useRef<HTMLDivElement>(null)
  const failedTableRef = useRef<HTMLDivElement>(null)
  
  // Combine team selection with filters
  const queryFilters = useMemo(() => ({
    ...filters,
    teamName: viewTeam,
    dateFrom: dateRange?.[0]?.startOf('day').format('YYYY-MM-DD HH:mm:ss'),
    dateTo: dateRange?.[1]?.endOf('day').format('YYYY-MM-DD HH:mm:ss'),
    status: statusFilter.join(',')
  }), [filters, viewTeam, dateRange, statusFilter])
  
  const { data: queueData, isLoading, refetch, isRefetching } = useQueueItems(queryFilters)
  const { data: dropdownData } = useDropdownData()
  const cancelQueueItemMutation = useCancelQueueItem()
  
  const isFetching = isLoading || isRefetching
  
  // Dynamic page sizes for tables with minimum size for small screens
  const activePageSize = useDynamicPageSize(activeTableRef, {
    containerOffset: 280, // Account for filters, stats cards, tabs
    minRows: 8, // Minimum for small screens
    maxRows: 50
  })
  
  const completedPageSize = useDynamicPageSize(completedTableRef, {
    containerOffset: 280,
    minRows: 8,
    maxRows: 50
  })
  
  const cancelledPageSize = useDynamicPageSize(cancelledTableRef, {
    containerOffset: 280,
    minRows: 8,
    maxRows: 50
  })
  
  const failedPageSize = useDynamicPageSize(failedTableRef, {
    containerOffset: 280,
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
          'COMPLETED': { color: 'success', icon: <CheckCircleOutlined /> },
          'FAILED': { color: 'error', icon: <ExclamationCircleOutlined /> },
          'CANCELLED': { color: 'error', icon: <CloseCircleOutlined /> },
          'UNKNOWN': { color: 'default', icon: <ExclamationCircleOutlined /> }
        }
        const config = statusConfig[healthStatus as keyof typeof statusConfig] || statusConfig.UNKNOWN
        
        // Show actual status alongside health status for active items
        const statusText = healthStatus === 'ACTIVE' && record.status ? 
          `${record.status} (${healthStatus})` : healthStatus
        
        return (
          <Tooltip title={record.minutesSinceHeartbeat ? `${record.minutesSinceHeartbeat} minutes since last heartbeat` : undefined}>
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
          <Tooltip title={record.lastFailureReason || 'No failures'}>
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
          <Button
            size="small"
            type="primary"
            icon={<HistoryOutlined />}
            onClick={() => handleViewTrace(record.taskId)}
          >
            Trace
          </Button>
          {record.canBeCancelled && record.healthStatus !== 'CANCELLED' && (
            <Button
              size="small"
              danger
              icon={<CloseCircleOutlined />}
              onClick={() => handleCancelQueueItem(record.taskId)}
              loading={cancelQueueItemMutation.isPending}
            >
              Cancel
            </Button>
          )}
        </Space>
      )
    }
  ]


  // Calculate container style for full height layout
  const containerStyle: React.CSSProperties = {
    height: 'calc(100vh - 64px - 48px)', // viewport - header - content margin
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden'
  }

  return (
    <div style={containerStyle}>
      <Row gutter={[16, 16]} align="middle" style={{ marginBottom: 16 }}>
        <Col>
          <Title level={2}>Queue Management</Title>
        </Col>
      </Row>

      <Card style={{ marginBottom: 16 }}>
        <Row gutter={[16, 16]} align="middle">
          <Col xs={24} sm={12} md={6}>
            <div style={{ marginBottom: 8 }}>
              <Text type="secondary">Team</Text>
            </div>
            <Select
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
            />
          </Col>

          {viewTeam && (
            <Col xs={24} sm={12} md={6}>
              <div style={{ marginBottom: 8 }}>
                <Text type="secondary">Machine</Text>
              </div>
              <Select
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
              />
            </Col>
          )}

          <Col xs={24} sm={12} md={6}>
            <div style={{ marginBottom: 8 }}>
              <Text type="secondary">Status</Text>
            </div>
            <Select
              mode="multiple"
              style={{ width: '100%' }}
              placeholder="All statuses"
              value={statusFilter}
              onChange={setStatusFilter}
              allowClear
            >
              <Select.Option value="PENDING">Pending</Select.Option>
              <Select.Option value="ACTIVE">Active</Select.Option>
              <Select.Option value="STALE">Stale</Select.Option>
              <Select.Option value="COMPLETED">Completed</Select.Option>
              <Select.Option value="FAILED">Failed</Select.Option>
              <Select.Option value="CANCELLED">Cancelled</Select.Option>
            </Select>
          </Col>

          <Col xs={24} sm={12} md={6}>
            <div style={{ marginBottom: 8 }}>
              <Text type="secondary">Date Range</Text>
            </div>
            <RangePicker
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
            />
          </Col>
        </Row>

        <Row gutter={[16, 16]} style={{ marginTop: 16 }} align="middle">
          <Col xs={24} sm={12} md={6}>
            <div style={{ marginBottom: 8 }}>
              <Text type="secondary">Options</Text>
            </div>
            <Space direction="vertical">
              <Checkbox
                checked={filters.includeCompleted}
                onChange={(e) => setFilters({ ...filters, includeCompleted: e.target.checked })}
              >
                Include Completed
              </Checkbox>
              <Checkbox
                checked={filters.includeCancelled}
                onChange={(e) => setFilters({ ...filters, includeCancelled: e.target.checked })}
              >
                Include Cancelled
              </Checkbox>
              <Checkbox
                checked={filters.onlyStale}
                onChange={(e) => setFilters({ ...filters, onlyStale: e.target.checked })}
              >
                Only Stale Items
              </Checkbox>
            </Space>
          </Col>

          <Col style={{ marginLeft: 'auto' }}>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={() => refetch()} loading={isFetching}>
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
                <Button icon={<ExportOutlined />}>
                  Export <DownOutlined />
                </Button>
              </Dropdown>
            </Space>
          </Col>
        </Row>
      </Card>

      {/* Queue Statistics */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col xs={24} sm={12} md={8} lg={4} xl={3}>
              <Card>
                <Statistic
                  title="Total"
                  value={(queueData?.statistics as any)?.totalCount || 0}
                  prefix={<ThunderboltOutlined />}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} md={8} lg={4} xl={3}>
              <Card>
                <Statistic
                  title="Pending"
                  value={(queueData?.statistics as any)?.pendingCount || 0}
                  valueStyle={{ color: '#8c8c8c' }}
                  prefix={<ClockCircleOutlined />}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} md={8} lg={4} xl={3}>
              <Card>
                <Statistic
                  title="Assigned"
                  value={(queueData?.statistics as any)?.assignedCount || 0}
                  valueStyle={{ color: '#1890ff' }}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} md={8} lg={4} xl={3}>
              <Card>
                <Statistic
                  title="Processing"
                  value={(queueData?.statistics as any)?.processingCount || 0}
                  valueStyle={{ color: '#1890ff' }}
                  prefix={<PlayCircleOutlined />}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} md={8} lg={4} xl={3}>
              <Card>
                <Statistic
                  title="Completed"
                  value={(queueData?.statistics as any)?.completedCount || 0}
                  valueStyle={{ color: '#52c41a' }}
                  prefix={<CheckCircleOutlined />}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} md={8} lg={4} xl={3}>
              <Card>
                <Statistic
                  title="Failed"
                  value={(queueData?.statistics as any)?.failedCount || 0}
                  valueStyle={{ color: '#ff4d4f' }}
                  prefix={<ExclamationCircleOutlined />}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} md={8} lg={4} xl={3}>
              <Card>
                <Statistic
                  title="Cancelled"
                  value={(queueData?.statistics as any)?.cancelledCount || 0}
                  valueStyle={{ color: '#ff4d4f' }}
                  prefix={<CloseCircleOutlined />}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} md={8} lg={4} xl={3}>
              <Card>
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
            defaultActiveKey="active"
            style={{ 
              flex: 1, 
              display: 'flex', 
              flexDirection: 'column',
              minHeight: 0,
              overflow: 'hidden'
            }}
            className="full-height-tabs"
          >
            <Tabs.TabPane 
              tab={
                <Space>
                  <span style={{ marginRight: 8 }}>Active Queue</span>
                  <Badge count={queueData?.items?.filter((item: any) => !['COMPLETED', 'CANCELLED'].includes(item.healthStatus)).length || 0} color="gold" />
                </Space>
              } 
              key="active"
            >
              <div ref={activeTableRef} style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
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
                    height: 'calc(100vh - 450px)', // Adjust based on header/filter/stats height
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
                <Space>
                  <span style={{ marginRight: 8 }}>Completed</span>
                  <Badge count={(queueData?.statistics as any)?.completedCount || 0} showZero color="#52c41a" />
                </Space>
              } 
              key="completed"
            >
              <div ref={completedTableRef} style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
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
                    height: 'calc(100vh - 450px)',
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
                <Space>
                  <span style={{ marginRight: 8 }}>Cancelled</span>
                  <Badge count={(queueData?.statistics as any)?.cancelledCount || 0} showZero color="#ff4d4f" />
                </Space>
              } 
              key="cancelled"
            >
              <div ref={cancelledTableRef} style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
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
                    height: 'calc(100vh - 450px)',
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
                <Space>
                  <span style={{ marginRight: 8 }}>Failed</span>
                  <Badge count={(queueData?.statistics as any)?.failedCount || 0} showZero color="#ff4d4f" />
                </Space>
              } 
              key="failed"
            >
              <div ref={failedTableRef} style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
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
                    height: 'calc(100vh - 450px)',
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