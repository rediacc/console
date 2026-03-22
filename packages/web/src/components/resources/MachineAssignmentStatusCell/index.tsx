import { Flex } from 'antd';
import React from 'react';
import { useGetMachineAssignmentStatus } from '@/api/api-hooks.generated';
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
  // Always call hooks at the top level - only fetch if not already assigned to cluster
  const shouldFetch = !machine.cephClusterName;
  const { data, isLoading } = useGetMachineAssignmentStatus(
    shouldFetch ? (machine.machineName ?? '') : '',
    shouldFetch ? (machine.teamName ?? '') : ''
  );

  // If machine already has cephClusterName, we know it's assigned to a cluster
  if (machine.cephClusterName) {
    return (
      <Flex align="flex-start" justify="flex-start" data-testid="machine-status-cell-cluster">
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
      <Flex align="center" justify="center">
        <InlineLoadingIndicator width={140} height={22} data-testid="machine-status-cell-loading" />
      </Flex>
    );
  }

  const statusData = data?.[0];

  if (!statusData) {
    return (
      <Flex align="flex-start" justify="flex-start" data-testid="machine-status-cell-available">
        <MachineAssignmentStatusBadge assignmentType="AVAILABLE" size="small" />
      </Flex>
    );
  }

  const assignmentType = normalizeAssignmentType(statusData.assignmentType);
  const assignmentDetails = getAssignmentDetails(statusData.assignmentDetails);

  return (
    <Flex
      align="flex-start"
      justify="flex-start"
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
