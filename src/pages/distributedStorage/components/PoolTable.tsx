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
  CloudServerOutlined,
  FileImageOutlined
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { DistributedStoragePool, DistributedStorageCluster } from '@/api/queries/distributedStorage'
import AuditTraceModal from '@/components/common/AuditTraceModal'
import RbdImageList from './RbdImageList'

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
      render: (name: string, record: DistributedStoragePool) => {
        const isExpanded = expandedRowKeys.includes(record.poolGuid)
        return (
          <Space>
            <span style={{ 
              display: 'inline-block',
              width: 12,
              transition: 'transform 0.3s ease',
              transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)'
            }}>
              <RightOutlined style={{ fontSize: 12, color: '#999' }} />
            </span>
            <DatabaseOutlined style={{ color: '#1890ff' }} />
            <strong>{name}</strong>
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
      render: (version: number) => <Tag>{t('common:general.versionFormat', { version })}</Tag>,
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
                  onRunFunction({ ...record, preselectedFunction: key })
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
            >
              {t('common:actions.remote')}
            </Button>
          </Dropdown>
          <Button
            type="primary"
            size="small"
            icon={<HistoryOutlined />}
            data-testid={`ds-pool-trace-${record.poolName}`}
            onClick={() => {
              setAuditTraceModal({
                open: true,
                entityType: 'DistributedStoragePool',
                entityIdentifier: record.poolName,
                entityName: record.poolName
              })
            }}
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
        style={{ marginTop: 48 }}
      >
        <Button type="primary" onClick={onCreatePool} data-testid="ds-create-pool-empty">
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
                <CloudServerOutlined style={{ color: '#556b2f' }} />
                <span>{t('pools.clusterPrefix')}: <strong>{clusterName}</strong></span>
                {cluster && <Tag color="#8FBC8F">{cluster.teamName}</Tag>}
              </Space>
            }
            style={{ marginBottom: 16 }}
          >
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
                  
                  const isExpanded = expandedRowKeys.includes(record.poolGuid)
                  if (isExpanded) {
                    setExpandedRowKeys(expandedRowKeys.filter(key => key !== record.poolGuid))
                  } else {
                    setExpandedRowKeys([...expandedRowKeys, record.poolGuid])
                  }
                },
                style: { 
                  cursor: 'pointer',
                  transition: 'background-color 0.3s ease'
                },
                onMouseEnter: (e) => {
                  e.currentTarget.style.backgroundColor = 'rgba(0, 0, 0, 0.02)'
                },
                onMouseLeave: (e) => {
                  e.currentTarget.style.backgroundColor = ''
                }
              })}
            />
          </Card>
        )
      })}
      
      {/* Audit Trace Modal */}
      <AuditTraceModal
        open={auditTraceModal.open}
        onCancel={() => setAuditTraceModal({ open: false, entityType: null, entityIdentifier: null })}
        entityType={auditTraceModal.entityType}
        entityIdentifier={auditTraceModal.entityIdentifier}
        entityName={auditTraceModal.entityName}
      />
    </>
  )
}

