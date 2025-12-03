import React from 'react'
import InlineLoadingIndicator from '@/components/common/InlineLoadingIndicator'
import { useMachineAssignmentStatus } from '@/api/queries/distributedStorage'
import MachineAssignmentStatusBadge from '../MachineAssignmentStatusBadge'
import type { Machine, MachineAssignmentType } from '@/types'
import { StatusCellWrapper } from './styles'

interface MachineAssignmentStatusCellProps {
  machine: Machine
}

const normalizeAssignmentType = (value?: string | null): MachineAssignmentType => {
  if (!value) return 'AVAILABLE'
  const normalized = value.toString().toUpperCase()
  if (normalized === 'CLUSTER' || normalized === 'IMAGE' || normalized === 'CLONE') {
    return normalized
  }
  return 'AVAILABLE'
}

const getAssignmentDetails = (value?: string | null) => {
  return value ?? undefined
}

const MachineAssignmentStatusCell: React.FC<MachineAssignmentStatusCellProps> = ({ machine }) => {
  // Always call hooks at the top level
  const { data, isLoading } = useMachineAssignmentStatus(
    machine.machineName,
    machine.teamName,
    !machine.distributedStorageClusterName // Only fetch if not already assigned to cluster
  )

  // If machine already has distributedStorageClusterName, we know it's assigned to a cluster
  if (machine.distributedStorageClusterName) {
    return (
      <StatusCellWrapper data-testid="machine-status-cell-cluster">
        <MachineAssignmentStatusBadge
          assignmentType="CLUSTER"
          assignmentDetails={`Assigned to cluster: ${machine.distributedStorageClusterName}`}
          size="small"
        />
      </StatusCellWrapper>
    )
  }

  if (isLoading) {
    return (
      <StatusCellWrapper $align="center">
        <InlineLoadingIndicator 
          width={140} 
          height={22} 
          data-testid="machine-status-cell-loading" 
        />
      </StatusCellWrapper>
    )
  }

  if (!data) {
    return (
      <StatusCellWrapper data-testid="machine-status-cell-available">
        <MachineAssignmentStatusBadge
          assignmentType="AVAILABLE"
          size="small"
        />
      </StatusCellWrapper>
    )
  }

  const legacyData = data as unknown as Record<string, unknown>
  const assignmentType = normalizeAssignmentType(
    data.assignmentType ||
    (legacyData.assignment_type as string) ||
    (legacyData.AssignmentType as string)
  )
  const assignmentDetails = getAssignmentDetails(
    data.assignmentDetails ||
    (legacyData.assignment_details as string) ||
    (legacyData.AssignmentDetails as string)
  )

  return (
    <StatusCellWrapper data-testid={`machine-status-cell-${assignmentType.toLowerCase()}`}>
      <MachineAssignmentStatusBadge
        assignmentType={assignmentType}
        assignmentDetails={assignmentDetails}
        size="small"
      />
    </StatusCellWrapper>
  )
}

export default MachineAssignmentStatusCell
