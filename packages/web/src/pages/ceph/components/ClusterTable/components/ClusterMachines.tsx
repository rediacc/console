import React, { useMemo } from 'react';
import { Empty, Flex, Table, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { CephCluster, CephClusterMachine, useCephClusterMachines } from '@/api/queries/ceph';
import { createSorter, formatTimestampAsIs } from '@/platform';
import { DesktopOutlined } from '@/utils/optimizedIcons';

interface ClusterMachinesProps {
  cluster: CephCluster;
}

export const ClusterMachines: React.FC<ClusterMachinesProps> = ({ cluster }) => {
  const { t } = useTranslation('ceph');
  const { data: machines = [], isLoading } = useCephClusterMachines(cluster.clusterName, true);

  const machineColumns = useMemo(
    () => [
      {
        title: t('machines.machineName'),
        dataIndex: 'machineName',
        key: 'machineName',
        sorter: createSorter<CephClusterMachine>('machineName'),
        render: (name: string) => (
          <Flex align="center" gap={8}>
            <DesktopOutlined />
            <Typography.Text>{name}</Typography.Text>
          </Flex>
        ),
      },
      {
        title: t('machines.bridgeName'),
        dataIndex: 'bridgeName',
        key: 'bridgeName',
        sorter: createSorter<CephClusterMachine>('bridgeName'),
        render: (name: string) => <Tag bordered={false}>{name}</Tag>,
      },
      {
        title: t('machines.assignedDate'),
        dataIndex: 'assignedDate',
        key: 'assignedDate',
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
          <Table<CephClusterMachine>
            data-testid={`ds-cluster-machines-table-${cluster.clusterName}`}
            columns={machineColumns}
            dataSource={machines}
            rowKey="machineName"
            loading={isLoading}
            size="small"
            pagination={false}
          />
        </Flex>
      )}
    </Flex>
  );
};
