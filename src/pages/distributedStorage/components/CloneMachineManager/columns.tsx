import type { ColumnsType } from 'antd/es/table'
import type { TFunction } from 'i18next'
import MachineAssignmentStatusBadge from '@/components/resources/MachineAssignmentStatusBadge'
import type { CloneMachine } from '@/api/queries/distributedStorage'
import { createSorter } from '@/core'
import {
  MachineNameCell,
  MachineNameIcon,
  MachineName,
  BridgeTag,
} from './styles'

interface BuildColumnsParams {
  t: TFunction<'distributedStorage' | 'machines' | 'common'>
  cloneName: string
}

export const buildCloneMachineColumns = ({
  t,
  cloneName,
}: BuildColumnsParams): ColumnsType<CloneMachine> => [
  {
    title: t('machines:machineName'),
    dataIndex: 'machineName',
    key: 'machineName',
    sorter: createSorter<CloneMachine>('machineName'),
    render: (name: string, record: CloneMachine) => (
      <MachineNameCell data-testid={`clone-manager-machine-${record.machineName}`}>
        <MachineNameIcon />
        <MachineName>{name}</MachineName>
      </MachineNameCell>
    ),
  },
  {
    title: t('machines:bridge'),
    dataIndex: 'bridgeName',
    key: 'bridgeName',
    sorter: createSorter<CloneMachine>('bridgeName'),
    render: (bridge: string, record: CloneMachine) => (
      <BridgeTag data-testid={`clone-manager-bridge-${record.machineName}`}>
        {bridge}
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
]
