import type { ColumnsType } from 'antd/es/table';
import type { TFunction } from 'i18next';
import {
  EditOutlined,
  DeleteOutlined,
  FunctionOutlined,
  HistoryOutlined,
} from '@/utils/optimizedIcons';
import type { DistributedStorageCluster } from '@/api/queries/distributedStorage';
import { createSorter } from '@/core';
import { ActionButtonGroup } from '@/components/common/ActionButtonGroup';
import { VersionTag, createActionColumn, createTruncatedColumn } from '@/components/common/columns';
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
  t: TFunction<'distributedStorage' | 'common' | 'machines'>;
  expandedRowKeys: string[];
  onManageMachines: (cluster: DistributedStorageCluster) => void;
  onEditCluster: (cluster: DistributedStorageCluster) => void;
  onDeleteCluster: (cluster: DistributedStorageCluster) => void;
  onRunFunction: (cluster: DistributedStorageCluster & { preselectedFunction?: string }) => void;
  onShowAuditTrace: (cluster: DistributedStorageCluster) => void;
}

export const buildClusterColumns = ({
  t,
  expandedRowKeys,
  onManageMachines,
  onEditCluster,
  onDeleteCluster,
  onRunFunction,
  onShowAuditTrace,
}: BuildClusterColumnsParams): ColumnsType<DistributedStorageCluster> => {
  const clusterNameColumn = createTruncatedColumn<DistributedStorageCluster>({
    title: t('clusters.clusterName'),
    dataIndex: 'clusterName',
    key: 'clusterName',
    sorter: createSorter<DistributedStorageCluster>('clusterName'),
  });

  const teamColumn = createTruncatedColumn<DistributedStorageCluster>({
    title: t('common:general.team'),
    dataIndex: 'teamName',
    key: 'teamName',
    width: 150,
    sorter: createSorter<DistributedStorageCluster>('teamName'),
  });

  return [
    {
      ...clusterNameColumn,
      render: (name: string, record: DistributedStorageCluster, index) => {
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
      render: (teamName: string, record: DistributedStorageCluster, index) => (
        <TeamTag>{teamColumn.render?.(teamName, record, index) as React.ReactNode}</TeamTag>
      ),
    },
    {
      title: t('machines:title'),
      key: 'machineCount',
      width: 160,
      align: 'center',
      render: (_: unknown, record: DistributedStorageCluster) => (
        <MachineManageCell>
          <MachineCountBadge cluster={record} />
          <ManageMachinesButton
            type="link"
            size="small"
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
    {
      title: t('common:general.vaultVersion'),
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 120,
      align: 'center',
      sorter: createSorter<DistributedStorageCluster>('vaultVersion'),
      render: (version: number) => (
        <VersionTag>{t('common:general.versionFormat', { version })}</VersionTag>
      ),
    },
    createActionColumn<DistributedStorageCluster>({
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
