import React, { useRef } from 'react'
import { Card, Table, Input, Spin, Empty, TableProps } from 'antd'
import { SearchOutlined } from '@/utils/optimizedIcons'
import { useDynamicPageSize } from '@/hooks/useDynamicPageSize'

const { Search } = Input

interface ResourceListViewProps<T = any> {
  title?: React.ReactNode
  loading?: boolean
  data?: T[]
  columns: TableProps<T>['columns']
  searchPlaceholder?: string
  onSearch?: (value: string) => void
  filters?: React.ReactNode
  actions?: React.ReactNode
  rowKey?: string | ((record: T) => string)
  emptyText?: string
  pagination?: TableProps<T>['pagination']
  onRow?: TableProps<T>['onRow']
  rowSelection?: TableProps<T>['rowSelection']
  tableStyle?: React.CSSProperties
  containerStyle?: React.CSSProperties
  enableDynamicPageSize?: boolean
}

function ResourceListView<T = any>({
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
  tableStyle,
  containerStyle,
  enableDynamicPageSize = false,
}: ResourceListViewProps<T>) {
  const tableContainerRef = useRef<HTMLDivElement>(null)
  
  // Use dynamic page size if enabled
  const dynamicPageSize = useDynamicPageSize(tableContainerRef, {
    containerOffset: 120, // Account for card header and search bar
    minRows: 5,
    maxRows: 50
  })
  const cardBodyStyle = containerStyle?.height ? {
    padding: '16px',
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden'
  } : {}

  return (
    <Card 
      style={containerStyle} 
      styles={{ body: cardBodyStyle }}
      data-testid="resource-list-container"
    >
      {(title || onSearch || filters || actions) && (
        <div style={{ marginBottom: 16, flexShrink: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, flex: 1 }}>
              {title}
              {onSearch && (
                <Search
                  key={searchPlaceholder}
                  placeholder={searchPlaceholder}
                  onSearch={onSearch}
                  style={{ width: 300 }}
                  prefix={<SearchOutlined />}
                  allowClear
                  autoComplete="off"
                  data-testid="resource-list-search"
                />
              )}
              <div data-testid="resource-list-filters">
                {filters}
              </div>
            </div>
            {actions && (
              <div style={{ display: 'flex', gap: 8 }} data-testid="resource-list-actions">
                {actions}
              </div>
            )}
          </div>
        </div>
      )}

      <div 
        ref={tableContainerRef}
        style={containerStyle?.height ? { flex: 1, overflow: 'hidden', minHeight: 0, display: 'flex', flexDirection: 'column' } : {}}
      >
        {loading ? (
          <div style={{ textAlign: 'center', padding: '50px 0' }} data-testid="resource-list-loading">
            <Spin size="large" />
          </div>
        ) : data.length === 0 ? (
          <Empty description={emptyText} data-testid="resource-list-empty" />
        ) : (
          <Table<T>
            columns={columns}
            dataSource={data}
            rowKey={rowKey}
            pagination={pagination !== false ? {
              showSizeChanger: !enableDynamicPageSize,
              showTotal: (total, range) => `Showing records ${range[0]}-${range[1]} of ${total}`,
              pageSizeOptions: enableDynamicPageSize ? undefined : ['10', '20', '50', '100'],
              pageSize: enableDynamicPageSize ? dynamicPageSize : undefined,
              defaultPageSize: enableDynamicPageSize ? undefined : 20,
              ...pagination,
            } : false}
            onRow={(record, index) => {
              const rowId = typeof rowKey === 'function' ? rowKey(record) : (record as any)[rowKey]
              return {
                ...onRow?.(record, index),
                'data-testid': `resource-list-item-${rowId}`
              }
            }}
            rowSelection={rowSelection}
            scroll={{ x: 'max-content', y: tableStyle?.height || 400 }}
            style={{ height: '100%' }}
            sticky
            data-testid="resource-list-table"
          />
        )}
      </div>
    </Card>
  )
}

export default ResourceListView