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
      <div data-testid="machine-status-cell-cluster">
        <MachineAssignmentStatusBadge 
          assignmentType="CLUSTER"
          assignmentDetails={`Assigned to cluster: ${machine.distributedStorageClusterName}`}
          size="small"
        />
      </div>
    )
  }

  // Otherwise, fetch the assignment status
  const { data, isLoading } = useGetMachineAssignmentStatus(
    machine.machineName,
    machine.teamName,
    true
  )

  if (isLoading) {
    return <Spin size="small" data-testid="machine-status-cell-loading" />
  }

  if (!data) {
    return (
      <div data-testid="machine-status-cell-available">
        <MachineAssignmentStatusBadge 
          assignmentType="AVAILABLE"
          size="small"
        />
      </div>
    )
  }

  return (
    <div data-testid={`machine-status-cell-${data.assignmentType.toLowerCase()}`}>
      <MachineAssignmentStatusBadge 
        assignmentType={data.assignmentType}
        assignmentDetails={data.assignmentDetails}
        size="small"
      />
    </div>
  )
}

export default MachineAssignmentStatusCell