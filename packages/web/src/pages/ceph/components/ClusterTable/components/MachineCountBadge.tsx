import React from 'react';
import { CephCluster, useCephClusterMachines } from '@/api/queries/ceph';
import {
  MachineCountBadgeWrapper,
  MachineCountIcon,
} from '@/pages/ceph/components/ClusterTable/styles';

interface MachineCountBadgeProps {
  cluster: CephCluster;
}

export const MachineCountBadge: React.FC<MachineCountBadgeProps> = ({ cluster }) => {
  const { data: machines = [] } = useCephClusterMachines(cluster.clusterName, true);

  return (
    <MachineCountBadgeWrapper count={machines.length} showZero $hasMachines={machines.length > 0}>
      <MachineCountIcon />
    </MachineCountBadgeWrapper>
  );
};
