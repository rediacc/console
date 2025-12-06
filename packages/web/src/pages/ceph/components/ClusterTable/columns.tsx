import type { ColumnsType } from 'antd/es/table';
import type { TFunction } from 'i18next';
import {
  EditOutlined,
  DeleteOutlined,
  FunctionOutlined,
  HistoryOutlined,
} from '@/utils/optimizedIcons';
import type { CephCluster } from '@/api/queries/ceph';
import { createSorter } from '@/core';
import { ActionButtonGroup } from '@/components/common/ActionButtonGroup';
import {
  createActionColumn,
  createTruncatedColumn,
  createVersionColumn,
} from '@/components/common/columns';
import { MachineCountBadge } from './components/MachineCountBadge';
import { getClusterFunctionMenuItems } from './menus';
import {
  ClusterNameCell,
  ExpandIcon,
  ClusterIcon,
  ClusterNameText,
  TeamTag,
  ManageMachinesButton,
  MachineManageCell,
} from './styles';

interface BuildClusterColumnsParams {
  t: TFunction<'ceph' | 'common' | 'machines'>;
  expandedRowKeys: string[];
  onManageMachines: (cluster: CephCluster) => void;
  onEditCluster: (cluster: CephCluster) => void;
  onDeleteCluster: (cluster: CephCluster) => void;
  onRunFunction: (cluster: CephCluster & { preselectedFunction?: string }) => void;
  onShowAuditTrace: (cluster: CephCluster) => void;
}

export const buildClusterColumns = ({
  t,
  expandedRowKeys,
  onManageMachines,
  onEditCluster,
  onDeleteCluster,
  onRunFunction,
  onShowAuditTrace,
}: BuildClusterColumnsParams): ColumnsType<CephCluster> => {
  const clusterNameColumn = createTruncatedColumn<CephCluster>({
    title: t('clusters.clusterName'),
    dataIndex: 'clusterName',
    key: 'clusterName',
    sorter: createSorter<CephCluster>('clusterName'),
  });

  const teamColumn = createTruncatedColumn<CephCluster>({
    title: t('common:general.team'),
    dataIndex: 'teamName',
    key: 'teamName',
    width: 150,
    sorter: createSorter<CephCluster>('teamName'),
  });

  return [
    {
      ...clusterNameColumn,
      render: (name: string, record: CephCluster, index) => {
        const isExpanded = expandedRowKeys.includes(record.clusterName);
        return (
          <ClusterNameCell>
            <ExpandIcon $expanded={isExpanded} />
            <ClusterIcon />
            <ClusterNameText>
              {clusterNameColumn.render?.(name, record, index) as React.ReactNode}
            </ClusterNameText>
          </ClusterNameCell>
        );
      },
    },
    {
      ...teamColumn,
      render: (teamName: string, record: CephCluster, index) => (
        <TeamTag>{teamColumn.render?.(teamName, record, index) as React.ReactNode}</TeamTag>
      ),
    },
    {
      title: t('machines:title'),
      key: 'machineCount',
      width: 160,
      align: 'center',
      render: (_: unknown, record: CephCluster) => (
        <MachineManageCell>
          <MachineCountBadge cluster={record} />
          <ManageMachinesButton
            size="sm"
            data-testid={`ds-cluster-manage-machines-${record.clusterName}`}
            onClick={(event) => {
              event.stopPropagation();
              onManageMachines(record);
            }}
          >
            {t('machines:manage')}
          </ManageMachinesButton>
        </MachineManageCell>
      ),
    },
    createVersionColumn<CephCluster>({
      title: t('common:general.vaultVersion'),
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 120,
      sorter: createSorter<CephCluster>('vaultVersion'),
      formatVersion: (version: number) => t('common:general.versionFormat', { version }),
    }),
    createActionColumn<CephCluster>({
      width: 260,
      renderActions: (record) => (
        <ActionButtonGroup
          buttons={[
            {
              type: 'edit',
              icon: <EditOutlined />,
              tooltip: 'common:actions.edit',
              onClick: () => onEditCluster(record),
            },
            {
              type: 'function-dropdown',
              icon: <FunctionOutlined />,
              tooltip: 'common:actions.remote',
              dropdownItems: getClusterFunctionMenuItems(t),
              onDropdownClick: (key) => {
                if (key === 'advanced') {
                  onRunFunction(record);
                } else {
                  onRunFunction({ ...record, preselectedFunction: key });
                }
              },
            },
            {
              type: 'trace',
              icon: <HistoryOutlined />,
              tooltip: 'common:actions.trace',
              onClick: () => onShowAuditTrace(record),
              variant: 'default',
            },
            {
              type: 'delete',
              icon: <DeleteOutlined />,
              tooltip: 'common:actions.delete',
              onClick: () => onDeleteCluster(record),
              danger: true,
            },
          ]}
          record={record}
          idField="clusterName"
          testIdPrefix="ds-cluster"
          t={t}
        />
      ),
    }),
  ];
};
