import { useCallback, useMemo, useState } from 'react'
import { Modal } from 'antd'
import { useTranslation } from 'react-i18next'
import {
  DistributedStoragePool,
  DistributedStorageCluster,
} from '@/api/queries/distributedStorage'
import AuditTraceModal from '@/components/common/AuditTraceModal'
import RbdImageList from '../RbdImageList'
import { buildPoolColumns } from './columns'
import { ClusterPoolsCard } from './components/ClusterPoolsCard'
import { EmptyStateWrapper, CreatePoolButton } from './styles'

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
  const [expandedRowKeys, setExpandedRowKeys] = useState<string[]>([])
  const [auditTraceModal, setAuditTraceModal] = useState<{
    open: boolean
    entityType: string | null
    entityIdentifier: string | null
    entityName?: string
  }>({ open: false, entityType: null, entityIdentifier: null })

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
      Modal.confirm({
        title: t('pools.confirmDelete'),
        content: t('pools.deleteWarning', { name: pool.poolName }),
        okText: t('common:actions.delete'),
        okType: 'danger',
        cancelText: t('common:actions.cancel'),
        onOk: () => onDeletePool(pool),
      })
    },
    [onDeletePool, t],
  )

  const handleAuditTrace = useCallback((pool: DistributedStoragePool) => {
    setAuditTraceModal({
      open: true,
      entityType: 'DistributedStoragePool',
      entityIdentifier: pool.poolName || '',
      entityName: pool.poolName,
    })
  }, [])

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
      return <RbdImageList pool={record} teamFilter={teamFilter} />
    },
    [],
  )

  const handleToggleRow = useCallback((poolGuid?: string) => {
    if (!poolGuid) {
      return
    }
    setExpandedRowKeys((prev) =>
      prev.includes(poolGuid)
        ? prev.filter((key) => key !== poolGuid)
        : [...prev, poolGuid],
    )
  }, [])

  const handleExpandedRowsChange = useCallback(
    (clusterKeys: string[], keys: string[]) => {
      setExpandedRowKeys((prev) => {
        const filtered = prev.filter((key) => !clusterKeys.includes(key))
        return [...filtered, ...keys]
      })
    },
    [],
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
        open={auditTraceModal.open}
        onCancel={() =>
          setAuditTraceModal({
            open: false,
            entityType: null,
            entityIdentifier: null,
          })
        }
        entityType={auditTraceModal.entityType || ''}
        entityIdentifier={auditTraceModal.entityIdentifier || ''}
        entityName={auditTraceModal.entityName}
      />
    </>
  )
}
