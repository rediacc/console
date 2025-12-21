import React, { useMemo } from 'react';
import { Empty, Table, Tag } from 'antd';
import { useTranslation } from 'react-i18next';
import { CephCluster, CephClusterMachine, useCephClusterMachines } from '@/api/queries/ceph';
import { DesktopOutlined } from '@/utils/optimizedIcons';
import { createSorter, formatTimestampAsIs } from '@/platform';

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
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <DesktopOutlined style={{ fontSize: 16, color: 'var(--ant-color-primary)' }} />
            <span style={{ fontWeight: 400 }}>{name}</span>
          </span>
        ),
      },
      {
        title: t('machines.bridgeName'),
        dataIndex: 'bridgeName',
        key: 'bridgeName',
        sorter: createSorter<CephClusterMachine>('bridgeName'),
        render: (name: string) => (
          <Tag bordered={false} color="processing">
            {name}
          </Tag>
        ),
      },
      {
        title: t('machines.assignedDate'),
        dataIndex: 'assignedDate',
        key: 'assignedDate',
        render: (date: string | null) => (
          <span>{date ? formatTimestampAsIs(date, 'datetime') : '-'}</span>
        ),
      },
    ],
    [t]
  );

  return (
    <div data-testid={`cluster-expanded-row-${cluster.clusterName}`}>
      <h4 style={{ fontSize: 16 }}>{t('clusters.assignedMachines')}</h4>
      {machines.length === 0 && !isLoading ? (
        <Empty description={t('clusters.noMachinesAssigned')} />
      ) : (
        <div style={{ overflow: 'hidden' }}>
          <Table<CephClusterMachine>
            data-testid={`ds-cluster-machines-table-${cluster.clusterName}`}
            columns={machineColumns}
            dataSource={machines}
            rowKey="machineName"
            loading={isLoading}
            size="small"
            pagination={false}
          />
        </div>
      )}
    </div>
  );
};
