import React from 'react';
import { CloudServerOutlined } from '@ant-design/icons';
import { Badge } from 'antd';
import { useGetCephClusterMachines } from '@/api/api-hooks.generated';
import type { GetCephClusters_ResultSet1 } from '@rediacc/shared/types';

interface MachineCountBadgeProps {
  cluster: GetCephClusters_ResultSet1;
}

export const ClusterMachineCountBadge: React.FC<MachineCountBadgeProps> = ({ cluster }) => {
  const { data: machines = [] } = useGetCephClusterMachines(cluster.clusterName ?? '');

  return (
    <Badge count={machines.length} showZero>
      <CloudServerOutlined />
    </Badge>
  );
};
