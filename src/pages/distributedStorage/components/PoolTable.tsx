import React, { useState } from 'react'
import { Table, Button, Space, Tag, Modal, Empty, Dropdown, Card } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  EditOutlined,
  DeleteOutlined,
  DatabaseOutlined,
  FunctionOutlined,
  HistoryOutlined,
  PlusOutlined,
  RightOutlined,
  CloudServerOutlined
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { DistributedStoragePool, DistributedStorageCluster } from '@/api/queries/distributedStorage'
import AuditTraceModal from '@/components/common/AuditTraceModal'
import RbdImageList from './RbdImageList'
import { useTableStyles, useComponentStyles } from '@/hooks/useComponentStyles'
import { createSorter } from '@/utils/tableSorters'

interface PoolTableProps {
  pools: DistributedStoragePool[]
  clusters: DistributedStorageCluster[]
  loading: boolean
  onCreatePool: () => void
  onEditPool: (pool: DistributedStoragePool) => void
  onDeletePool: (pool: DistributedStoragePool) => void
  onRunFunction: (pool: DistributedStoragePool) => void
}

export const PoolTable: React.FC<PoolTableProps> = ({
  pools,
  clusters,
  loading,
  onCreatePool,
  onEditPool,
  onDeletePool,
  onRunFunction
}) => {
  const { t } = useTranslation(['distributedStorage', 'common'])
  const tableStyles = useTableStyles()
  const componentStyles = useComponentStyles()
  const [expandedRowKeys, setExpandedRowKeys] = useState<string[]>([])
  const [auditTraceModal, setAuditTraceModal] = useState<{
    open: boolean
    entityType: string | null
    entityIdentifier: string | null
    entityName?: string
  }>({ open: false, entityType: null, entityIdentifier: null })

  // Group pools by cluster
  const poolsByCluster = pools.reduce((acc, pool) => {
    if (!acc[pool.clusterName]) {
      acc[pool.clusterName] = []
    }
    acc[pool.clusterName].push(pool)
    return acc
  }, {} as Record<string, DistributedStoragePool[]>)

  // Function menu items
  const getFunctionMenuItems = (_pool: DistributedStoragePool) => [
    {
      key: 'list',
      label: t('functions.pool_list'),
      icon: <DatabaseOutlined />,
    },
    {
      key: 'image_create',
      label: t('functions.image_create'),
      icon: <PlusOutlined />,
    },
    {
      type: 'divider' as const,
    },
    {
      key: 'advanced',
      label: t('common:actions.advanced'),
      icon: <FunctionOutlined />,
    },
  ]

  const handleDelete = (pool: DistributedStoragePool) => {
    Modal.confirm({
      title: t('pools.confirmDelete'),
      content: t('pools.deleteWarning', { name: pool.poolName }),
      okText: t('common:actions.delete'),
      okType: 'danger',
      cancelText: t('common:actions.cancel'),
      onOk: () => onDeletePool(pool),
    })
  }

  const columns: ColumnsType<DistributedStoragePool> = [
    {
      title: t('pools.poolName'),
      dataIndex: 'poolName',
      key: 'poolName',
      ellipsis: true,
      sorter: createSorter<DistributedStoragePool>('poolName'),
      render: (name: string, record: DistributedStoragePool) => {
        const isExpanded = expandedRowKeys.includes(record.poolGuid || '')
        return (
          <Space>
            <span style={{ 
              display: 'inline-block',
              width: 12,
              transition: 'transform 0.3s ease',
              transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)'
            }}>
              <RightOutlined style={{ ...tableStyles.icon.small, color: 'var(--color-text-tertiary)' }} />
            </span>
            <DatabaseOutlined style={{ ...tableStyles.icon.medium, color: 'var(--color-primary)' }} />
            <strong style={{ color: 'var(--color-text-primary)' }}>{name}</strong>
          </Space>
        )
      },
    },
    {
      title: t('common:general.vaultVersion'),
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 100,
      align: 'center',
      sorter: createSorter<DistributedStoragePool>('vaultVersion'),
      render: (version: number) => <Tag color="blue">{t('common:general.versionFormat', { version })}</Tag>,
    },
    {
      title: t('common:table.actions'),
      key: 'actions',
      width: 250,
      render: (_: unknown, record: DistributedStoragePool) => (
        <Space>
          <Button
            type="primary"
            size="small"
            icon={<EditOutlined />}
            onClick={() => onEditPool(record)}
            data-testid={`ds-pool-edit-${record.poolName}`}
            style={tableStyles.tableActionButton}
          >
            {t('common:actions.edit')}
          </Button>
          <Dropdown
            menu={{
              items: getFunctionMenuItems(record),
              onClick: ({ key }) => {
                if (key === 'advanced') {
                  onRunFunction(record)
                } else {
                  // Handle specific function
                  onRunFunction({ ...record, preselectedFunction: key } as DistributedStoragePool & { preselectedFunction: string })
                }
              }
            }}
            trigger={['click']}
          >
            <Button
              type="primary"
              size="small"
              icon={<FunctionOutlined />}
              data-testid={`ds-pool-function-dropdown-${record.poolName}`}
              style={tableStyles.tableActionButton}
            >
              {t('common:actions.remote')}
            </Button>
          </Dropdown>
          <Button
            type="default"
            size="small"
            icon={<HistoryOutlined />}
            data-testid={`ds-pool-trace-${record.poolName}`}
            onClick={() => {
              setAuditTraceModal({
                open: true,
                entityType: 'DistributedStoragePool',
                entityIdentifier: record.poolName || '',
                entityName: record.poolName
              })
            }}
            style={tableStyles.tableActionButton}
          >
            {t('common:actions.trace')}
          </Button>
          <Button
            type="primary"
            danger
            size="small"
            icon={<DeleteOutlined />}
            onClick={() => handleDelete(record)}
            data-testid={`ds-pool-delete-${record.poolName}`}
            style={tableStyles.tableActionButton}
          >
            {t('common:actions.delete')}
          </Button>
        </Space>
      ),
    },
  ]

  // Expanded row render to show RBD images in pool
  const expandedRowRender = (record: DistributedStoragePool) => {
    const teamFilter = record.teamName
    return <RbdImageList pool={record} teamFilter={teamFilter} />
  }

  if (pools.length === 0 && !loading) {
    return (
      <Empty
        description={t('pools.noPools')}
        style={componentStyles.marginBottom.xl}
      >
        <Button type="primary" onClick={onCreatePool} data-testid="ds-create-pool-empty" style={componentStyles.controlSurface}>
          {t('pools.create')}
        </Button>
      </Empty>
    )
  }

  // Render pools grouped by cluster
  return (
    <>
      {Object.entries(poolsByCluster).map(([clusterName, clusterPools]) => {
        const cluster = clusters.find(c => c.clusterName === clusterName)
        
        return (
          <Card
            key={clusterName}
            title={
              <Space>
                <CloudServerOutlined style={{ ...tableStyles.icon.medium, color: 'var(--color-primary)' }} />
                <span>{t('pools.clusterPrefix')}: <strong style={{ color: 'var(--color-text-primary)' }}>{clusterName}</strong></span>
                {cluster && <Tag color="green">{cluster.teamName}</Tag>}
              </Space>
            }
            style={{ ...componentStyles.card, ...componentStyles.marginBottom.md }}
          >
            <div style={tableStyles.tableContainer}>
              <Table
                columns={columns}
                dataSource={clusterPools}
                rowKey="poolGuid"
                loading={loading}
                scroll={{ x: 'max-content' }}
                pagination={false}
                data-testid={`ds-pool-table-${clusterName}`}
                expandable={{
                  expandedRowRender,
                  expandedRowKeys,
                  onExpandedRowsChange: (keys) => setExpandedRowKeys(keys as string[]),
                  expandIcon: () => null,
                  expandRowByClick: false,
                }}
                onRow={(record) => ({
                  'data-testid': `ds-pool-row-${record.poolName}`,
                  onClick: (e) => {
                    const target = e.target as HTMLElement
                    if (target.closest('button') || target.closest('.ant-dropdown-trigger')) {
                      return
                    }
                    
                    const isExpanded = expandedRowKeys.includes(record.poolGuid ?? '')
                    if (isExpanded) {
                      setExpandedRowKeys(expandedRowKeys.filter(key => key !== record.poolGuid))
                    } else {
                      setExpandedRowKeys([...expandedRowKeys, record.poolGuid ?? ''])
                    }
                  },
                  style: { 
                    cursor: 'pointer',
                    transition: 'background-color 0.3s ease'
                  },
                  onMouseEnter: (e) => {
                    e.currentTarget.style.backgroundColor = 'var(--color-fill-tertiary)'
                  },
                  onMouseLeave: (e) => {
                    e.currentTarget.style.backgroundColor = ''
                  }
                })}
              />
            </div>
          </Card>
        )
      })}
      
      {/* Audit Trace Modal */}
      <AuditTraceModal
        open={auditTraceModal.open}
        onCancel={() => setAuditTraceModal({ open: false, entityType: null, entityIdentifier: null })}
        entityType={auditTraceModal.entityType || ''}
        entityIdentifier={auditTraceModal.entityIdentifier || ''}
        entityName={auditTraceModal.entityName}
      />
    </>
  )
}

