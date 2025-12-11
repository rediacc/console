import React, { type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useMachineAssignmentStatus } from '@/api/queries/ceph';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import MachineAssignmentStatusBadge from '@/components/resources/MachineAssignmentStatusBadge';
import { IconWrapper, RediaccDivider, RediaccStack, RediaccText } from '@/components/ui';
import type { Machine, MachineAssignmentType } from '@/types';
import {
  CloudServerOutlined,
  CopyOutlined,
  DatabaseOutlined,
  HddOutlined,
  HistoryOutlined,
  RightOutlined,
} from '@/utils/optimizedIcons';
import {
  ActionButton,
  ActionsRow,
  AlertWrapper,
  DividerContent,
  LabelBlock,
  LoadingState,
  SectionCard,
  SectionTitle,
} from './styles';

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
      <LoadingState data-testid="ds-section-loading">
        <LoadingWrapper loading centered minHeight={120}>
          <div />
        </LoadingWrapper>
      </LoadingState>
    );
  }

  const showAssignmentAlert = assignmentType !== 'AVAILABLE' && Boolean(assignmentDetails);

  return (
    <>
      <RediaccDivider spacing="lg" data-testid="ds-section-divider">
        <DividerContent>
          <IconWrapper $size="lg">
            <CloudServerOutlined />
          </IconWrapper>
          <SectionTitle>{t('machineSection.title')}</SectionTitle>
        </DividerContent>
      </RediaccDivider>

      <SectionCard size="sm" data-testid="ds-section-card">
        <RediaccStack variant="spaced-column" fullWidth>
          <div>
            <LabelBlock data-testid="ds-section-assignment-label">
              <RediaccText variant="label">{t('assignment.currentAssignment')}</RediaccText>
            </LabelBlock>
            <MachineAssignmentStatusBadge
              assignmentType={assignmentType}
              assignmentDetails={assignmentDetails}
              size="default"
              data-testid="ds-section-assignment-badge"
            />
          </div>

          {showAssignmentAlert && assignmentDetails && (
            <AlertWrapper
              message={<RediaccText variant="value">{assignmentDetails}</RediaccText>}
              variant="info"
              showIcon
              icon={
                <IconWrapper $size="sm" $tone="info">
                  {getAssignmentIcon(assignmentType)}
                </IconWrapper>
              }
              data-testid="ds-section-assignment-alert"
            />
          )}

          <ActionsRow>
            {onViewDetails && (
              <ActionButton
                icon={
                  <IconWrapper $size="sm" $tone="muted">
                    <HistoryOutlined />
                  </IconWrapper>
                }
                onClick={onViewDetails}
                data-testid="ds-section-history-button"
              >
                <RediaccText variant="caption" weight="medium">
                  {t('assignment.history')}
                </RediaccText>
              </ActionButton>
            )}

            {onManageAssignment && assignmentType !== 'AVAILABLE' && (
              <ActionButton
                variant="primary"
                icon={
                  <IconWrapper $size="sm">
                    <RightOutlined />
                  </IconWrapper>
                }
                onClick={onManageAssignment}
                data-testid="ds-section-manage-button"
              >
                <RediaccText variant="caption" weight="medium">
                  {t('machineSection.manageAssignment')}
                </RediaccText>
              </ActionButton>
            )}
          </ActionsRow>

          {assignmentType !== 'AVAILABLE' && (
            <AlertWrapper
              message={<RediaccText variant="value">{t('warnings.exclusivity')}</RediaccText>}
              variant="warning"
              showIcon
              icon={
                <IconWrapper $size="sm" $tone="warning">
                  <CloudServerOutlined />
                </IconWrapper>
              }
              data-testid="ds-section-exclusivity-warning"
            />
          )}
        </RediaccStack>
      </SectionCard>
    </>
  );
};
