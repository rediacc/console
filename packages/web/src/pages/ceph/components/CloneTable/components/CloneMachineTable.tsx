import React from 'react';
import { CloudServerOutlined, TeamOutlined } from '@ant-design/icons';
import { Empty } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  type CephPool,
  type CephRbdClone,
  type CephRbdImage,
  type CephRbdSnapshot,
  type CloneMachine,
  useCloneMachines,
} from '@/api/queries/ceph';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { RediaccStack, RediaccTag, RediaccText } from '@/components/ui';
import {
  AssignButton,
  EmptyState,
  MachineListButton,
  MachineListHeader,
  MachineListWrapper,
  MachineTagGrid,
} from '@/pages/ceph/components/CloneTable/styles';

interface CloneMachineTableProps {
  clone: CephRbdClone;
  snapshot: CephRbdSnapshot;
  image: CephRbdImage;
  pool: CephPool;
  onManageMachines: (clone: CephRbdClone) => void;
}

export const CloneMachineTable: React.FC<CloneMachineTableProps> = ({
  clone,
  snapshot,
  image,
  pool,
  onManageMachines,
}) => {
  const { t } = useTranslation(['ceph', 'machines']);
  const { data: machines = [], isLoading } = useCloneMachines(
    clone.cloneName,
    snapshot.snapshotName,
    image.imageName,
    pool.poolName,
    pool.teamName,
    true
  );

  if (isLoading) {
    return (
      <MachineListWrapper data-testid={`clone-list-machines-loading-${clone.cloneName}`}>
        <LoadingWrapper loading centered minHeight={120}>
          <div />
        </LoadingWrapper>
      </MachineListWrapper>
    );
  }

  if (machines.length === 0) {
    return (
      <MachineListWrapper>
        <EmptyState>
          <Empty description={t('clones.noMachinesAssigned')} />
          <AssignButton
            variant="primary"
            icon={<TeamOutlined />}
            onClick={() => onManageMachines(clone)}
            data-testid={`clone-list-assign-machines-empty-${clone.cloneName}`}
          >
            {t('clones.assignMachines')}
          </AssignButton>
        </EmptyState>
      </MachineListWrapper>
    );
  }

  return (
    <MachineListWrapper data-testid={`clone-list-machines-container-${clone.cloneName}`}>
      <RediaccStack direction="vertical" gap="md" fullWidth>
        <MachineListHeader>
          <TeamOutlined />
          <RediaccText weight="bold">{t('clones.assignedMachines')}:</RediaccText>
          <RediaccTag
            variant="neutral"
            compact
            data-testid={`clone-list-machine-count-${clone.cloneName}`}
          >
            {machines.length} {t('machines:machines')}
          </RediaccTag>
        </MachineListHeader>

        <MachineTagGrid>
          {machines.map((machine: CloneMachine) => (
            <RediaccTag
              key={machine.machineName}
              preset="machine"
              compact
              icon={<CloudServerOutlined />}
              data-testid={`clone-list-machine-tag-${clone.cloneName}-${machine.machineName}`}
            >
              {machine.machineName}
            </RediaccTag>
          ))}
        </MachineTagGrid>

        <MachineListButton
          icon={<TeamOutlined />}
          onClick={() => onManageMachines(clone)}
          data-testid={`clone-list-manage-machines-button-${clone.cloneName}`}
        >
          {t('clones.manageMachines')}
        </MachineListButton>
      </RediaccStack>
    </MachineListWrapper>
  );
};
