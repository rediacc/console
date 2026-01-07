import { useCallback, useMemo } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Dropdown,
  Flex,
  Input,
  Row,
  Select,
  Space,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import dayjs, { Dayjs } from 'dayjs';
import { useTranslation } from 'react-i18next';
import { useGetAuditLogs } from '@/api/api-hooks.generated';
import { buildAuditColumns } from '@/components/common/columns/builders/auditColumns';
import { MobileCard } from '@/components/common/MobileCard';
import ResourceListView from '@/components/common/ResourceListView';
import { useFilters, useMessage, usePagination } from '@/hooks';
import {
  buildCSVContent,
  downloadCSV,
  downloadJSON,
  findActionConfig,
  generateTimestampedFilename,
  getUniqueMappedValues,
  searchInFields,
} from '@/platform';
import {
  DownloadOutlined,
  FileExcelOutlined,
  FileTextOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@/utils/optimizedIcons';
import type { GetAuditLogs_ResultSet1 } from '@rediacc/shared/types';

interface AuditPageFilters extends Record<string, unknown> {
  dateRange: [Dayjs | null, Dayjs | null];
  entityFilter: string | undefined;
  searchText: string;
}

const { RangePicker } = DatePicker;

const AuditPage = () => {
  const { t } = useTranslation(['system', 'common']);
  const message = useMessage();

  // Filter state with useFilters hook
  const { filters, setFilter } = useFilters<AuditPageFilters>({
    dateRange: [dayjs().subtract(7, 'days'), dayjs()],
    entityFilter: undefined,
    searchText: '',
  });

  // Pagination with usePagination hook
  const { page: currentPage, pageSize, onPageChange } = usePagination({ defaultPageSize: 25 });

  // Ensure dates are always defined before passing to the hook
  // Use ISO 8601 format (with 'T' separator) for proper JSON datetime parsing
  const startDate = filters.dateRange[0]?.startOf('day').format('YYYY-MM-DDTHH:mm:ss');
  const endDate = filters.dateRange[1]?.endOf('day').format('YYYY-MM-DDTHH:mm:ss');

  const {
    data: auditLogs,
    isLoading,
    refetch,
    error,
    isError,
  } = useGetAuditLogs(startDate, endDate, filters.entityFilter, 1000);

  const getActionIcon = useCallback((action: string) => {
    const config = findActionConfig(action);
    const IconComponent = config.icon;

    return (
      <Typography.Text className="inline-flex">
        <IconComponent />
      </Typography.Text>
    );
  }, []);

  const filteredLogs = auditLogs?.filter((log) =>
    searchInFields(log, filters.searchText, ['entityName', 'action', 'details', 'actionByUser'])
  );

  const columns = useMemo(
    () =>
      buildAuditColumns({
        t,
        auditLogs,
        getActionIcon,
      }),
    [t, auditLogs, getActionIcon]
  );

  const mobileRender = useMemo(
    // eslint-disable-next-line react/display-name
    () => (record: GetAuditLogs_ResultSet1) => {
      const config = findActionConfig(record.action ?? '');
      const IconComponent = config.icon;

      const timestampDisplay = (
        <Typography.Text type="secondary" className="text-xs">
          {dayjs(record.timestamp).format('MM/DD HH:mm')}
        </Typography.Text>
      );

      return (
        <MobileCard actions={timestampDisplay}>
          <Space>
            <IconComponent />
            <Typography.Text strong>{(record.action ?? '').replace(/_/g, ' ')}</Typography.Text>
          </Space>
          <Flex wrap align="center">
            <Tag>{record.entity}</Tag>
            {record.entityName && (
              <Typography.Text className="truncate">{record.entityName}</Typography.Text>
            )}
          </Flex>
          <Typography.Text type="secondary" className="text-xs">
            {t('system:audit.columns.user')}: {record.actionByUser}
          </Typography.Text>
          {record.details && (
            <Typography.Text type="secondary" className="text-xs truncate">
              {record.details}
            </Typography.Text>
          )}
        </MobileCard>
      );
    },
    [t]
  );

  const entityTypes = getUniqueMappedValues(auditLogs ?? [], (log) => log.entity);

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
      t('system:audit.columns.details'),
    ];
    const rows = filteredLogs.map((log) => [
      dayjs(log.timestamp).format('YYYY-MM-DD HH:mm:ss'),
      (log.action ?? '').replace(/_/g, ' '),
      log.entity,
      log.entityName ?? '',
      log.actionByUser,
      log.details ?? '',
    ]);

    const csvContent = buildCSVContent(headers, rows);
    downloadCSV(csvContent, generateTimestampedFilename('audit_logs', 'csv').replace('.csv', ''));
    message.success('system:audit.export.successCSV', { count: filteredLogs.length });
  };

  const exportToJSON = () => {
    if (!filteredLogs || filteredLogs.length === 0) {
      return;
    }

    const exportData = {
      exportDate: dayjs().format('YYYY-MM-DD HH:mm:ss'),
      dateRange: {
        from: filters.dateRange[0]?.format('YYYY-MM-DD HH:mm:ss'),
        to: filters.dateRange[1]?.format('YYYY-MM-DD HH:mm:ss'),
      },
      filters: {
        entityType: filters.entityFilter ?? 'All',
        searchText: filters.searchText || 'None',
      },
      totalRecords: filteredLogs.length,
      logs: filteredLogs,
    };

    downloadJSON(
      exportData,
      generateTimestampedFilename('audit_logs', 'json').replace('.json', '')
    );
    message.success('system:audit.export.successJSON', { count: filteredLogs.length });
  };

  const exportMenuItems = [
    {
      key: 'csv',
      label: (
        <Typography.Text data-testid="audit-export-csv">{t('common:exportCSV')}</Typography.Text>
      ),
      icon: <FileExcelOutlined />,
      onClick: exportToCSV,
    },
    {
      key: 'json',
      label: (
        <Typography.Text data-testid="audit-export-json">{t('common:exportJSON')}</Typography.Text>
      ),
      icon: <FileTextOutlined />,
      onClick: exportToJSON,
    },
  ];

  return (
    <Flex vertical>
      <Flex vertical className="w-full">
        {/* Filters */}
        <Card data-testid="audit-filter-card">
          <Space direction="vertical" size="large">
            <Row gutter={[24, 16]}>
              <Col xs={24} sm={24} md={8}>
                <Flex vertical className="gap-sm w-full">
                  <Typography.Text>{t('system:audit.filters.dateRange')}</Typography.Text>
                  <RangePicker
                    data-testid="audit-filter-date"
                    value={filters.dateRange}
                    onChange={(dates) =>
                      setFilter('dateRange', dates as [Dayjs | null, Dayjs | null])
                    }
                    allowClear={false}
                    showTime={{
                      format: 'HH:mm:ss',
                      defaultValue: [dayjs('00:00:00', 'HH:mm:ss'), dayjs('23:59:59', 'HH:mm:ss')],
                    }}
                    format="YYYY-MM-DD HH:mm:ss"
                    presets={[
                      {
                        label: t('common:today'),
                        value: [dayjs().startOf('day'), dayjs().endOf('day')],
                      },
                      {
                        label: t('common:yesterday'),
                        value: [
                          dayjs().subtract(1, 'day').startOf('day'),
                          dayjs().subtract(1, 'day').endOf('day'),
                        ],
                      },
                      {
                        label: t('common:last7Days'),
                        value: [dayjs().subtract(7, 'day').startOf('day'), dayjs().endOf('day')],
                      },
                      {
                        label: t('common:last30Days'),
                        value: [dayjs().subtract(30, 'day').startOf('day'), dayjs().endOf('day')],
                      },
                      {
                        label: t('common:thisMonth'),
                        value: [dayjs().startOf('month'), dayjs().endOf('month')],
                      },
                      {
                        label: t('common:lastMonth'),
                        value: [
                          dayjs().subtract(1, 'month').startOf('month'),
                          dayjs().subtract(1, 'month').endOf('month'),
                        ],
                      },
                    ]}
                  />
                </Flex>
              </Col>
              <Col xs={24} sm={12} md={6}>
                <Flex vertical className="gap-sm w-full">
                  <Typography.Text>{t('system:audit.filters.entityType')}</Typography.Text>
                  <Select
                    data-testid="audit-filter-entity"
                    placeholder={t('system:audit.filters.allEntities')}
                    allowClear
                    value={filters.entityFilter}
                    onChange={(value) => setFilter('entityFilter', value)}
                    options={[
                      { label: t('system:audit.filters.allEntities'), value: undefined },
                      ...entityTypes.map((entity) => ({ label: entity, value: entity })),
                    ]}
                  />
                </Flex>
              </Col>
              <Col xs={24} sm={12} md={6}>
                <Flex vertical className="gap-sm w-full">
                  <Typography.Text>{t('system:audit.filters.search')}</Typography.Text>
                  <Input
                    data-testid="audit-filter-search"
                    placeholder={t('system:audit.filters.searchPlaceholder')}
                    prefix={<SearchOutlined />}
                    value={filters.searchText}
                    onChange={(e) => setFilter('searchText', e.target.value)}
                    allowClear
                    autoComplete="off"
                  />
                </Flex>
              </Col>
              <Col xs={24} sm={12} md={2}>
                <Flex vertical className="gap-sm w-full">
                  <Typography.Text>{t('system:audit.filters.actions')}</Typography.Text>
                  <Button
                    data-testid="audit-refresh-button"
                    icon={<ReloadOutlined />}
                    onClick={() => refetch()}
                    loading={isLoading}
                    // eslint-disable-next-line no-restricted-syntax
                    style={{
                      width: '100%',
                      minHeight: 48,
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    {t('common:actions.refresh')}
                  </Button>
                </Flex>
              </Col>
              <Col xs={24} sm={12} md={2}>
                <Flex vertical className="gap-sm w-full">
                  <Typography.Text>{t('system:audit.filters.export')}</Typography.Text>
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
                        // eslint-disable-next-line no-restricted-syntax
                        style={{
                          width: '100%',
                          minHeight: 48,
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                        }}
                      >
                        {t('common:actions.export')}
                      </Button>
                    </Dropdown>
                  </Tooltip>
                </Flex>
              </Col>
            </Row>
          </Space>
        </Card>

        {/* Error Display */}
        {isError && (
          <Alert
            message={t('system:audit.errors.loadTitle')}
            description={error.message || t('system:audit.errors.loadDescription')}
            type="error"
            closable
            action={
              <Button onClick={() => refetch()} loading={isLoading}>
                {t('system:audit.errors.tryAgain')}
              </Button>
            }
          />
        )}

        {/* Audit Logs Table */}
        <Card data-testid="audit-table-card">
          <ResourceListView<GetAuditLogs_ResultSet1>
            data-testid="audit-table"
            columns={columns}
            data={filteredLogs ?? []}
            loading={isLoading}
            rowKey={(record) => `${record.timestamp}-${record.action}-${record.entityName}`}
            mobileRender={mobileRender}
            emptyDescription={
              isError
                ? t('system:audit.errors.unableToLoad')
                : filteredLogs?.length === 0 && auditLogs && auditLogs.length > 0
                  ? t('system:audit.empty.noMatchingFilters')
                  : t('system:audit.empty.noLogsInRange')
            }
            pagination={{
              current: currentPage,
              pageSize,
              total: filteredLogs?.length ?? 0,
              showSizeChanger: true,
              pageSizeOptions: ['10', '25', '50', '100'],
              showTotal: (total, range) =>
                t('system:audit.pagination.showing', { start: range[0], end: range[1], total }),
              onChange: onPageChange,
              position: ['bottomRight'],
            }}
          />
        </Card>
      </Flex>
    </Flex>
  );
};

export default AuditPage;
