import type { Key, ReactNode } from 'react';
import {
  Button,
  Card,
  Empty,
  Flex,
  Grid,
  Input,
  List,
  Table,
  Tooltip,
  Typography,
  type TableProps,
} from 'antd';
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
}

function ResourceListView<T extends object = Record<string, unknown>>({
  title,
  loading = false,
  data = [],
  columns,
  searchPlaceholder = 'Search...',
  onSearch,
  filters,
  actions,
  rowKey = 'id',
  emptyText = 'No data available',
  pagination,
  onRow,
  rowSelection,
  onCreateNew,
  onRefresh,
  createButtonText = 'Create New',
  emptyDescription,
  resourceType = 'items',
  mobileRender,
  expandable,
  rowClassName,
  'data-testid': dataTestId,
}: ResourceListViewProps<T>) {
  const screens = Grid.useBreakpoint();
  const isMobile = !screens.sm;
  const shouldRenderControls = Boolean(title || onSearch || filters || actions);
  const resolvedEmptyDescription = emptyDescription || emptyText;
  const singularResourceType =
    resourceType && resourceType.endsWith('s') ? resourceType.slice(0, -1) : resourceType;

  const resolvedPagination =
    pagination !== false
      ? {
          showSizeChanger: true,
          size: 'small' as const,
          showTotal: (total: number, range: [number, number]) =>
            `Showing records ${range[0]}-${range[1]} of ${total}`,
          pageSizeOptions: ['10', '20', '50', '100'],
          defaultPageSize: 20,
          ...pagination,
        }
      : false;

  const getRowKey = (record: T, index: number): Key => {
    if (typeof rowKey === 'function') return rowKey(record);
    return ((record as Record<string, unknown>)[rowKey] as Key) ?? index;
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
                  key={searchPlaceholder}
                  placeholder={searchPlaceholder}
                  onSearch={onSearch}
                  prefix={<SearchOutlined />}
                  allowClear
                  autoComplete="off"
                  data-testid="resource-list-search"
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
        {data.length === 0 ? (
          <Empty
            description={
              <Flex vertical align="center">
                <Typography.Text strong>{resolvedEmptyDescription}</Typography.Text>
                <Typography.Text>
                  {onCreateNew
                    ? `Get started by creating your first ${singularResourceType}`
                    : `No ${resourceType} found. Try adjusting your search criteria.`}
                </Typography.Text>
                {(onCreateNew || onRefresh) && (
                  <Flex align="center" justify="center">
                    {onCreateNew && (
                      <Tooltip title={createButtonText}>
                        <Button
                          icon={<PlusOutlined />}
                          onClick={onCreateNew}
                          data-testid="resource-list-create-new"
                          aria-label={createButtonText}
                        />
                      </Tooltip>
                    )}
                    {onRefresh && (
                      <Tooltip title="Refresh">
                        <Button
                          shape="circle"
                          icon={<ReloadOutlined />}
                          onClick={onRefresh}
                          data-testid="resource-list-refresh"
                          aria-label="Refresh"
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
        ) : isMobile && mobileRender ? (
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
        ) : (
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
            data-testid={dataTestId || 'resource-list-table'}
          />
        )}
      </LoadingWrapper>
    </Card>
  );
}

export default ResourceListView;
