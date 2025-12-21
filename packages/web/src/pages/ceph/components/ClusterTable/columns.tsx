import { Button, Flex, Tag, Typography } from 'antd';
import type { CephCluster } from '@/api/queries/ceph';
import { ActionButtonGroup } from '@/components/common/ActionButtonGroup';
import {
  createActionColumn,
  createTruncatedColumn,
  createVersionColumn,
} from '@/components/common/columns';
import { createSorter } from '@/platform';
import {
  DeleteOutlined,
  EditOutlined,
  FunctionOutlined,
  HistoryOutlined,
  RightOutlined,
  CloudServerOutlined,
} from '@/utils/optimizedIcons';
import { MachineCountBadge } from './components/MachineCountBadge';
import { getClusterFunctionMenuItems } from './menus';
import type { ColumnsType } from 'antd/es/table';
import type { TFunction } from 'i18next';

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
          <Flex align="center" gap={8}>
            <RightOutlined
              style={{
                transform: isExpanded ? 'rotate(90deg)' : undefined,
                transition: 'transform 0.2s ease',
              }}
            />
            <CloudServerOutlined style={{ fontSize: 16 }} />
            <Typography.Text style={{ fontWeight: 400 }}>
              {clusterNameColumn.render?.(name, record, index) as React.ReactNode}
            </Typography.Text>
          </Flex>
        );
      },
    },
    {
      ...teamColumn,
      render: (teamName: string, record: CephCluster, index) => (
        <Tag bordered={false} color="success">
          {teamColumn.render?.(teamName, record, index) as React.ReactNode}
        </Tag>
      ),
    },
    {
      title: t('machines:title'),
      key: 'machineCount',
      width: 160,
      align: 'center',
      render: (_: unknown, record: CephCluster) => (
        <Flex align="center" gap={8}>
          <MachineCountBadge cluster={record} />
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
