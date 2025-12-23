import { useCallback, useMemo } from 'react';
import { Button, Dropdown, Empty, Flex, Modal, Space, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { CephCluster } from '@/api/queries/ceph';
import AuditTraceModal from '@/components/common/AuditTraceModal';
import { ExpandIcon } from '@/components/common/ExpandIcon';
import { buildDeleteMenuItem, buildDivider, buildEditMenuItem, buildTraceMenuItem } from '@/components/common/menuBuilders';
import { MobileCard } from '@/components/common/MobileCard';
import ResourceListView from '@/components/common/ResourceListView';
import { useDialogState, useExpandableTable, useTraceModal } from '@/hooks';
import { ManageClusterMachinesModal } from '@/pages/ceph/components/ManageClusterMachinesModal';
import { confirmAction } from '@/utils/confirmations';
import { CloudServerOutlined, FunctionOutlined, MoreOutlined } from '@/utils/optimizedIcons';
import { buildClusterColumns } from './columns';
import { ClusterMachines } from './components/ClusterMachines';
import { MachineCountBadge } from './components/MachineCountBadge';
import { getClusterFunctionMenuItems } from './menus';
import type { MenuProps } from 'antd';
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

  const mobileRender = useMemo(
    () => (record: CephCluster) => {
      const isExpanded = expandedRowKeys.includes(record.clusterName);

      const menuItems: MenuProps['items'] = [
        buildEditMenuItem(t, () => onEditCluster(record)),
        {
          key: 'manage',
          label: t('machines:manage'),
          icon: <CloudServerOutlined />,
          onClick: () => handleManageMachines(record),
        },
        buildTraceMenuItem(t, () => handleAuditTrace(record)),
        buildDivider(),
        buildDeleteMenuItem(t, () => handleDelete(record)),
      ];

      const actions = (
        <Space onClick={(e) => e.stopPropagation()}>
          <Dropdown
            menu={{
              items: getClusterFunctionMenuItems(t),
              onClick: ({ key }) => {
                if (key === 'advanced') {
                  handleFunctionRun(record);
                } else {
                  handleFunctionRun({ ...record, preselectedFunction: key });
                }
              },
            }}
            trigger={['click']}
          >
            <Button type="text" size="small" icon={<FunctionOutlined />} aria-label={t('common:actions.remote')} />
          </Dropdown>
          <Dropdown menu={{ items: menuItems }} trigger={['click']} placement="bottomRight">
            <Button type="text" size="small" icon={<MoreOutlined />} aria-label="Actions" />
          </Dropdown>
        </Space>
      );

      return (
        <MobileCard onClick={() => handleToggleRow(record.clusterName)} actions={actions}>
          <Space>
            <ExpandIcon isExpanded={isExpanded} />
            <CloudServerOutlined />
            <Typography.Text strong>{record.clusterName}</Typography.Text>
          </Space>
          <Flex gap={8} wrap align="center">
            <Tag bordered={false}>{record.teamName}</Tag>
            <MachineCountBadge cluster={record} />
          </Flex>
          <Typography.Text type="secondary" className="text-xs">
            {t('common:general.versionFormat', { version: record.vaultVersion || 0 })}
          </Typography.Text>
        </MobileCard>
      );
    },
    [t, expandedRowKeys, onEditCluster, handleManageMachines, handleAuditTrace, handleDelete, handleFunctionRun, handleToggleRow]
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
      <Flex className="overflow-hidden">
        <ResourceListView<CephCluster>
          data-testid="ds-cluster-table"
          columns={columns}
          data={clusters}
          rowKey="clusterName"
          loading={loading}
          pagination={{
            showSizeChanger: true,
            showTotal: (total, range) =>
              t('common:table.showingRecords', {
                start: range[0],
                end: range[1],
                total,
              }),
          }}
          mobileRender={mobileRender}
          expandable={{
            expandedRowRender,
            expandedRowKeys,
            onExpandedRowsChange: (keys: readonly React.Key[]) =>
              setExpandedRowKeys(keys as string[]),
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
      </Flex>

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
