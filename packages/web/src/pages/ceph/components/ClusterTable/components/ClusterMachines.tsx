import React, { useMemo } from 'react';
import { Table, Empty } from 'antd';
import { useTranslation } from 'react-i18next';
import { CephCluster, useCephClusterMachines, CephClusterMachine } from '@/api/queries/ceph';
import { RediaccTag } from '@/components/ui';
import {
  ExpandedRowContainer,
  ExpandedRowTitle,
  MachinesTableWrapper,
  MachineNameCell,
  MachineNameIcon,
  MachineNameText,
  AssignedDateText,
} from '@/pages/ceph/components/ClusterTable/styles';
import { createSorter } from '@/platform';
import { formatTimestampAsIs } from '@/platform';

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
          <MachineNameCell>
            <MachineNameIcon />
            <MachineNameText>{name}</MachineNameText>
          </MachineNameCell>
        ),
      },
      {
        title: t('machines.bridgeName'),
        dataIndex: 'bridgeName',
        key: 'bridgeName',
        sorter: createSorter<CephClusterMachine>('bridgeName'),
        render: (name: string) => (
          <RediaccTag preset="bridge" compact borderless>
            {name}
          </RediaccTag>
        ),
      },
      {
        title: t('machines.assignedDate'),
        dataIndex: 'assignedDate',
        key: 'assignedDate',
        render: (date: string | null) => (
          <AssignedDateText>{date ? formatTimestampAsIs(date, 'datetime') : '-'}</AssignedDateText>
        ),
      },
    ],
    [t]
  );

  return (
    <ExpandedRowContainer data-testid={`cluster-expanded-row-${cluster.clusterName}`}>
      <ExpandedRowTitle>{t('clusters.assignedMachines')}</ExpandedRowTitle>
      {machines.length === 0 && !isLoading ? (
        <Empty description={t('clusters.noMachinesAssigned')} />
      ) : (
        <MachinesTableWrapper>
          <Table
            data-testid={`ds-cluster-machines-table-${cluster.clusterName}`}
            columns={machineColumns}
            dataSource={machines}
            rowKey="machineName"
            loading={isLoading}
            size="small"
            pagination={false}
          />
        </MachinesTableWrapper>
      )}
    </ExpandedRowContainer>
  );
};
