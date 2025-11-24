import React from 'react'
import { Table, Tag, Typography, Space, Alert, Button, Dropdown, message } from 'antd'
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
  DownloadOutlined,
  FileTextOutlined,
  FileExcelOutlined,
  DatabaseOutlined,
  HddOutlined,
  CopyOutlined
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useEntityAuditTrace, AuditTraceRecord } from '@/api/queries/audit'
import { formatTimestampAsIs } from '@/core'
import { useComponentStyles } from '@/hooks/useComponentStyles'
import { DESIGN_TOKENS } from '@/utils/styleConstants'
import {
  StyledModal,
  LoadingContainer,
  LoadingText,
  SummaryContainer,
  SummaryRow,
  SummaryStats,
  StatItem,
  StatValue,
  IconWrapper
} from './styles'
import { createSorter, createDateSorter } from '@/core'
import LoadingWrapper from '@/components/common/LoadingWrapper'

const { Text } = Typography

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
  const styles = useComponentStyles()
  
  const { data, isLoading, error } = useEntityAuditTrace(
    entityType,
    entityIdentifier,
    open // Only fetch when modal is open
  )

  // Map icon hints to actual icons
  // Using grayscale with opacity variations for differentiation
  const getIcon = (iconHint: string) => {
    // Use CSS variables for theme-aware colors
    const errorColor = 'var(--color-error)'
    const defaultColor = 'var(--color-text-secondary)'

    switch (iconHint) {
      case 'plus-circle':
        return <IconWrapper $color={defaultColor}><PlusCircleOutlined /></IconWrapper>
      case 'edit':
        return <IconWrapper $color={defaultColor}><EditOutlined /></IconWrapper>
      case 'trash':
        return <IconWrapper $color={errorColor}><DeleteOutlined /></IconWrapper>
      case 'lock':
        return <IconWrapper $color={defaultColor}><LockOutlined /></IconWrapper>
      case 'key':
        return <IconWrapper $color={defaultColor}><KeyOutlined /></IconWrapper>
      case 'users':
        return <IconWrapper $color={defaultColor}><UserOutlined /></IconWrapper>
      case 'check-circle':
        return <IconWrapper $color={defaultColor}><CheckCircleOutlined /></IconWrapper>
      case 'x-circle':
        return <IconWrapper $color={errorColor}><CloseCircleOutlined /></IconWrapper>
      case 'database':
        return <IconWrapper $color={defaultColor}><DatabaseOutlined /></IconWrapper>
      case 'hdd':
        return <IconWrapper $color={defaultColor}><HddOutlined /></IconWrapper>
      case 'copy':
        return <IconWrapper $color={defaultColor}><CopyOutlined /></IconWrapper>
      default:
        return <IconWrapper $color={defaultColor}><InfoCircleOutlined /></IconWrapper>
    }
  }

  // Get action color based on type
  // Using grayscale system - only 'error' for actual delete/cancel actions
  const getActionColor = (actionType: string) => {
    switch (actionType) {
      case 'Deleted':
      case 'Cancelled':
        return 'error'  // Red for destructive actions only
      default:
        return 'default'  // Grayscale for all other actions
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
          formatTimestampAsIs(record.timestamp, 'datetime'),
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
      sorter: createSorter<AuditTraceRecord>('actionType'),
      render: (_: unknown, record: AuditTraceRecord, index: number) => (
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
      sorter: createSorter<AuditTraceRecord>('details'),
    },
    {
      title: t('audit.performedBy'),
      dataIndex: 'performedBy',
      key: 'performedBy',
      width: 200,
      sorter: createSorter<AuditTraceRecord>('performedBy'),
      render: (user: string, _record: AuditTraceRecord, index: number) => (
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
      sorter: createDateSorter<AuditTraceRecord>('timestamp'),
      render: (timestamp: string, record: AuditTraceRecord, index: number) => (
        <Space direction="vertical" size={0} data-testid={`audit-trace-timestamp-${index}`}>
          <Text>{formatTimestampAsIs(timestamp, 'datetime')}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {record.timeAgo}
          </Text>
        </Space>
      ),
    },
  ]

  // Alternative timeline view (commented out for now, may be used in future)
  // const renderTimelineView = () => {
  //   if (!data?.records || data.records.length === 0) {
  //     return <Empty description={t('audit.noRecords')} data-testid="audit-trace-empty-state" />
  //   }
  //
  //   return (
  //     <Timeline mode="left" data-testid="audit-trace-timeline">
  //       {data.records.map((record, index) => (
  //         <Timeline.Item
  //           key={index}
  //           dot={getIcon(record.iconHint)}
  //           color={getActionColor(record.actionType)}
  //           data-testid={`audit-trace-timeline-item-${index}`}
  //         >
  //           <Space direction="vertical" size={0}>
  //             <Space>
  //               <Text strong>{record.actionType}</Text>
  //               <Text type="secondary">{record.timeAgo}</Text>
  //             </Space>
  //             <Paragraph style={{ margin: 0 }}>{record.details}</Paragraph>
  //             <Text type="secondary" style={{ fontSize: 12 }}>
  //               {t('audit.by')} {record.performedBy || t('audit.system')}
  //             </Text>
  //           </Space>
  //         </Timeline.Item>
  //       ))}
  //     </Timeline>
  //   )
  // }

  return (
    <StyledModal
      title={
        <Space>
          <HistoryOutlined />
          {t('audit.title', { name: entityName || entityIdentifier })}
        </Space>
      }
      open={open}
      onCancel={onCancel}
      width={DESIGN_TOKENS.DIMENSIONS.MODAL_WIDTH_XL}
      footer={null}
      destroyOnHidden
      data-testid="audit-trace-modal"
    >
      {isLoading ? (
        <LoadingContainer data-testid="audit-trace-loading">
          <LoadingWrapper loading centered minHeight={160}>
            <div />
          </LoadingWrapper>
          <LoadingText>
            {t('common:general.loading')}
          </LoadingText>
        </LoadingContainer>
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
            <SummaryContainer data-testid="audit-trace-summary">
              <SummaryRow>
                <SummaryStats>
                  <StatItem data-testid="audit-trace-total-records">
                    <Text type="secondary">{t('audit.totalRecords')}</Text>
                    <StatValue>{data.summary.totalAuditRecords}</StatValue>
                  </StatItem>
                  <StatItem data-testid="audit-trace-visible-records">
                    <Text type="secondary">{t('audit.visibleRecords')}</Text>
                    <StatValue>{data.summary.visibleAuditRecords}</StatValue>
                  </StatItem>
                  {data.summary.lastActivity && (
                    <StatItem data-testid="audit-trace-last-activity">
                      <Text type="secondary">{t('audit.lastActivity')}</Text>
                      <Text strong>{new Date(data.summary.lastActivity).toLocaleDateString()}</Text>
                    </StatItem>
                  )}
                </SummaryStats>

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
                  <Button 
                    icon={<DownloadOutlined />} 
                    data-testid="audit-trace-export-button"
                    style={styles.buttonSecondary}
                  >
                    {t('audit.export')}
                  </Button>
                </Dropdown>
              </SummaryRow>
            </SummaryContainer>
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
        </>
      ) : null}
    </StyledModal>
  )
}

export default AuditTraceModal
