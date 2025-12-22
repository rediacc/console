import React, { type ReactNode } from 'react';
import { Alert, Button, Card, Divider, Flex, Typography } from 'antd';
const { Text } = Typography;
import { useTranslation } from 'react-i18next';
import { useMachineAssignmentStatus } from '@/api/queries/ceph';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import MachineAssignmentStatusBadge from '@/components/resources/MachineAssignmentStatusBadge';
import type { Machine, MachineAssignmentType } from '@/types';
import {
  CloudServerOutlined,
  CopyOutlined,
  DatabaseOutlined,
  HddOutlined,
  HistoryOutlined,
  RightOutlined,
} from '@/utils/optimizedIcons';

interface CephSectionProps {
  machine: Machine;
  onViewDetails?: () => void;
  onManageAssignment?: () => void;
}

const getAssignmentIcon = (assignmentType: MachineAssignmentType): ReactNode => {
  switch (assignmentType) {
    case 'CLUSTER':
      return <DatabaseOutlined />;
    case 'IMAGE':
      return <HddOutlined />;
    case 'CLONE':
      return <CopyOutlined />;
    case 'AVAILABLE':
    default:
      return <CloudServerOutlined />;
  }
};

export const CephSection: React.FC<CephSectionProps> = ({
  machine,
  onViewDetails,
  onManageAssignment,
}) => {
  const { t } = useTranslation(['ceph', 'machines']);

  const hasClusterAssignment = Boolean(machine.cephClusterName);

  const { data: assignmentData, isLoading } = useMachineAssignmentStatus(
    machine.machineName,
    machine.teamName,
    !hasClusterAssignment
  );

  const assignmentType: MachineAssignmentType = hasClusterAssignment
    ? 'CLUSTER'
    : ((assignmentData?.assignmentType as MachineAssignmentType) ?? 'AVAILABLE');

  const assignmentDetails = hasClusterAssignment
    ? `Assigned to cluster: ${machine.cephClusterName}`
    : assignmentData?.assignmentDetails;

  if (isLoading) {
    return (
      <Flex
        align="center"
        justify="center"
        // eslint-disable-next-line no-restricted-syntax
        style={{ paddingBlock: 20 }}
        data-testid="ds-section-loading"
      >
        <LoadingWrapper loading centered minHeight={120}>
          <Flex />
        </LoadingWrapper>
      </Flex>
    );
  }

  const showAssignmentAlert = assignmentType !== 'AVAILABLE' && Boolean(assignmentDetails);

  return (
    <>
      <Divider
        // eslint-disable-next-line no-restricted-syntax
        style={{ margin: '24px 0' }}
        data-testid="ds-section-divider"
      >
        <Flex align="center" className="inline-flex">
          <CloudServerOutlined />
          <Text>{t('machineSection.title')}</Text>
        </Flex>
      </Divider>

      <Card size="small" data-testid="ds-section-card">
        <Flex vertical gap={24} className="w-full">
          <Flex vertical>
            <Flex className="block" data-testid="ds-section-assignment-label">
              <Typography.Text>{t('assignment.currentAssignment')}</Typography.Text>
            </Flex>
            <MachineAssignmentStatusBadge
              assignmentType={assignmentType}
              assignmentDetails={assignmentDetails}
              size="default"
              data-testid="ds-section-assignment-badge"
            />
          </Flex>

          {showAssignmentAlert && assignmentDetails && (
            <Alert
              message={<Typography.Text>{assignmentDetails}</Typography.Text>}
              type="info"
              showIcon
              icon={getAssignmentIcon(assignmentType)}
              data-testid="ds-section-assignment-alert"
            />
          )}

          <Flex align="center" wrap>
            {onViewDetails && (
              <Button
                icon={<HistoryOutlined />}
                onClick={onViewDetails}
                data-testid="ds-section-history-button"
              >
                <Typography.Text>{t('assignment.history')}</Typography.Text>
              </Button>
            )}

            {onManageAssignment && assignmentType !== 'AVAILABLE' && (
              <Button
                type="primary"
                icon={<RightOutlined />}
                onClick={onManageAssignment}
                data-testid="ds-section-manage-button"
              >
                <Typography.Text>{t('machineSection.manageAssignment')}</Typography.Text>
              </Button>
            )}
          </Flex>

          {assignmentType !== 'AVAILABLE' && (
            <Alert
              message={<Typography.Text>{t('warnings.exclusivity')}</Typography.Text>}
              type="warning"
              showIcon
              icon={<CloudServerOutlined />}
              data-testid="ds-section-exclusivity-warning"
            />
          )}
        </Flex>
      </Card>
    </>
  );
};
