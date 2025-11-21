import { useCallback, useMemo, useState } from 'react'
import { Table, Modal } from 'antd'
import { useTranslation } from 'react-i18next'
import type { ColumnsType } from 'antd/es/table'
import { DistributedStorageCluster } from '@/api/queries/distributedStorage'
import AuditTraceModal from '@/components/common/AuditTraceModal'
import { ManageClusterMachinesModal } from '../ManageClusterMachinesModal'
import { buildClusterColumns } from './columns'
import { ClusterMachines } from './components/ClusterMachines'
import {
  TableContainer,
  EmptyStateWrapper,
  CreateClusterButton,
} from './styles'

interface ClusterTableProps {
  clusters: DistributedStorageCluster[]
  loading: boolean
  onCreateCluster: () => void
  onEditCluster: (cluster: DistributedStorageCluster) => void
  onDeleteCluster: (cluster: DistributedStorageCluster) => void
  onRunFunction: (cluster: DistributedStorageCluster) => void
}

export const ClusterTable: React.FC<ClusterTableProps> = ({
  clusters,
  loading,
  onCreateCluster,
  onEditCluster,
  onDeleteCluster,
  onRunFunction,
}) => {
  const { t } = useTranslation(['distributedStorage', 'common', 'machines'])
  const [expandedRowKeys, setExpandedRowKeys] = useState<string[]>([])
  const [selectedCluster, setSelectedCluster] =
    useState<DistributedStorageCluster | null>(null)
  const [assignModalOpen, setAssignModalOpen] = useState(false)
  const [auditTraceModal, setAuditTraceModal] = useState<{
    open: boolean
    entityType: string | null
    entityIdentifier: string | null
    entityName?: string
  }>({ open: false, entityType: null, entityIdentifier: null })

  const handleManageMachines = useCallback((cluster: DistributedStorageCluster) => {
    setSelectedCluster(cluster)
    setAssignModalOpen(true)
  }, [])

  const handleAuditTrace = useCallback((cluster: DistributedStorageCluster) => {
    setAuditTraceModal({
      open: true,
      entityType: 'DistributedStorageCluster',
      entityIdentifier: cluster.clusterName,
      entityName: cluster.clusterName,
    })
  }, [])

  const handleDelete = useCallback(
    (cluster: DistributedStorageCluster) => {
      Modal.confirm({
        title: t('clusters.confirmDelete'),
        content: t('clusters.deleteWarning', { name: cluster.clusterName }),
        okText: t('common:actions.delete'),
        okType: 'danger',
        cancelText: t('common:actions.cancel'),
        onOk: () => onDeleteCluster(cluster),
      })
    },
    [onDeleteCluster, t],
  )

  const handleFunctionRun = useCallback(
    (cluster: DistributedStorageCluster & { preselectedFunction?: string }) => {
      onRunFunction(cluster)
    },
    [onRunFunction],
  )

  const columns = useMemo<ColumnsType<DistributedStorageCluster>>(
    () =>
      buildClusterColumns({
        t,
        expandedRowKeys,
        onManageMachines: handleManageMachines,
        onEditCluster,
        onDeleteCluster: handleDelete,
        onRunFunction: handleFunctionRun,
        onShowAuditTrace: handleAuditTrace,
      }),
    [
      expandedRowKeys,
      handleAuditTrace,
      handleDelete,
      handleManageMachines,
      handleFunctionRun,
      onEditCluster,
      t,
    ],
  )

  const toggleRow = useCallback(
    (clusterName: string) => {
      setExpandedRowKeys((prev) =>
        prev.includes(clusterName)
          ? prev.filter((key) => key !== clusterName)
          : [...prev, clusterName],
      )
    },
    [],
  )

  const expandedRowRender = useCallback(
    (record: DistributedStorageCluster) => <ClusterMachines cluster={record} />,
    [],
  )

  if (clusters.length === 0 && !loading) {
    return (
      <EmptyStateWrapper description={t('clusters.noClusters')}>
        <CreateClusterButton
          type="primary"
          data-testid="ds-create-cluster-empty"
          onClick={onCreateCluster}
        >
          {t('clusters.create')}
        </CreateClusterButton>
      </EmptyStateWrapper>
    )
  }

  return (
    <>
      <TableContainer>
        <Table<DistributedStorageCluster>
          data-testid="ds-cluster-table"
          columns={columns}
          dataSource={clusters}
          rowKey="clusterName"
          loading={loading}
          scroll={{ x: 'max-content' }}
          pagination={{
            showSizeChanger: true,
            showTotal: (total, range) =>
              t('common:table.showingRecords', {
                start: range[0],
                end: range[1],
                total,
              }),
          }}
          expandable={{
            expandedRowRender,
            expandedRowKeys,
            onExpandedRowsChange: (keys) =>
              setExpandedRowKeys(keys as string[]),
            expandIcon: () => null,
            expandRowByClick: false,
          }}
          onRow={(record) => ({
            'data-testid': `ds-cluster-row-${record.clusterName}`,
            onClick: (event) => {
              const target = event.target as HTMLElement
              if (
                target.closest('button') ||
                target.closest('.ant-dropdown-trigger')
              ) {
                return
              }
              toggleRow(record.clusterName)
            },
          })}
          rowClassName={() => 'cluster-row'}
        />
      </TableContainer>

      <AuditTraceModal
        open={auditTraceModal.open}
        onCancel={() =>
          setAuditTraceModal({
            open: false,
            entityType: null,
            entityIdentifier: null,
          })
        }
        entityType={auditTraceModal.entityType}
        entityIdentifier={auditTraceModal.entityIdentifier}
        entityName={auditTraceModal.entityName}
      />

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
            if (!selectedCluster) {
              return
            }
            setAssignModalOpen(false)
            const clusterName = selectedCluster.clusterName
            setSelectedCluster(null)
            if (expandedRowKeys.includes(clusterName)) {
              setExpandedRowKeys([])
              setTimeout(() => {
                setExpandedRowKeys([clusterName])
              }, 100)
            }
          }}
        />
      )}
    </>
  )
}
