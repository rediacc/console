import React from 'react';
import {
  Alert,
  Button,
  Dropdown,
  Flex,
  Grid,
  List,
  Modal,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd';
import { useTranslation } from 'react-i18next';
import { useEntityAuditTraceWithEnabled } from '@/api/hooks-organization';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { MobileCard } from '@/components/common/MobileCard';
import { useMessage } from '@/hooks';
import { createDateSorter, createSorter, formatTimestampAsIs } from '@/platform';
import type { BaseModalProps } from '@/types';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  CopyOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  FileExcelOutlined,
  FileTextOutlined,
  HddOutlined,
  HistoryOutlined,
  InfoCircleOutlined,
  KeyOutlined,
  LockOutlined,
  PlusCircleOutlined,
  UserOutlined,
} from '@/utils/optimizedIcons';
import type { AuditTraceRecord } from '@rediacc/shared/types';

const { Text: AntText } = Typography;

export interface AuditTraceModalProps extends BaseModalProps {
  entityType: string | null;
  entityIdentifier: string | null;
  entityName?: string;
}

const AuditTraceModal: React.FC<AuditTraceModalProps> = ({
  open,
  onCancel,
  entityType,
  entityIdentifier,
  entityName,
}) => {
  const { t } = useTranslation(['resources', 'common']);
  const message = useMessage();
  const screens = Grid.useBreakpoint();
  const isMobile = !screens.sm;

  const { data, isLoading, error } = useEntityAuditTraceWithEnabled(
    entityType,
    entityIdentifier,
    open // Only fetch when modal is open
  );

  // Map icon hints to actual icons
  // Using grayscale with opacity variations for differentiation
  const getIcon = (iconHint: string) => {
    switch (iconHint) {
      case 'plus-circle':
        return <PlusCircleOutlined />;
      case 'edit':
        return <EditOutlined />;
      case 'trash':
        return <DeleteOutlined />;
      case 'lock':
        return <LockOutlined />;
      case 'key':
        return <KeyOutlined />;
      case 'users':
        return <UserOutlined />;
      case 'check-circle':
        return <CheckCircleOutlined />;
      case 'x-circle':
        return <CloseCircleOutlined />;
      case 'database':
        return <DatabaseOutlined />;
      case 'hdd':
        return <HddOutlined />;
      case 'copy':
        return <CopyOutlined />;
      default:
        return <InfoCircleOutlined />;
    }
  };

  // Export functions
  const exportToCSV = () => {
    if (!data?.records || data.records.length === 0) return;

    // Create CSV header
    const headers = ['Action', 'Details', 'Performed By', 'Timestamp', 'Time Ago'];
    const csvContent = [
      headers.join(','),
      ...data.records.map((record) => {
        const row = [
          record.actionType,
          `"${(record.details ?? '').replaceAll('"', '""')}"`, // Escape quotes in details
          record.performedBy ?? 'System',
          formatTimestampAsIs(record.timestamp, 'datetime'),
          record.timeAgo,
        ];
        return row.join(',');
      }),
    ].join('\n');

    // Create and download file
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `audit-trace-${entityType}-${entityIdentifier}-${new Date().toISOString().split('T')[0]}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);

    message.success('resources:audit.exportSuccess', { format: 'CSV' });
  };

  const exportToJSON = () => {
    if (!data?.records || data.records.length === 0) return;

    const exportData = {
      entityType,
      entityIdentifier,
      entityName,
      exportDate: new Date().toISOString(),
      summary: data.summary,
      records: data.records.map((record) => ({
        actionType: record.actionType,
        details: record.details,
        performedBy: record.performedBy ?? 'System',
        timestamp: record.timestamp,
        timeAgo: record.timeAgo,
        iconHint: record.iconHint,
      })),
    };

    // Create and download file
    const jsonString = JSON.stringify(exportData, null, 2);
    const blob = new Blob([jsonString], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `audit-trace-${entityType}-${entityIdentifier}-${new Date().toISOString().split('T')[0]}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);

    message.success('resources:audit.exportSuccess', { format: 'JSON' });
  };

  const columns = [
    {
      title: t('audit.action'),
      key: 'action',
      width: 150,
      sorter: createSorter<AuditTraceRecord>('actionType'),
      render: (_: unknown, record: AuditTraceRecord, index: number) => (
        <Space data-testid={`audit-trace-action-${index}`}>
          {getIcon(record.iconHint ?? 'info')}
          <Tag data-testid={`audit-trace-action-tag-${index}`}>{record.actionType}</Tag>
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
        <Typography.Text data-testid={`audit-trace-performed-by-${index}`}>
          {user || t('audit.system')}
        </Typography.Text>
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
          <AntText>{formatTimestampAsIs(timestamp, 'datetime')}</AntText>
          <Typography.Text>{record.timeAgo}</Typography.Text>
        </Space>
      ),
    },
  ];

  return (
    <Modal
      title={
        <Space>
          <HistoryOutlined />
          {t('audit.title', { name: entityName ?? entityIdentifier })}
        </Space>
      }
      open={open}
      onCancel={onCancel}
      width={1024}
      footer={null}
      destroyOnHidden
      data-testid="audit-trace-modal"
      centered
    >
      {(() => {
        if (isLoading) {
          return (
            <LoadingWrapper
              loading
              centered
              minHeight={160}
              tip={t('common:general.loading')}
              showTextBelow
              data-testid="audit-trace-loading"
            >
              <Flex />
            </LoadingWrapper>
          );
        } else if (error) {
          return (
            <Alert
              message={t('audit.error')}
              description={error instanceof Error ? error.message : t('audit.errorLoading')}
              type="error"
              data-testid="audit-trace-error-alert"
            />
          );
        } else if (data) {
          return (
            <>
              {/* Summary Section */}
              <Flex vertical className="w-full" data-testid="audit-trace-summary">
                <Flex align="center" justify="space-between" wrap>
                  <Flex className="gap-md" wrap>
                    <Flex vertical data-testid="audit-trace-total-records">
                      <AntText type="secondary">{t('audit.totalRecords')}</AntText>
                      <Typography.Text strong>{data.summary.totalAuditRecords}</Typography.Text>
                    </Flex>
                    <Flex vertical data-testid="audit-trace-visible-records">
                      <AntText type="secondary">{t('audit.visibleRecords')}</AntText>
                      <Typography.Text strong>{data.summary.visibleAuditRecords}</Typography.Text>
                    </Flex>
                    {data.summary.lastActivity && (
                      <Flex vertical data-testid="audit-trace-last-activity">
                        <AntText type="secondary">{t('audit.lastActivity')}</AntText>
                        <AntText strong>
                          {new Date(data.summary.lastActivity).toLocaleString()}
                        </AntText>
                      </Flex>
                    )}
                  </Flex>

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
                </Flex>
              </Flex>

              {/* Records Table / List */}
              {isMobile ? (
                <List
                  dataSource={data.records}
                  data-testid="audit-trace-table"
                  pagination={{
                    pageSize: 10,
                    showSizeChanger: false,
                    showTotal: (total, range) =>
                      t('common:general.showingRecords', {
                        start: range[0],
                        end: range[1],
                        total,
                      }),
                  }}
                  renderItem={(record, index) => (
                    <List.Item key={`${record.timestamp}-${index}`}>
                      <MobileCard>
                        <Flex align="center" justify="space-between">
                          <Space data-testid={`audit-trace-action-${index}`}>
                            {getIcon(record.iconHint ?? 'info')}
                            <Tag data-testid={`audit-trace-action-tag-${index}`}>
                              {record.actionType}
                            </Tag>
                          </Space>
                          <Typography.Text type="secondary">{record.timeAgo}</Typography.Text>
                        </Flex>
                        {record.details && (
                          <Typography.Text type="secondary">{record.details}</Typography.Text>
                        )}
                        <Typography.Text
                          type="secondary"
                          data-testid={`audit-trace-performed-by-${index}`}
                        >
                          {t('audit.performedBy')}: {record.performedBy ?? t('audit.system')}
                        </Typography.Text>
                      </MobileCard>
                    </List.Item>
                  )}
                />
              ) : (
                <Table<AuditTraceRecord>
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
                        total,
                      }),
                  }}
                  scroll={{ x: 800 }}
                  data-testid="audit-trace-table"
                />
              )}

              {/* Alternative Timeline View (could be toggled) */}
              {/* {renderTimelineView()} */}
            </>
          );
        }
        return null;
      })()}
    </Modal>
  );
};

export default AuditTraceModal;
