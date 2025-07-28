import React from 'react'
import { Spin } from 'antd'
import { useGetMachineAssignmentStatus } from '@/api/queries/distributedStorage'
import MachineAssignmentStatusBadge from './MachineAssignmentStatusBadge'
import type { Machine } from '@/types'

interface MachineAssignmentStatusCellProps {
  machine: Machine
}

const MachineAssignmentStatusCell: React.FC<MachineAssignmentStatusCellProps> = ({ machine }) => {
  // If machine already has distributedStorageClusterName, we know it's assigned to a cluster
  if (machine.distributedStorageClusterName) {
    return (
      <MachineAssignmentStatusBadge 
        assignmentType="CLUSTER"
        assignmentDetails={`Assigned to cluster: ${machine.distributedStorageClusterName}`}
        size="small"
      />
    )
  }

  // Otherwise, fetch the assignment status
  const { data, isLoading } = useGetMachineAssignmentStatus(
    machine.machineName,
    machine.teamName,
    true
  )

  if (isLoading) {
    return <Spin size="small" />
  }

  if (!data) {
    return (
      <MachineAssignmentStatusBadge 
        assignmentType="AVAILABLE"
        size="small"
      />
    )
  }

  return (
    <MachineAssignmentStatusBadge 
      assignmentType={data.assignmentType}
      assignmentDetails={data.assignmentDetails}
      size="small"
    />
  )
}

export default MachineAssignmentStatusCell