import React from 'react';
import { CloudServerOutlined, TeamOutlined } from '@ant-design/icons';
import { Button, Empty, Flex, Tag, Typography } from 'antd';
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
      <Flex className="w-full" data-testid={`clone-list-machines-loading-${clone.cloneName}`}>
        <LoadingWrapper loading centered minHeight={120}>
          <Flex />
        </LoadingWrapper>
      </Flex>
    );
  }

  if (machines.length === 0) {
    return (
      <Flex className="w-full">
        <Flex vertical align="center" gap={12} className="w-full">
          <Empty description={t('clones.noMachinesAssigned')} />
          <Button
            type="primary"
            icon={<TeamOutlined />}
            onClick={() => onManageMachines(clone)}
            data-testid={`clone-list-assign-machines-empty-${clone.cloneName}`}
          >
            {t('clones.assignMachines')}
          </Button>
        </Flex>
      </Flex>
    );
  }

  return (
    <Flex className="w-full" data-testid={`clone-list-machines-container-${clone.cloneName}`}>
      <Flex vertical gap={16} className="w-full">
        <Flex align="center" gap={8} wrap>
          <TeamOutlined />
          <Typography.Text strong>{t('clones.assignedMachines')}:</Typography.Text>
          <Tag data-testid={`clone-list-machine-count-${clone.cloneName}`} bordered={false}>
            {machines.length} {t('machines:machines')}
          </Tag>
        </Flex>

        <Flex wrap gap={8}>
          {machines.map((machine: CloneMachine) => (
            <Tag
              key={machine.machineName}
              icon={<CloudServerOutlined />}
              bordered={false}
              data-testid={`clone-list-machine-tag-${clone.cloneName}-${machine.machineName}`}
            >
              {machine.machineName}
            </Tag>
          ))}
        </Flex>

        <Button
          icon={<TeamOutlined />}
          onClick={() => onManageMachines(clone)}
          data-testid={`clone-list-manage-machines-button-${clone.cloneName}`}
          block
        >
          {t('clones.manageMachines')}
        </Button>
      </Flex>
    </Flex>
  );
};
