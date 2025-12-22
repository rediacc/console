import React from 'react';
import { Flex } from 'antd';
import { useMachineAssignmentStatus } from '@/api/queries/ceph';
import InlineLoadingIndicator from '@/components/common/InlineLoadingIndicator';
import MachineAssignmentStatusBadge from '@/components/resources/MachineAssignmentStatusBadge';
import type { Machine, MachineAssignmentType } from '@/types';

interface MachineAssignmentStatusCellProps {
  machine: Machine;
}

const normalizeAssignmentType = (value?: string | null): MachineAssignmentType => {
  if (!value) return 'AVAILABLE';
  const normalized = value.toString().toUpperCase();
  if (normalized === 'CLUSTER' || normalized === 'IMAGE' || normalized === 'CLONE') {
    return normalized;
  }
  return 'AVAILABLE';
};

const getAssignmentDetails = (value?: string | null) => {
  return value ?? undefined;
};

const MachineAssignmentStatusCell: React.FC<MachineAssignmentStatusCellProps> = ({ machine }) => {
  // Always call hooks at the top level
  const { data, isLoading } = useMachineAssignmentStatus(
    machine.machineName,
    machine.teamName,
    !machine.cephClusterName // Only fetch if not already assigned to cluster
  );

  // If machine already has cephClusterName, we know it's assigned to a cluster
  if (machine.cephClusterName) {
    return (
      // eslint-disable-next-line no-restricted-syntax
      <Flex
        align="flex-start"
        justify="flex-start"
        style={{ minHeight: 24 }}
        data-testid="machine-status-cell-cluster"
      >
        <MachineAssignmentStatusBadge
          assignmentType="CLUSTER"
          assignmentDetails={`Assigned to cluster: ${machine.cephClusterName}`}
          size="small"
        />
      </Flex>
    );
  }

  if (isLoading) {
    return (
      // eslint-disable-next-line no-restricted-syntax
      <Flex align="center" justify="center" style={{ minHeight: 24 }}>
        <InlineLoadingIndicator width={140} height={22} data-testid="machine-status-cell-loading" />
      </Flex>
    );
  }

  if (!data) {
    return (
      // eslint-disable-next-line no-restricted-syntax
      <Flex
        align="flex-start"
        justify="flex-start"
        style={{ minHeight: 24 }}
        data-testid="machine-status-cell-available"
      >
        <MachineAssignmentStatusBadge assignmentType="AVAILABLE" size="small" />
      </Flex>
    );
  }

  const legacyData = data as unknown as Record<string, unknown>;
  const assignmentType = normalizeAssignmentType(
    data.assignmentType ||
      (legacyData.assignment_type as string) ||
      (legacyData.AssignmentType as string)
  );
  const assignmentDetails = getAssignmentDetails(
    data.assignmentDetails ||
      (legacyData.assignment_details as string) ||
      (legacyData.AssignmentDetails as string)
  );

  return (
    // eslint-disable-next-line no-restricted-syntax
    <Flex
      align="flex-start"
      justify="flex-start"
      style={{ minHeight: 24 }}
      data-testid={`machine-status-cell-${assignmentType.toLowerCase()}`}
    >
      <MachineAssignmentStatusBadge
        assignmentType={assignmentType}
        assignmentDetails={assignmentDetails}
        size="small"
      />
    </Flex>
  );
};

export default MachineAssignmentStatusCell;
