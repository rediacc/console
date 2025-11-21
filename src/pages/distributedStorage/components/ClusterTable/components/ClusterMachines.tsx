import React, { useMemo } from 'react'
import { Table, Empty } from 'antd'
import { useTranslation } from 'react-i18next'
import {
  DistributedStorageCluster,
  useDistributedStorageClusterMachines,
} from '@/api/queries/distributedStorage'
import { createSorter, createDateSorter } from '@/utils/tableSorters'
import { formatTimestampAsIs } from '@/utils/timeUtils'
import {
  ExpandedRowContainer,
  ExpandedRowTitle,
  MachinesTableWrapper,
  MachineNameCell,
  MachineNameIcon,
  MachineNameText,
  MachineBridgeTag,
  AssignedDateText,
} from '../styles'

interface ClusterMachinesProps {
  cluster: DistributedStorageCluster
}

export const ClusterMachines: React.FC<ClusterMachinesProps> = ({
  cluster,
}) => {
  const { t } = useTranslation('distributedStorage')
  const { data: machines = [], isLoading } = useDistributedStorageClusterMachines(
    cluster.clusterName,
    true,
  )

  const machineColumns = useMemo(
    () => [
      {
        title: t('machines.machineName'),
        dataIndex: 'machineName',
        key: 'machineName',
        sorter: createSorter<Record<string, unknown>>('machineName'),
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
        sorter: createSorter<Record<string, unknown>>('bridgeName'),
        render: (name: string) => <MachineBridgeTag>{name}</MachineBridgeTag>,
      },
      {
        title: t('machines.assignedDate'),
        dataIndex: 'assignedDate',
        key: 'assignedDate',
        sorter: createDateSorter<Record<string, unknown>>('assignedDate'),
        render: (date: string) => (
          <AssignedDateText>
            {date ? formatTimestampAsIs(date, 'datetime') : '-'}
          </AssignedDateText>
        ),
      },
    ],
    [t],
  )

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
  )
}
