import React, { useState } from 'react'
import { Table, Button, Space, Tag, Modal, Empty, Dropdown, Badge, Tooltip } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  EditOutlined,
  DeleteOutlined,
  CloudServerOutlined,
  FunctionOutlined,
  HistoryOutlined,
  ExpandOutlined,
  KeyOutlined,
  DesktopOutlined,
  RightOutlined,
  TeamOutlined
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { DistributedStorageCluster } from '@/api/queries/distributedStorage'
import { useDistributedStorageClusterMachines } from '@/api/queries/distributedStorage'
import AuditTraceModal from '@/components/common/AuditTraceModal'
import { ManageClusterMachinesModal } from './ManageClusterMachinesModal'
import { formatTimestampAsIs } from '@/utils/timeUtils'
import { useTableStyles } from '@/hooks/useComponentStyles'
import { createSorter, createDateSorter } from '@/utils/tableSorters'

interface ClusterTableProps {
  clusters: DistributedStorageCluster[]
  loading: boolean
  onCreateCluster: () => void
  onEditCluster: (cluster: DistributedStorageCluster) => void
  onDeleteCluster: (cluster: DistributedStorageCluster) => void
  onRunFunction: (cluster: DistributedStorageCluster) => void
}

// Machine count badge component
const MachineCountBadge: React.FC<{ cluster: DistributedStorageCluster }> = ({ cluster }) => {
  const { data: machines = [] } = useDistributedStorageClusterMachines(
    cluster.clusterName,
    true
  )
  const tableStyles = useTableStyles()
  
  return (
    <Badge 
      count={machines.length} 
      showZero 
      style={{ 
        backgroundColor: machines.length > 0 ? 'var(--color-success)' : 'var(--color-fill-quaternary)',
        color: machines.length > 0 ? 'var(--color-white)' : 'var(--color-text-secondary)'
      }}
    >
      <TeamOutlined style={tableStyles.icon.medium} />
    </Badge>
  )
}

export const ClusterTable: React.FC<ClusterTableProps> = ({
  clusters,
  loading,
  onCreateCluster,
  onEditCluster,
  onDeleteCluster,
  onRunFunction
}) => {
  const { t } = useTranslation(['distributedStorage', 'common', 'machines'])
  const tableStyles = useTableStyles()
  const [expandedRowKeys, setExpandedRowKeys] = useState<string[]>([])
  const [selectedCluster, setSelectedCluster] = useState<DistributedStorageCluster | null>(null)
  const [assignModalOpen, setAssignModalOpen] = useState(false)
  const [auditTraceModal, setAuditTraceModal] = useState<{
    open: boolean
    entityType: string | null
    entityIdentifier: string | null
    entityName?: string
  }>({ open: false, entityType: null, entityIdentifier: null })

  // Function menu items
  const getFunctionMenuItems = (_cluster: DistributedStorageCluster) => [
    {
      key: 'status',
      label: t('functions.cluster_status'),
      icon: <ExpandOutlined />,
    },
    {
      key: 'dashboard',
      label: t('functions.cluster_dashboard'),
      icon: <KeyOutlined />,
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

  const handleDelete = (cluster: DistributedStorageCluster) => {
    Modal.confirm({
      title: t('clusters.confirmDelete'),
      content: t('clusters.deleteWarning', { name: cluster.clusterName }),
      okText: t('common:actions.delete'),
      okType: 'danger',
      cancelText: t('common:actions.cancel'),
      onOk: () => onDeleteCluster(cluster),
    })
  }

  const columns: ColumnsType<DistributedStorageCluster> = [
    {
      title: t('clusters.clusterName'),
      dataIndex: 'clusterName',
      key: 'clusterName',
      ellipsis: true,
      sorter: createSorter<DistributedStorageCluster>('clusterName'),
      render: (name: string, record: DistributedStorageCluster) => {
        const isExpanded = expandedRowKeys.includes(record.clusterName)
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
            <CloudServerOutlined style={{ ...tableStyles.icon.medium, color: 'var(--color-primary)' }} />
            <strong style={{ color: 'var(--color-text-primary)' }}>{name}</strong>
          </Space>
        )
      },
    },
    {
      title: t('common:general.team'),
      dataIndex: 'teamName',
      key: 'teamName',
      width: 150,
      ellipsis: true,
      sorter: createSorter<DistributedStorageCluster>('teamName'),
      render: (teamName: string) => <Tag color="green">{teamName}</Tag>,
    },
    {
      title: t('machines:title'),
      key: 'machineCount',
      width: 120,
      align: 'center',
      render: (_: unknown, record: DistributedStorageCluster) => (
        <Space size="small">
          <MachineCountBadge cluster={record} />
          <Button
            type="link"
            size="small"
            data-testid={`ds-cluster-manage-machines-${record.clusterName}`}
            onClick={(e) => {
              e.stopPropagation()
              setSelectedCluster(record)
              setAssignModalOpen(true)
            }}
          >
            {t('machines:manage')}
          </Button>
        </Space>
      ),
    },
    {
      title: t('common:general.vaultVersion'),
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 100,
      align: 'center',
      sorter: createSorter<DistributedStorageCluster>('vaultVersion'),
      render: (version: number) => <Tag color="blue">{t('common:general.versionFormat', { version })}</Tag>,
    },
    {
      title: t('common:table.actions'),
      key: 'actions',
      width: 250,
      render: (_: unknown, record: DistributedStorageCluster) => (
        <Space>
          <Tooltip title={t('common:actions.edit')}>
            <Button
              type="primary"
              size="small"
              icon={<EditOutlined />}
              data-testid={`ds-cluster-edit-${record.clusterName}`}
              onClick={() => onEditCluster(record)}
              style={tableStyles.tableActionButton}
              aria-label={t('common:actions.edit')}
            />
          </Tooltip>
          <Dropdown
            menu={{
              items: getFunctionMenuItems(record),
              onClick: ({ key }) => {
                if (key === 'advanced') {
                  onRunFunction(record)
                } else {
                  // Handle specific function
                  onRunFunction({ ...record, preselectedFunction: key } as DistributedStorageCluster & { preselectedFunction: string })
                }
              }
            }}
            trigger={['click']}
          >
            <Tooltip title={t('common:actions.remote')}>
              <Button
                type="primary"
                size="small"
                icon={<FunctionOutlined />}
                data-testid={`ds-cluster-function-dropdown-${record.clusterName}`}
                style={tableStyles.tableActionButton}
                aria-label={t('common:actions.remote')}
              />
            </Tooltip>
          </Dropdown>
          <Tooltip title={t('common:actions.trace')}>
            <Button
              type="default"
              size="small"
              icon={<HistoryOutlined />}
              data-testid={`ds-cluster-trace-${record.clusterName}`}
              onClick={() => {
                setAuditTraceModal({
                  open: true,
                  entityType: 'DistributedStorageCluster',
                  entityIdentifier: record.clusterName,
                  entityName: record.clusterName
                })
              }}
              style={tableStyles.tableActionButton}
              aria-label={t('common:actions.trace')}
            />
          </Tooltip>
          <Tooltip title={t('common:actions.delete')}>
            <Button
              type="primary"
              danger
              size="small"
              icon={<DeleteOutlined />}
              data-testid={`ds-cluster-delete-${record.clusterName}`}
              onClick={() => handleDelete(record)}
              style={tableStyles.tableActionButton}
              aria-label={t('common:actions.delete')}
            />
          </Tooltip>
        </Space>
      ),
    },
  ]

  // Expanded row render to show machines in cluster
  const expandedRowRender = (record: DistributedStorageCluster) => {
    return <ClusterMachines cluster={record} />
  }

  return (
    <>
      {clusters.length === 0 && !loading ? (
        <Empty
          description={t('clusters.noClusters')}
          style={{ marginTop: 48 }}
        >
          <Button type="primary" data-testid="ds-create-cluster-empty" onClick={onCreateCluster}>
            {t('clusters.create')}
          </Button>
        </Empty>
      ) : (
        <div style={tableStyles.tableContainer}>
          <Table
            data-testid="ds-cluster-table"
            columns={columns}
            dataSource={clusters}
            rowKey="clusterName"
            loading={loading}
            scroll={{ x: 'max-content' }}
            pagination={{
              showSizeChanger: true,
              showTotal: (total, range) => t('common:table.showingRecords', { start: range[0], end: range[1], total }),
            }}
            expandable={{
              expandedRowRender,
              expandedRowKeys,
              onExpandedRowsChange: (keys) => setExpandedRowKeys(keys as string[]),
              expandIcon: () => null,
              expandRowByClick: false,
            }}
            onRow={(record) => ({
              'data-testid': `ds-cluster-row-${record.clusterName}`,
              onClick: (e) => {
                const target = e.target as HTMLElement
                if (target.closest('button') || target.closest('.ant-dropdown-trigger')) {
                  return
                }
                
                const isExpanded = expandedRowKeys.includes(record.clusterName)
                if (isExpanded) {
                  setExpandedRowKeys(expandedRowKeys.filter(key => key !== record.clusterName))
                } else {
                  setExpandedRowKeys([...expandedRowKeys, record.clusterName])
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
      )}
      
      {/* Audit Trace Modal */}
      <AuditTraceModal
        open={auditTraceModal.open}
        onCancel={() => setAuditTraceModal({ open: false, entityType: null, entityIdentifier: null })}
        entityType={auditTraceModal.entityType}
        entityIdentifier={auditTraceModal.entityIdentifier}
        entityName={auditTraceModal.entityName}
      />
      
      {/* Manage Cluster Machines Modal */}
      {selectedCluster && (
        <ManageClusterMachinesModal
          open={assignModalOpen}
          clusterName={selectedCluster.clusterName}
          teamName={selectedCluster.teamName || ''}
          onCancel={() => {
            setAssignModalOpen(false)
            setSelectedCluster(null)
          }}
          onSuccess={() => {
            setAssignModalOpen(false)
            setSelectedCluster(null)
            // Force refresh of expanded rows if this cluster is expanded
            if (expandedRowKeys.includes(selectedCluster.clusterName)) {
              setExpandedRowKeys([])
              setTimeout(() => {
                setExpandedRowKeys([selectedCluster.clusterName])
              }, 100)
            }
          }}
        />
      )}
    </>
  )
}

// Sub-component to show machines in a cluster
const ClusterMachines: React.FC<{ cluster: DistributedStorageCluster }> = ({ cluster }) => {
  const { t } = useTranslation(['distributedStorage', 'common'])
  const tableStyles = useTableStyles()
  const { data: machines = [], isLoading } = useDistributedStorageClusterMachines(
    cluster.clusterName,
    true
  )

  const machineColumns: ColumnsType<Record<string, unknown>> = [
    {
      title: t('machines.machineName'),
      dataIndex: 'machineName',
      key: 'machineName',
      sorter: createSorter<Record<string, unknown>>('machineName'),
      render: (name: string) => (
        <Space>
          <DesktopOutlined style={{ ...tableStyles.icon.medium, color: 'var(--color-primary)' }} />
          <strong style={{ color: 'var(--color-text-primary)' }}>{name}</strong>
        </Space>
      ),
    },
    {
      title: t('machines.bridgeName'),
      dataIndex: 'bridgeName',
      key: 'bridgeName',
      sorter: createSorter<Record<string, unknown>>('bridgeName'),
      render: (name: string) => <Tag color="green">{name}</Tag>,
    },
    {
      title: t('machines.assignedDate'),
      dataIndex: 'assignedDate',
      key: 'assignedDate',
      sorter: createDateSorter<Record<string, unknown>>('assignedDate'),
      render: (date: string) => (
        <span style={{ color: 'var(--color-text-secondary)' }}>
          {date ? formatTimestampAsIs(date, 'datetime') : '-'}
        </span>
      ),
    },
  ]

  return (
    <div style={{ ...tableStyles.padding.md, background: 'var(--color-fill-quaternary)' }} data-testid={`cluster-expanded-row-${cluster.clusterName}`}>
      <h4 style={{ ...tableStyles.heading4, ...tableStyles.marginBottom.sm }}>{t('clusters.assignedMachines')}</h4>
      {machines.length === 0 && !isLoading ? (
        <Empty description={t('clusters.noMachinesAssigned')} />
      ) : (
        <div style={tableStyles.tableContainer}>
          <Table
            data-testid={`ds-cluster-machines-table-${cluster.clusterName}`}
            columns={machineColumns}
            dataSource={machines}
            rowKey="machineName"
            loading={isLoading}
            size="small"
            pagination={false}
          />
        </div>
      )}
    </div>
  )
}