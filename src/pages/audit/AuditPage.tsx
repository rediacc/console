import React, { useState, useRef } from 'react';
import { Card, Space, Typography, DatePicker, Select, Button, Table, Tag, Input, Row, Col, Empty, Dropdown, message } from 'antd';
import { 
  HistoryOutlined, 
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
import type { ColumnsType } from 'antd/es/table';
import { useDynamicPageSize } from '@/hooks/useDynamicPageSize';

const { Title, Text } = Typography;
const { RangePicker } = DatePicker;

const AuditPage = () => {
  const { t } = useTranslation('system');
  const tableRef = useRef<HTMLDivElement>(null);
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs | null, dayjs.Dayjs | null]>([
    dayjs().subtract(7, 'days'),
    dayjs()
  ]);
  const [entityFilter, setEntityFilter] = useState<string | undefined>();
  const [searchText, setSearchText] = useState('');
  
  const { data: auditLogs, isLoading, refetch } = useAuditLogs({
    startDate: dateRange[0]?.startOf('day').format('YYYY-MM-DD HH:mm:ss'),
    endDate: dateRange[1]?.endOf('day').format('YYYY-MM-DD HH:mm:ss'),
    entityFilter,
    maxRecords: 1000
  });

  const pageSize = useDynamicPageSize(tableRef, {
    containerOffset: 200, // Account for table header, pagination, and internal padding
    minRows: 10,
    maxRows: 100,
    rowHeight: 55
  });

  const getActionIcon = (action: string) => {
    const actionLower = action.toLowerCase();
    if (actionLower.includes('create')) return <CheckCircleOutlined style={{ color: '#52c41a' }} />;
    if (actionLower.includes('delete')) return <CloseCircleOutlined style={{ color: '#ff4d4f' }} />;
    if (actionLower.includes('update') || actionLower.includes('modify')) return <EditOutlined style={{ color: '#faad14' }} />;
    if (actionLower.includes('login') || actionLower.includes('auth')) return <LoginOutlined style={{ color: '#1890ff' }} />;
    if (actionLower.includes('export') || actionLower.includes('import')) return <SwapOutlined style={{ color: '#556b2f' }} />;
    return <InfoCircleOutlined style={{ color: '#8c8c8c' }} />;
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
      title: 'Timestamp',
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 180,
      render: (timestamp: string) => dayjs(timestamp).format('YYYY-MM-DD HH:mm:ss'),
      sorter: (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
      defaultSortOrder: 'descend'
    },
    {
      title: 'Action',
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
      onFilter: (value, record) => record.action === value
    },
    {
      title: 'Entity Type',
      dataIndex: 'entity',
      key: 'entity',
      width: 120,
      render: (entity: string) => <Tag>{entity}</Tag>,
      filters: [...new Set(auditLogs?.map(log => log.entity) || [])].map(entity => ({
        text: entity,
        value: entity
      })),
      onFilter: (value, record) => record.entity === value
    },
    {
      title: 'Entity Name',
      dataIndex: 'entityName',
      key: 'entityName',
      width: 200,
      ellipsis: true
    },
    {
      title: 'User',
      dataIndex: 'actionByUser',
      key: 'user',
      width: 180,
      filters: [...new Set(auditLogs?.map(log => log.actionByUser) || [])].map(user => ({
        text: user,
        value: user
      })),
      onFilter: (value, record) => record.actionByUser === value
    },
    {
      title: 'Details',
      dataIndex: 'details',
      key: 'details',
      ellipsis: true,
      render: (details: string) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {details}
        </Text>
      )
    }
  ];

  const entityTypes = [...new Set(auditLogs?.map(log => log.entity) || [])];

  const exportToCSV = () => {
    if (!filteredLogs || filteredLogs.length === 0) {
      return;
    }

    const headers = ['Timestamp', 'Action', 'Entity Type', 'Entity Name', 'User', 'Details'];
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
    message.success(`Exported ${filteredLogs.length} audit logs to CSV`);
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
    message.success(`Exported ${filteredLogs.length} audit logs to JSON`);
  };

  const exportMenuItems = [
    {
      key: 'csv',
      label: <span data-testid="audit-export-csv">Export as CSV</span>,
      icon: <FileExcelOutlined />,
      onClick: exportToCSV
    },
    {
      key: 'json',
      label: <span data-testid="audit-export-json">Export as JSON</span>,
      icon: <FileTextOutlined />,
      onClick: exportToJSON
    }
  ];

  // Calculate container height similar to ResourcesPage
  const containerStyle: React.CSSProperties = {
    height: 'calc(100vh - 64px - 48px)', // viewport - header - content margin
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column'
  };

  const cardStyle: React.CSSProperties = {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden'
  };

  const cardBodyStyle: React.CSSProperties = {
    flex: 1,
    overflow: 'hidden',
    padding: '16px',
    display: 'flex',
    flexDirection: 'column'
  };

  return (
    <div style={containerStyle}>
      {/* Header */}
      <div style={{ marginBottom: 16, flexShrink: 0 }}>
        <Title level={2} style={{ marginBottom: 8 }}>
          <HistoryOutlined style={{ marginRight: 8 }} />
          Audit Logs
        </Title>
        <Text type="secondary">Track all activities and changes in your organization</Text>
      </div>

      {/* Filters */}
      <Card data-testid="audit-filter-card" style={{ marginBottom: 16, flexShrink: 0 }}>
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Row gutter={[16, 16]}>
            <Col xs={24} sm={24} md={8}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Text type="secondary">Date Range</Text>
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
                    { label: 'Today', value: [dayjs().startOf('day'), dayjs().endOf('day')] },
                    { label: 'Yesterday', value: [dayjs().subtract(1, 'day').startOf('day'), dayjs().subtract(1, 'day').endOf('day')] },
                    { label: 'Last 7 Days', value: [dayjs().subtract(7, 'day').startOf('day'), dayjs().endOf('day')] },
                    { label: 'Last 30 Days', value: [dayjs().subtract(30, 'day').startOf('day'), dayjs().endOf('day')] },
                    { label: 'This Month', value: [dayjs().startOf('month'), dayjs().endOf('month')] },
                    { label: 'Last Month', value: [dayjs().subtract(1, 'month').startOf('month'), dayjs().subtract(1, 'month').endOf('month')] },
                  ]}
                />
              </Space>
            </Col>
            <Col xs={24} sm={12} md={6}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Text type="secondary">Entity Type</Text>
                <Select
                  data-testid="audit-filter-entity"
                  placeholder="All entities"
                  allowClear
                  value={entityFilter}
                  onChange={setEntityFilter}
                  style={{ width: '100%' }}
                  options={[
                    { label: 'All Entities', value: undefined },
                    ...entityTypes.map(entity => ({ label: entity, value: entity }))
                  ]}
                />
              </Space>
            </Col>
            <Col xs={24} sm={12} md={6}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Text type="secondary">Search</Text>
                <Input
                  data-testid="audit-filter-search"
                  placeholder="Search in logs..."
                  prefix={<SearchOutlined />}
                  value={searchText}
                  onChange={(e) => setSearchText(e.target.value)}
                  allowClear
                  autoComplete="off"
                />
              </Space>
            </Col>
            <Col xs={24} sm={12} md={2}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Text type="secondary">&nbsp;</Text>
                <Button
                  data-testid="audit-refresh-button"
                  icon={<ReloadOutlined />}
                  onClick={() => refetch()}
                  loading={isLoading}
                  style={{ width: '100%' }}
                >
                  Refresh
                </Button>
              </Space>
            </Col>
            <Col xs={24} sm={12} md={2}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Text type="secondary">&nbsp;</Text>
                <Dropdown
                  menu={{ items: exportMenuItems }}
                  disabled={!filteredLogs || filteredLogs.length === 0}
                >
                  <Button 
                    data-testid="audit-export-button"
                    icon={<DownloadOutlined />} 
                    style={{ width: '100%' }}
                  >
                    Export
                  </Button>
                </Dropdown>
              </Space>
            </Col>
          </Row>
        </Space>
      </Card>

      {/* Audit Logs Table */}
      <Card data-testid="audit-table-card" style={cardStyle} bodyStyle={cardBodyStyle}>
        <div ref={tableRef} style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <Table
            data-testid="audit-table"
            columns={columns}
            dataSource={filteredLogs}
            loading={isLoading}
            rowKey={(record) => `${record.timestamp}-${record.action}-${record.entityName}`}
            pagination={{
              total: filteredLogs?.length || 0,
              pageSize: pageSize,
              showSizeChanger: false,
              showTotal: (total, range) => `Showing ${range[0]}-${range[1]} of ${total} logs`,
              position: ['bottomRight'],
              className: 'audit-table-pagination'
            }}
            scroll={{ x: 1000 }}
            className="full-height-table"
            style={{ flex: 1 }}
            sticky
            locale={{
              emptyText: <Empty description="No audit logs found" />
            }}
          />
        </div>
      </Card>
    </div>
  );
};

export default AuditPage;