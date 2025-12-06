import React from 'react';
import { Empty } from 'antd';
import { TeamOutlined, CloudServerOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import {
  useCloneMachines,
  type CephRbdClone,
  type CephRbdSnapshot,
  type CephRbdImage,
  type CephPool,
  type CloneMachine,
} from '@/api/queries/ceph';
import {
  AssignButton,
  EmptyState,
  MachineCountTag,
  MachineListButton,
  MachineListHeader,
  MachineListStack,
  MachineListWrapper,
  MachineTag,
  MachineTagGrid,
} from '../styles';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { RediaccText as Text } from '@/components/ui';

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
      <MachineListStack>
        <MachineListHeader>
          <TeamOutlined />
          <Text weight="bold">{t('clones.assignedMachines')}:</Text>
          <MachineCountTag data-testid={`clone-list-machine-count-${clone.cloneName}`}>
            {machines.length} {t('machines:machines')}
          </MachineCountTag>
        </MachineListHeader>

        <MachineTagGrid>
          {machines.map((machine: CloneMachine) => (
            <MachineTag
              key={machine.machineName}
              icon={<CloudServerOutlined />}
              data-testid={`clone-list-machine-tag-${clone.cloneName}-${machine.machineName}`}
            >
              {machine.machineName}
            </MachineTag>
          ))}
        </MachineTagGrid>

        <MachineListButton
          icon={<TeamOutlined />}
          onClick={() => onManageMachines(clone)}
          data-testid={`clone-list-manage-machines-button-${clone.cloneName}`}
        >
          {t('clones.manageMachines')}
        </MachineListButton>
      </MachineListStack>
    </MachineListWrapper>
  );
};
