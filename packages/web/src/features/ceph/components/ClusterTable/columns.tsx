import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { GetCephClusters_ResultSet1 } from '@rediacc/shared/types';
import { Button, Flex, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ActionButtonGroup } from '@/components/common/ActionButtonGroup';
import {
  createTruncatedColumn,
  createVersionColumn,
  RESPONSIVE_HIDE_XS,
} from '@/components/common/columns';
import { createActionColumn } from '@/components/common/columns/factories/action';
import { buildClusterMenuItems } from '@/features/ceph/utils/menuItems';
import { createSorter } from '@/platform';
import {
  CloudServerOutlined,
  DeleteOutlined,
  EditOutlined,
  FunctionOutlined,
  HistoryOutlined,
  RightOutlined,
} from '@/utils/optimizedIcons';
import { ClusterMachineCountBadge } from '../ClusterMachineCountBadge';

interface BuildClusterColumnsParams {
  t: TypedTFunction;
  expandedRowKeys: string[];
  onManageMachines: (cluster: GetCephClusters_ResultSet1) => void;
  onEditCluster: (cluster: GetCephClusters_ResultSet1) => void;
  onDeleteCluster: (cluster: GetCephClusters_ResultSet1) => void;
  onRunFunction: (cluster: GetCephClusters_ResultSet1 & { preselectedFunction?: string }) => void;
  onShowAuditTrace: (cluster: GetCephClusters_ResultSet1) => void;
}

export const buildClusterColumns = ({
  t,
  expandedRowKeys,
  onManageMachines,
  onEditCluster,
  onDeleteCluster,
  onRunFunction,
  onShowAuditTrace,
}: BuildClusterColumnsParams): ColumnsType<GetCephClusters_ResultSet1> => {
  const clusterNameColumn = createTruncatedColumn<GetCephClusters_ResultSet1>({
    title: t('clusters.clusterName'),
    dataIndex: 'clusterName',
    key: 'clusterName',
    sorter: createSorter<GetCephClusters_ResultSet1>('clusterName'),
  });

  const teamColumn = createTruncatedColumn<GetCephClusters_ResultSet1>({
    title: t('common:general.team'),
    dataIndex: 'teamName',
    key: 'teamName',
    width: 150,
    sorter: createSorter<GetCephClusters_ResultSet1>('teamName'),
  });

  return [
    {
      ...clusterNameColumn,
      render: (name: string, record: GetCephClusters_ResultSet1, index) => {
        const isExpanded = expandedRowKeys.includes(record.clusterName ?? '');
        return (
          <Flex align="center">
            <RightOutlined className={`expand-icon ${isExpanded ? 'expand-icon-rotated' : ''}`} />
            <CloudServerOutlined />
            <Typography.Text>
              {clusterNameColumn.render?.(name, record, index) as React.ReactNode}
            </Typography.Text>
          </Flex>
        );
      },
    },
    {
      ...teamColumn,
      responsive: RESPONSIVE_HIDE_XS,
      render: (teamName: string, record: GetCephClusters_ResultSet1, index) => (
        <Tag bordered={false}>
          {teamColumn.render?.(teamName, record, index) as React.ReactNode}
        </Tag>
      ),
    },
    {
      title: t('machines:title'),
      key: 'machineCount',
      width: 160,
      align: 'center',
      render: (_: unknown, record: GetCephClusters_ResultSet1) => (
        <Flex align="center">
          <ClusterMachineCountBadge cluster={record} />
          <Button
            data-testid={`ds-cluster-manage-machines-${record.clusterName}`}
            onClick={(event) => {
              event.stopPropagation();
              onManageMachines(record);
            }}
          >
            {t('machines:manage')}
          </Button>
        </Flex>
      ),
    },
    {
      ...createVersionColumn<GetCephClusters_ResultSet1>({
        title: t('common:general.vaultVersion'),
        dataIndex: 'vaultVersion',
        key: 'vaultVersion',
        width: 120,
        sorter: createSorter<GetCephClusters_ResultSet1>('vaultVersion'),
        formatVersion: (version: number) => t('common:general.versionFormat', { version }),
      }),
      responsive: RESPONSIVE_HIDE_XS,
    },
    createActionColumn<GetCephClusters_ResultSet1>({
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
              dropdownItems: buildClusterMenuItems(t),
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
