import { useCallback, useMemo } from 'react';
import { Button, Empty, Modal, Space, Table } from 'antd';
import { useTranslation } from 'react-i18next';
import { CephCluster } from '@/api/queries/ceph';
import AuditTraceModal from '@/components/common/AuditTraceModal';
import { useDialogState, useExpandableTable, useTraceModal } from '@/hooks';
import { ManageClusterMachinesModal } from '@/pages/ceph/components/ManageClusterMachinesModal';
import { confirmAction } from '@/utils/confirmations';
import { buildClusterColumns } from './columns';
import { ClusterMachines } from './components/ClusterMachines';
import type { ColumnsType } from 'antd/es/table';

interface ClusterTableProps {
  clusters: CephCluster[];
  loading: boolean;
  onCreateCluster: () => void;
  onEditCluster: (cluster: CephCluster) => void;
  onDeleteCluster: (cluster: CephCluster) => void;
  onRunFunction: (cluster: CephCluster) => void;
}

export const ClusterTable: React.FC<ClusterTableProps> = ({
  clusters,
  loading,
  onCreateCluster,
  onEditCluster,
  onDeleteCluster,
  onRunFunction,
}) => {
  const { t } = useTranslation(['ceph', 'common', 'machines']);
  const [modal, contextHolder] = Modal.useModal();
  const { expandedRowKeys, toggleRow, setExpandedRowKeys } = useExpandableTable();
  const manageMachinesModal = useDialogState<CephCluster>();
  const auditTrace = useTraceModal();

  const handleManageMachines = useCallback(
    (cluster: CephCluster) => {
      manageMachinesModal.open(cluster);
    },
    [manageMachinesModal]
  );

  const handleAuditTrace = useCallback(
    (cluster: CephCluster) => {
      auditTrace.open({
        entityType: 'CephCluster',
        entityIdentifier: cluster.clusterName,
        entityName: cluster.clusterName,
      });
    },
    [auditTrace]
  );

  const handleDelete = useCallback(
    (cluster: CephCluster) => {
      confirmAction({
        modal,
        title: t('clusters.confirmDelete') as string,
        content: t('clusters.deleteWarning', { name: cluster.clusterName }) as string,
        okText: t('common:actions.delete') as string,
        okType: 'danger',
        cancelText: t('common:actions.cancel') as string,
        onConfirm: async () => {
          onDeleteCluster(cluster);
        },
      });
    },
    [modal, onDeleteCluster, t]
  );

  const handleFunctionRun = useCallback(
    (cluster: CephCluster & { preselectedFunction?: string }) => {
      onRunFunction(cluster);
    },
    [onRunFunction]
  );

  const columns = useMemo<ColumnsType<CephCluster>>(
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
    ]
  );

  const handleToggleRow = useCallback(
    (clusterName: string) => {
      toggleRow(clusterName);
    },
    [toggleRow]
  );

  const expandedRowRender = useCallback(
    (record: CephCluster) => <ClusterMachines cluster={record} />,
    []
  );

  if (clusters.length === 0 && !loading) {
    return (
      <Space direction="vertical" align="center">
        <Empty description={t('clusters.noClusters')} />
        <Button type="primary" data-testid="ds-create-cluster-empty" onClick={onCreateCluster}>
          {t('clusters.create')}
        </Button>
      </Space>
    );
  }

  return (
    <>
      {contextHolder}
      <div style={{ overflow: 'hidden' }}>
        <Table<CephCluster>
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
            onExpandedRowsChange: (keys) => setExpandedRowKeys(keys as string[]),
            expandIcon: () => null,
            expandRowByClick: false,
          }}
          onRow={(record) => ({
            'data-testid': `ds-cluster-row-${record.clusterName}`,
            onClick: (event) => {
              const target = event.target as HTMLElement;
              if (target.closest('button') || target.closest('.ant-dropdown-trigger')) {
                return;
              }
              handleToggleRow(record.clusterName);
            },
          })}
          rowClassName={() => 'cluster-row'}
        />
      </div>

      <AuditTraceModal
        open={auditTrace.isOpen}
        onCancel={auditTrace.close}
        entityType={auditTrace.entityType}
        entityIdentifier={auditTrace.entityIdentifier}
        entityName={auditTrace.entityName}
      />

      {manageMachinesModal.state.data && (
        <ManageClusterMachinesModal
          open={manageMachinesModal.isOpen}
          clusterName={manageMachinesModal.state.data.clusterName}
          teamName={manageMachinesModal.state.data.teamName || ''}
          onCancel={() => {
            manageMachinesModal.close();
          }}
          onSuccess={() => {
            const clusterName = manageMachinesModal.state.data?.clusterName;
            manageMachinesModal.close();
            if (clusterName && expandedRowKeys.includes(clusterName)) {
              setExpandedRowKeys([]);
              setTimeout(() => {
                setExpandedRowKeys([clusterName]);
              }, 100);
            }
          }}
        />
      )}
    </>
  );
};
