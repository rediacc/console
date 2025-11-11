import React from 'react'
import { Spin } from 'antd'
import { useGetMachineAssignmentStatus } from '@/api/queries/distributedStorage'
import MachineAssignmentStatusBadge from './MachineAssignmentStatusBadge'
import { useComponentStyles } from '@/hooks/useComponentStyles'
import type { Machine, MachineAssignmentType } from '@/types'

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
  const styles = useComponentStyles()

  // Always call hooks at the top level
  const { data, isLoading } = useGetMachineAssignmentStatus(
    machine.machineName,
    machine.teamName,
    !machine.distributedStorageClusterName // Only fetch if not already assigned to cluster
  )

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

  const assignmentType = normalizeAssignmentType(
    data.assignmentType ||
    (data as Record<string, unknown>)?.assignment_type as string ||
    (data as Record<string, unknown>)?.AssignmentType as string
  )
  const assignmentDetails = getAssignmentDetails(
    data.assignmentDetails ||
    (data as Record<string, unknown>)?.assignment_details as string ||
    (data as Record<string, unknown>)?.AssignmentDetails as string
  )

  return (
    <div 
      data-testid={`machine-status-cell-${assignmentType.toLowerCase()}`}
      style={{
        ...styles.flexStart,
        minHeight: '24px'
      }}
    >
      <MachineAssignmentStatusBadge 
        assignmentType={assignmentType}
        assignmentDetails={assignmentDetails}
        size="small"
      />
    </div>
  )
}

export default MachineAssignmentStatusCell
