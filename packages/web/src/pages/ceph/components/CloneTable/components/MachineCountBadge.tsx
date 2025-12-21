import React from 'react';
import { CloudServerOutlined } from '@ant-design/icons';
import { Badge } from 'antd';
import { type CephRbdClone, useCloneMachines } from '@/api/queries/ceph';

interface MachineCountBadgeProps {
  clone: CephRbdClone;
  snapshotName: string;
  imageName: string;
  poolName: string;
  teamName: string;
}

export const MachineCountBadge: React.FC<MachineCountBadgeProps> = ({
  clone,
  snapshotName,
  imageName,
  poolName,
  teamName,
}) => {
  const { data: machines = [] } = useCloneMachines(
    clone.cloneName,
    snapshotName,
    imageName,
    poolName,
    teamName,
    true
  );

  return (
    <Badge
      count={machines.length}
      showZero
      color={machines.length > 0 ? 'var(--ant-color-success)' : 'var(--ant-color-text-tertiary)'}
      data-testid={`clone-list-machine-badge-${clone.cloneName}`}
    >
      <CloudServerOutlined />
    </Badge>
  );
};
