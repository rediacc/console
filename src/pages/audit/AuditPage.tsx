import { useState } from 'react';
import { Card, Space, Typography, DatePicker, Select, Button, Table, Tag, Input, Row, Col, Empty, Dropdown, message, Alert, Tooltip, theme } from 'antd';
import {
  FilterOutlined,
  ReloadOutlined,
  SearchOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  EditOutlined,
  LoginOutlined,
  SwapOutlined,
  InfoCircleOutlined,
  DownloadOutlined,
  FileExcelOutlined,
  FileTextOutlined
} from '@/utils/optimizedIcons';
import { useAuditLogs, AuditLog } from '../../api/queries/audit';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import { useComponentStyles } from '@/hooks/useComponentStyles';
import type { ColumnsType } from 'antd/es/table';

const { Text } = Typography;
const { RangePicker } = DatePicker;

const AuditPage = () => {
  const { t } = useTranslation(['system', 'common']);
  const { token } = theme.useToken();
  const styles = useComponentStyles();
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs | null, dayjs.Dayjs | null]>([
    dayjs().subtract(7, 'days'),
    dayjs()
  ]);
  const [entityFilter, setEntityFilter] = useState<string | undefined>();
  const [searchText, setSearchText] = useState('');
  const [pageSize, setPageSize] = useState(25);
  const [currentPage, setCurrentPage] = useState(1);

  // Ensure dates are always defined before passing to the hook
  // Use ISO 8601 format (with 'T' separator) for proper JSON datetime parsing
  const startDate = dateRange[0]?.startOf('day').format('YYYY-MM-DDTHH:mm:ss');
  const endDate = dateRange[1]?.endOf('day').format('YYYY-MM-DDTHH:mm:ss');

  const { data: auditLogs, isLoading, refetch, error, isError } = useAuditLogs({
    startDate,
    endDate,
    entityFilter,
    maxRecords: 1000
  });

  const getActionIcon = (action: string) => {
    const actionLower = action.toLowerCase();
    if (actionLower.includes('create')) return <CheckCircleOutlined style={{ color: token.colorSuccess }} />;
    if (actionLower.includes('delete')) return <CloseCircleOutlined style={{ color: token.colorError }} />;
    if (actionLower.includes('update') || actionLower.includes('modify')) return <EditOutlined style={{ color: token.colorWarning }} />;
    if (actionLower.includes('login') || actionLower.includes('auth')) return <LoginOutlined style={{ color: token.colorPrimary }} />;
    if (actionLower.includes('export') || actionLower.includes('import')) return <SwapOutlined style={{ color: token.colorInfo }} />;
    return <InfoCircleOutlined style={{ color: token.colorTextSecondary }} />;
  };

  const getActionColor = (action: string) => {
    const actionLower = action.toLowerCase();
    if (actionLower.includes('create')) return 'success';
    if (actionLower.includes('delete')) return 'error';
    if (actionLower.includes('update') || actionLower.includes('modify')) return 'warning';
    if (actionLower.includes('login') || actionLower.includes('auth')) return 'processing';
    return 'default';
  };

  const filteredLogs = auditLogs?.filter(log => {
    if (!searchText) return true;
    const search = searchText.toLowerCase();
    return (
      log.entityName?.toLowerCase().includes(search) ||
      log.action?.toLowerCase().includes(search) ||
      log.details?.toLowerCase().includes(search) ||
      log.actionByUser?.toLowerCase().includes(search)
    );
  });

  const columns: ColumnsType<AuditLog> = [
    {
      title: t('system:audit.columns.timestamp'),
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 180,
      render: (timestamp: string) => dayjs(timestamp).format('YYYY-MM-DD HH:mm:ss'),
      sorter: (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
      defaultSortOrder: 'descend'
    },
    {
      title: (
        <Space>
          {t('system:audit.columns.action')}
          <FilterOutlined style={{ opacity: 0.6, fontSize: '12px' }} />
        </Space>
      ),
      dataIndex: 'action',
      key: 'action',
      width: 200,
      render: (action: string) => (
        <Space>
          {getActionIcon(action)}
          <Tag color={getActionColor(action)}>
            {action.replace(/_/g, ' ')}
          </Tag>
        </Space>
      ),
      filters: [...new Set(auditLogs?.map(log => log.action) || [])].map(action => ({
        text: action.replace(/_/g, ' '),
        value: action
      })),
      onFilter: (value, record) => record.action === value,
      filterIcon: (filtered: boolean) => (
        <FilterOutlined style={{ color: filtered ? '#1890ff' : undefined, fontSize: '14px' }} />
      )
    },
    {
      title: (
        <Space>
          {t('system:audit.columns.entityType')}
          <FilterOutlined style={{ opacity: 0.6, fontSize: '12px' }} />
        </Space>
      ),
      dataIndex: 'entity',
      key: 'entity',
      width: 120,
      render: (entity: string) => <Tag>{entity}</Tag>,
      filters: [...new Set(auditLogs?.map(log => log.entity) || [])].map(entity => ({
        text: entity,
        value: entity
      })),
      onFilter: (value, record) => record.entity === value,
      filterIcon: (filtered: boolean) => (
        <FilterOutlined style={{ color: filtered ? '#1890ff' : undefined, fontSize: '14px' }} />
      )
    },
    {
      title: t('system:audit.columns.entityName'),
      dataIndex: 'entityName',
      key: 'entityName',
      width: 200,
      ellipsis: {
        showTitle: false
      },
      render: (entityName: string) => (
        <Tooltip title={entityName} placement="topLeft">
          <span>{entityName}</span>
        </Tooltip>
      )
    },
    {
      title: (
        <Space>
          {t('system:audit.columns.user')}
          <FilterOutlined style={{ opacity: 0.6, fontSize: '12px' }} />
        </Space>
      ),
      dataIndex: 'actionByUser',
      key: 'user',
      width: 180,
      filters: [...new Set(auditLogs?.map(log => log.actionByUser) || [])].map(user => ({
        text: user,
        value: user
      })),
      onFilter: (value, record) => record.actionByUser === value,
      filterIcon: (filtered: boolean) => (
        <FilterOutlined style={{ color: filtered ? '#1890ff' : undefined, fontSize: '14px' }} />
      )
    },
    {
      title: t('system:audit.columns.details'),
      dataIndex: 'details',
      key: 'details',
      ellipsis: {
        showTitle: false
      },
      render: (details: string) => (
        <Tooltip title={details} placement="topLeft">
          <Text type="secondary" style={{ fontSize: 12 }}>
            {details}
          </Text>
        </Tooltip>
      )
    }
  ];

  const entityTypes = [...new Set(auditLogs?.map(log => log.entity) || [])];

  const exportToCSV = () => {
    if (!filteredLogs || filteredLogs.length === 0) {
      return;
    }

    const headers = [
      t('system:audit.columns.timestamp'),
      t('system:audit.columns.action'),
      t('system:audit.columns.entityType'),
      t('system:audit.columns.entityName'),
      t('system:audit.columns.user'),
      t('system:audit.columns.details')
    ];
    const rows = filteredLogs.map(log => [
      dayjs(log.timestamp).format('YYYY-MM-DD HH:mm:ss'),
      log.action.replace(/_/g, ' '),
      log.entity,
      log.entityName || '',
      log.actionByUser,
      log.details || ''
    ]);

    const csvContent = [
      headers.join(','),
      ...rows.map(row => row.map(cell => `"${cell}"`).join(','))
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', `audit_logs_${dayjs().format('YYYY-MM-DD_HHmmss')}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    message.success(t('system:audit.export.successCSV', { count: filteredLogs.length }));
  };

  const exportToJSON = () => {
    if (!filteredLogs || filteredLogs.length === 0) {
      return;
    }

    const exportData = {
      exportDate: dayjs().format('YYYY-MM-DD HH:mm:ss'),
      dateRange: {
        from: dateRange[0]?.format('YYYY-MM-DD HH:mm:ss'),
        to: dateRange[1]?.format('YYYY-MM-DD HH:mm:ss')
      },
      filters: {
        entityType: entityFilter || 'All',
        searchText: searchText || 'None'
      },
      totalRecords: filteredLogs.length,
      logs: filteredLogs
    };

    const jsonContent = JSON.stringify(exportData, null, 2);
    const blob = new Blob([jsonContent], { type: 'application/json' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', `audit_logs_${dayjs().format('YYYY-MM-DD_HHmmss')}.json`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    message.success(t('system:audit.export.successJSON', { count: filteredLogs.length }));
  };

  const exportMenuItems = [
    {
      key: 'csv',
      label: <span data-testid="audit-export-csv">{t('common:exportCSV')}</span>,
      icon: <FileExcelOutlined />,
      onClick: exportToCSV
    },
    {
      key: 'json',
      label: <span data-testid="audit-export-json">{t('common:exportJSON')}</span>,
      icon: <FileTextOutlined />,
      onClick: exportToJSON
    }
  ];

  return (
    <div style={{ padding: 24 }}>
      {/* Filters */}
      <Card data-testid="audit-filter-card" style={{ marginBottom: 16 }}>
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Row gutter={[24, 16]}>
            <Col xs={24} sm={24} md={8}>
              <Space direction="vertical" size="small" style={{ width: '100%' }}>
                <Text strong style={{ fontSize: '14px', color: token.colorText }}>{t('system:audit.filters.dateRange')}</Text>
                <RangePicker
                  data-testid="audit-filter-date"
                  value={dateRange}
                  onChange={(dates) => setDateRange(dates as [dayjs.Dayjs | null, dayjs.Dayjs | null])}
                  style={{ width: '100%' }}
                  allowClear={false}
                  showTime={{
                    format: 'HH:mm:ss',
                    defaultValue: [dayjs('00:00:00', 'HH:mm:ss'), dayjs('23:59:59', 'HH:mm:ss')]
                  }}
                  format="YYYY-MM-DD HH:mm:ss"
                  presets={[
                    { label: t('common:today'), value: [dayjs().startOf('day'), dayjs().endOf('day')] },
                    { label: t('common:yesterday'), value: [dayjs().subtract(1, 'day').startOf('day'), dayjs().subtract(1, 'day').endOf('day')] },
                    { label: t('common:last7Days'), value: [dayjs().subtract(7, 'day').startOf('day'), dayjs().endOf('day')] },
                    { label: t('common:last30Days'), value: [dayjs().subtract(30, 'day').startOf('day'), dayjs().endOf('day')] },
                    { label: t('common:thisMonth'), value: [dayjs().startOf('month'), dayjs().endOf('month')] },
                    { label: t('common:lastMonth'), value: [dayjs().subtract(1, 'month').startOf('month'), dayjs().subtract(1, 'month').endOf('month')] },
                  ]}
                />
              </Space>
            </Col>
            <Col xs={24} sm={12} md={6}>
              <Space direction="vertical" size="small" style={{ width: '100%' }}>
                <Text strong style={{ fontSize: '14px', color: token.colorText }}>{t('system:audit.filters.entityType')}</Text>
                <Select
                  data-testid="audit-filter-entity"
                  placeholder={t('system:audit.filters.allEntities')}
                  allowClear
                  value={entityFilter}
                  onChange={setEntityFilter}
                  style={{ width: '100%' }}
                  options={[
                    { label: t('system:audit.filters.allEntities'), value: undefined },
                    ...entityTypes.map(entity => ({ label: entity, value: entity }))
                  ]}
                />
              </Space>
            </Col>
            <Col xs={24} sm={12} md={6}>
              <Space direction="vertical" size="small" style={{ width: '100%' }}>
                <Text strong style={{ fontSize: '14px', color: token.colorText }}>{t('system:audit.filters.search')}</Text>
                <Input
                  data-testid="audit-filter-search"
                  placeholder={t('system:audit.filters.searchPlaceholder')}
                  prefix={<SearchOutlined />}
                  value={searchText}
                  onChange={(e) => setSearchText(e.target.value)}
                  allowClear
                  autoComplete="off"
                />
              </Space>
            </Col>
            <Col xs={24} sm={12} md={2}>
              <Space direction="vertical" size="small" style={{ width: '100%' }}>
                <Text strong style={{ fontSize: '14px', color: 'transparent' }}>{t('system:audit.filters.actions')}</Text>
                <Button
                  data-testid="audit-refresh-button"
                  icon={<ReloadOutlined />}
                  onClick={() => refetch()}
                  loading={isLoading}
                  style={{ ...styles.touchTarget, width: '100%' }}
                >
                  {t('common:actions.refresh')}
                </Button>
              </Space>
            </Col>
            <Col xs={24} sm={12} md={2}>
              <Space direction="vertical" size="small" style={{ width: '100%' }}>
                <Text strong style={{ fontSize: '14px', color: 'transparent' }}>{t('system:audit.filters.export')}</Text>
                <Tooltip 
                  title={
                    !filteredLogs || filteredLogs.length === 0 
                      ? t('system:audit.export.noData')
                      : t('system:audit.export.tooltip')
                  }
                >
                  <Dropdown
                    menu={{ items: exportMenuItems }}
                    disabled={!filteredLogs || filteredLogs.length === 0}
                  >
                    <Button 
                      data-testid="audit-export-button"
                      icon={<DownloadOutlined />} 
                      style={{ ...styles.touchTarget, width: '100%' }}
                    >
                      {t('common:actions.export')}
                    </Button>
                  </Dropdown>
                </Tooltip>
              </Space>
            </Col>
          </Row>
        </Space>
      </Card>

      {/* Error Display */}
      {isError && (
        <Alert
          message={t('system:audit.errors.loadTitle')}
          description={error?.message || t('system:audit.errors.loadDescription')}
          type="error"
          closable
          showIcon
          style={{ marginBottom: 16 }}
          action={
            <Button
              size="small"
              style={styles.touchTargetSmall}
              onClick={() => refetch()}
              loading={isLoading}
            >
              {t('system:audit.errors.tryAgain')}
            </Button>
          }
        />
      )}

      {/* Audit Logs Table */}
      <Card data-testid="audit-table-card">
        <Table
          data-testid="audit-table"
          columns={columns}
          dataSource={filteredLogs}
          loading={isLoading}
          rowKey={(record) => `${record.timestamp}-${record.action}-${record.entityName}`}
          pagination={{
            current: currentPage,
            pageSize: pageSize,
            total: filteredLogs?.length || 0,
            showSizeChanger: true,
            pageSizeOptions: ['10', '25', '50', '100'],
            showTotal: (total, range) => t('system:audit.pagination.showing', { start: range[0], end: range[1], total }),
            onChange: (page, size) => {
              setCurrentPage(page);
              if (size !== pageSize) {
                setPageSize(size);
                setCurrentPage(1); // Reset to first page when page size changes
              }
            },
            position: ['bottomRight'],
            className: 'audit-table-pagination'
          }}
          scroll={{ x: 'max-content' }}
          locale={{
            emptyText: (
              <Empty
                description={
                  <Space direction="vertical" align="center">
                    <Text type="secondary">
                      {isError
                        ? t('system:audit.errors.unableToLoad')
                        : (filteredLogs?.length === 0 && auditLogs && auditLogs.length > 0)
                          ? t('system:audit.empty.noMatchingFilters')
                          : t('system:audit.empty.noLogsInRange')
                      }
                    </Text>
                    {!isError && (
                      <Button
                        type="link"
                        style={styles.touchTarget}
                        onClick={() => {
                          setSearchText('');
                          setEntityFilter(undefined);
                          setDateRange([dayjs().subtract(30, 'days'), dayjs()]);
                        }}
                      >
                        {t('system:audit.empty.clearFilters')}
                      </Button>
                    )}
                  </Space>
                }
              />
            )
          }}
        />
      </Card>
    </div>
  );
};

export default AuditPage;