import React from 'react'
import { Spin } from 'antd'
import { useGetMachineAssignmentStatus } from '@/api/queries/distributedStorage'
import MachineAssignmentStatusBadge from './MachineAssignmentStatusBadge'
import { useComponentStyles } from '@/hooks/useComponentStyles'
import type { Machine } from '@/types'

interface MachineAssignmentStatusCellProps {
  machine: Machine
}

const MachineAssignmentStatusCell: React.FC<MachineAssignmentStatusCellProps> = ({ machine }) => {
  const styles = useComponentStyles()
  // If machine already has distributedStorageClusterName, we know it's assigned to a cluster
  if (machine.distributedStorageClusterName) {
    return (
      <div 
        data-testid="machine-status-cell-cluster"
        style={{
          ...styles.flexStart,
          minHeight: '24px'
        }}
      >
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
    return (
      <div style={{
        ...styles.flexCenter,
        minHeight: '24px'
      }}>
        <Spin size="small" data-testid="machine-status-cell-loading" />
      </div>
    )
  }

  if (!data) {
    return (
      <div 
        data-testid="machine-status-cell-available"
        style={{
          ...styles.flexStart,
          minHeight: '24px'
        }}
      >
        <MachineAssignmentStatusBadge 
          assignmentType="AVAILABLE"
          size="small"
        />
      </div>
    )
  }

  return (
    <div 
      data-testid={`machine-status-cell-${data.assignmentType.toLowerCase()}`}
      style={{
        ...styles.flexStart,
        minHeight: '24px'
      }}
    >
      <MachineAssignmentStatusBadge 
        assignmentType={data.assignmentType}
        assignmentDetails={data.assignmentDetails}
        size="small"
      />
    </div>
  )
}

export default MachineAssignmentStatusCell