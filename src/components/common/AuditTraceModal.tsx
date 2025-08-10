import React from 'react'
import { Modal, Table, Tag, Timeline, Typography, Space, Alert, Spin, Empty, Button, Dropdown, message } from 'antd'
import { 
  PlusCircleOutlined, 
  EditOutlined, 
  DeleteOutlined, 
  LockOutlined, 
  KeyOutlined, 
  UserOutlined, 
  CheckCircleOutlined, 
  CloseCircleOutlined,
  InfoCircleOutlined,
  HistoryOutlined,
  ClockCircleOutlined,
  DownloadOutlined,
  FileTextOutlined,
  FileExcelOutlined,
  DatabaseOutlined,
  HddOutlined,
  CopyOutlined
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useEntityAuditTrace, AuditTraceRecord } from '@/api/queries/audit'

const { Title, Text, Paragraph } = Typography

interface AuditTraceModalProps {
  open: boolean
  onCancel: () => void
  entityType: string | null
  entityIdentifier: string | null
  entityName?: string
}

const AuditTraceModal: React.FC<AuditTraceModalProps> = ({
  open,
  onCancel,
  entityType,
  entityIdentifier,
  entityName
}) => {
  const { t } = useTranslation(['resources', 'common'])
  
  const { data, isLoading, error } = useEntityAuditTrace(
    entityType,
    entityIdentifier,
    open // Only fetch when modal is open
  )

  // Map icon hints to actual icons
  const getIcon = (iconHint: string) => {
    switch (iconHint) {
      case 'plus-circle':
        return <PlusCircleOutlined style={{ color: '#52c41a' }} />
      case 'edit':
        return <EditOutlined style={{ color: '#1890ff' }} />
      case 'trash':
        return <DeleteOutlined style={{ color: '#ff4d4f' }} />
      case 'lock':
        return <LockOutlined style={{ color: '#fa8c16' }} />
      case 'key':
        return <KeyOutlined style={{ color: '#722ed1' }} />
      case 'users':
        return <UserOutlined style={{ color: '#13c2c2' }} />
      case 'check-circle':
        return <CheckCircleOutlined style={{ color: '#52c41a' }} />
      case 'x-circle':
        return <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
      case 'database':
        return <DatabaseOutlined style={{ color: '#1890ff' }} />
      case 'hdd':
        return <HddOutlined style={{ color: '#fa8c16' }} />
      case 'copy':
        return <CopyOutlined style={{ color: '#722ed1' }} />
      default:
        return <InfoCircleOutlined style={{ color: '#1890ff' }} />
    }
  }

  // Get action color based on type
  const getActionColor = (actionType: string) => {
    switch (actionType) {
      case 'Created':
        return 'green'
      case 'Updated':
      case 'Renamed':
        return 'blue'
      case 'Deleted':
        return 'red'
      case 'Activated':
        return 'cyan'
      case 'Deactivated':
        return 'orange'
      case 'Security Update':
      case 'Security Setting':
        return 'gold'
      case 'Completed':
        return 'success'
      case 'Cancelled':
        return 'error'
      case 'Assigned to Cluster':
      case 'Assigned to Image':
      case 'Assigned to Clone':
        return 'blue'
      case 'Removed from Cluster':
      case 'Removed from Clone':
        return 'orange'
      case 'Reassigned Image':
        return 'purple'
      default:
        return 'default'
    }
  }

  // Export functions
  const exportToCSV = () => {
    if (!data?.records || data.records.length === 0) return

    // Create CSV header
    const headers = ['Action', 'Details', 'Performed By', 'Timestamp', 'Time Ago']
    const csvContent = [
      headers.join(','),
      ...data.records.map(record => {
        const row = [
          record.actionType,
          `"${record.details.replace(/"/g, '""')}"`, // Escape quotes in details
          record.performedBy || 'System',
          new Date(record.timestamp).toLocaleString(),
          record.timeAgo
        ]
        return row.join(',')
      })
    ].join('\n')

    // Create and download file
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `audit-trace-${entityType}-${entityIdentifier}-${new Date().toISOString().split('T')[0]}.csv`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    
    message.success(t('audit.exportSuccess', { format: 'CSV' }))
  }

  const exportToJSON = () => {
    if (!data?.records || data.records.length === 0) return

    const exportData = {
      entityType,
      entityIdentifier,
      entityName,
      exportDate: new Date().toISOString(),
      summary: data.summary,
      records: data.records.map(record => ({
        actionType: record.actionType,
        details: record.details,
        performedBy: record.performedBy || 'System',
        timestamp: record.timestamp,
        timeAgo: record.timeAgo,
        iconHint: record.iconHint
      }))
    }

    // Create and download file
    const jsonString = JSON.stringify(exportData, null, 2)
    const blob = new Blob([jsonString], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `audit-trace-${entityType}-${entityIdentifier}-${new Date().toISOString().split('T')[0]}.json`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    
    message.success(t('audit.exportSuccess', { format: 'JSON' }))
  }

  const columns = [
    {
      title: t('audit.action'),
      key: 'action',
      width: 150,
      render: (_: any, record: AuditTraceRecord, index: number) => (
        <Space data-testid={`audit-trace-action-${index}`}>
          {getIcon(record.iconHint)}
          <Tag color={getActionColor(record.actionType)} data-testid={`audit-trace-action-tag-${index}`}>
            {record.actionType}
          </Tag>
        </Space>
      ),
    },
    {
      title: t('audit.details'),
      dataIndex: 'details',
      key: 'details',
      ellipsis: true,
    },
    {
      title: t('audit.performedBy'),
      dataIndex: 'performedBy',
      key: 'performedBy',
      width: 200,
      render: (user: string, record: AuditTraceRecord, index: number) => (
        <span data-testid={`audit-trace-performed-by-${index}`}>
          {user || t('audit.system')}
        </span>
      ),
    },
    {
      title: t('audit.timestamp'),
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 200,
      render: (timestamp: string, record: AuditTraceRecord, index: number) => (
        <Space direction="vertical" size={0} data-testid={`audit-trace-timestamp-${index}`}>
          <Text>{new Date(timestamp).toLocaleString()}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {record.timeAgo}
          </Text>
        </Space>
      ),
    },
  ]

  const renderTimelineView = () => {
    if (!data?.records || data.records.length === 0) {
      return <Empty description={t('audit.noRecords')} data-testid="audit-trace-empty-state" />
    }

    return (
      <Timeline mode="left" data-testid="audit-trace-timeline">
        {data.records.map((record, index) => (
          <Timeline.Item 
            key={index}
            dot={getIcon(record.iconHint)}
            color={getActionColor(record.actionType)}
            data-testid={`audit-trace-timeline-item-${index}`}
          >
            <Space direction="vertical" size={0}>
              <Space>
                <Text strong>{record.actionType}</Text>
                <Text type="secondary">{record.timeAgo}</Text>
              </Space>
              <Paragraph style={{ margin: 0 }}>{record.details}</Paragraph>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {t('audit.by')} {record.performedBy || t('audit.system')}
              </Text>
            </Space>
          </Timeline.Item>
        ))}
      </Timeline>
    )
  }

  return (
    <Modal
      title={
        <Space>
          <HistoryOutlined />
          {t('audit.title', { name: entityName || entityIdentifier })}
        </Space>
      }
      open={open}
      onCancel={onCancel}
      width={900}
      footer={null}
      destroyOnHidden
      data-testid="audit-trace-modal"
    >
      {isLoading ? (
        <div style={{ textAlign: 'center', padding: '50px 0' }} data-testid="audit-trace-loading">
          <Spin size="large" tip={t('common:general.loading')} />
        </div>
      ) : error ? (
        <Alert
          message={t('audit.error')}
          description={error instanceof Error ? error.message : t('audit.errorLoading')}
          type="error"
          showIcon
          data-testid="audit-trace-error-alert"
        />
      ) : data ? (
        <>
          {/* Summary Section */}
          {data.summary && (
            <Space direction="vertical" size={16} style={{ width: '100%', marginBottom: 24 }} data-testid="audit-trace-summary">
              
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Space size={32}>
                  <Space direction="vertical" size={0} data-testid="audit-trace-total-records">
                    <Text type="secondary">{t('audit.totalRecords')}</Text>
                    <Text strong style={{ fontSize: 20 }}>{data.summary.totalAuditRecords}</Text>
                  </Space>
                  <Space direction="vertical" size={0} data-testid="audit-trace-visible-records">
                    <Text type="secondary">{t('audit.visibleRecords')}</Text>
                    <Text strong style={{ fontSize: 20 }}>{data.summary.visibleAuditRecords}</Text>
                  </Space>
                  {data.summary.lastActivity && (
                    <Space direction="vertical" size={0} data-testid="audit-trace-last-activity">
                      <Text type="secondary">{t('audit.lastActivity')}</Text>
                      <Text strong>{new Date(data.summary.lastActivity).toLocaleDateString()}</Text>
                    </Space>
                  )}
                </Space>

                {/* Export Button */}
                <Dropdown
                  menu={{
                    items: [
                      {
                        key: 'csv',
                        label: t('audit.exportCSV'),
                        icon: <FileExcelOutlined />,
                        onClick: exportToCSV,
                        'data-testid': 'audit-trace-export-csv',
                      },
                      {
                        key: 'json',
                        label: t('audit.exportJSON'),
                        icon: <FileTextOutlined />,
                        onClick: exportToJSON,
                        'data-testid': 'audit-trace-export-json',
                      },
                    ],
                  }}
                  placement="bottomRight"
                  data-testid="audit-trace-export-dropdown"
                >
                  <Button icon={<DownloadOutlined />} data-testid="audit-trace-export-button">
                    {t('audit.export')}
                  </Button>
                </Dropdown>
              </div>

              {data.summary.hasOlderRecords && (
                <Alert
                  message={t('audit.olderRecordsNotVisible')}
                  type="warning"
                  showIcon
                  data-testid="audit-trace-older-records-alert"
                />
              )}
            </Space>
          )}

          {/* Records Table */}
          <Table
            columns={columns}
            dataSource={data.records}
            rowKey={(record, index) => `${record.timestamp}-${index}`}
            pagination={{
              pageSize: 10,
              showSizeChanger: false,
              showTotal: (total, range) => 
                t('common:general.showingRecords', { 
                  start: range[0], 
                  end: range[1], 
                  total 
                }),
            }}
            scroll={{ x: 800 }}
            size="small"
            data-testid="audit-trace-table"
          />

          {/* Alternative Timeline View (could be toggled) */}
          {/* {renderTimelineView()} */}
          
          {/* Bottom retention info */}
          {data.summary && (
            <div style={{ marginTop: 24, textAlign: 'center' }} data-testid="audit-trace-retention-info">
              <Text type="secondary">
                {t('audit.retentionInfo', {
                  days: data.summary.auditRetentionDays,
                  tier: data.summary.subscriptionTier
                })}
              </Text>
            </div>
          )}
        </>
      ) : null}
    </Modal>
  )
}

export default AuditTraceModal