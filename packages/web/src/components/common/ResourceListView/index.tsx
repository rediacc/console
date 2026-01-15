import { DEFAULTS, UI_IDS } from '@rediacc/shared/config';
import {
  Button,
  Card,
  Empty,
  Flex,
  Grid,
  Input,
  List,
  Table,
  type TableProps,
  Tooltip,
  Typography,
} from 'antd';
import type { Key, ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@/utils/optimizedIcons';

export { COLUMN_RESPONSIVE, COLUMN_WIDTHS } from './columnConstants';

export interface ResourceListViewProps<T extends object = Record<string, unknown>> {
  title?: ReactNode;
  loading?: boolean;
  data?: T[];
  columns: TableProps<T>['columns'];
  searchPlaceholder?: string;
  onSearch?: (value: string) => void;
  filters?: ReactNode;
  actions?: ReactNode;
  rowKey?: string | ((record: T) => Key);
  emptyText?: string;
  pagination?: TableProps<T>['pagination'];
  onRow?: TableProps<T>['onRow'];
  rowSelection?: TableProps<T>['rowSelection'];
  onCreateNew?: () => void;
  onRefresh?: () => void;
  createButtonText?: string;
  emptyDescription?: string;
  resourceType?: string;
  /** Custom render function for mobile view */
  mobileRender?: (record: T, index: number) => ReactNode;
  /** Expandable row configuration */
  expandable?: TableProps<T>['expandable'];
  /** Row class name */
  rowClassName?: TableProps<T>['rowClassName'];
  /** Custom data-testid for the table */
  'data-testid'?: string;
  /** Custom data-testid for the search input */
  searchTestId?: string;
  /** Custom data-testid for the refresh button */
  refreshTestId?: string;
}

function ResourceListView<T extends object = Record<string, unknown>>({
  title,
  loading = false,
  data = [],
  columns,
  searchPlaceholder,
  onSearch,
  filters,
  actions,
  rowKey = 'id',
  emptyText,
  pagination,
  onRow,
  rowSelection,
  onCreateNew,
  onRefresh,
  createButtonText,
  emptyDescription,
  resourceType = 'items',
  mobileRender,
  expandable,
  rowClassName,
  'data-testid': dataTestId,
  searchTestId,
  refreshTestId,
}: ResourceListViewProps<T>) {
  const { t } = useTranslation('common');
  const screens = Grid.useBreakpoint();
  const isMobile = !screens.sm;
  const shouldRenderControls = Boolean(title ?? onSearch ?? filters ?? actions);
  const resolvedEmptyDescription =
    emptyDescription ?? emptyText ?? t('resourceList.noDataAvailable');
  const resolvedSearchPlaceholder = searchPlaceholder ?? t('resourceList.searchPlaceholder');
  const resolvedCreateButtonText = createButtonText ?? t('resourceList.createNew');
  const singularResourceType = resourceType.endsWith('s')
    ? resourceType.slice(0, -1)
    : resourceType;

  const resolvedPagination =
    pagination === false
      ? false
      : {
          showSizeChanger: true,
          size: 'small' as const,
          showTotal: (total: number, range: [number, number]) =>
            t('resourceList.showingRecords', {
              start: range[0],
              end: range[1],
              total,
            }),
          pageSizeOptions: ['10', '20', '50', '100'],
          defaultPageSize: 20,
          ...pagination,
        };

  const getRowKey = (record: T, index: number): Key => {
    if (typeof rowKey === 'function') return rowKey(record);
    return ((record as Record<string, unknown>)[rowKey] as Key | undefined) ?? index;
  };

  const getRowDataTestId = (record: T): string => {
    if (typeof rowKey === 'function') {
      return `resource-list-item-${rowKey(record)}`;
    }
    const recordValue = (record as Record<string, unknown>)[rowKey];
    return `resource-list-item-${recordValue ?? rowKey}`;
  };

  return (
    <Card data-testid="resource-list-container">
      {shouldRenderControls && (
        <Flex>
          <Flex wrap justify="space-between" align="center" className="w-full">
            <Flex align="center" className="flex-1 min-w-0">
              {title}
              {onSearch && (
                <Input.Search
                  key={resolvedSearchPlaceholder}
                  placeholder={resolvedSearchPlaceholder}
                  onSearch={onSearch}
                  prefix={<SearchOutlined />}
                  allowClear
                  autoComplete="off"
                  data-testid={searchTestId ?? DEFAULTS.UI.SEARCH_INPUT_ID}
                />
              )}
              <Flex align="center" data-testid="resource-list-filters">
                {filters}
              </Flex>
            </Flex>
            {actions && (
              <Flex align="center" wrap data-testid="resource-list-actions">
                {actions}
              </Flex>
            )}
          </Flex>
        </Flex>
      )}

      <LoadingWrapper loading={loading} centered minHeight={240}>
        {(() => {
          if (data.length === 0) {
            return (
              <Empty
                description={
                  <Flex vertical align="center">
                    <Typography.Text strong>{resolvedEmptyDescription}</Typography.Text>
                    <Typography.Text>
                      {onCreateNew
                        ? t('resourceList.getStartedMessage', { resource: singularResourceType })
                        : t('resourceList.noResourcesFound', { resources: resourceType })}
                    </Typography.Text>
                    {(onCreateNew ?? onRefresh) && (
                      <Flex align="center" justify="center">
                        {onCreateNew && (
                          <Tooltip title={resolvedCreateButtonText}>
                            <Button
                              icon={<PlusOutlined />}
                              onClick={onCreateNew}
                              data-testid="resource-list-create-new"
                              aria-label={resolvedCreateButtonText}
                            />
                          </Tooltip>
                        )}
                        {onRefresh && (
                          <Tooltip title={t('actions.refresh')}>
                            <Button
                              shape="circle"
                              icon={<ReloadOutlined />}
                              onClick={onRefresh}
                              data-testid={refreshTestId ?? UI_IDS.RESOURCE_LIST_REFRESH}
                              aria-label={t('actions.refresh')}
                            />
                          </Tooltip>
                        )}
                      </Flex>
                    )}
                  </Flex>
                }
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                data-testid="resource-list-empty"
              />
            );
          } else if (isMobile && mobileRender) {
            return (
              <List
                dataSource={data}
                renderItem={(record, index) => (
                  <List.Item
                    key={getRowKey(record, index)}
                    className="mobile-list-item"
                    data-testid={getRowDataTestId(record)}
                  >
                    {mobileRender(record, index)}
                  </List.Item>
                )}
                pagination={
                  resolvedPagination
                    ? {
                        size: resolvedPagination.size,
                        showSizeChanger: resolvedPagination.showSizeChanger,
                        showTotal: resolvedPagination.showTotal,
                        pageSizeOptions: resolvedPagination.pageSizeOptions,
                        defaultPageSize: resolvedPagination.defaultPageSize,
                      }
                    : false
                }
                split={false}
              />
            );
          }
          return (
            <Table<T>
              columns={columns}
              dataSource={data}
              rowKey={rowKey}
              pagination={resolvedPagination}
              onRow={(record, index) => ({
                ...onRow?.(record, index),
                'data-testid': getRowDataTestId(record),
              })}
              rowSelection={rowSelection}
              expandable={expandable}
              rowClassName={rowClassName}
              scroll={{ x: true }}
              data-testid={dataTestId ?? UI_IDS.RESOURCE_LIST_TABLE}
            />
          );
        })()}
      </LoadingWrapper>
    </Card>
  );
}

export default ResourceListView;
