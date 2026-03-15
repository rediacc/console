import { CloudServerOutlined, TeamOutlined } from '@ant-design/icons';
import type {
  GetCephPools_ResultSet1,
  GetCephRbdClones_ResultSet1,
  GetCephRbdImages_ResultSet1,
  GetCephRbdSnapshots_ResultSet1,
  GetCloneMachines_ResultSet1,
} from '@rediacc/shared/types';
import { Button, Empty, Flex, Tag, Typography } from 'antd';
import React from 'react';
import { useTranslation } from 'react-i18next';
import { useGetCloneMachines } from '@/api/api-hooks.generated';
import LoadingWrapper from '@/components/common/LoadingWrapper';

interface CloneMachineTableProps {
  clone: GetCephRbdClones_ResultSet1;
  snapshot: GetCephRbdSnapshots_ResultSet1;
  image: GetCephRbdImages_ResultSet1;
  pool: GetCephPools_ResultSet1;
  onManageMachines: (clone: GetCephRbdClones_ResultSet1) => void;
}

export const CloneMachineTable: React.FC<CloneMachineTableProps> = ({
  clone,
  snapshot,
  image,
  pool,
  onManageMachines,
}) => {
  const { t } = useTranslation(['ceph', 'machines']);
  const { data: machines = [], isLoading } = useGetCloneMachines(
    clone.cloneName ?? '',
    snapshot.snapshotName ?? '',
    image.imageName ?? '',
    pool.poolName ?? '',
    pool.teamName ?? ''
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
      <Flex vertical align="center" className="gap-sm">
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
    );
  }

  return (
    <Flex vertical data-testid={`clone-list-machines-container-${clone.cloneName}`}>
      <Flex align="center" wrap>
        <TeamOutlined />
        <Typography.Text strong>{t('clones.assignedMachines')}:</Typography.Text>
        <Tag data-testid={`clone-list-machine-count-${clone.cloneName}`} bordered={false}>
          {machines.length} {t('machines:machines')}
        </Tag>
      </Flex>

      <Flex wrap>
        {machines.map((machine: GetCloneMachines_ResultSet1) => (
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
  );
};
