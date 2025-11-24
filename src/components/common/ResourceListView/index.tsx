import type { Key, ReactNode } from 'react'
import { Table, Empty, type TableProps, Tooltip } from 'antd'
import { SearchOutlined, PlusOutlined, ReloadOutlined } from '@/utils/optimizedIcons'
import {
  ContainerCard,
  HeaderSection,
  HeaderRow,
  ControlGroup,
  FiltersSlot,
  ActionsGroup,
  SearchInput,
  EmptyDescriptionStack,
  EmptyTitle,
  EmptySubtitle,
  EmptyActions,
  CreateButton,
  RefreshButton,
  TableWrapper,
} from './styles'
import LoadingWrapper from '@/components/common/LoadingWrapper'

interface ResourceListViewProps<T extends Record<string, unknown> = Record<string, unknown>> {
  title?: ReactNode
  loading?: boolean
  data?: T[]
  columns: TableProps<T>['columns']
  searchPlaceholder?: string
  onSearch?: (value: string) => void
  filters?: ReactNode
  actions?: ReactNode
  rowKey?: string | ((record: T) => Key)
  emptyText?: string
  pagination?: TableProps<T>['pagination']
  onRow?: TableProps<T>['onRow']
  rowSelection?: TableProps<T>['rowSelection']
  onCreateNew?: () => void
  onRefresh?: () => void
  createButtonText?: string
  emptyDescription?: string
  resourceType?: string
}

function ResourceListView<T extends Record<string, unknown> = Record<string, unknown>>({
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
  const shouldRenderControls = Boolean(title || onSearch || filters || actions)
  const resolvedEmptyDescription = emptyDescription || emptyText
  const singularResourceType =
    resourceType && resourceType.endsWith('s') ? resourceType.slice(0, -1) : resourceType

  const resolvedPagination =
    pagination !== false
      ? {
          showSizeChanger: true,
          showTotal: (total: number, range: [number, number]) =>
            `Showing records ${range[0]}-${range[1]} of ${total}`,
          pageSizeOptions: ['10', '20', '50', '100'],
          defaultPageSize: 20,
          ...pagination,
        }
      : false

  const getRowDataTestId = (record: T): string => {
    if (typeof rowKey === 'function') {
      return `resource-list-item-${rowKey(record)}`
    }

    const recordValue = (record as Record<string, unknown>)[rowKey]
    return `resource-list-item-${recordValue ?? rowKey}`
  }

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
            {actions && (
              <ActionsGroup data-testid="resource-list-actions">{actions}</ActionsGroup>
            )}
          </HeaderRow>
        </HeaderSection>
      )}

      <LoadingWrapper loading={loading} centered minHeight={240}>
        {data.length === 0 ? (
          <Empty
            description={
              <EmptyDescriptionStack>
                <EmptyTitle>{resolvedEmptyDescription}</EmptyTitle>
                <EmptySubtitle>
                  {onCreateNew
                    ? `Get started by creating your first ${singularResourceType}`
                    : `No ${resourceType} found. Try adjusting your search criteria.`}
                </EmptySubtitle>
                {(onCreateNew || onRefresh) && (
                  <EmptyActions>
                    {onCreateNew && (
                      <Tooltip title={createButtonText}>
                        <CreateButton
                          type="primary"
                          icon={<PlusOutlined />}
                          onClick={onCreateNew}
                          data-testid="resource-list-create-new"
                          aria-label={createButtonText}
                        />
                      </Tooltip>
                    )}
                    {onRefresh && (
                      <Tooltip title="Refresh">
                        <RefreshButton
                          icon={<ReloadOutlined />}
                          onClick={onRefresh}
                          data-testid="resource-list-refresh"
                          aria-label="Refresh"
                        />
                      </Tooltip>
                    )}
                  </EmptyActions>
                )}
              </EmptyDescriptionStack>
            }
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            data-testid="resource-list-empty"
          />
        ) : (
          <TableWrapper>
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
              scroll={{ x: true }}
              data-testid="resource-list-table"
            />
          </TableWrapper>
        )}
      </LoadingWrapper>
    </ContainerCard>
  )
}

export default ResourceListView
