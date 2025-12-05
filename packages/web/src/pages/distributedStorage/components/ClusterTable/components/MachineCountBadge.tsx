import React from 'react';
import {
  DistributedStorageCluster,
  useDistributedStorageClusterMachines,
} from '@/api/queries/distributedStorage';
import { MachineCountBadgeWrapper, MachineCountIcon } from '../styles';

interface MachineCountBadgeProps {
  cluster: DistributedStorageCluster;
}

export const MachineCountBadge: React.FC<MachineCountBadgeProps> = ({ cluster }) => {
  const { data: machines = [] } = useDistributedStorageClusterMachines(cluster.clusterName, true);

  return (
    <MachineCountBadgeWrapper count={machines.length} showZero $hasMachines={machines.length > 0}>
      <MachineCountIcon />
    </MachineCountBadgeWrapper>
  );
};
