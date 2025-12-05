import type { ReactNode } from 'react';
import type { ColumnsType } from 'antd/es/table';
import type { TFunction } from 'i18next';
import MachineAssignmentStatusBadge from '@/components/resources/MachineAssignmentStatusBadge';
import type { CloneMachine } from '@/api/queries/distributedStorage';
import { createSorter } from '@/core';
import { createTruncatedColumn } from '@/components/common/columns';
import { MachineNameCell, MachineNameIcon, MachineName, BridgeTag } from './styles';

interface BuildColumnsParams {
  t: TFunction<'distributedStorage' | 'machines' | 'common'>;
  cloneName: string;
}

export const buildCloneMachineColumns = ({
  t,
  cloneName,
}: BuildColumnsParams): ColumnsType<CloneMachine> => {
  const machineNameColumn = createTruncatedColumn<CloneMachine>({
    title: t('machines:machineName'),
    dataIndex: 'machineName',
    key: 'machineName',
    sorter: createSorter<CloneMachine>('machineName'),
  });

  const bridgeColumn = createTruncatedColumn<CloneMachine>({
    title: t('machines:bridge'),
    dataIndex: 'bridgeName',
    key: 'bridgeName',
    sorter: createSorter<CloneMachine>('bridgeName'),
  });

  return [
    {
      ...machineNameColumn,
      render: (name: string, record: CloneMachine) => (
        <MachineNameCell data-testid={`clone-manager-machine-${record.machineName}`}>
          <MachineNameIcon />
          <MachineName>{machineNameColumn.render?.(name, record, 0) as ReactNode}</MachineName>
        </MachineNameCell>
      ),
    },
    {
      ...bridgeColumn,
      render: (bridge: string, record: CloneMachine) => (
        <BridgeTag data-testid={`clone-manager-bridge-${record.machineName}`}>
          {bridgeColumn.render?.(bridge, record, 0) as ReactNode}
        </BridgeTag>
      ),
    },
    {
      title: t('machines:assignmentStatus.title'),
      key: 'status',
      render: () => (
        <MachineAssignmentStatusBadge
          assignmentType="CLONE"
          assignmentDetails={t('machines:assignmentStatus.cloneDetails', { clone: cloneName })}
          size="small"
        />
      ),
    },
  ];
};
