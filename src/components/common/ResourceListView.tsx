import React from 'react'
import { Card, Table, Input, Select, Space, Spin, Empty, TableProps } from 'antd'
import { SearchOutlined } from '@ant-design/icons'

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
}: ResourceListViewProps<T>) {
  return (
    <Card>
      {(title || onSearch || filters || actions) && (
        <div style={{ marginBottom: 16 }}>
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
                />
              )}
              {filters}
            </div>
            {actions && (
              <div style={{ display: 'flex', gap: 8 }}>
                {actions}
              </div>
            )}
          </div>
        </div>
      )}

      {loading ? (
        <div style={{ textAlign: 'center', padding: '50px 0' }}>
          <Spin size="large" />
        </div>
      ) : data.length === 0 ? (
        <Empty description={emptyText} />
      ) : (
        <Table<T>
          columns={columns}
          dataSource={data}
          rowKey={rowKey}
          pagination={
            pagination !== false
              ? {
                  showSizeChanger: true,
                  showTotal: (total) => `Total ${total} items`,
                  pageSizeOptions: ['10', '20', '50', '100'],
                  defaultPageSize: 20,
                  ...pagination,
                }
              : false
          }
          onRow={onRow}
          rowSelection={rowSelection}
          scroll={{ x: 'max-content' }}
        />
      )}
    </Card>
  )
}

export default ResourceListView