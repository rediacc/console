import { useCallback, useMemo } from 'react';
import { Modal } from 'antd';
import { useTranslation } from 'react-i18next';
import { CephPool, CephCluster } from '@/api/queries/ceph';
import AuditTraceModal from '@/components/common/AuditTraceModal';
import { RediaccButton } from '@/components/ui';
import { useTraceModal, useExpandableTable } from '@/hooks';
import RbdImageTable from '@/pages/ceph/components/RbdImageTable';
import { EmptyStatePanel } from '@/styles/primitives';
import { confirmAction } from '@/utils/confirmations';
import { buildPoolColumns } from './columns';
import { ClusterPoolsCard } from './components/ClusterPoolsCard';

interface PoolTableProps {
  pools: CephPool[];
  clusters: CephCluster[];
  loading: boolean;
  onCreatePool: () => void;
  onEditPool: (pool: CephPool) => void;
  onDeletePool: (pool: CephPool) => void;
  onRunFunction: (pool: CephPool) => void;
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
  const { t } = useTranslation(['ceph', 'common']);
  const [modal, contextHolder] = Modal.useModal();
  const { expandedRowKeys, toggleRow, setExpandedRowKeys } = useExpandableTable();
  const auditTrace = useTraceModal();

  const poolsByCluster = useMemo(() => {
    return pools.reduce<Record<string, CephPool[]>>((acc, pool) => {
      if (!acc[pool.clusterName]) {
        acc[pool.clusterName] = [];
      }
      acc[pool.clusterName].push(pool);
      return acc;
    }, {});
  }, [pools]);

  const clusterMap = useMemo(() => {
    const map = new Map<string, CephCluster>();
    clusters.forEach((cluster) => {
      map.set(cluster.clusterName, cluster);
    });
    return map;
  }, [clusters]);

  const handleDelete = useCallback(
    (pool: CephPool) => {
      confirmAction({
        modal,
        title: t('pools.confirmDelete') as string,
        content: t('pools.deleteWarning', { name: pool.poolName }) as string,
        okText: t('common:actions.delete') as string,
        okType: 'danger',
        cancelText: t('common:actions.cancel') as string,
        onConfirm: async () => {
          onDeletePool(pool);
        },
      });
    },
    [modal, onDeletePool, t]
  );

  const handleAuditTrace = useCallback(
    (pool: CephPool) => {
      auditTrace.open({
        entityType: 'CephPool',
        entityIdentifier: pool.poolName,
        entityName: pool.poolName,
      });
    },
    [auditTrace]
  );

  const handleRunFunction = useCallback(
    (pool: CephPool & { preselectedFunction?: string }) => {
      onRunFunction(pool);
    },
    [onRunFunction]
  );

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
    [expandedRowKeys, handleAuditTrace, handleDelete, handleRunFunction, onEditPool, t]
  );

  const expandedRowRender = useCallback((record: CephPool) => {
    const teamFilter = record.teamName;
    return <RbdImageTable pool={record} teamFilter={teamFilter} />;
  }, []);

  const handleToggleRow = useCallback(
    (poolGuid?: string) => {
      if (!poolGuid) {
        return;
      }
      toggleRow(poolGuid);
    },
    [toggleRow]
  );

  const handleExpandedRowsChange = useCallback(
    (clusterKeys: string[], keys: string[]) => {
      setExpandedRowKeys((prev) => {
        const filtered = prev.filter((key) => !clusterKeys.includes(key));
        return [...filtered, ...keys];
      });
    },
    [setExpandedRowKeys]
  );

  if (pools.length === 0 && !loading) {
    return (
      <EmptyStatePanel
        description={t('pools.noPools')}
        $marginBottom="XL"
        action={
          <RediaccButton onClick={onCreatePool} data-testid="ds-create-pool-empty">
            {t('pools.create')}
          </RediaccButton>
        }
      />
    );
  }

  return (
    <>
      {contextHolder}
      {Object.entries(poolsByCluster).map(([clusterName, clusterPools]) => {
        const cluster = clusterMap.get(clusterName);
        return (
          <ClusterPoolsCard
            key={clusterName}
            clusterName={clusterName}
            teamName={cluster?.teamName ?? undefined}
            pools={clusterPools}
            loading={loading}
            columns={columns}
            expandedRowKeys={expandedRowKeys}
            onExpandedRowsChange={handleExpandedRowsChange}
            expandedRowRender={expandedRowRender}
            onToggleRow={handleToggleRow}
            t={t}
          />
        );
      })}

      <AuditTraceModal
        open={auditTrace.isOpen}
        onCancel={auditTrace.close}
        entityType={auditTrace.entityType}
        entityIdentifier={auditTrace.entityIdentifier}
        entityName={auditTrace.entityName}
      />
    </>
  );
};
