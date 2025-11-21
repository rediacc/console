import React from 'react'
import { CloudServerOutlined } from '@ant-design/icons'
import { useGetCloneMachines, type DistributedStorageRbdClone } from '@/api/queries/distributedStorage'
import { MachineCountBadgeWrapper } from '../styles'

interface MachineCountBadgeProps {
  clone: DistributedStorageRbdClone
  snapshotName: string
  imageName: string
  poolName: string
  teamName: string
}

export const MachineCountBadge: React.FC<MachineCountBadgeProps> = ({
  clone,
  snapshotName,
  imageName,
  poolName,
  teamName,
}) => {
  const { data: machines = [] } = useGetCloneMachines(
    clone.cloneName,
    snapshotName,
    imageName,
    poolName,
    teamName,
    true,
  )

  return (
    <MachineCountBadgeWrapper
      count={machines.length}
      showZero
      $active={machines.length > 0}
      data-testid={`clone-list-machine-badge-${clone.cloneName}`}
    >
      <CloudServerOutlined />
    </MachineCountBadgeWrapper>
  )
}
