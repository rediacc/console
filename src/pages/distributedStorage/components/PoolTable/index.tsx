import { useCallback, useMemo } from 'react'
import { Modal } from 'antd'
import { useTranslation } from 'react-i18next'
import {
  DistributedStoragePool,
  DistributedStorageCluster,
} from '@/api/queries/distributedStorage'
import AuditTraceModal from '@/components/common/AuditTraceModal'
import RbdImageTable from '../RbdImageTable'
import { buildPoolColumns } from './columns'
import { ClusterPoolsCard } from './components/ClusterPoolsCard'
import { useTraceModal, useExpandableTable } from '@/hooks'
import { EmptyStateWrapper, CreatePoolButton } from './styles'
import { confirmAction } from '@/utils/confirmations'

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
  onRunFunction,
}) => {
  const { t } = useTranslation(['distributedStorage', 'common'])
  const [modal, contextHolder] = Modal.useModal()
  const { expandedRowKeys, toggleRow, setExpandedRowKeys } = useExpandableTable()
  const auditTrace = useTraceModal()

  const poolsByCluster = useMemo(() => {
    return pools.reduce<Record<string, DistributedStoragePool[]>>(
      (acc, pool) => {
        if (!acc[pool.clusterName]) {
          acc[pool.clusterName] = []
        }
        acc[pool.clusterName].push(pool)
        return acc
      },
      {},
    )
  }, [pools])

  const clusterMap = useMemo(() => {
    const map = new Map<string, DistributedStorageCluster>()
    clusters.forEach((cluster) => {
      map.set(cluster.clusterName, cluster)
    })
    return map
  }, [clusters])

  const handleDelete = useCallback(
    (pool: DistributedStoragePool) => {
      confirmAction({
        modal,
        title: t('pools.confirmDelete') as string,
        content: t('pools.deleteWarning', { name: pool.poolName }) as string,
        okText: t('common:actions.delete') as string,
        okType: 'danger',
        cancelText: t('common:actions.cancel') as string,
        onConfirm: async () => {
          onDeletePool(pool)
        },
      })
    },
    [modal, onDeletePool, t],
  )

  const handleAuditTrace = useCallback((pool: DistributedStoragePool) => {
    auditTrace.open({
      entityType: 'DistributedStoragePool',
      entityIdentifier: pool.poolName,
      entityName: pool.poolName,
    })
  }, [auditTrace])

  const handleRunFunction = useCallback(
    (pool: DistributedStoragePool & { preselectedFunction?: string }) => {
      onRunFunction(pool)
    },
    [onRunFunction],
  )

  const columns = useMemo(
    () =>
      buildPoolColumns({
        t,
        expandedRowKeys,
        onEditPool,
        onDeletePool: handleDelete,
        onRunFunction: handleRunFunction,
        onShowAuditTrace: handleAuditTrace,
      }),
    [
      expandedRowKeys,
      handleAuditTrace,
      handleDelete,
      handleRunFunction,
      onEditPool,
      t,
    ],
  )

  const expandedRowRender = useCallback(
    (record: DistributedStoragePool) => {
      const teamFilter = record.teamName
      return <RbdImageTable pool={record} teamFilter={teamFilter} />
    },
    [],
  )

  const handleToggleRow = useCallback((poolGuid?: string) => {
    if (!poolGuid) {
      return
    }
    toggleRow(poolGuid)
  }, [toggleRow])

  const handleExpandedRowsChange = useCallback(
    (clusterKeys: string[], keys: string[]) => {
      setExpandedRowKeys((prev) => {
        const filtered = prev.filter((key) => !clusterKeys.includes(key))
        return [...filtered, ...keys]
      })
    },
    [setExpandedRowKeys],
  )

  if (pools.length === 0 && !loading) {
    return (
      <EmptyStateWrapper description={t('pools.noPools')}>
        <CreatePoolButton
          type="primary"
          onClick={onCreatePool}
          data-testid="ds-create-pool-empty"
        >
          {t('pools.create')}
        </CreatePoolButton>
      </EmptyStateWrapper>
    )
  }

  return (
    <>
      {contextHolder}
      {Object.entries(poolsByCluster).map(([clusterName, clusterPools]) => {
        const cluster = clusterMap.get(clusterName)
        return (
          <ClusterPoolsCard
            key={clusterName}
            clusterName={clusterName}
            teamName={cluster?.teamName}
            pools={clusterPools}
            loading={loading}
            columns={columns}
            expandedRowKeys={expandedRowKeys}
            onExpandedRowsChange={handleExpandedRowsChange}
            expandedRowRender={expandedRowRender}
            onToggleRow={handleToggleRow}
            t={t}
          />
        )
      })}

      <AuditTraceModal
        open={auditTrace.isOpen}
        onCancel={auditTrace.close}
        entityType={auditTrace.entityType}
        entityIdentifier={auditTrace.entityIdentifier}
        entityName={auditTrace.entityName}
      />
    </>
  )
}
