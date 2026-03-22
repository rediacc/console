import type { GetCephClusters_ResultSet1, GetCephPools_ResultSet1 } from '@rediacc/shared/types';
import type { MenuProps } from 'antd';
import { Button, Dropdown, Empty, Modal, Space, Typography } from 'antd';
import { useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import AuditTraceModal from '@/components/common/AuditTraceModal';
import { ExpandIcon } from '@/components/common/ExpandIcon';
import { MobileCard } from '@/components/common/MobileCard';
import {
  buildDeleteMenuItem,
  buildDivider,
  buildEditMenuItem,
  buildTraceMenuItem,
} from '@/components/common/menuBuilders';
import { ResourceActionsDropdown } from '@/components/common/ResourceActionsDropdown';
import RbdImageTable from '@/features/ceph/components/RbdImageTable';
import { buildPoolMenuItems } from '@/features/ceph/utils/menuItems';
import { useExpandableTable, useTraceModal } from '@/hooks';
import { confirmAction } from '@/utils/confirmations';
import { DatabaseOutlined, FunctionOutlined } from '@/utils/optimizedIcons';
import { ClusterPoolsCard } from '../ClusterPoolsCard';
import { buildPoolColumns } from './columns';

interface PoolTableProps {
  pools: GetCephPools_ResultSet1[];
  clusters: GetCephClusters_ResultSet1[];
  loading: boolean;
  onCreatePool: () => void;
  onEditPool: (pool: GetCephPools_ResultSet1) => void;
  onDeletePool: (pool: GetCephPools_ResultSet1) => void;
  onRunFunction: (pool: GetCephPools_ResultSet1) => void;
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
    return pools.reduce<Record<string, GetCephPools_ResultSet1[]>>((acc, pool) => {
      const clusterName = pool.clusterName ?? '';
      const existing = acc[clusterName] as GetCephPools_ResultSet1[] | undefined;
      if (existing === undefined) {
        acc[clusterName] = [];
      }
      acc[clusterName].push(pool);
      return acc;
    }, {});
  }, [pools]);

  const clusterMap = useMemo(() => {
    const map = new Map<string, GetCephClusters_ResultSet1>();
    clusters.forEach((cluster) => {
      map.set(cluster.clusterName ?? '', cluster);
    });
    return map;
  }, [clusters]);

  const handleDelete = useCallback(
    (pool: GetCephPools_ResultSet1) => {
      confirmAction({
        modal,
        title: t('pools.confirmDelete'),
        content: t('pools.deleteWarning', { name: pool.poolName }),
        okText: t('common:actions.delete'),
        okType: 'danger',
        cancelText: t('common:actions.cancel'),
        onConfirm: async () => {
          await Promise.resolve(onDeletePool(pool));
        },
      });
    },
    [modal, onDeletePool, t]
  );

  const handleAuditTrace = useCallback(
    (pool: GetCephPools_ResultSet1) => {
      auditTrace.open({
        entityType: 'CephPool',
        entityIdentifier: pool.poolName ?? '',
        entityName: pool.poolName ?? '',
      });
    },
    [auditTrace]
  );

  const handleRunFunction = useCallback(
    (pool: GetCephPools_ResultSet1 & { preselectedFunction?: string }) => {
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

  const handleToggleRow = useCallback(
    (poolGuid?: string) => {
      if (!poolGuid) {
        return;
      }
      toggleRow(poolGuid);
    },
    [toggleRow]
  );

  const mobileRender = useMemo(
    // eslint-disable-next-line react/display-name
    () => (record: GetCephPools_ResultSet1) => {
      const isExpanded = expandedRowKeys.includes(record.poolGuid ?? '');

      const menuItems: MenuProps['items'] = [
        buildEditMenuItem(t, () => onEditPool(record)),
        buildTraceMenuItem(t, () => handleAuditTrace(record)),
        buildDivider(),
        buildDeleteMenuItem(t, () => handleDelete(record)),
      ];

      const actions = (
        <Space onClick={(e) => e.stopPropagation()}>
          <Dropdown
            menu={{
              items: buildPoolMenuItems(t),
              onClick: ({ key }) => {
                if (key === 'advanced') {
                  handleRunFunction(record);
                } else {
                  handleRunFunction({ ...record, preselectedFunction: key });
                }
              },
            }}
            trigger={['click']}
          >
            <Button
              type="text"
              size="small"
              icon={<FunctionOutlined />}
              aria-label={t('common:actions.remote')}
            />
          </Dropdown>
          <ResourceActionsDropdown menuItems={menuItems} />
        </Space>
      );

      return (
        <MobileCard onClick={() => handleToggleRow(record.poolGuid ?? undefined)} actions={actions}>
          <Space>
            <ExpandIcon isExpanded={isExpanded} />
            <DatabaseOutlined />
            <Typography.Text strong>{record.poolName}</Typography.Text>
          </Space>
          <Typography.Text type="secondary" className="text-xs">
            {t('common:general.versionFormat', { version: record.vaultVersion ?? 0 })}
          </Typography.Text>
        </MobileCard>
      );
    },
    [
      t,
      expandedRowKeys,
      onEditPool,
      handleAuditTrace,
      handleDelete,
      handleRunFunction,
      handleToggleRow,
    ]
  );

  const expandedRowRender = useCallback((record: GetCephPools_ResultSet1) => {
    const teamFilter = record.teamName ?? '';
    return <RbdImageTable pool={record} teamFilter={teamFilter} />;
  }, []);

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
      <Space direction="vertical" align="center">
        <Empty description={t('pools.noPools')} />
        <Button type="primary" onClick={onCreatePool} data-testid="ds-create-pool-empty">
          {t('pools.create')}
        </Button>
      </Space>
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
            mobileRender={mobileRender}
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
