import React from 'react';
import { CloudServerOutlined } from '@ant-design/icons';
import { Badge } from 'antd';
import { CephCluster, useCephClusterMachines } from '@/api/queries/ceph';

interface MachineCountBadgeProps {
  cluster: CephCluster;
}

export const MachineCountBadge: React.FC<MachineCountBadgeProps> = ({ cluster }) => {
  const { data: machines = [] } = useCephClusterMachines(cluster.clusterName, true);

  return (
    <Badge
      count={machines.length}
      showZero
      color={machines.length > 0 ? 'var(--ant-color-success)' : 'var(--ant-color-text-tertiary)'}
    >
      <CloudServerOutlined />
    </Badge>
  );
};
