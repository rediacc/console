import { useCallback, useMemo } from 'react';
import {
  Space,
  DatePicker,
  Select,
  Table,
  Input,
  Row,
  Col,
  Empty,
  Dropdown,
  message,
  Alert,
  Tooltip,
} from 'antd';
import dayjs, { Dayjs } from 'dayjs';
import { useTranslation } from 'react-i18next';
import { useAuditLogs } from '@/api/queries/audit';
import { RediaccText, RediaccButton } from '@/components/ui';
import { useFilters, usePagination } from '@/hooks';
import {
  findActionConfig,
  getActionTagColor,
  searchInFields,
  getUniqueMappedValues,
  buildCSVContent,
  downloadCSV,
  downloadJSON,
  generateTimestampedFilename,
} from '@/platform';
import { PageCard } from '@/styles/primitives';
import {
  ReloadOutlined,
  SearchOutlined,
  DownloadOutlined,
  FileExcelOutlined,
  FileTextOutlined,
} from '@/utils/optimizedIcons';
import { buildAuditColumns } from './columns';
import {
  PageWrapper,
  ContentStack,
  FilterField,
  FilterLabel,
  PlaceholderLabel,
  ActionButtonFull,
  LinkButton,
  ActionIcon,
} from './styles';

const { RangePicker } = DatePicker;

const AuditPage = () => {
  const { t } = useTranslation(['system', 'common']);

  // Filter state with useFilters hook
  const { filters, setFilter, clearAllFilters } = useFilters<AuditPageFilters>({
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
  } = useAuditLogs({
    startDate,
    endDate,
    entityFilter: filters.entityFilter,
    maxRecords: 1000,
  });

  const getActionIcon = useCallback((action: string) => {
    const config = findActionConfig(action);
    const IconComponent = config.icon;

    return (
      <ActionIcon $color={config.color}>
        <IconComponent />
      </ActionIcon>
    );
  }, []);

  const getActionColor = useCallback((action: string) => {
    return getActionTagColor(action);
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
        getActionColor,
      }),
    [t, auditLogs, getActionIcon, getActionColor]
  );

  const entityTypes = getUniqueMappedValues(auditLogs || [], (log) => log.entity);

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
      log.action.replace(/_/g, ' '),
      log.entity,
      log.entityName || '',
      log.actionByUser,
      log.details || '',
    ]);

    const csvContent = buildCSVContent(headers, rows);
    downloadCSV(csvContent, generateTimestampedFilename('audit_logs', 'csv').replace('.csv', ''));
    message.success(t('system:audit.export.successCSV', { count: filteredLogs.length }));
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
        entityType: filters.entityFilter || 'All',
        searchText: filters.searchText || 'None',
      },
      totalRecords: filteredLogs.length,
      logs: filteredLogs,
    };

    downloadJSON(
      exportData,
      generateTimestampedFilename('audit_logs', 'json').replace('.json', '')
    );
    message.success(t('system:audit.export.successJSON', { count: filteredLogs.length }));
  };

  const exportMenuItems = [
    {
      key: 'csv',
      label: <span data-testid="audit-export-csv">{t('common:exportCSV')}</span>,
      icon: <FileExcelOutlined />,
      onClick: exportToCSV,
    },
    {
      key: 'json',
      label: <span data-testid="audit-export-json">{t('common:exportJSON')}</span>,
      icon: <FileTextOutlined />,
      onClick: exportToJSON,
    },
  ];

  return (
    <PageWrapper>
      <ContentStack>
        {/* Filters */}
        <PageCard data-testid="audit-filter-card">
          <Space direction="vertical" size="large">
            <Row gutter={[24, 16]}>
              <Col xs={24} sm={24} md={8}>
                <FilterField>
                  <FilterLabel>{t('system:audit.filters.dateRange')}</FilterLabel>
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
                </FilterField>
              </Col>
              <Col xs={24} sm={12} md={6}>
                <FilterField>
                  <FilterLabel>{t('system:audit.filters.entityType')}</FilterLabel>
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
                </FilterField>
              </Col>
              <Col xs={24} sm={12} md={6}>
                <FilterField>
                  <FilterLabel>{t('system:audit.filters.search')}</FilterLabel>
                  <Input
                    data-testid="audit-filter-search"
                    placeholder={t('system:audit.filters.searchPlaceholder')}
                    prefix={<SearchOutlined />}
                    value={filters.searchText}
                    onChange={(e) => setFilter('searchText', e.target.value)}
                    allowClear
                    autoComplete="off"
                  />
                </FilterField>
              </Col>
              <Col xs={24} sm={12} md={2}>
                <FilterField>
                  <PlaceholderLabel>{t('system:audit.filters.actions')}</PlaceholderLabel>
                  <ActionButtonFull
                    data-testid="audit-refresh-button"
                    icon={<ReloadOutlined />}
                    onClick={() => refetch()}
                    loading={isLoading}
                  >
                    {t('common:actions.refresh')}
                  </ActionButtonFull>
                </FilterField>
              </Col>
              <Col xs={24} sm={12} md={2}>
                <FilterField>
                  <PlaceholderLabel>{t('system:audit.filters.export')}</PlaceholderLabel>
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
                      <ActionButtonFull
                        data-testid="audit-export-button"
                        icon={<DownloadOutlined />}
                      >
                        {t('common:actions.export')}
                      </ActionButtonFull>
                    </Dropdown>
                  </Tooltip>
                </FilterField>
              </Col>
            </Row>
          </Space>
        </PageCard>

        {/* Error Display */}
        {isError && (
          <Alert
            message={t('system:audit.errors.loadTitle')}
            description={error?.message || t('system:audit.errors.loadDescription')}
            type="error"
            closable
            showIcon
            action={
              <RediaccButton size="sm" onClick={() => refetch()} loading={isLoading}>
                {t('system:audit.errors.tryAgain')}
              </RediaccButton>
            }
          />
        )}

        {/* Audit Logs Table */}
        <PageCard data-testid="audit-table-card">
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
              showTotal: (total, range) =>
                t('system:audit.pagination.showing', { start: range[0], end: range[1], total }),
              onChange: onPageChange,
              position: ['bottomRight'],
              className: 'audit-table-pagination',
            }}
            scroll={{ x: 'max-content' }}
            locale={{
              emptyText: (
                <Empty
                  description={
                    <Space direction="vertical" align="center">
                      <RediaccText color="secondary">
                        {isError
                          ? t('system:audit.errors.unableToLoad')
                          : filteredLogs?.length === 0 && auditLogs && auditLogs.length > 0
                            ? t('system:audit.empty.noMatchingFilters')
                            : t('system:audit.empty.noLogsInRange')}
                      </RediaccText>
                      {!isError && (
                        <LinkButton onClick={clearAllFilters}>
                          {t('system:audit.empty.clearFilters')}
                        </LinkButton>
                      )}
                    </Space>
                  }
                />
              ),
            }}
          />
        </PageCard>
      </ContentStack>
    </PageWrapper>
  );
};

export default AuditPage;
