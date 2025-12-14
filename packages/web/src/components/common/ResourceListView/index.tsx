import type { Key, ReactNode } from 'react';
import { Empty } from 'antd';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { RediaccButton, RediaccTable, RediaccText, RediaccTooltip } from '@/components/ui';
import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@/utils/optimizedIcons';
import {
  ActionsGroup,
  ContainerCard,
  ControlGroup,
  EmptyActions,
  EmptyDescriptionStack,
  FiltersSlot,
  HeaderRow,
  HeaderSection,
  RefreshButton,
  SearchInput,
} from './styles';
import type { TableProps } from 'antd';

export { COLUMN_RESPONSIVE, COLUMN_WIDTHS } from './columnConstants';

interface ResourceListViewProps<T extends object = Record<string, unknown>> {
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
}: ResourceListViewProps<T>) {
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

  const getRowDataTestId = (record: T): string => {
    if (typeof rowKey === 'function') {
      return `resource-list-item-${rowKey(record)}`;
    }

    const recordValue = (record as Record<string, unknown>)[rowKey];
    return `resource-list-item-${recordValue ?? rowKey}`;
  };

  return (
    <ContainerCard data-testid="resource-list-container">
      {shouldRenderControls && (
        <HeaderSection>
          <HeaderRow>
            <ControlGroup>
              {title}
              {onSearch && (
                <SearchInput
                  key={searchPlaceholder}
                  placeholder={searchPlaceholder}
                  onSearch={onSearch}
                  prefix={<SearchOutlined />}
                  allowClear
                  autoComplete="off"
                  data-testid="resource-list-search"
                />
              )}
              <FiltersSlot data-testid="resource-list-filters">{filters}</FiltersSlot>
            </ControlGroup>
            {actions && <ActionsGroup data-testid="resource-list-actions">{actions}</ActionsGroup>}
          </HeaderRow>
        </HeaderSection>
      )}

      <LoadingWrapper loading={loading} centered minHeight={240}>
        {data.length === 0 ? (
          <Empty
            description={
              <EmptyDescriptionStack>
                <RediaccText variant="title">{resolvedEmptyDescription}</RediaccText>
                <RediaccText variant="description">
                  {onCreateNew
                    ? `Get started by creating your first ${singularResourceType}`
                    : `No ${resourceType} found. Try adjusting your search criteria.`}
                </RediaccText>
                {(onCreateNew || onRefresh) && (
                  <EmptyActions>
                    {onCreateNew && (
                      <RediaccTooltip title={createButtonText}>
                        <RediaccButton
                          icon={<PlusOutlined />}
                          onClick={onCreateNew}
                          data-testid="resource-list-create-new"
                          aria-label={createButtonText}
                        />
                      </RediaccTooltip>
                    )}
                    {onRefresh && (
                      <RediaccTooltip title="Refresh">
                        <RefreshButton
                          icon={<ReloadOutlined />}
                          onClick={onRefresh}
                          data-testid="resource-list-refresh"
                          aria-label="Refresh"
                        />
                      </RediaccTooltip>
                    )}
                  </EmptyActions>
                )}
              </EmptyDescriptionStack>
            }
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            data-testid="resource-list-empty"
          />
        ) : (
          <RediaccTable<T>
            columns={columns}
            dataSource={data}
            rowKey={rowKey}
            pagination={resolvedPagination}
            onRow={(record, index) => ({
              ...onRow?.(record, index),
              'data-testid': getRowDataTestId(record),
            })}
            rowSelection={rowSelection}
            scroll={{ x: true }}
            data-testid="resource-list-table"
          />
        )}
      </LoadingWrapper>
    </ContainerCard>
  );
}

export default ResourceListView;
