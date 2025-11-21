import React from 'react'
import { Empty, Spin, Typography } from 'antd'
import { TeamOutlined, CloudServerOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import {
  useGetCloneMachines,
  type DistributedStorageRbdClone,
  type DistributedStorageRbdSnapshot,
  type DistributedStorageRbdImage,
  type DistributedStoragePool,
} from '@/api/queries/distributedStorage'
import {
  AssignButton,
  EmptyState,
  MachineCountTag,
  MachineListButton,
  MachineListHeader,
  MachineListStack,
  MachineListWrapper,
  MachineTag,
  MachineTagGrid,
} from '../styles'

const { Text } = Typography

interface CloneMachineListProps {
  clone: DistributedStorageRbdClone
  snapshot: DistributedStorageRbdSnapshot
  image: DistributedStorageRbdImage
  pool: DistributedStoragePool
  onManageMachines: (clone: DistributedStorageRbdClone) => void
}

export const CloneMachineList: React.FC<CloneMachineListProps> = ({
  clone,
  snapshot,
  image,
  pool,
  onManageMachines,
}) => {
  const { t } = useTranslation(['distributedStorage', 'machines'])
  const { data: machines = [], isLoading } = useGetCloneMachines(
    clone.cloneName,
    snapshot.snapshotName,
    image.imageName,
    pool.poolName,
    pool.teamName,
    true,
  )

  if (isLoading) {
    return (
      <MachineListWrapper data-testid={`clone-list-machines-loading-${clone.cloneName}`}>
        <Spin />
      </MachineListWrapper>
    )
  }

  if (machines.length === 0) {
    return (
      <MachineListWrapper>
        <EmptyState>
          <Empty description={t('clones.noMachinesAssigned')} />
          <AssignButton
            type="primary"
            icon={<TeamOutlined />}
            onClick={() => onManageMachines(clone)}
            data-testid={`clone-list-assign-machines-empty-${clone.cloneName}`}
          >
            {t('clones.assignMachines')}
          </AssignButton>
        </EmptyState>
      </MachineListWrapper>
    )
  }

  return (
    <MachineListWrapper data-testid={`clone-list-machines-container-${clone.cloneName}`}>
      <MachineListStack>
        <MachineListHeader>
          <TeamOutlined />
          <Text strong>{t('clones.assignedMachines')}:</Text>
          <MachineCountTag data-testid={`clone-list-machine-count-${clone.cloneName}`}>
            {machines.length} {t('machines:machines')}
          </MachineCountTag>
        </MachineListHeader>

        <MachineTagGrid>
          {machines.map((machine) => (
            <MachineTag
              key={machine.machineName}
              icon={<CloudServerOutlined />}
              color="blue"
              data-testid={`clone-list-machine-tag-${clone.cloneName}-${machine.machineName}`}
            >
              {machine.machineName}
            </MachineTag>
          ))}
        </MachineTagGrid>

        <MachineListButton
          icon={<TeamOutlined />}
          onClick={() => onManageMachines(clone)}
          data-testid={`clone-list-manage-machines-button-${clone.cloneName}`}
        >
          {t('clones.manageMachines')}
        </MachineListButton>
      </MachineListStack>
    </MachineListWrapper>
  )
}
