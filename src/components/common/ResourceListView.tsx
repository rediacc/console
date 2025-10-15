import React from 'react'
import { Card, Table, Input, Spin, Empty, TableProps, Space, Typography, Button, Tooltip } from 'antd'
import { SearchOutlined, PlusOutlined, ReloadOutlined } from '@/utils/optimizedIcons'

const { Text } = Typography

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
  // Enhanced empty state props
  onCreateNew?: () => void
  onRefresh?: () => void
  createButtonText?: string
  emptyDescription?: string
  resourceType?: string
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
  onCreateNew,
  onRefresh,
  createButtonText = 'Create New',
  emptyDescription,
  resourceType = 'items',
}: ResourceListViewProps<T>) {

  return (
    <Card
      data-testid="resource-list-container"
    >
      {(title || onSearch || filters || actions) && (
        <div style={{ marginBottom: 'var(--space-md)' }}>
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 'var(--space-md)'
          }}>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--space-md)',
              flex: 1
            }}>
              {title}
              {onSearch && (
                <Search
                  key={searchPlaceholder}
                  placeholder={searchPlaceholder}
                  onSearch={onSearch}
                  style={{
                    width: 300,
                    minHeight: '44px' // Accessibility compliance
                  }}
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
              <div style={{
                display: 'flex',
                gap: 'var(--space-sm)'
              }} data-testid="resource-list-actions">
                {actions}
              </div>
            )}
          </div>
        </div>
      )}

      <div>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '50px 0' }} data-testid="resource-list-loading">
            <Spin size="large" />
          </div>
        ) : data.length === 0 ? (
          <Empty 
            description={
              <Space direction="vertical" align="center" size="middle" style={{ 
                textAlign: 'center',
                padding: 'var(--space-lg)'
              }}>
                <Text>{emptyDescription || emptyText}</Text>
                <Text type="secondary" style={{ 
                  fontSize: 14,
                  color: 'var(--color-text-secondary)'
                }}>
                  {onCreateNew ? `Get started by creating your first ${resourceType.slice(0, -1)}` : 
                   `No ${resourceType} found. Try adjusting your search criteria.`}
                </Text>
                <Space>
                  {onCreateNew && (
                    <Tooltip title={createButtonText}>
                      <Button 
                        type="primary" 
                        icon={<PlusOutlined />}
                        onClick={onCreateNew}
                        data-testid="resource-list-create-new"
                        style={{ 
                          minHeight: '44px',
                          backgroundColor: 'var(--color-primary)',
                          borderColor: 'var(--color-primary)',
                          borderRadius: '8px'
                        }}
                        aria-label={createButtonText}
                      />
                    </Tooltip>
                  )}
                  {onRefresh && (
                    <Tooltip title="Refresh">
                      <Button 
                        icon={<ReloadOutlined />}
                        onClick={onRefresh}
                        data-testid="resource-list-refresh"
                        style={{ 
                          minHeight: '44px',
                          borderRadius: '8px',
                          borderColor: 'var(--color-border-primary)'
                        }}
                        aria-label="Refresh"
                      />
                    </Tooltip>
                  )}
                </Space>
              </Space>
            }
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            data-testid="resource-list-empty" 
          />
        ) : (
          <Table<T>
            columns={columns}
            dataSource={data}
            rowKey={rowKey}
            pagination={pagination !== false ? {
              showSizeChanger: true,
              showTotal: (total, range) => `Showing records ${range[0]}-${range[1]} of ${total}`,
              pageSizeOptions: ['10', '20', '50', '100'],
              defaultPageSize: 20,
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
            scroll={{ x: 'max-content' }}
            data-testid="resource-list-table"
          />
        )}
      </div>
    </Card>
  )
}

export default ResourceListView