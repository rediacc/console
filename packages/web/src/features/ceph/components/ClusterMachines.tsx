import React, { useMemo } from 'react';
import { Empty, Flex, Table, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { useGetCephClusterMachines } from '@/api/api-hooks.generated';
import { RESPONSIVE_HIDE_XS } from '@/components/common/columns';
import { createSorter, formatTimestampAsIs } from '@/platform';
import { DesktopOutlined } from '@/utils/optimizedIcons';
import type {
  GetCephClusterMachines_ResultSet1,
  GetCephClusters_ResultSet1,
} from '@rediacc/shared/types';
import type { ColumnsType } from 'antd/es/table';

interface ClusterMachinesProps {
  cluster: GetCephClusters_ResultSet1;
}

export const ClusterMachines: React.FC<ClusterMachinesProps> = ({ cluster }) => {
  const { t } = useTranslation('ceph');
  const { data: machines = [], isLoading } = useGetCephClusterMachines(cluster.clusterName ?? '');

  const machineColumns: ColumnsType<GetCephClusterMachines_ResultSet1> = useMemo(
    () => [
      {
        title: t('machines.machineName'),
        dataIndex: 'machineName',
        key: 'machineName',
        sorter: createSorter<GetCephClusterMachines_ResultSet1>('machineName'),
        render: (name: string) => (
          <Flex align="center">
            <DesktopOutlined />
            <Typography.Text>{name}</Typography.Text>
          </Flex>
        ),
      },
      {
        title: t('machines.bridgeName'),
        dataIndex: 'bridgeName',
        key: 'bridgeName',
        sorter: createSorter<GetCephClusterMachines_ResultSet1>('bridgeName'),
        render: (name: string) => <Tag bordered={false}>{name}</Tag>,
      },
      {
        title: t('machines.assignedDate'),
        dataIndex: 'assignedDate',
        key: 'assignedDate',
        responsive: RESPONSIVE_HIDE_XS,
        render: (date: string | null) => (
          <Typography.Text>{date ? formatTimestampAsIs(date, 'datetime') : '-'}</Typography.Text>
        ),
      },
    ],
    [t]
  );

  return (
    <Flex vertical data-testid={`cluster-expanded-row-${cluster.clusterName}`}>
      <Typography.Title level={4}>{t('clusters.assignedMachines')}</Typography.Title>
      {machines.length === 0 && !isLoading ? (
        <Empty description={t('clusters.noMachinesAssigned')} />
      ) : (
        <Flex className="overflow-hidden">
          <Table<GetCephClusterMachines_ResultSet1>
            data-testid={`ds-cluster-machines-table-${cluster.clusterName}`}
            columns={machineColumns}
            dataSource={machines}
            rowKey="machineName"
            loading={isLoading}
            pagination={false}
            scroll={{ x: 'max-content' }}
          />
        </Flex>
      )}
    </Flex>
  );
};
