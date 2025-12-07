import React from 'react';
import { CloudServerOutlined } from '@ant-design/icons';
import { useCloneMachines, type CephRbdClone } from '@/api/queries/ceph';
import { MachineCountBadgeWrapper } from '@/pages/ceph/components/CloneTable/styles';

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
    <MachineCountBadgeWrapper
      count={machines.length}
      showZero
      $active={machines.length > 0}
      data-testid={`clone-list-machine-badge-${clone.cloneName}`}
    >
      <CloudServerOutlined />
    </MachineCountBadgeWrapper>
  );
};
