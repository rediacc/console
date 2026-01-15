import { CloudServerOutlined } from '@ant-design/icons';
import type { GetCephRbdClones_ResultSet1 } from '@rediacc/shared/types';
import { Badge } from 'antd';
import React from 'react';
import { useGetCloneMachines } from '@/api/api-hooks.generated';

interface MachineCountBadgeProps {
  clone: GetCephRbdClones_ResultSet1;
  snapshotName: string;
  imageName: string;
  poolName: string;
  teamName: string;
}

export const CloneMachineCountBadge: React.FC<MachineCountBadgeProps> = ({
  clone,
  snapshotName,
  imageName,
  poolName,
  teamName,
}) => {
  const { data: machines = [] } = useGetCloneMachines(
    clone.cloneName ?? '',
    snapshotName,
    imageName,
    poolName,
    teamName
  );

  return (
    <Badge
      count={machines.length}
      showZero
      data-testid={`clone-list-machine-badge-${clone.cloneName}`}
    >
      <CloudServerOutlined />
    </Badge>
  );
};
